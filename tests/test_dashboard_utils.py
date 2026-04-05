from web_dashboard_clean import safe_int, safe_float, sanitize_string


def test_safe_int_guards_invalid_and_negative_values():
    assert safe_int("12") == 12
    assert safe_int("-2", default=3) == 3
    assert safe_int("abc", default=7) == 7


def test_safe_float_guards_invalid_and_negative_values():
    assert safe_float("12.5") == 12.5
    assert safe_float("-2", default=3.5) == 3.5
    assert safe_float("abc", default=7.25) == 7.25


def test_sanitize_string_removes_tags_and_scripts():
    raw = '<script>alert(1)</script><b>Deal</b>javascript:bad'
    cleaned = sanitize_string(raw, max_length=50)

    assert "<" not in cleaned
    assert "javascript:" not in cleaned.lower()
