from mailroom_clf import classify_with_raw_bytes, top_choices
from mailroom_clf import client as client_mod


def _canned_post(payload, *, endpoint=None, api_key=None):
    def ans(choice, conf):
        return {"type": "choice", "choice": choice,
                "probabilities": {choice: conf, "other": 0.01}, "confidence": conf}

    assert endpoint == "e" and api_key == "k"
    return {"answers": {"branch": ans("DBS_KOVAN", 0.8),
                        "department": ans("WEALTH_INVESTMENT_ADVISORY", 0.7),
                        "recipient": ans("lim_hui_ling", 0.6)}}


def test_with_raw_returns_summary_and_full_distribution(monkeypatch):
    monkeypatch.setattr(client_mod, "_post", _canned_post)
    summary, raw = classify_with_raw_bytes(b"fakepng", "image/png",
                                           endpoint="e", api_key="k")
    assert summary["branch"] == "DBS_KOVAN"
    assert set(summary["usage"]["seconds"]) == {"branch", "department", "recipient", "total"}
    assert set(raw["answers"]["branch"]["probabilities"]) == {"DBS_KOVAN", "other"}


def test_env_settings(monkeypatch):
    from mailroom_clf import get_settings

    monkeypatch.setenv("AI_BASE_URL", "e2")
    monkeypatch.setenv("AI_API_KEY", "k2")
    monkeypatch.setenv("AI_DECISION_MODEL", "m2")
    s = get_settings()
    assert (s["endpoint"], s["api_key"], s["model"]) == ("e2", "k2", "m2")


def test_top_choices_orders_desc():
    assert top_choices({"a": 0.1, "b": 0.9, "c": 0.5}, 2) == [("b", 0.9), ("c", 0.5)]


def test_payload_carries_custom_options():
    from mailroom_clf import build_payload_from_uri
    from mailroom_clf.options import RoutingOptions

    opts = RoutingOptions(branches={"HQ": "Head Office"},
                          departments={"OPS": "Operations"},
                          people={"a_b": "A B"})
    payload = build_payload_from_uri("data:image/png;base64,AA==", options=opts)
    assert list(payload["questions"]["branch"]["criteria"]) == ["HQ", "unclear"]
    assert list(payload["questions"]["recipient"]["criteria"]) == ["a_b", "not_in_list"]


def test_classify_forwards_custom_options_to_the_request(monkeypatch):
    from mailroom_clf.options import RoutingOptions

    seen = {}

    def fake_post(payload, *, endpoint=None, api_key=None):
        (field, question), = payload["questions"].items()
        seen[field] = question["criteria"]
        ans = {"type": "choice", "choice": "HQ",
               "probabilities": {"HQ": 0.9}, "confidence": 0.9}
        return {"answers": {field: ans}}

    opts = RoutingOptions(branches={"HQ": "Head Office"},
                          departments={"OPS": "Operations"},
                          people={"a_b": "A B"})
    monkeypatch.setattr(client_mod, "_post", fake_post)
    classify_with_raw_bytes(b"fakepng", "image/png", endpoint="e", api_key="k",
                            options=opts)
    assert list(seen["branch"]) == ["HQ", "unclear"]
    assert list(seen["department"]) == ["OPS", "other"]
    assert list(seen["recipient"]) == ["a_b", "not_in_list"]
