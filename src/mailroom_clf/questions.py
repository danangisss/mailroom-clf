"""The three multiple-choice decisions asked about each scan."""

import re

from .config import (
    BRANCHES,
    DEPARTMENTS,
    KNOWN_PEOPLE,
    NOT_IN_LIST,
    OTHER,
    UNCLEAR,
)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def build_questions(options=None):
    """The three questions. `options` defaults to the hardcoded lists in config.

    Criteria are flat lists of strings: the chosen string is the answer, so the
    option name is also what the reviewer sees. Escapes are appended last.
    """
    branches = [*BRANCHES] if options is None else [*options.branches]
    departments = [*DEPARTMENTS] if options is None else [*options.departments]
    people = [*KNOWN_PEOPLE] if options is None else [*options.people]
    return {
        "branch": {"type": "choice",
                   "instructions": "Which DBS branch is this mail for?",
                   "criteria": [*branches, UNCLEAR]},
        "department": {"type": "choice",
                       "instructions": "Which department within the branch should receive it?",
                       "criteria": [*departments, OTHER]},
        "recipient": {"type": "choice",
                      "instructions": "Who is the intended recipient named on the page?",
                      "criteria": [*people, NOT_IN_LIST]},
    }
