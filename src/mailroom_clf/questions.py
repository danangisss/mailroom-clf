"""The three multiple-choice decisions asked about each scan."""

import re

from .config import (
    BRANCHES,
    DEPARTMENTS,
    KNOWN_PEOPLE,
    NOT_IN_LIST,
    NO_THREAT,
    OTHER,
    THREAT_KEYWORDS,
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


def build_keyword_question(keywords=None):
    """The threat-keyword question that rides along with the department one.

    The server has no free-text answers, so this is a choice over a known list;
    `NO_THREAT` is appended last and never appears in the editable list.
    """
    words = [*THREAT_KEYWORDS] if keywords is None else [*keywords]
    return {
        "type": "choice",
        "instructions": "Which of these threat-related words appear on the page?",
        "criteria": [*words, NO_THREAT],
    }
