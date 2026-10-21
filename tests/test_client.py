import requests

from mailroom_clf import classify_with_raw_bytes, detect_threat, top_choices
from mailroom_clf import client as client_mod
from mailroom_clf.config import NO_THREAT, THREAT_DEPARTMENT, THREAT_THRESHOLD
from mailroom_clf.options import RoutingOptions

OPTS = RoutingOptions(branches=["Head Office"], departments=["Operations"],
                      people=["A B"], keywords=["bomb", "gun"])
OPTS_WITH_COMPLIANCE = RoutingOptions(
    branches=["Head Office"], departments=["Operations", THREAT_DEPARTMENT],
    people=["A B"], keywords=["bomb", "gun"])


def _answer(choice, confidence):
    return {"type": "choice", "choice": choice,
            "probabilities": {choice: confidence}, "confidence": confidence}


def _canned_post(payload, *, endpoint=None, api_key=None):
    """Answer every question in the payload with its first option.

    Keyword questions pick `NO_THREAT`, so this fixture behaves like a clean
    letter. The answers use numeric ids, exactly like the real server.
    """
    assert endpoint == "e" and api_key == "k"
    answers = {}
    for field, question in payload["questions"].items():
        ids = question["criteria"]
        if field == "threat_keywords":
            choice = next(i for i, name in ids.items() if name == NO_THREAT)
            answers[field] = _answer(choice, 0.95)
        else:
            choice = next(iter(ids))
            answers[field] = _answer(choice, 0.9)
    return {"answers": answers}


def test_with_raw_returns_summary_and_full_distribution(monkeypatch):
    monkeypatch.setattr(client_mod, "_post", _canned_post)
    summary, raw = classify_with_raw_bytes(b"fakepng", "image/png",
                                           endpoint="e", api_key="k", options=OPTS)
    assert summary["branch"] == "Head Office"
    assert summary["department"] == "Operations"
    assert set(summary["usage"]["seconds"]) == {"branch", "department", "recipient", "total"}
    assert set(raw["answers"]["branch"]["probabilities"]) == {"Head Office"}
    assert "threat" not in summary


def test_department_request_carries_the_keyword_question(monkeypatch):
    seen = {}

    def fake_post(payload, *, endpoint=None, api_key=None):
        seen[tuple(payload["questions"])] = payload
        return _canned_post(payload, endpoint=endpoint, api_key=api_key)

    monkeypatch.setattr(client_mod, "_post", fake_post)
    classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k",
                            options=OPTS)
    assert ("department", "threat_keywords") in seen
    assert set(seen[("department", "threat_keywords")]["questions"]) == {
        "department", "threat_keywords"}
    assert set(seen[("branch",)]["questions"]) == {"branch"}
    assert set(seen[("recipient",)]["questions"]) == {"recipient"}


def test_requests_always_use_object_criteria(monkeypatch):
    shapes = []

    def fake_post(payload, *, endpoint=None, api_key=None):
        for question in payload["questions"].values():
            shapes.append(type(question["criteria"]))
        return _canned_post(payload, endpoint=endpoint, api_key=api_key)

    monkeypatch.setattr(client_mod, "_post", fake_post)
    classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k",
                            options=OPTS)
    assert shapes and all(shape is dict for shape in shapes)


def test_custom_options_reach_the_request_as_names(monkeypatch):
    seen = {}

    def fake_post(payload, *, endpoint=None, api_key=None):
        for field, question in payload["questions"].items():
            seen[field] = list(question["criteria"].values())
        return _canned_post(payload, endpoint=endpoint, api_key=api_key)

    monkeypatch.setattr(client_mod, "_post", fake_post)
    classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k",
                            options=OPTS)
    assert seen["branch"] == ["Head Office", "branch cannot be determined from this page"]
    assert seen["department"] == ["Operations", "none of the listed departments fits"]
    assert seen["recipient"] == ["A B", "recipient missing or not one of the listed people"]
    assert seen["threat_keywords"] == ["bomb", "gun", NO_THREAT]


def _threat_post(keyword="bomb", probability=0.9, department="Operations"):
    def fake_post(payload, *, endpoint=None, api_key=None):
        answers = {}
        for field, question in payload["questions"].items():
            ids = question["criteria"]
            if field == "threat_keywords":
                hit = next(i for i, name in ids.items() if name == keyword)
                answers[field] = _answer(hit, probability)
            elif field == "department":
                choice = next(i for i, name in ids.items() if name == department)
                answers[field] = _answer(choice, 0.8)
            else:
                answers[field] = _answer(next(iter(ids)), 0.9)
        return {"answers": answers}

    return fake_post


def test_keyword_above_threshold_overrides_the_department(monkeypatch):
    monkeypatch.setattr(client_mod, "_post", _threat_post())
    summary, raw = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k", options=OPTS)
    assert summary["department"] == THREAT_DEPARTMENT
    assert summary["threat"]["keywords"] == ["bomb"]
    assert summary["threat"]["model_department"] == "Operations"
    assert summary["qc"]["tier"] == 0
    assert any("threat keyword 'bomb'" in r for r in summary["qc"]["reasons"])
    assert "bomb" in raw["threat"]["probabilities"]


def test_keyword_below_threshold_keeps_the_model_department(monkeypatch):
    monkeypatch.setattr(client_mod, "_post",
                        _threat_post(probability=THREAT_THRESHOLD - 0.01))
    summary, _ = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k", options=OPTS)
    assert summary["department"] == "Operations"
    assert "threat" not in summary


def test_keyword_at_threshold_triggers(monkeypatch):
    monkeypatch.setattr(client_mod, "_post",
                        _threat_post(probability=THREAT_THRESHOLD))
    summary, _ = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k", options=OPTS)
    assert summary["department"] == THREAT_DEPARTMENT


def test_already_compliance_is_reported_as_such(monkeypatch):
    monkeypatch.setattr(client_mod, "_post",
                        _threat_post(department=THREAT_DEPARTMENT))
    summary, _ = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k",
        options=OPTS_WITH_COMPLIANCE)
    assert summary["department"] == THREAT_DEPARTMENT
    assert any(f"already {THREAT_DEPARTMENT}" in r for r in summary["qc"]["reasons"])


def test_detect_threat_excludes_none_of_these_and_orders_by_probability():
    answer = {"probabilities": {NO_THREAT: 0.9, "gun": 0.7, "bomb": 0.8, "arson": 0.2}}
    assert detect_threat(answer) == ["bomb", "gun"]
    assert detect_threat(answer, threshold=0.75) == ["bomb"]


def test_detect_threat_handles_missing_probabilities():
    assert detect_threat({}) == []


def test_env_settings(monkeypatch):
    from mailroom_clf import get_settings

    monkeypatch.setenv("AI_BASE_URL", "e2")
    monkeypatch.setenv("AI_API_KEY", "k2")
    monkeypatch.setenv("AI_DECISION_MODEL", "m2")
    s = get_settings()
    assert (s["endpoint"], s["api_key"], s["model"]) == ("e2", "k2", "m2")


def test_top_choices_orders_desc():
    assert top_choices({"a": 0.1, "b": 0.9, "c": 0.5}, 2) == [("b", 0.9), ("c", 0.5)]


def test_too_large_is_not_retried(monkeypatch):
    calls = []

    def fake_post(payload, *, endpoint=None, api_key=None):
        calls.append(payload)
        raise _http_error(500, '{"error":{"message":"input is too large to process"}}')

    monkeypatch.setattr(client_mod, "_post", fake_post)
    try:
        classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k")
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("expected the 500 to propagate")
    assert len(calls) == 1


def _http_error(status, body):
    response = requests.Response()
    response.status_code = status
    response._content = body.encode()
    response.url = "http://test/v1/systemone"
    return requests.HTTPError(f"{status} for {response.url}", response=response)
