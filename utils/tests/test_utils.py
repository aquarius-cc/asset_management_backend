"""
工具函数测试

覆盖 utils/date_utils.py 与 utils/string_utils.py 的全部公开函数。
"""

from datetime import date, datetime

from utils.date_utils import (
    format_date,
    get_date_range,
    get_month_start_end,
    get_week_start_end,
    parse_date,
)
from utils.string_utils import (
    generate_numeric_code,
    generate_random_string,
    generate_token,
    mask_id_card,
    mask_phone_number,
    mask_sensitive_info,
)


class TestFormatDate:
    def test_none_returns_none(self):
        assert format_date(None) is None

    def test_date_object_default_format(self):
        assert format_date(date(2024, 1, 15)) == "2024-01-15"

    def test_datetime_object(self):
        assert format_date(datetime(2024, 1, 15, 10, 30)) == "2024-01-15"

    def test_custom_format(self):
        assert format_date(date(2024, 1, 15), "%Y/%m/%d") == "2024/01/15"

    def test_non_date_value_returns_str(self):
        assert format_date("2024-01-15") == "2024-01-15"


class TestParseDate:
    def test_parse_valid(self):
        assert parse_date("2024-01-15") == date(2024, 1, 15)

    def test_parse_empty(self):
        assert parse_date("") is None
        assert parse_date(None) is None

    def test_parse_invalid_format(self):
        assert parse_date("2024-13-45") is None

    def test_parse_custom_format(self):
        assert parse_date("2024/01/15", "%Y/%m/%d") == date(2024, 1, 15)


class TestGetDateRange:
    def test_single_day(self):
        assert get_date_range(date(2024, 1, 1), date(2024, 1, 1)) == [date(2024, 1, 1)]

    def test_multi_day(self):
        result = get_date_range(date(2024, 1, 1), date(2024, 1, 3))
        assert result == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]

    def test_length_matches_delta(self):
        start, end = date(2024, 1, 5), date(2024, 1, 10)
        assert len(get_date_range(start, end)) == 6


class TestGetWeekStartEnd:
    def test_known_wednesday(self):
        wednesday = date(2024, 1, 17)  # 2024-01-17 为周三
        start, end = get_week_start_end(wednesday)
        assert start == date(2024, 1, 15)  # 周一
        assert end == date(2024, 1, 21)  # 周日

    def test_default_is_today(self):
        start, end = get_week_start_end()
        assert start <= date.today() <= end
        assert start.weekday() == 0
        assert end.weekday() == 6


class TestGetMonthStartEnd:
    def test_regular_month(self):
        start, end = get_month_start_end(2024, 2)
        assert start == date(2024, 2, 1)
        assert end == date(2024, 2, 29)  # 2024 为闰年

    def test_december_rollover(self):
        start, end = get_month_start_end(2024, 12)
        assert start == date(2024, 12, 1)
        assert end == date(2024, 12, 31)


class TestGenerateRandomString:
    def test_default_length(self):
        result = generate_random_string()
        assert len(result) == 8

    def test_custom_length_and_chars(self):
        result = generate_random_string(4, chars="AB")
        assert len(result) == 4
        assert set(result) <= {"A", "B"}

    def test_uses_expected_charset(self):
        result = generate_random_string(32)
        assert all(c.isalnum() for c in result)


class TestGenerateNumericCode:
    def test_default_length(self):
        assert len(generate_numeric_code()) == 6

    def test_all_digits(self):
        code = generate_numeric_code(4)
        assert set(code) <= set("0123456789")


class TestGenerateToken:
    def test_length(self):
        assert len(generate_token(16)) > 0

    def test_urlsafe(self):
        token = generate_token()
        chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert set(token) <= chars


class TestMaskSensitiveInfo:
    def test_standard(self):
        assert mask_sensitive_info("13812345678") == "138****5678"

    def test_custom_start_end(self):
        assert mask_sensitive_info("13812345678", start=2, end=2) == "13*******78"

    def test_short_string_all_masked(self):
        assert mask_sensitive_info("12345", start=3, end=4) == "*****"

    def test_empty(self):
        assert mask_sensitive_info("") == ""
        assert mask_sensitive_info(None) == ""


class TestMaskPhoneNumber:
    def test_standard(self):
        assert mask_phone_number("13812345678") == "138****5678"


class TestMaskIdCard:
    def test_standard(self):
        assert mask_id_card("110101199001011234") == "110101********1234"

    def test_short_id_all_masked(self):
        assert mask_id_card("1234567890123") == "*" * 13

    def test_empty(self):
        assert mask_id_card("") == ""
