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
    """The three questions. `options` defaults to the hardcoded lists in config."""
    branches = BRANCHES if options is None else options.branches
    departments = DEPARTMENTS if options is None else options.departments
    people = ({slug(p): p for p in KNOWN_PEOPLE} if options is None else options.people)
    branch = {code: name if name.lower().endswith("branch") else f"{name} branch"
              for code, name in branches.items()}
    branch[UNCLEAR] = "branch cannot be determined from this page"
    dept = dict(departments)
    dept[OTHER] = "none of the listed departments fits"
    person = dict(people)
    person[NOT_IN_LIST] = "recipient missing or not one of the listed people"
    return {
        "branch": {"type": "choice",
                   "instructions": "Which DBS branch is this mail for?", "criteria": branch},
        "department": {"type": "choice",
                       "instructions": "Which department within the branch should receive it?",
                       "criteria": dept},
        "recipient": {"type": "choice",
                      "instructions": "Who is the intended recipient named on the page?",
                      "criteria": person},
    }
