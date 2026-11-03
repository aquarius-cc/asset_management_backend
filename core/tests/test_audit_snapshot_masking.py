"""OP-05 审计快照脱敏单元测试(OC-3 唯一实现, DR-1/DR-4)

mask_sensitive_snapshot: 递归脱敏、幂等、未登记字段原样透传、None/空串透传、非 str 不崩。
"""

from core.audit_sanitizer import mask_sensitive_snapshot
from utils.string_utils import mask_phone_number


class TestMaskSensitiveSnapshot:
    def test_top_level_phone_masked(self):
        data = {"employee_phone": "13812345678", "employee_name": "张三"}
        result = mask_sensitive_snapshot(data)

        assert result["employee_phone"] == "138****5678"
        assert result["employee_name"] == "张三"

    def test_nested_dict_masked(self):
        data = {"before": {"employee_phone": "13812345678"}}
        result = mask_sensitive_snapshot(data)

        assert result["before"]["employee_phone"] == "138****5678"

    def test_unregistered_field_passthrough(self):
        data = {"employee_name": "13812345678", "other_phone": "13812345678"}
        result = mask_sensitive_snapshot(data)

        # 仅登记字段名脱敏, 未登记字段(即使值形似手机号)原样透传
        assert result == data

    def test_none_and_empty_passthrough(self):
        assert mask_sensitive_snapshot(None) is None
        assert mask_sensitive_snapshot({}) == {}
        assert mask_sensitive_snapshot({"employee_phone": ""}) == {"employee_phone": ""}
        assert mask_sensitive_snapshot({"employee_phone": None}) == {"employee_phone": None}

    def test_non_str_value_not_crash(self):
        data = {"employee_phone": 13812345678, "count": 3}
        result = mask_sensitive_snapshot(data)

        assert result == data

    def test_idempotent(self):
        once = mask_sensitive_snapshot({"employee_phone": "13812345678"})
        twice = mask_sensitive_snapshot(once)

        # 幂等: 已脱敏值再脱敏结果不变(掩码值 12 位, 前 3 后 4 重新掩码结果相同)
        assert twice == once
        assert mask_phone_number("138****5678") == "138****5678"
