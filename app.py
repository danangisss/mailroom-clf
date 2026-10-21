"""Mailroom classification prototype: single scan in, proposal + QC correction out.

Run with:  uv run streamlit run app.py
"""

import hashlib
import json
import os

import streamlit as st

from mailroom_clf import (
    build_payload_from_uri,
    classify_with_raw_bytes,
    summarize,
    to_data_uri_bytes,
    top_choices,
)
from mailroom_clf.options import default_options, format_options, parse_options
from mailroom_clf.questions import build_questions
from mailroom_clf.config import THREAT_DEPARTMENT

FIELD_NAMES = {"branch": "Branch", "department": "Department", "recipient": "Recipient",
               "threat_keywords": "Threat keywords"}


def friendly_reason(reason):
    """Turn an internal QC reason into plain English for reviewers."""
    if reason == "no flags":
        return "no warning signs"
    import re
    m = re.match(r"(\w+): threat keyword '(.+)' detected; routed to (.+)$", reason)
    if m:
        keyword, target = m.group(2), m.group(3)
        return f'Threat keyword "{keyword}" detected — sent to {target}'
    m = re.match(r"(\w+): threat keyword '(.+)' detected; already (.+)$", reason)
    if m:
        keyword, target = m.group(2), m.group(3)
        return f'Threat keyword "{keyword}" detected — already sent to {target}'
    m = re.match(r"(\w+): model chose '(.+)'$", reason)
    if m:
        field, choice = m.groups()
        return f"{FIELD_NAMES.get(field, field)} couldn't be decided ({choice})"
    return reason


def _is_threat_reason(reason):
    return "threat keyword '" in reason


def _server_detail(exc):
    """The server's own explanation, which is the actionable part of a 500."""
    response = getattr(exc, "response", None)
    if response is None:
        return ""
    try:
        data = response.json()
    except Exception:
        return (response.text or "").strip()[:300]
    error = data.get("error") if isinstance(data, dict) else None
    message = error.get("message", "") if isinstance(error, dict) else ""
    return message or (response.text or "").strip()[:300]


def _seed_option_texts():
    branch_text, department_text, recipient_text, keyword_text = format_options(
        default_options())
    st.session_state.setdefault("opt_branch", branch_text)
    st.session_state.setdefault("opt_department", department_text)
    st.session_state.setdefault("opt_recipient", recipient_text)
    st.session_state.setdefault("opt_keywords", keyword_text)


def _set_proposal(proposal):
    """Store a new proposal under a fresh nonce.

    Widget keys include the nonce, so a new proposal can never inherit an old
    dropdown value from session state.
    """
    st.session_state["proposal_nonce"] = st.session_state.get("proposal_nonce", 0) + 1
    for k in [k for k in st.session_state if k.startswith("fix_")]:
        del st.session_state[k]
    st.session_state["proposal"] = proposal


def _options_changed():
    st.session_state.pop("proposal", None)
    for k in [k for k in st.session_state if k.startswith("fix_")]:
        del st.session_state[k]


def _reset_options():
    branch_text, department_text, recipient_text, keyword_text = format_options(
        default_options())
    st.session_state["opt_branch"] = branch_text
    st.session_state["opt_department"] = department_text
    st.session_state["opt_recipient"] = recipient_text
    st.session_state["opt_keywords"] = keyword_text
    _options_changed()


def _secret(*names):
    for name in names:
        try:
            val = st.secrets.get(name)
            if val:
                return val
        except Exception:
            pass
        val = os.environ.get(name)
        if val:
            return val
    return ""


st.set_page_config(page_title="Mailroom Classification", layout="wide")
st.title("Mailroom Classification")

with st.sidebar:
    st.header("Connection")
    endpoint = st.text_input("Endpoint", value=_secret("AI_BASE_URL"), type="password")
    api_key = st.text_input("API key", value=_secret("AI_API_KEY"), type="password")
    model = st.text_input("Model", value=_secret("AI_DECISION_MODEL") or "clef-flash")
    st.divider()
    _seed_option_texts()
    with st.expander("Routing options"):
        st.caption("One name per line. The model answers with one of these "
                   "names; escape choices are added automatically.")
        branch_text = st.text_area("Branches", key="opt_branch", height=200,
                                   on_change=_options_changed)
        department_text = st.text_area("Departments", key="opt_department", height=200,
                                       on_change=_options_changed)
        recipient_text = st.text_area("Recipients", key="opt_recipient", height=200,
                                      on_change=_options_changed)
        keyword_text = st.text_area("Threat keywords", key="opt_keywords", height=140,
                                    on_change=_options_changed,
                                    help="Any match routes the item to Compliance.")
        options, option_errors = parse_options(
            branch_text, department_text, recipient_text, keyword_text)
        if option_errors:
            for err in option_errors:
                st.error(err)
        else:
            st.caption(f"{len(options.branches)} branches · "
                       f"{len(options.departments)} departments · "
                       f"{len(options.people)} recipients · "
                       f"{len(options.keywords)} threat keywords")
        st.button("Reset to defaults", on_click=_reset_options)
    st.divider()
    dry_run = st.checkbox("Dry run (don't call the model)", value=False)
    if st.button("Self-test (offline)"):
        try:
            def ans(choice, conf):
                return {"type": "choice", "choice": choice,
                        "probabilities": {choice: conf}, "confidence": conf}

            good = {"answers": {"branch": ans("DBS Toa Payoh", 0.97),
                                "department": ans("Customer Service / Account Services", 0.91),
                                "recipient": ans("Tan Wei Ming", 0.95)}}
            st.success(f"Self-test passed (tier {summarize(good)['qc']['tier']})")
        except AssertionError as e:
            st.error(f"Self-test failed: {e}")

uploaded = st.file_uploader("Upload the first-page scan", type=["png", "jpg", "jpeg"])
classify_btn = st.button("Classify", type="primary",
                         disabled=uploaded is None or bool(option_errors))

if uploaded is None:
    st.session_state.pop("proposal", None)
    st.session_state.pop("file_id", None)
    for k in [k for k in st.session_state if k.startswith("fix_")]:
        del st.session_state[k]
    st.stop()

file_id = hashlib.sha256(uploaded.getvalue()).hexdigest()
if st.session_state.get("file_id") != file_id:
    st.session_state["file_id"] = file_id
    st.session_state.pop("proposal", None)
    for k in [k for k in st.session_state if k.startswith("fix_")]:
        del st.session_state[k]

if classify_btn and uploaded is not None:
    raw = uploaded.getvalue()
    mime = uploaded.type or "image/png"
    for k in [k for k in st.session_state if k.startswith("fix_")]:
        del st.session_state[k]
    if dry_run:
        payloads = {}
        for field in ("branch", "department", "recipient"):
            p = build_payload_from_uri(to_data_uri_bytes(raw, mime), model=model,
                                       only=[field], options=options)
            p["images"] = [p["images"][0][:60] + "...<truncated>"]
            payloads[field] = p
        _set_proposal({"dry_run_payload": payloads})
    else:
        if not endpoint or not api_key:
            st.error("The endpoint or API key is missing — fill them in the sidebar, "
                     ".streamlit/secrets.toml, or the environment.")
            st.stop()
        with st.spinner("Reading the scan…"):
            try:
                summary, raw = classify_with_raw_bytes(
                    raw, mime, endpoint=endpoint, api_key=api_key, model=model,
                    options=options)
                summary["_raw"] = raw
                _set_proposal(summary)
            except Exception as e:
                detail = _server_detail(e)
                message = f"{e} — {detail}" if detail else str(e)
                st.error(f"Classification failed: {message}")
                st.stop()

proposal = st.session_state.get("proposal")
if proposal is None:
    st.stop()

if "dry_run_payload" in proposal:
    st.subheader("Request preview (no network call)")
    st.json(proposal["dry_run_payload"])
    st.stop()

questions = build_questions(options)
left, right = st.columns(2)
with left:
    st.subheader("Scanned letter")
    st.image(uploaded.getvalue(), width="stretch")
with right:
    st.subheader("Result")
    tier = proposal["qc"]["tier"]
    threats = (proposal.get("threat") or {}).get("keywords") or []
    friendly = [friendly_reason(r) for r in proposal["qc"]["reasons"]
                if not _is_threat_reason(r)]
    if tier == 0:
        detail = "; ".join(friendly) or "a threat keyword needs a human decision"
        st.error(f"Needs a closer look: {detail}")
    else:
        st.success(f"Looks good — {'; '.join(friendly)}")

    corrections = {}
    for field in ("branch", "department", "recipient"):
        choice = proposal[field]
        st.markdown(f"**{FIELD_NAMES[field]}:** {choice}")
        choices = list(questions[field]["criteria"])
        if field == "department" and THREAT_DEPARTMENT not in choices:
            choices.insert(len(choices) - 1, THREAT_DEPARTMENT)
        if choice not in choices:
            choices = [choice] + choices
        corrections[field] = st.selectbox(
            f"Correct the {field} if needed",
            choices,
            index=choices.index(choice),
            key=f"fix_{field}_{st.session_state.get('proposal_nonce', 0)}",
        )

    if proposal.get("usage"):
        with st.expander("Technical details"):
            st.json(proposal["usage"])

    if "_raw" in proposal:
        with st.expander("Model details (for debugging)"):
            for field, q in proposal["_raw"]["answers"].items():
                st.markdown(f"**{FIELD_NAMES.get(field, field)}** — most likely first")
                st.json(dict(top_choices(q["probabilities"], 5)))
            threat_raw = proposal["_raw"].get("threat") or {}
            if threat_raw.get("probabilities"):
                st.markdown("**Threat keywords** — most likely first")
                st.json(dict(top_choices(threat_raw["probabilities"], 5)))

    changed = {f: c for f, c in corrections.items() if c != proposal[f]}
    if threats:
        quoted = ", ".join(f'"{k}"' for k in threats)
        if corrections["department"] != proposal["department"]:
            st.warning(f"Threat keyword {quoted} detected; reviewer overrode "
                       f"to {corrections['department']}.")
        elif proposal.get("threat", {}).get("model_department") == proposal["department"]:
            st.warning(f"Threat keyword {quoted} detected — already sent to "
                       f"{proposal['department']}.")
        else:
            st.warning(f"Threat keyword {quoted} detected — route to "
                       f"{proposal['department']}.")
        changed = {f: c for f, c in changed.items() if f != "department"}

    if changed:
        parts = [f'{FIELD_NAMES[f].lower()}: "{proposal[f]}" → "{c}"'
                 for f, c in changed.items()]
        st.warning(f"Corrections: {'; '.join(parts)} (kept on this screen only)")
    else:
        st.caption("No corrections — the proposal stands as shown.")
