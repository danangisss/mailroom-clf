"""Network client + result shaping. UI-free: no Streamlit, no argparse here."""

import base64
import mimetypes
import time

import requests

from .config import (
    ESCAPES,
    NO_THREAT,
    THREAT_DEPARTMENT,
    THREAT_THRESHOLD,
    VALID_COMBOS,
    get_settings,
)
from .questions import build_keyword_question, build_questions


def to_data_uri(path):
    mime, _ = mimetypes.guess_type(path)
    with open(path, "rb") as f:
        return f"data:{mime or 'image/png'};base64," + base64.b64encode(f.read()).decode()


def to_data_uri_bytes(raw: bytes, mime: str = "image/png"):
    return f"data:{mime or 'image/png'};base64," + base64.b64encode(raw).decode()


STATE = ("Bank mailroom scan, first page. "
         "Answer each question from the printed page.")

# The patched server caps a request at ~1024 tokens (image ~627), so the
# three decisions go out as three independent calls — matching the spec's
# "three independent decisions" and isolating per-question failures.
FIELDS = ("branch", "department", "recipient")


def build_payload_from_uri(data_uri, model=None, only=None, options=None):
    settings = get_settings(model=model)
    questions = build_questions(options)
    if only is not None:
        questions = {f: questions[f] for f in only}
    if "department" in questions:
        questions["threat_keywords"] = build_keyword_question(
            None if options is None else options.keywords)
    return {
        "model": settings["model"],
        "state": STATE,
        "images": [data_uri],
        "questions": questions,
    }


def build_payload(image_path, model=None, only=None, options=None):
    return build_payload_from_uri(to_data_uri(image_path), model=model, only=only,
                                  options=options)


def _post(payload, *, endpoint=None, api_key=None):
    settings = get_settings(endpoint=endpoint, api_key=api_key, model=payload.get("model"))
    if not settings["endpoint"] or not settings["api_key"]:
        raise RuntimeError("Missing AI_BASE_URL / AI_API_KEY (env or app secrets).")
    r = requests.post(f"{settings['endpoint']}/v1/systemone",
                      headers={"Authorization": f"Bearer {settings['api_key']}"},
                      json=payload, timeout=600)
    r.raise_for_status()
    return r.json()


def _as_object_criteria(payload):
    """Array criteria -> {id: name} for every question in the payload.

    The server only accepts object criteria. Returns the rewritten payload and
    the per-question id -> name maps needed to translate answers back to names.
    """
    questions, maps = {}, {}
    for field, question in payload["questions"].items():
        names = question["criteria"]
        id_map = {str(i): name for i, name in enumerate(names, 1)}
        questions[field] = {**question, "criteria": id_map}
        maps[field] = id_map
    return {**payload, "questions": questions}, maps


def _translate_answers(resp, maps):
    """Map numeric ids back to names so callers only ever see names."""
    answers = dict(resp["answers"])
    for field, id_map in maps.items():
        answer = answers.get(field)
        if answer is None:
            continue
        answer = dict(answer)
        answer["choice"] = id_map.get(str(answer["choice"]), answer["choice"])
        answer["probabilities"] = {id_map.get(str(k), k): v
                                   for k, v in answer["probabilities"].items()}
        answers[field] = answer
    return {**resp, "answers": answers}


def _request(payload, *, endpoint=None, api_key=None):
    """POST the payload with object criteria and answer names restored."""
    rewritten, maps = _as_object_criteria(payload)
    return _translate_answers(_post(rewritten, endpoint=endpoint, api_key=api_key),
                              maps)


def classify(image_path, *, endpoint=None, api_key=None, model=None, options=None):
    mime, _ = mimetypes.guess_type(image_path)
    with open(image_path, "rb") as f:
        return classify_bytes(f.read(), mime or "image/png",
                              endpoint=endpoint, api_key=api_key, model=model,
                              options=options)


def classify_bytes(raw: bytes, mime: str = "image/png", *, endpoint=None, api_key=None,
                   model=None, options=None):
    summary, _ = classify_with_raw_bytes(
        raw, mime, endpoint=endpoint, api_key=api_key, model=model, options=options)
    return summary


def classify_with_raw_bytes(raw: bytes, mime: str = "image/png", *,
                            endpoint=None, api_key=None, model=None, options=None):
    """Like classify_bytes but also returns the raw response (full per-option
    probabilities) for diagnosis. Returns (summary, raw).

    One request per decision (see FIELDS): the server caps input size, and
    the spec wants the three decisions independent anyway.
    """
    data_uri = to_data_uri_bytes(raw, mime)
    answers, usages, seconds = {}, [], {}
    keyword_answer = None
    t0 = time.perf_counter()
    for field in FIELDS:
        payload = build_payload_from_uri(data_uri, model=model, only=[field],
                                          options=options)
        t1 = time.perf_counter()
        resp = _request(payload, endpoint=endpoint, api_key=api_key)
        seconds[field] = round(time.perf_counter() - t1, 2)
        answers[field] = resp["answers"][field]
        keyword_answer = resp["answers"].get("threat_keywords", keyword_answer)
        if resp.get("usage"):
            usages.append(resp["usage"])
    seconds["total"] = round(time.perf_counter() - t0, 2)
    usage = _merge_usage(usages) or {}
    usage["seconds"] = seconds
    data = {"answers": answers, "usage": usage}
    if keyword_answer is not None:
        data["threat"] = {"keywords": detect_threat(keyword_answer),
                          "probabilities": keyword_answer["probabilities"]}
    return summarize(data), data


def _merge_usage(usages):
    if not usages:
        return None
    merged = {}
    for u in usages:
        for k, v in u.items():
            if isinstance(v, (int, float)):
                merged[k] = merged.get(k, 0) + v
    return merged or None


def top_choices(probabilities, n=5):
    return sorted(probabilities.items(), key=lambda kv: -kv[1])[:n]


def detect_threat(answer, threshold=THREAT_THRESHOLD):
    """Keywords at or above `threshold`, most likely first. `NO_THREAT` never counts."""
    probabilities = answer.get("probabilities") or {}
    hits = [(name, p) for name, p in probabilities.items()
            if name != NO_THREAT and p >= threshold]
    return [name for name, _ in sorted(hits, key=lambda kv: (-kv[1], kv[0]))]


def qc_priority(answers, keywords=(), model_department=None):
    """Lower number = look at it sooner. Every document still goes to a human."""
    reasons = []
    for field in ("branch", "department", "recipient"):
        if field == "department" and keywords:
            continue
        if answers[field]["choice"] in ESCAPES:
            reasons.append(f"{field}: model chose '{answers[field]['choice']}'")
    pair = (answers["branch"]["choice"], answers["department"]["choice"])
    if VALID_COMBOS is not None and pair not in VALID_COMBOS:
        reasons.append(f"branch/department combination {pair} is not valid")
    if keywords:
        hit = keywords[0]
        if model_department == THREAT_DEPARTMENT:
            reasons.append(f"department: threat keyword '{hit}' detected; "
                           f"already {THREAT_DEPARTMENT}")
        else:
            reasons.append(f"department: threat keyword '{hit}' detected; "
                           f"routed to {THREAT_DEPARTMENT}")
    min_conf = min(a["confidence"] for a in answers.values())
    if reasons:
        return 0, min_conf, reasons       # top of the queue
    return 1, min_conf, ["no flags; ordered by lowest field confidence"]


def summarize(data):
    answers = data["answers"]
    keywords = (data.get("threat") or {}).get("keywords") or []
    model_department = answers["department"]["choice"]
    department = model_department
    if keywords:
        department = THREAT_DEPARTMENT
    tier, min_conf, reasons = qc_priority(answers, keywords=keywords,
                                          model_department=model_department)
    summary = {
        "branch": answers["branch"]["choice"],
        "department": department,
        "recipient": answers["recipient"]["choice"],
        "confidence": {k: round(v["confidence"], 3) for k, v in answers.items()},
        "qc": {"tier": tier, "sort_key": [tier, round(min_conf, 3)], "reasons": reasons},
        "usage": data.get("usage"),
    }
    if keywords:
        summary["threat"] = {"keywords": keywords, "model_department": model_department}
    return summary
