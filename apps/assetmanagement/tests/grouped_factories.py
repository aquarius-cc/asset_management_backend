"""
分组端点测试的共享数据工厂

`grouped`（汇总）与 `group_children`（明细）两组测试需要**完全相同**的造数逻辑 ——
组键四元组、null 组键元素、RBAC 行级隔离三处一旦两边不一致，
就会造出「明细数 ≠ 汇总数」的假绿数据（B4 的 I-1 用例尤其敏感）。

故工厂唯一实现于本模块，两个测试文件均从此导入（DR-1 / DR-4）。
函数名保留前导下划线：它们是测试内部助手，不是对外 API。

⚠️ `python_files = test_*.py`（pytest.ini:3），本模块不会被收集为测试文件。
"""

import json

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee


def _make_dept(code: str, name: str) -> Department:
    return Department.objects.create(department_code=code, department_name=name)


def _make_employee(dept: Department, jobcode: str, name: str) -> Employee:
    return Employee.objects.create(
        employee_jobcode=jobcode,
        employee_name=name,
        employee_department=dept,
        employee_phone=f"13{abs(sum(map(ord, jobcode))) % 100000000:08d}",
        role="regular_user",
    )


def _make_asset(
    storage: Storage,
    asset_type: AssetType,
    manager: Employee | None,
    code: str,
    *,
    name: str = "笔记本电脑",
    spec: str | None = "14寸/i5",
    brand: str | None = "联想",
    price: float | None = 4500.00,
    contract: Contract | None = None,
    status: str = "in_store",
) -> Asset:
    return Asset.objects.create(
        asset_code=code,
        asset_name=name,
        asset_purchase_price=price,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_specification=spec,
        asset_brand=brand,
        asset_contract_recordcode=contract,
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_manager_recordcode=manager,
        asset_current_status=status,
    )


def _make_contract(code: str) -> Contract:
    return Contract.objects.create(
        contract_code=code,
        contract_name=f"合同{code}",
        contract_amount=10000.00,
        contract_status="purchasing",
        contract_type="service",
        contract_start_date="2024-01-01",
        contract_end_date="2025-01-01",
    )


def _cold(user: AuthUser) -> None:
    """清掉 RBAC 的请求级缓存, 使每次查询数测量都从冷路径开始

    `get_employee_for_user`(core/department_scope.py:26)把 Employee 缓存在
    `user._rbac_employee` 上。测试里 force_authenticate 复用同一实例, 不清缓存
    会让第二次测量凭空少一次查询, 把「无 N+1」误判成「有缓存」。
    """
    user.__dict__.pop("_rbac_employee", None)


def group_key_json(contract_code: str | None, name: str, spec: str | None, brand: str | None) -> str:
    """按 B4 契约拼 `group_key` 查询串

        `ensure_ascii=False` 与生产的编码侧一致：中文不必转义成 `\\uXXXX`，
        两端都能解析，但保持一致可让测试日志可读、便于与抓包结果比对。
    `ensure_ascii` 不影响解析结果，故不影响「原样回传」的正确性。
    """
    return json.dumps([contract_code, name, spec, brand], ensure_ascii=False)
