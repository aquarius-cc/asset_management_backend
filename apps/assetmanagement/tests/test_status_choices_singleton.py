"""
资产状态枚举单一来源回归护栏(审查 #36 / DR-1)

权威源 = `Asset.ASSET_STATUS_CHOICES`(apps/assetmanagement/models/asset.py:109)。
防止重复定义被重新引入 core/constants.py 或消费方自行复制。
"""

from pathlib import Path


_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def _read(relative: str) -> str:
    return (_BACKEND_ROOT / relative).read_text(encoding="utf-8")


class TestAssetStatusChoicesSingleSource:
    """资产状态枚举仅允许 Model 侧唯一实现(DR-1)"""

    def test_core_constants_does_not_redefine(self):
        src = _read("core/constants.py")
        assert "ASSET_STATUS_CHOICES" not in src, (
            "core/constants.py 不得重复定义 ASSET_STATUS_CHOICES(权威源在 Asset 模型)"
        )

    def test_asset_view_uses_model_choices(self):
        src = _read("apps/assetmanagement/views/asset_view.py")
        assert "ASSET_STATUS_MAP = dict(Asset.ASSET_STATUS_CHOICES)" in src, (
            "asset_view.py 的 ASSET_STATUS_MAP 必须直接引用 Asset.ASSET_STATUS_CHOICES"
        )

    def test_asset_view_no_core_constants_status_import(self):
        src = _read("apps/assetmanagement/views/asset_view.py")
        assert "from core.constants import ASSET_STATUS_CHOICES" not in src, (
            "asset_view.py 禁止从 core.constants 导入重复的状态枚举"
        )
