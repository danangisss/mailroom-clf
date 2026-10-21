from mailroom_clf.config import MAX_THREAT_KEYWORDS, NO_THREAT, THREAT_KEYWORDS
from mailroom_clf.options import (
    RoutingOptions,
    default_options,
    format_options,
    parse_options,
)


def test_defaults_round_trip_through_the_text_fields():
    opts = default_options()
    b, d, r, k = format_options(opts)
    parsed, errors = parse_options(b, d, r, k)
    assert errors == []
    assert parsed == opts


def test_names_are_one_per_line_and_comments_are_skipped():
    parsed, errors = parse_options(
        "DBS MBFC\n# comment\n\n  DBS Kovan  \n",
        "Operations\n",
        "Tan Wei Ming\nLim Hui Ling\n",
        "bomb\nthreat\n",
    )
    assert errors == []
    assert parsed.branches == ["DBS MBFC", "DBS Kovan"]
    assert parsed.departments == ["Operations"]
    assert parsed.people == ["Tan Wei Ming", "Lim Hui Ling"]
    assert parsed.keywords == ["bomb", "threat"]


def test_equals_is_part_of_the_name_now():
    parsed, errors = parse_options("DBS_MBFC = DBS MBFC", "D = D", "N", "bomb")
    assert errors == []
    assert parsed.branches == ["DBS_MBFC = DBS MBFC"]


def test_duplicates_keep_the_first_occurrence():
    parsed, errors = parse_options(
        "DBS Kovan\nDBS MBFC\ndbs  kovan\n",
        "D = D",
        "Tan Wei Ming\ntan wei ming\n",
        "bomb\nBomb\n",
    )
    assert errors == []
    assert parsed.branches == ["DBS Kovan", "DBS MBFC"]
    assert parsed.people == ["Tan Wei Ming"]
    assert parsed.keywords == ["bomb"]


def test_empty_list_is_rejected():
    parsed, errors = parse_options("", "D = D", "N", "bomb")
    assert parsed is None
    assert any("branch: add at least one option" in e for e in errors)


def test_comment_only_list_is_rejected():
    parsed, errors = parse_options("# nothing here", "D = D", "N", "bomb")
    assert parsed is None
    assert any("branch: add at least one option" in e for e in errors)


def test_frozen_value_object():
    opts = RoutingOptions(branches=["A"], departments=["B"], people=["C"], keywords=["D"])
    try:
        opts.branches = []
    except Exception as exc:
        assert "cannot assign" in str(exc).lower() or "frozen" in str(exc).lower()
    else:
        raise AssertionError("RoutingOptions should be immutable")


def test_escape_phrase_is_dropped_from_user_input():
    parsed, errors = parse_options(
        "DBS MBFC\nbranch cannot be determined from this page",
        "D = D",
        "N",
        "bomb",
    )
    assert errors == []
    assert parsed.branches == ["DBS MBFC"]


def test_a_list_of_only_escapes_is_empty():
    parsed, errors = parse_options(
        "branch cannot be determined from this page", "D = D", "N", "bomb")
    assert parsed is None
    assert any("add at least one option" in e for e in errors)


def test_empty_keyword_list_is_rejected():
    parsed, errors = parse_options("B", "D", "N", "")
    assert parsed is None
    assert any("threat keyword: add at least one option" in e for e in errors)


def test_keyword_list_has_a_cap():
    text = "\n".join(f"word{i}" for i in range(MAX_THREAT_KEYWORDS + 1))
    parsed, errors = parse_options("B", "D", "N", text)
    assert parsed is None
    assert any(f"threat keyword: keep at most {MAX_THREAT_KEYWORDS}" in e for e in errors)


def test_keyword_cap_boundary_is_allowed():
    text = "\n".join(f"word{i}" for i in range(MAX_THREAT_KEYWORDS))
    parsed, errors = parse_options("B", "D", "N", text)
    assert errors == []
    assert len(parsed.keywords) == MAX_THREAT_KEYWORDS


def test_none_of_these_is_system_owned():
    parsed, errors = parse_options("B", "D", "N", f"bomb\n{NO_THREAT}\n")
    assert errors == []
    assert parsed.keywords == ["bomb"]


def test_defaults_include_the_threat_keywords():
    assert default_options().keywords == list(THREAT_KEYWORDS)
