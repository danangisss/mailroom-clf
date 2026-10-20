from mailroom_clf import build_questions
from mailroom_clf.config import BRANCHES, NOT_IN_LIST, OTHER, UNCLEAR


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
    )
    q = build_questions(opts)
    assert q["branch"]["criteria"] == ["Head Office", UNCLEAR]
    assert q["department"]["criteria"] == ["Operations", OTHER]
    assert q["recipient"]["criteria"] == ["A B", NOT_IN_LIST]
