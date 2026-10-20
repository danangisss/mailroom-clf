import requests

from mailroom_clf import classify_with_raw_bytes, top_choices
from mailroom_clf import client as client_mod
from mailroom_clf.options import RoutingOptions


def _canned_post(payload, *, endpoint=None, api_key=None):
    def ans(choice, conf):
        return {"type": "choice", "choice": choice,
                "probabilities": {choice: conf, "escape": 0.01}, "confidence": conf}

    assert endpoint == "e" and api_key == "k"
    return {"answers": {"branch": ans("DBS Kovan", 0.8),
                        "department": ans("Wealth & Investment Advisory", 0.7),
                        "recipient": ans("Lim Hui Ling", 0.6)}}


def test_with_raw_returns_summary_and_full_distribution(monkeypatch):
    monkeypatch.setattr(client_mod, "_post", _canned_post)
    summary, raw = classify_with_raw_bytes(b"fakepng", "image/png",
                                           endpoint="e", api_key="k")
    assert summary["branch"] == "DBS Kovan"
    assert set(summary["usage"]["seconds"]) == {"branch", "department", "recipient", "total"}
    assert set(raw["answers"]["branch"]["probabilities"]) == {"DBS Kovan", "escape"}


def test_env_settings(monkeypatch):
    from mailroom_clf import get_settings

    monkeypatch.setenv("AI_BASE_URL", "e2")
    monkeypatch.setenv("AI_API_KEY", "k2")
    monkeypatch.setenv("AI_DECISION_MODEL", "m2")
    s = get_settings()
    assert (s["endpoint"], s["api_key"], s["model"]) == ("e2", "k2", "m2")


def test_top_choices_orders_desc():
    assert top_choices({"a": 0.1, "b": 0.9, "c": 0.5}, 2) == [("b", 0.9), ("c", 0.5)]


def test_payload_carries_custom_options_as_string_lists():
    from mailroom_clf import build_payload_from_uri

    opts = RoutingOptions(branches=["Head Office"],
                          departments=["Operations"],
                          people=["A B"])
    payload = build_payload_from_uri("data:image/png;base64,AA==", options=opts)
    assert payload["questions"]["branch"]["criteria"] == ["Head Office",
                                                          "branch cannot be determined from this page"]
    assert payload["questions"]["recipient"]["criteria"] == [
        "A B", "recipient missing or not one of the listed people"]


def test_classify_forwards_custom_options_to_the_request(monkeypatch):
    seen = {}

    def fake_post(payload, *, endpoint=None, api_key=None):
        (field, question), = payload["questions"].items()
        seen[field] = question["criteria"]
        choice = question["criteria"][0]
        return {"answers": {field: {"type": "choice", "choice": choice,
                                    "probabilities": {choice: 0.9},
                                    "confidence": 0.9}}}

    opts = RoutingOptions(branches=["Head Office"],
                          departments=["Operations"],
                          people=["A B"])
    monkeypatch.setattr(client_mod, "_post", fake_post)
    classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k",
                            options=opts)
    assert seen["branch"] == ["Head Office", "branch cannot be determined from this page"]
    assert seen["department"] == ["Operations", "none of the listed departments fits"]
    assert seen["recipient"] == ["A B", "recipient missing or not one of the listed people"]


def test_object_criteria_fallback_translates_ids_back_to_names(monkeypatch):
    calls = []

    def fake_post(payload, *, endpoint=None, api_key=None):
        (field, question), = payload["questions"].items()
        calls.append(question["criteria"])
        if isinstance(question["criteria"], list):
            raise _http_error(400, '{"error":{"message":"criteria must be an object"}}')
        return {"answers": {field: {"type": "choice", "choice": "2",
                                    "probabilities": {"2": 0.7, "1": 0.2},
                                    "confidence": 0.7}}}

    monkeypatch.setattr(client_mod, "_post", fake_post)
    summary, raw = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k",
        options=RoutingOptions(branches=["One", "Two"], departments=["D"], people=["N"]))
    assert isinstance(calls[0], list)
    assert isinstance(calls[1], dict)
    assert summary["branch"] == "Two"
    assert raw["answers"]["branch"]["choice"] == "Two"
    assert raw["answers"]["branch"]["probabilities"]["Two"] == 0.7


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


def test_object_criteria_fallback_handles_integer_ids(monkeypatch):
    def fake_post(payload, *, endpoint=None, api_key=None):
        (field, question), = payload["questions"].items()
        if isinstance(question["criteria"], list):
            raise _http_error(400, '{"error":{"message":"criteria must be an object"}}')
        return {"answers": {field: {"type": "choice", "choice": 2,
                                    "probabilities": {2: 0.7}, "confidence": 0.7}}}

    monkeypatch.setattr(client_mod, "_post", fake_post)
    summary, raw = classify_with_raw_bytes(
        b"fakepng", "image/png", endpoint="e", api_key="k",
        options=RoutingOptions(branches=["One", "Two"], departments=["D"], people=["N"]))
    assert summary["branch"] == "Two"
    assert raw["answers"]["branch"]["probabilities"] == {"Two": 0.7}


def test_object_criteria_fallback_keeps_sibling_questions():
    payload = {"questions": {"branch": {"criteria": ["A", "B"]},
                             "department": {"criteria": ["D"]}}}
    rewritten, id_map = client_mod._with_object_criteria(payload, "branch")
    assert set(rewritten["questions"]) == {"branch", "department"}
    assert rewritten["questions"]["branch"]["criteria"] == {"1": "A", "2": "B"}
    assert id_map == {"1": "A", "2": "B"}


def test_criteria_list_too_large_is_not_retried(monkeypatch):
    calls = []

    def fake_post(payload, *, endpoint=None, api_key=None):
        calls.append(payload)
        raise _http_error(400, '{"error":{"message":"criteria list is too large"}}')

    monkeypatch.setattr(client_mod, "_post", fake_post)
    try:
        classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k")
    except requests.HTTPError:
        pass
    else:
        raise AssertionError("expected the 400 to propagate")
    assert len(calls) == 1
