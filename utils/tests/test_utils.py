"""utils 死代码收敛后余量自测（批次5 M-45 批A）——date_utils 整删、
string_utils 仅存 mask_phone_number，对应测试仅保留存活函数用例。"""

from utils.string_utils import mask_phone_number


class TestMaskPhoneNumber:
    def test_standard(self):
        assert mask_phone_number("13812345678") == "138****5678"

    def test_variable_length_asterisks(self):
        # 逐字等值语义：星号数 = len - 7，随长度变化（原 mask_sensitive_info 链路）
        assert mask_phone_number("138123456789") == "138*****6789"

    def test_short_string_all_masked(self):
        assert mask_phone_number("1381234") == "*******"

    def test_empty(self):
        assert mask_phone_number("") == ""
