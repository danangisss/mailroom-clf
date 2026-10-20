"""User-editable routing options.

The sidebar lets a reviewer replace the branch, department and recipient lists
for the current session. Text is the input format (`CODE = Label` per line for
branches and departments, one name per line for recipients) and the hardcoded
lists in `config` are the defaults.
"""

from dataclasses import dataclass

from .config import BRANCHES, DEPARTMENTS, ESCAPES, KNOWN_PEOPLE
from .questions import slug

@dataclass(frozen=True)
class RoutingOptions:
    """One session's option lists. Escape options are not stored here."""

    branches: dict[str, str]
    departments: dict[str, str]
    people: dict[str, str]


def default_options():
    return RoutingOptions(
        branches=dict(BRANCHES),
        departments=dict(DEPARTMENTS),
        people={slug(p): p for p in KNOWN_PEOPLE},
    )


def format_options(options):
    """Render options back into the three textarea texts (round-trips defaults)."""
    def pairs(mapping):
        return "\n".join(f"{code} = {label}" for code, label in mapping.items())

    return (
        pairs(options.branches),
        pairs(options.departments),
        "\n".join(options.people.values()),
    )


def parse_options(branch_text, department_text, recipient_text):
    """Parse the three text fields. Returns (options, errors).

    `options` is None whenever `errors` is non-empty, so callers can show the
    errors and refuse to classify instead of sending a guess.
    """
    branches, branch_errors = _parse_pairs(branch_text, "branch")
    departments, department_errors = _parse_pairs(department_text, "department")
    people, recipient_errors = _parse_pairs(recipient_text, "recipient", slug_only=True)
    errors = branch_errors + department_errors + recipient_errors
    if errors:
        return None, errors
    return RoutingOptions(branches=branches, departments=departments, people=people), []


def _parse_pairs(text, field, *, slug_only=False):
    """`CODE = Label` lines; a bare line takes its code from the label.

    Blank lines and `#` comments are skipped. Recipients always derive their
    code from the display name (slug_only). Duplicate codes, empty labels,
    reserved escape codes and an all-empty list are errors.
    """
    mapping = {}
    errors = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        label = line
        code = ""
        if "=" in line:
            code, label = (part.strip() for part in line.split("=", 1))
            if not code or not label:
                errors.append(
                    f"{field}: line {lineno} needs both a code and a label (CODE = Label)")
                continue
        else:
            code = slug(label)
            if not code:
                errors.append(f"{field}: line {lineno} has no usable code")
                continue
        if slug_only:
            code = slug(label)
            if not code:
                errors.append(f"{field}: line {lineno} has no usable code")
                continue
        if slug(code) in ESCAPES:
            errors.append(f"{field}: code '{code}' is reserved (added automatically)")
            continue
        if code in mapping:
            errors.append(f"{field}: duplicate code '{code}'")
            continue
        mapping[code] = label
    if not mapping and not errors:
        errors.append(f"{field}: add at least one option")
    return mapping, errors
