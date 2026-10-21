from mailroom_clf import build_keyword_question, build_questions
from mailroom_clf.config import (
    BRANCHES,
    NO_THREAT,
    NOT_IN_LIST,
    OTHER,
    THREAT_KEYWORDS,
    UNCLEAR,
)


def test_branch_has_all_branches_plus_unclear():
    criteria = build_questions()["branch"]["criteria"]
    assert len(criteria) == len(BRANCHES) + 1
    assert criteria[0] == "DBS MBFC"
    assert UNCLEAR in criteria


def test_department_has_other_escape():
    assert OTHER in build_questions()["department"]["criteria"]


def test_recipient_has_not_in_list_escape():
    assert NOT_IN_LIST in build_questions()["recipient"]["criteria"]


def test_custom_options_replace_the_hardcoded_lists():
    from mailroom_clf.options import RoutingOptions

    opts = RoutingOptions(
        branches=["Head Office"],
        departments=["Operations"],
        people=["A B"],
        keywords=["bomb"],
    )
    q = build_questions(opts)
    assert q["branch"]["criteria"] == ["Head Office", UNCLEAR]
    assert q["department"]["criteria"] == ["Operations", OTHER]
    assert q["recipient"]["criteria"] == ["A B", NOT_IN_LIST]


def test_keyword_question_uses_the_defaults_and_ends_with_none():
    q = build_keyword_question()
    assert q["type"] == "choice"
    assert q["criteria"] == [*THREAT_KEYWORDS, NO_THREAT]
    assert q["criteria"][-1] == NO_THREAT


def test_keyword_question_accepts_custom_keywords():
    q = build_keyword_question(["bomb", "gun"])
    assert q["criteria"] == ["bomb", "gun", NO_THREAT]
