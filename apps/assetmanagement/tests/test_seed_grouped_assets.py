"""`seed_grouped_assets` 命令测试（v2.3 §阶段5）

验证命令的三项**契约性**行为，而非「数据是否写进去了」这种会随矩阵调整而失效的断言：

1. **幂等**：重复执行不重复插入（二次执行新建数为 0）
2. **`--reset` 精确性**：按 `DEMO-` 前缀软删除，**不误伤业务数据**
3. **`--dry-run` 无副作用**：只打印不落库

另有一类测试**从矩阵反推期望**（`TestMatrixContract`）——它不硬编码「6 组 38 条」
这类会随矩阵调整而失效的数字，而是从 `_seed_grouped_assets_data` 推导，
使矩阵改动必须同步更新断言，而不能悄悄破坏 §阶段5 的场景覆盖。

⚠️ 数据矩阵的唯一事实源在 `_seed_grouped_assets_data.py`，本文件**不复写**任何组键期望值
（DR-1）。若测试另写一份期望，就等于用第二套组键语义验证第一套，数据一改即假绿。
"""

from io import StringIO
from typing import Any

import pytest
from django.core.management import call_command
from django.db.models import Sum

from apps.assetmanagement.management.commands._seed_grouped_assets_data import (
    ASSET_CODE_PREFIX,
    ASSET_GROUPS,
    ASSET_TYPES,
    CONTRACTS,
    DEMO_PREFIX,
    STORAGES,
    total_asset_count,
)
from apps.assetmanagement.management.commands.seed_grouped_assets import Command
from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.usermanagement.models import Department, Employee


@pytest.fixture
def business_noise(db: Any) -> None:
    """非演示数据（验证 `--reset` 绝不误伤）

    代码刻意**不用** `DEMO-` 前缀，且类型/仓库/合同与演示数据同名不同码 ——
    若 `--reset` 的前缀过滤写错成「按名称删」，这些行就会一起消失。
    """
    AssetType.objects.create(type_code="REAL-T01", type_name="真实类型")
    Storage.objects.create(storage_code="REAL-S01", storage_name="真实仓", storage_address="真实地址")
    Contract.objects.create(contract_code="REAL-C01", contract_name="真实合同")
    Department.objects.create(
        department_code="REAL-D01", department_name="真实部门", department_information="真实信息员"
    )
    Employee.objects.create(
        employee_jobcode="REAL-E01",
        employee_name="真实员工",
        employee_phone="13900000002",
        employee_location="真实地点",
        employee_department=Department.objects.get(department_code="REAL-D01"),
    )


def _run(*args: str) -> str:
    """执行命令并返回输出（供脱敏断言与计数断言用）"""
    out = StringIO()
    call_command(Command(), *args, stdout=out)
    return out.getvalue()


class TestIdempotency:
    def test_first_run_creates_matrix(self, db: Any) -> None:
        _run()

        assert Asset.objects.count() == total_asset_count()
        assert AssetType.objects.count() == len(ASSET_TYPES)
        assert Storage.objects.count() == len(STORAGES)
        assert Contract.objects.count() == len(CONTRACTS)

    def test_second_run_creates_nothing(self, db: Any) -> None:
        """幂等：第二次执行不重复插入、不报错

        这是 `init_production_data` 已有测试的同款断言模式（幂等是该目录的既有约定）。
        """
        _run()
        before = Asset.objects.count()

        output = _run()

        assert Asset.objects.count() == before
        assert f"{before} 条新建" not in output  # 二次输出应为 0 条新建
        assert "0 条新建" in output

    def test_repeated_runs_keep_counts_stable(self, db: Any) -> None:
        """连续三次执行，行数恒定（排除「第三次又插一遍」这类累积型幂等破窗）"""
        _run()
        first = Asset.objects.count()
        _run()
        _run()

        assert Asset.objects.count() == first


class TestResetPrecision:
    def test_reset_soft_deletes_demo_rows(self, db: Any) -> None:
        """`--reset` 后演示数据软删除并重建，故总行数不变、活跃行仍为矩阵规模"""
        _run()
        before = Asset.objects.count()

        _run("--reset")

        assert Asset.objects.count() == before  # 软删除后重建，活跃行数不变
        # all_objects 可见软删除行，说明确实走的是软删除而非硬删
        assert Asset.all_objects.filter(asset_code__startswith=ASSET_CODE_PREFIX, is_deleted=True).exists()

    def test_reset_does_not_touch_business_data(self, db: Any, business_noise: None) -> None:
        """`--reset` 绝不误伤非演示数据（防前缀过滤写错成按名称删除）"""
        _run()

        _run("--reset")

        assert AssetType.objects.filter(type_code="REAL-T01").exists()
        assert Storage.objects.filter(storage_code="REAL-S01").exists()
        assert Contract.objects.filter(contract_code="REAL-C01").exists()
        assert Department.objects.filter(department_code="REAL-D01").exists()
        assert Employee.objects.filter(employee_jobcode__startswith="REAL-").exists()

    def test_reset_is_idempotent(self, db: Any) -> None:
        """连续两次 `--reset` 不报错（软删除后可重复执行）"""
        _run()
        _run("--reset")

        _run("--reset")

        assert Asset.objects.count() == total_asset_count()

    def test_reset_soft_deletes_in_dependency_order(self, db: Any) -> None:
        """`_reset` 的删除顺序：先 Asset 后 AssetType

        AssetType 被 Asset 以 `PROTECT` 引用，若先删类型会撞外键保护。
        断言执行后类型仍为软删除（而非因顺序错误抛 IntegrityError 被回滚）。
        """
        _run()

        output = _run("--reset")

        assert "am_asset: 软删除" in output
        assert AssetType.all_objects.filter(type_code__startswith=DEMO_PREFIX, is_deleted=True).exists()


class TestDryRun:
    def test_dry_run_writes_nothing(self, db: Any) -> None:
        _run("--dry-run")

        assert Asset.objects.count() == 0
        assert AssetType.objects.count() == 0
        assert Contract.objects.count() == 0

    def test_dry_run_output_lists_planned_rows(self, db: Any) -> None:
        """`--dry-run` 仍须列出将建内容（否则「无副作用」就变成了「无从预览」）"""
        output = _run("--dry-run")

        assert "将创建" in output
        assert f"{total_asset_count()} 条新建" in output

    def test_dry_run_marks_itself(self, db: Any) -> None:
        """输出须显式标注 dry-run，避免有人把预览误当真实结果"""
        assert "dry-run" in _run("--dry-run")


class TestOutputHygiene:
    """输出脱敏（OC-3 精神：即便演示数据也不打印字段值）"""

    def test_output_has_no_field_values(self, db: Any) -> None:
        """输出只给计数，不给手机号等字段值

        命令输出可能进 CI 日志或被截图，故只允许出现计数与业务键。
        """
        output = _run()

        assert "13800000001" not in output  # 演示员工手机号
        assert "4500.00" not in output  # 单条价格（分组汇总里才有意义）
        assert "30.00" not in output  # 区间价下限

    def test_output_points_at_endpoints(self, db: Any) -> None:
        """输出须指明验证入口（否则用户不知道下一步看哪里）"""
        output = _run()

        assert "/api/v1/assets/grouped/" in output
        assert "/api/v1/assets/group_children/" in output


class TestMatrixContract:
    """从矩阵反推的契约断言（不硬编码会漂移的数字）"""

    def test_reference_data_meets_stage5_scenario_1(self) -> None:
        """场景 1：≥2 合同 + ≥3 资产类型 + ≥2 仓库"""
        assert len(CONTRACTS) >= 2
        assert len(ASSET_TYPES) >= 3
        assert len(STORAGES) >= 2

    def test_matrix_has_sentinel_group_with_equal_count_sibling(self) -> None:
        """场景 2 的**可验证性**前提：哨兵组必须有同条数的有合同组

        排序第一关键字是 `-asset_count`，`nulls_last` 只在条数相同的组之间可见。
        若哨兵组是唯一的该条数组，「排序置末」就无法与「条数不同导致的靠后」区分开，
        场景 2 的验证目标将无法被肉眼证伪。此断言把该设计前提固化为契约。
        """
        sentinel_groups = [g for g in ASSET_GROUPS if g.contract_code is None]
        assert sentinel_groups, "矩阵缺少无合同哨兵组（场景 2）"

        sentinel_counts = {g.total_count for g in sentinel_groups}
        contract_counts = {g.total_count for g in ASSET_GROUPS if g.contract_code is not None}
        assert sentinel_counts & contract_counts, "哨兵组无同条数的有合同组，场景 2 的排序置末无法验证"

    def test_matrix_covers_null_group_key_combinations(self) -> None:
        """场景 3：`group_key` 的 null 元素须有独立成组的样本

        需同时覆盖「仅规格 null」与「规格+品牌双 null」，
        才能验证 null 自成一组而不被合并（R-1 核心）。
        """
        null_spec = [g for g in ASSET_GROUPS if g.spec is None and g.brand is not None]
        null_both = [g for g in ASSET_GROUPS if g.spec is None and g.brand is None]
        assert null_spec, "矩阵缺少「规格 null + 品牌非 null」样本（场景 3）"
        assert null_both, "矩阵缺少「规格+品牌双 null」样本（场景 3）"

    def test_matrix_covers_single_and_multi_count_groups(self) -> None:
        """场景 4：`asset_count == 1` 的组存在（自动展开的前提）"""
        assert any(g.total_count == 1 for g in ASSET_GROUPS), "矩阵缺少单条组（场景 4）"

    def test_matrix_has_group_larger_than_page_size(self) -> None:
        """场景 5：存在条数超过 `DEFAULT_PAGE_SIZE` 的组（组内分页的前提）

        取 `core.constants.DEFAULT_PAGE_SIZE` 而非硬编码 20 —— 后者是唯一来源，
        改分页默认值时本断言自动跟随，不会静默失效。
        """
        from core.constants import DEFAULT_PAGE_SIZE

        assert any(g.total_count > DEFAULT_PAGE_SIZE for g in ASSET_GROUPS), (
            f"矩阵无组超过 DEFAULT_PAGE_SIZE={DEFAULT_PAGE_SIZE}，组内分页（场景 5）无法验证"
        )

    def test_matrix_covers_single_and_range_price_groups(self) -> None:
        """场景 6/7：单值态与区间态各至少一组"""
        assert any(len(g.prices) == 1 for g in ASSET_GROUPS), "矩阵缺少单值态组（场景 6）"
        assert any(len(g.prices) > 1 for g in ASSET_GROUPS), "矩阵缺少区间态组（场景 7）"

    def test_matrix_covers_quantity_semantics_contrast(self) -> None:
        """场景 8：同时存在「N 条明细每条 1 台」与「1 条明细 N 台」

        若二者恒等，场景 8 要验证的数量语义链就退化成无法证伪的同义反复。
        """
        assert any(g.purchase_number == 1 and g.total_count > 1 for g in ASSET_GROUPS), (
            "矩阵缺少「多条明细每条 1 台」样本，无法对比两个数量口径（场景 8）"
        )
        assert any(g.purchase_number > 1 for g in ASSET_GROUPS), (
            "矩阵缺少「单条明细多台」样本，asset_count 与导出实物数量的差异无法肉眼验证（场景 8）"
        )


class TestSeededDataSemantics:
    """落库后的实际语义（验证矩阵意图确实体现在数据里）"""

    @pytest.fixture
    def seeded(self, db: Any) -> None:
        _run()

    def test_physical_quantity_differs_from_row_count(self, seeded: None) -> None:
        """核心语义：汇总条数 ≠ 实物台数之和

        这是 §阶段5 场景 8 的真正验证点。若某天 `asset_count` 被改成
        `Sum("asset_purchase_number")`，本断言立刻失败。
        """
        row_count = Asset.objects.count()
        physical_total = Asset.objects.aggregate(total=Sum("asset_purchase_number"))["total"]

        assert physical_total > row_count, "矩阵未制造两口径差异，场景 8 的语义链无法证伪"

    def test_no_contract_assets_exist(self, seeded: None) -> None:
        assert Asset.objects.filter(asset_contract_recordcode__isnull=True).exists()

    def test_null_specification_assets_exist(self, seeded: None) -> None:
        assert Asset.objects.filter(asset_specification__isnull=True).exists()

    def test_null_brand_assets_exist(self, seeded: None) -> None:
        assert Asset.objects.filter(asset_brand__isnull=True).exists()

    def test_no_login_account_is_created(self, seeded: None) -> None:
        """不造 AuthUser —— 演示数据不该凭空产生可登录账号（SC-1 边界）"""
        from apps.authusermanagement.models import AuthUser

        assert not AuthUser.objects.filter(auth_username__startswith=DEMO_PREFIX).exists()
        assert not AuthUser.objects.filter(auth_phone__startswith="138").exists()

    def test_asset_codes_are_prefixed(self, seeded: None) -> None:
        """全部资产码带 DEMO 前缀（`--reset` 的精确定位依据）"""
        for code in Asset.objects.values_list("asset_code", flat=True):
            assert code.startswith(ASSET_CODE_PREFIX)
