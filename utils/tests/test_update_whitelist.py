"""字段白名单更新 helper 单元测试(M-31 / BF-142)

两形态 5 处同形收敛的契约:
- 严格形态 apply_whitelisted_updates: 合法 setattr、首个非法即拒、
  error_code 三态(out/recycle 传 FIELD_NOT_ALLOWED; unregistered 不传=None)
- 宽松形态 filter_whitelisted_fields: 白名单过滤 + skip_none 软更新口径
行为等价由既有集成锚回归: test_recycle_service_gaps:78 / unregistered
test_services:215 / test_asset_service FIELD_NOT_ALLOWED / damaged 更新用例。
"""

from typing import Any

import pytest

from core.exceptions import AppValidationError
from utils.update_whitelist import apply_whitelisted_updates, filter_whitelisted_fields


class _Target:
    """极简可 setattr 目标"""

    def __init__(self, **initial: Any) -> None:
        for key, value in initial.items():
            setattr(self, key, value)


class TestApplyWhitelistedUpdatesStrict:
    """严格形态: 白名单 setattr + 首个非法字段即拒"""

    def test_sets_whitelisted_fields(self) -> None:
        """白名单内字段全部原地写入"""
        target = _Target()
        apply_whitelisted_updates(target, {"name": "A", "qty": 2}, {"name", "qty"})
        assert target.name == "A"
        assert target.qty == 2

    def test_rejects_first_illegal_field_with_error_code(self) -> None:
        """非法字段抛 "不允许修改字段: {key}" + 调用方 error_code(out/recycle 口径)"""
        target = _Target(good="x")
        with pytest.raises(AppValidationError) as exc_info:
            apply_whitelisted_updates(target, {"good": "y", "bad": 1}, {"good"}, error_code="FIELD_NOT_ALLOWED")
        assert exc_info.value.detail == "不允许修改字段: bad"
        assert exc_info.value.error_code == "FIELD_NOT_ALLOWED"

    def test_illegal_field_itself_not_set(self) -> None:
        """非法键不被 setattr(拒绝发生在该键写入前)"""
        target = _Target()
        with pytest.raises(AppValidationError):
            apply_whitelisted_updates(target, {"bad": 1}, {"good"}, error_code="FIELD_NOT_ALLOWED")
        assert not hasattr(target, "bad")

    def test_legal_fields_before_illegal_already_set(self) -> None:
        """原循环语义逐字等价: 遍历序中在非法键之前的合法键已落写后才抛"""
        target = _Target()
        with pytest.raises(AppValidationError):
            apply_whitelisted_updates(target, {"good": "y", "bad": 1}, {"good"}, error_code="FIELD_NOT_ALLOWED")
        assert target.good == "y"

    def test_none_error_code_matches_unregistered_default(self) -> None:
        """error_code 不传时为 AppValidationError 默认 None(unregistered 路径口径)"""
        target = _Target()
        with pytest.raises(AppValidationError) as exc_info:
            apply_whitelisted_updates(target, {"bad": 1}, {"good"})
        assert exc_info.value.detail == "不允许修改字段: bad"
        assert exc_info.value.error_code is None


class TestFilterWhitelistedFieldsLoose:
    """宽松形态: 非白名单静默跳过(返回新 dict)"""

    def test_filters_non_whitelisted_preserving_order(self) -> None:
        """仅留白名单键,保持插入序;输入 dict 不被改动"""
        update_data = {"a": 1, "bad": 2, "b": 3}
        result = filter_whitelisted_fields(update_data, {"a", "b"})
        assert list(result.items()) == [("a", 1), ("b", 3)]
        assert "bad" in update_data

    def test_skip_none_drops_none_values(self) -> None:
        """skip_none=True: 白名单内 None 值一并跳过(damaged 软更新口径)"""
        result = filter_whitelisted_fields({"a": 1, "b": None}, {"a", "b"}, skip_none=True)
        assert result == {"a": 1}

    def test_without_skip_none_keeps_none_values(self) -> None:
        """默认不跳 None(严格键集过滤)"""
        result = filter_whitelisted_fields({"a": 1, "b": None}, {"a", "b"})
        assert result == {"a": 1, "b": None}

    def test_empty_whitelist_returns_empty(self) -> None:
        """空白名单过滤为空 dict(含输入为空的退化口径)"""
        assert filter_whitelisted_fields({}, set()) == {}
        assert filter_whitelisted_fields({"a": 1}, set()) == {}
