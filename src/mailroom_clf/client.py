"""Network client + result shaping. UI-free: no Streamlit, no argparse here."""

import base64
import mimetypes
import time

import requests

from .config import ESCAPES, VALID_COMBOS, get_settings
from .questions import build_questions


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


def _with_object_criteria(payload, field):
    """Array criteria -> {id: name} for servers that only accept an object.

    `payload` must carry exactly the field being rewritten. Returns the
    rewritten payload and the id -> name map needed to translate the answer
    back into a name.
    """
    names = payload["questions"][field]["criteria"]
    id_map = {str(i): name for i, name in enumerate(names, 1)}
    rewritten = {**payload,
                 "questions": {**payload["questions"],
                               field: {**payload["questions"][field],
                                       "criteria": id_map}}}
    return rewritten, id_map


def _translate_answer(resp, field, id_map):
    """Map numeric ids back to names so callers only ever see names."""
    answer = dict(resp["answers"][field])
    answer["choice"] = id_map.get(str(answer["choice"]), answer["choice"])
    answer["probabilities"] = {id_map.get(str(k), k): v
                               for k, v in answer["probabilities"].items()}
    return {**resp, "answers": {**resp["answers"], field: answer}}


def _rejects_array(exc):
    """True when the failure looks like 'criteria must be an object'.

    Shape errors are the only ones worth retrying with object criteria; a
    request that is simply too large must not be sent twice.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return False
    if response.status_code not in (400, 422, 500):
        return False
    body = (response.text or "").lower()
    if "too large" in body or "batch size" in body:
        return False
    return "criteria" in body and any(
        word in body for word in ("object", "array", "list", "expected", "type"))


def _request(payload, field, *, endpoint=None, api_key=None):
    """POST one field; fall back to object criteria if the server rejects arrays."""
    try:
        return _post(payload, endpoint=endpoint, api_key=api_key)
    except requests.HTTPError as exc:
        if not _rejects_array(exc):
            raise
        rewritten, id_map = _with_object_criteria(payload, field)
        resp = _post(rewritten, endpoint=endpoint, api_key=api_key)
        return _translate_answer(resp, field, id_map)


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
    t0 = time.perf_counter()
    for field in FIELDS:
        payload = build_payload_from_uri(data_uri, model=model, only=[field],
                                          options=options)
        t1 = time.perf_counter()
        resp = _request(payload, field, endpoint=endpoint, api_key=api_key)
        seconds[field] = round(time.perf_counter() - t1, 2)
        answers[field] = resp["answers"][field]
        if resp.get("usage"):
            usages.append(resp["usage"])
    seconds["total"] = round(time.perf_counter() - t0, 2)
    usage = _merge_usage(usages) or {}
    usage["seconds"] = seconds
    data = {"answers": answers, "usage": usage}
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


def qc_priority(answers):
    """Lower number = look at it sooner. Every document still goes to a human."""
    reasons = []
    for field in ("branch", "department", "recipient"):
        if answers[field]["choice"] in ESCAPES:
            reasons.append(f"{field}: model chose '{answers[field]['choice']}'")
    pair = (answers["branch"]["choice"], answers["department"]["choice"])
    if VALID_COMBOS is not None and pair not in VALID_COMBOS:
        reasons.append(f"branch/department combination {pair} is not valid")
    min_conf = min(a["confidence"] for a in answers.values())
    if reasons:
        return 0, min_conf, reasons       # top of the queue
    return 1, min_conf, ["no flags; ordered by lowest field confidence"]


def summarize(data):
    answers = data["answers"]
    tier, min_conf, reasons = qc_priority(answers)
    return {
        "branch": answers["branch"]["choice"],
        "department": answers["department"]["choice"],
        "recipient": answers["recipient"]["choice"],
        "confidence": {k: round(v["confidence"], 3) for k, v in answers.items()},
        "qc": {"tier": tier, "sort_key": [tier, round(min_conf, 3)], "reasons": reasons},
        "usage": data.get("usage"),
    }
