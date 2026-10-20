from mailroom_clf.options import (
    RoutingOptions,
    default_options,
    format_options,
    parse_options,
)


def test_defaults_round_trip_through_the_text_fields():
    opts = default_options()
    b, d, r = format_options(opts)
    parsed, errors = parse_options(b, d, r)
    assert errors == []
    assert parsed == opts


def test_names_are_one_per_line_and_comments_are_skipped():
    parsed, errors = parse_options(
        "DBS MBFC\n# comment\n\n  DBS Kovan  \n",
        "Operations\n",
        "Tan Wei Ming\nLim Hui Ling\n",
    )
    assert errors == []
    assert parsed.branches == ["DBS MBFC", "DBS Kovan"]
    assert parsed.departments == ["Operations"]
    assert parsed.people == ["Tan Wei Ming", "Lim Hui Ling"]


def test_equals_is_part_of_the_name_now():
    parsed, errors = parse_options("DBS_MBFC = DBS MBFC", "D = D", "N")
    assert errors == []
    assert parsed.branches == ["DBS_MBFC = DBS MBFC"]


def test_duplicates_keep_the_first_occurrence():
    parsed, errors = parse_options(
        "DBS Kovan\nDBS MBFC\ndbs  kovan\n",
        "D = D",
        "Tan Wei Ming\ntan wei ming\n",
    )
    assert errors == []
    assert parsed.branches == ["DBS Kovan", "DBS MBFC"]
    assert parsed.people == ["Tan Wei Ming"]


def test_empty_list_is_rejected():
    parsed, errors = parse_options("", "D = D", "N")
    assert parsed is None
    assert any("branch: add at least one option" in e for e in errors)


def test_comment_only_list_is_rejected():
    parsed, errors = parse_options("# nothing here", "D = D", "N")
    assert parsed is None
    assert any("branch: add at least one option" in e for e in errors)


def test_frozen_value_object():
    opts = RoutingOptions(branches=["A"], departments=["B"], people=["C"])
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
    )
    assert errors == []
    assert parsed.branches == ["DBS MBFC"]


def test_a_list_of_only_escapes_is_empty():
    parsed, errors = parse_options(
        "branch cannot be determined from this page", "D = D", "N")
    assert parsed is None
    assert any("add at least one option" in e for e in errors)
