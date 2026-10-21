import base64
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mailroom_clf import client as client_mod
from mailroom_clf.config import NO_THREAT, THREAT_DEPARTMENT

APP = Path(__file__).resolve().parents[1] / "app.py"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
IMAGE = PNG + b"\x00" * 4

CHOICES = {"branch": "DBS Kovan",
           "department": "Wealth & Investment Advisory",
           "recipient": "Lim Hui Ling"}


def _answer(choice, confidence=0.9):
    return {"type": "choice", "choice": choice,
            "probabilities": {choice: confidence}, "confidence": confidence}


def _fake_post(monkeypatch, keyword=NO_THREAT, department=None):
    def fake_post(payload, *, endpoint=None, api_key=None):
        answers = {}
        for field, question in payload["questions"].items():
            ids = question["criteria"]
            if field == "threat_keywords":
                choice = next(i for i, name in ids.items() if name == keyword)
                answers[field] = _answer(choice, 0.95)
            else:
                wanted = department if field == "department" and department else CHOICES[field]
                choice = next(i for i, name in ids.items() if name == wanted)
                answers[field] = _answer(choice)
        return {"answers": answers}

    monkeypatch.setattr(client_mod, "_post", fake_post)
    monkeypatch.setenv("AI_BASE_URL", "http://example.invalid")
    monkeypatch.setenv("AI_API_KEY", "test-key")


@pytest.fixture
def canned_post(monkeypatch):
    _fake_post(monkeypatch)


@pytest.fixture
def threat_post(monkeypatch):
    _fake_post(monkeypatch, keyword="bomb",
               department="Customer Service / Account Services")


def _classify(at, name="letter.png", raw=None, mime="image/png"):
    raw = IMAGE if raw is None else raw
    at.file_uploader[0].set_value((name, raw, mime)).run(timeout=30)
    next(b for b in at.button if b.label == "Classify").click().run(timeout=30)
    return at


def _selectbox(at, field):
    return next(s for s in at.selectbox if s.key.startswith(f"fix_{field}_"))


def test_proposal_renders_names(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    text = " | ".join(m.value for m in at.markdown)
    assert "**Branch:** DBS Kovan" in text
    assert "**Department:** Wealth & Investment Advisory" in text


def test_reclassifying_clears_an_earlier_correction(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    assert _selectbox(at, "branch").value == "DBS Kovan"
    first_key = _selectbox(at, "branch").key

    _selectbox(at, "branch").set_value("DBS Thomson").run(timeout=30)
    assert _selectbox(at, "branch").value == "DBS Thomson"
    assert 'branch: "DBS Kovan" → "DBS Thomson"' in " | ".join(
        w.value for w in at.warning)

    next(b for b in at.button if b.label == "Classify").click().run(timeout=30)
    assert _selectbox(at, "branch").value == "DBS Kovan"
    assert _selectbox(at, "branch").key != first_key


def test_editing_options_discards_the_proposal(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    assert "proposal" in at.session_state

    at.text_area[0].set_value("HQ = Head Office").run(timeout=30)
    assert "proposal" not in at.session_state


def test_same_name_and_size_but_different_bytes_is_a_new_file(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30), raw=IMAGE)
    assert "proposal" in at.session_state

    at.file_uploader[0].set_value(("letter.png", PNG + b"X" * 4, "image/png")).run(timeout=30)
    assert "proposal" not in at.session_state


def test_reset_restores_the_default_lists():
    at = AppTest.from_file(APP).run(timeout=30)
    at.text_area[0].set_value("HQ = Head Office").run(timeout=30)
    next(b for b in at.button if b.label == "Reset to defaults").click().run(timeout=30)
    assert len(at.text_area[0].value.splitlines()) == 170
    assert not list(at.exception)


os.environ.pop("AI_BASE_URL", None)


def test_threat_keyword_routes_the_department_to_compliance(threat_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    text = " | ".join(m.value for m in at.markdown)
    assert f"**Department:** {THREAT_DEPARTMENT}" in text
    assert any('Threat keyword "bomb" detected' in w.value for w in at.warning)
    assert _selectbox(at, "department").value == THREAT_DEPARTMENT
    assert THREAT_DEPARTMENT in _selectbox(at, "department").options


def test_reviewer_override_is_reflected_in_the_threat_note(threat_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    _selectbox(at, "department").set_value("Wealth & Investment Advisory").run(timeout=30)
    warnings = " | ".join(w.value for w in at.warning)
    assert "reviewer overrode to Wealth & Investment Advisory" in warnings


def test_keyword_list_is_editable_in_the_sidebar(canned_post):
    at = AppTest.from_file(APP).run(timeout=30)
    assert len(at.text_area) == 4
    at.text_area[3].set_value("# none left").run(timeout=30)
    assert any("threat keyword: add at least one option" in e.value for e in at.error)
