import base64
import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from mailroom_clf import client as client_mod

APP = Path(__file__).resolve().parents[1] / "app.py"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
IMAGE = PNG + b"\x00" * 4

CHOICES = {"branch": "DBS Kovan",
           "department": "Wealth & Investment Advisory",
           "recipient": "Lim Hui Ling"}


@pytest.fixture
def canned_post(monkeypatch):
    def fake_post(payload, *, endpoint=None, api_key=None):
        (field, _), = payload["questions"].items()
        choice = CHOICES[field]
        ans = {"type": "choice", "choice": choice,
               "probabilities": {choice: 0.9}, "confidence": 0.9}
        return {"answers": {field: ans}}

    monkeypatch.setattr(client_mod, "_post", fake_post)
    monkeypatch.setenv("AI_BASE_URL", "http://example.invalid")
    monkeypatch.setenv("AI_API_KEY", "test-key")


def _classify(at, name="letter.png", raw=None, mime="image/png"):
    raw = IMAGE if raw is None else raw
    at.file_uploader[0].set_value((name, raw, mime)).run(timeout=30)
    next(b for b in at.button if b.label == "Classify").click().run(timeout=30)
    return at


def _selectbox(at, key):
    return next(s for s in at.selectbox if s.key == key)


def test_proposal_renders_names(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    text = " | ".join(m.value for m in at.markdown)
    assert "**Branch:** DBS Kovan" in text
    assert "**Department:** Wealth & Investment Advisory" in text


def test_reclassifying_clears_an_earlier_correction(canned_post):
    at = _classify(AppTest.from_file(APP).run(timeout=30))
    assert _selectbox(at, "fix_branch").value == "DBS Kovan"

    _selectbox(at, "fix_branch").set_value("DBS Thomson").run(timeout=30)
    assert _selectbox(at, "fix_branch").value == "DBS Thomson"

    next(b for b in at.button if b.label == "Classify").click().run(timeout=30)
    assert _selectbox(at, "fix_branch").value == "DBS Kovan"


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
