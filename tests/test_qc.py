from mailroom_clf import qc_priority, summarize
from mailroom_clf.config import NOT_IN_LIST


def _ans(choice, conf):
    return {"type": "choice", "choice": choice,
            "probabilities": {choice: conf}, "confidence": conf}


def test_clean_proposal_is_tier_1():
    data = {"answers": {"branch": _ans("DBS_TOA_PAYOH", 0.97),
                        "department": _ans("CUSTOMER_SERVICE", 0.91),
                        "recipient": _ans("tan_wei_ming", 0.95)}}
    out = summarize(data)
    assert out["qc"]["tier"] == 1
    assert out["qc"]["sort_key"] == [1, 0.91]


def test_escape_forces_tier_0():
    data = {"answers": {"branch": _ans("DBS_TOA_PAYOH", 0.97),
                        "department": _ans("CUSTOMER_SERVICE", 0.91),
                        "recipient": _ans(NOT_IN_LIST, 0.88)}}
    tier, _, reasons = qc_priority(data["answers"])
    assert tier == 0
    assert any("recipient" in r for r in reasons)
