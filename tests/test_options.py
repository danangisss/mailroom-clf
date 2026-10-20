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


def test_code_equals_label_and_bare_lines():
    parsed, errors = parse_options(
        "DBS_MBFC = DBS MBFC\nDBS_Kovan\n",
        "OPS = Operations\n# comment\n\n",
        "Tan Wei Ming\nLim Hui Ling\n",
    )
    assert errors == []
    assert parsed.branches == {"DBS_MBFC": "DBS MBFC", "dbs_kovan": "DBS_Kovan"}
    assert parsed.departments == {"OPS": "Operations"}
    assert parsed.people == {"tan_wei_ming": "Tan Wei Ming", "lim_hui_ling": "Lim Hui Ling"}


def test_recipient_pair_form_uses_the_display_name_as_the_key_source():
    parsed, errors = parse_options("B = B", "D = D", "lim_hui_ling = Lim Hui Ling")
    assert errors == []
    assert parsed.people == {"lim_hui_ling": "Lim Hui Ling"}


def test_duplicate_code_is_rejected():
    parsed, errors = parse_options("A = One\nA = Two", "D = D", "N")
    assert parsed is None
    assert any("duplicate code 'A'" in e for e in errors)


def test_duplicate_recipient_slug_is_rejected():
    parsed, errors = parse_options("A = A", "D = D", "Tan Wei Ming\ntan  wei ming")
    assert parsed is None
    assert any("duplicate code 'tan_wei_ming'" in e for e in errors)


def test_empty_list_is_rejected():
    parsed, errors = parse_options("", "D = D", "N")
    assert parsed is None
    assert any("branch: add at least one option" in e for e in errors)


def test_reserved_escape_code_is_rejected():
    parsed, errors = parse_options("unclear = Something", "D = D", "N")
    assert parsed is None
    assert any("reserved" in e for e in errors)


def test_malformed_pair_is_rejected():
    parsed, errors = parse_options("= Missing Code", "D = D", "N")
    assert parsed is None
    assert any("line 1" in e for e in errors)


def test_frozen_value_object():
    opts = RoutingOptions(branches={"A": "A"}, departments={"B": "B"}, people={"c": "C"})
    try:
        opts.branches = {}
    except Exception as exc:
        assert "cannot assign" in str(exc).lower() or "frozen" in str(exc).lower()
    else:
        raise AssertionError("RoutingOptions should be immutable")


def test_reserved_escape_check_ignores_case_for_pairs():
    for text in ("OTHER = Something", "Unclear = Something", "Not-In-List = X"):
        parsed, errors = parse_options(text, "D = D", "N")
        assert parsed is None, text
        assert any("reserved" in e for e in errors), (text, errors)
