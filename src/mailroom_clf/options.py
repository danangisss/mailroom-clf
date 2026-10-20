"""User-editable routing options.

The sidebar lets a reviewer replace the branch, department and recipient lists
for the current session. Options are plain names, one per line; the name is the
value the model answers with. The hardcoded lists in `config` are the defaults.
"""

from dataclasses import dataclass

from .config import BRANCHES, DEPARTMENTS, ESCAPES, KNOWN_PEOPLE


@dataclass(frozen=True)
class RoutingOptions:
    """One session's option lists. Escape phrases are not stored here."""

    branches: list[str]
    departments: list[str]
    people: list[str]


def default_options():
    return RoutingOptions(
        branches=list(BRANCHES),
        departments=list(DEPARTMENTS),
        people=list(KNOWN_PEOPLE),
    )


def format_options(options):
    """Render options back into the three textarea texts (round-trips defaults)."""
    return (
        "\n".join(options.branches),
        "\n".join(options.departments),
        "\n".join(options.people),
    )


def parse_options(branch_text, department_text, recipient_text):
    """Parse the three text fields. Returns (options, errors).

    `options` is None whenever `errors` is non-empty, so callers can show the
    errors and refuse to classify instead of sending a guess.
    """
    branches, branch_errors = _parse_names(branch_text, "branch")
    departments, department_errors = _parse_names(department_text, "department")
    people, recipient_errors = _parse_names(recipient_text, "recipient")
    errors = branch_errors + department_errors + recipient_errors
    if errors:
        return None, errors
    return RoutingOptions(branches=branches, departments=departments, people=people), []


def _parse_names(text, field):
    """One name per line.

    Blank lines and `#` comments are skipped. Duplicates are dropped, keeping
    the first occurrence (compared after trimming, lowercasing and collapsing
    internal whitespace). Escape phrases are system-owned, so a line that
    repeats one is dropped too. An empty list is an error: the decision would
    have nothing to choose from.
    """
    names = []
    seen = {_key(phrase) for phrase in ESCAPES}
    for raw in text.splitlines():
        name = raw.strip()
        if not name or name.startswith("#"):
            continue
        key = _key(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    if not names:
        return [], [f"{field}: add at least one option"]
    return names, []


def _key(name):
    return " ".join(name.lower().split())
