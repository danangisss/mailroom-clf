from mailroom_clf import qc_priority, summarize
from mailroom_clf.config import NOT_IN_LIST, THREAT_DEPARTMENT


def _ans(choice, conf):
    return {"type": "choice", "choice": choice,
            "probabilities": {choice: conf}, "confidence": conf}


def test_clean_proposal_is_tier_1():
    data = {"answers": {"branch": _ans("DBS Toa Payoh", 0.97),
                        "department": _ans("Customer Service / Account Services", 0.91),
                        "recipient": _ans("Tan Wei Ming", 0.95)}}
    out = summarize(data)
    assert out["qc"]["tier"] == 1
    assert out["qc"]["sort_key"] == [1, 0.91]


def test_escape_forces_tier_0():
    data = {"answers": {"branch": _ans("DBS Toa Payoh", 0.97),
                        "department": _ans("Customer Service / Account Services", 0.91),
                        "recipient": _ans(NOT_IN_LIST, 0.88)}}
    tier, _, reasons = qc_priority(data["answers"])
    assert tier == 0
    assert any("recipient" in r for r in reasons)


def test_threat_keyword_forces_tier_0_and_overrides_the_department():
    data = {"answers": {"branch": _ans("DBS Toa Payoh", 0.97),
                        "department": _ans("Customer Service / Account Services", 0.91),
                        "recipient": _ans("Tan Wei Ming", 0.95)},
            "threat": {"keywords": ["bomb"],
                       "model_department": "Customer Service / Account Services"}}
    out = summarize(data)
    assert out["department"] == THREAT_DEPARTMENT
    assert out["qc"]["tier"] == 0
    assert out["threat"] == {"keywords": ["bomb"],
                             "model_department": "Customer Service / Account Services"}
    assert any("routed to Compliance" in r for r in out["qc"]["reasons"])


def test_threat_keyword_on_an_already_compliance_item_is_reported():
    data = {"answers": {"branch": _ans("DBS Toa Payoh", 0.97),
                        "department": _ans(THREAT_DEPARTMENT, 0.91),
                        "recipient": _ans("Tan Wei Ming", 0.95)},
            "threat": {"keywords": ["bomb"], "model_department": THREAT_DEPARTMENT}}
    out = summarize(data)
    assert out["department"] == THREAT_DEPARTMENT
    assert any("already Compliance" in r for r in out["qc"]["reasons"])


def test_a_threat_keyword_suppresses_a_department_escape_reason():
    data = {"answers": {"branch": _ans("DBS Toa Payoh", 0.97),
                        "department": _ans("none of the listed departments fits", 0.4),
                        "recipient": _ans("Tan Wei Ming", 0.95)},
            "threat": {"keywords": ["bomb"],
                       "model_department": "none of the listed departments fits"}}
    out = summarize(data)
    assert not any("department: model chose" in r for r in out["qc"]["reasons"])
