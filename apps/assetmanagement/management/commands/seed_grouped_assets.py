"""
`seed_grouped_assets` — 分组展开表格的**手工验证用演示数据**

v2.3 §阶段5：`am_asset_type = 0`（无参照数据）时分组功能无法手工验证 ——
没有合同可分、没有类型可筛、null 品牌/规格组合造不出。本命令一次性铺好这些前提，
使 `grouped` / `group_children` 两个端点可被人在浏览器里直接操作验证。

## 为什么不是 `loaddata` fixture

`init_production_data`（RBAC 初始化）用的是「模块级常量 + `handle()` 分步 + 先查后写」
的 management command 模式，本命令照抄同一模式以保持仓库风格一致（DR-1）。
fixture 需要手写 JSON/YAML，38 条资产无法阅读与校对，且重复执行不幂等。

## ⚠️ 绝不自动执行

`docker-entrypoint.sh` 会调 `init_production_data`，本命令**故意不在任何自动通道中**
—— 演示数据不该出现在生产库。故无 `--skip-admin` 之类的开关，也不进 entrypoint。

## 幂等与开关

- **幂等**：重复执行不重复插入、不报错（每个对象按业务键先查后写）。
- `--dry-run`：只打印将要写入的内容，不落库。
- `--reset`：按 `DEMO-` 前缀软删除（`is_deleted=True`）本命令造的数据，
  再重新铺一遍。用软删除而非硬删：条件唯一约束 `*_not_deleted` 会被 `is_deleted`
  一并释放，故二次执行仍可正常重建；而硬删在有业务数据引用时会撞 PROTECT 外键。

## 数据矩阵

见 `_seed_grouped_assets_data.py`（唯一事实源，测试也从那里导入同一份）。
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.db.models import Model

from apps.assetmanagement.management.commands._seed_grouped_assets_data import (
    ASSET_CODE_PREFIX,
    ASSET_GROUPS,
    ASSET_TYPES,
    CONTRACTS,
    DEMO_PREFIX,
    STORAGES,
    AssetGroupSpec,
    total_asset_count,
)
from apps.assetmanagement.models import Asset, AssetType, Contract, Storage
from apps.usermanagement.models import Department, Employee


# 资产采购/入库日期：固定值而非 today()，使同一命令两次执行产出完全一致（幂等可校对）
PURCHASE_DATE = "2026-01-15"
ENTRY_DATE = "2026-02-01"

DEMO_DEPARTMENT = ("DEMO-D01", "演示部门", "演示信息员")
DEMO_EMPLOYEE = ("DEMO-E01", "演示资产管理员", "13800000001", "总部大楼 A 座 3 层")

# 每个模型的业务定位键（幂等查询用）—— 显式表而非 `model._meta` 推断，避免隐式约定
LOOKUP_KEY: dict[type[Any], str] = {
    AssetType: "type_code",
    Storage: "storage_code",
    Contract: "contract_code",
    Department: "department_code",
    Employee: "employee_jobcode",
    Asset: "asset_code",
}


class Command(BaseCommand):
    help = "铺入分组展开表格的演示数据（幂等可重复执行；绝不自动执行）"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="仅打印将要执行的操作，不实际写入数据库",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="先按 DEMO- 前缀软删除既有演示数据，再重新铺入",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run: bool = options["dry_run"]
        reset: bool = options["reset"]

        self.stdout.write(self.style.SUCCESS("=" * 56))
        self.stdout.write(self.style.SUCCESS(" 分组展开表格 · 演示数据"))
        self.stdout.write(self.style.SUCCESS("=" * 56))
        if dry_run:
            self.stdout.write(self.style.WARNING(" [dry-run] 不会写入数据库"))

        if reset:
            self._reset()

        with transaction.atomic():
            stats = self._seed_assets(self._seed_reference_data(dry_run), dry_run)

        self._report(stats, dry_run)

    def _seed_reference_data(self, dry_run: bool) -> dict[str, Model]:
        """铺入参照数据（类型/仓库/合同/部门/员工），返回按业务键索引的对象表

        资产行需要引用这些对象，故必须先建。此处刻意**不建 AuthUser** ——
        演示数据不该凭空产生一个能登录的账号（SC-1 边界：凭据不入种子数据）。
        演示账号由使用者自己的 `init_production_data` 或 `createsuperuser` 提供。
        """
        self.stdout.write("\n[1/3] 参照数据...")
        registry: dict[str, Model] = {}
        # 三个循环的变量名各自独立（`type_spec`/`storage_spec`/`contract_spec`）而非复用 `spec`：
        # 复用会让 mypy 把首个循环的 AssetTypeSpec 推断硬套到后两个循环上（--strict 下报
        # assignment 冲突与 attr-defined）。分名即可让各类型独立推导（AR-1 按实测修）。
        for type_spec in ASSET_TYPES:
            registry[type_spec.type_code], _ = self._get_or_create(
                AssetType,
                {"type_code": type_spec.type_code, "type_name": type_spec.type_name},
                f"资产类型 {type_spec.type_name}",
                dry_run,
            )
        for storage_spec in STORAGES:
            registry[storage_spec.storage_code], _ = self._get_or_create(
                Storage,
                {
                    "storage_code": storage_spec.storage_code,
                    "storage_name": storage_spec.storage_name,
                    "storage_address": "演示地址",
                    "storage_type": storage_spec.storage_type,
                },
                f"仓库 {storage_spec.storage_name}",
                dry_run,
            )
        for contract_spec in CONTRACTS:
            registry[contract_spec.contract_code], _ = self._get_or_create(
                Contract,
                {
                    "contract_code": contract_spec.contract_code,
                    "contract_name": contract_spec.contract_name,
                },
                f"合同 {contract_spec.contract_code}",
                dry_run,
            )
        registry.update(self._seed_people(dry_run))
        return registry

    def _seed_people(self, dry_run: bool) -> dict[str, Model]:
        """演示部门与员工（资产的管理员/录入人需引用 Employee）

        `department_information` 与 `employee_location` 都是**无 default 的必填**字段，
        现有测试 fixture 靠空串隐式通过；此处显式填写，避免种子数据留下「靠巧合过校验」的脏点。
        """
        dept, _ = self._get_or_create(
            Department,
            {
                "department_code": DEMO_DEPARTMENT[0],
                "department_name": DEMO_DEPARTMENT[1],
                "department_information": DEMO_DEPARTMENT[2],
            },
            f"部门 {DEMO_DEPARTMENT[1]}",
            dry_run,
        )
        employee, _ = self._get_or_create(
            Employee,
            {
                "employee_jobcode": DEMO_EMPLOYEE[0],
                "employee_name": DEMO_EMPLOYEE[1],
                "employee_phone": DEMO_EMPLOYEE[2],
                "employee_location": DEMO_EMPLOYEE[3],
                "employee_department": dept,
            },
            f"员工 {DEMO_EMPLOYEE[1]}",
            dry_run,
        )
        return {"__dept__": dept, "__employee__": employee}

    def _seed_assets(self, registry: dict[str, Model], dry_run: bool) -> dict[str, int]:
        """铺入资产行，返回统计计数"""
        self.stdout.write("\n[2/3] 资产数据...")
        created = 0
        counter = 0
        for group in ASSET_GROUPS:
            created += self._seed_group(group, registry, dry_run, counter)
            counter += group.total_count
        return {"资产": created}

    def _seed_group(self, group: AssetGroupSpec, registry: dict[str, Model], dry_run: bool, offset: int) -> int:
        """铺入一个分组的所有资产行，返回新建条数

        `prices` 长度为 1 时全组同价；否则逐条取用（制造区间态）。
        """
        created = 0
        for index in range(group.total_count):
            price = group.prices[index % len(group.prices)]
            code = f"{ASSET_CODE_PREFIX}{offset + index + 1:03d}"
            label = f"{group.name} #{offset + index + 1}"
            _, is_created = self._get_or_create(
                Asset,
                {
                    "asset_code": code,
                    "asset_name": group.name,
                    "asset_purchase_price": price,
                    "asset_purchase_number": group.purchase_number,
                    "asset_purchase_date": PURCHASE_DATE,
                    "asset_entry_date": ENTRY_DATE,
                    "asset_specification": group.spec,
                    "asset_brand": group.brand,
                    "asset_unit": "台",
                    # 哨兵组（contract_code=None）故用 .get 而非 []：直接索引会 KeyError。
                    # 类型标注为 str | None，故此处显式收窄避免 dict[str, Model] 索引告警。
                    "asset_contract_recordcode": (
                        registry[group.contract_code] if group.contract_code is not None else None
                    ),
                    "asset_type_recordcode": registry[group.asset_type],
                    "asset_storage_recordcode": registry[group.storage],
                    "asset_manager_recordcode": registry["__employee__"],
                    "asset_entry_person_recordcode": registry["__employee__"],
                    "asset_current_status": "in_store",
                },
                label,
                dry_run,
            )
            created += int(is_created)
        self.stdout.write(f"  · {group.name}: {group.total_count} 条 — {group.intent}")
        return created

    def _get_or_create(self, model: type[Any], fields: dict[str, Any], label: str, dry_run: bool) -> tuple[Model, bool]:
        """按业务键先查后写（幂等唯一入口），返回 `(对象, 是否新建)`

        刻意用 `filter().first() + create()` 而非 `get_or_create`：
        后者会把 `defaults` 之外的 `fields` 当作查询条件做 `SELECT ... WHERE`，
        但本命令的查询键与写入字段并非一一对应（如 `asset_code` 需跨表定位，
        而 `asset_name` 又不该参与定位），显式先查更易读、也便于 `--dry-run` 复用同一分支。

        ⚠️ 必须返回 `(对象, 布尔)` 而非裸对象：`--dry-run` 下返回的是**未持久化实例**，
        若调用方写 `created += self._get_or_create(...)` 就会拿实例与 int 相加，
        抛 `TypeError`（本命令首次 dry-run 即命中该 bug，见 §实测）。
        把「是否新建」作为独立返回值，调用方无需 `isinstance` 猜测。
        """
        # ⚠️ `model` 标注为 `type[Any]` 而非 `type[Model]`：`type[Model]` 上的
        # `objects` 在 django-stubs 下不可见（`objects` 是 `SoftDeleteManager`，
        # 非 `Model` 的声明成员），--strict 会报 attr-defined。此处按项目既有惯例
        # （`services/asset_lifecycle_mixin.py:27` 的 `record_model: type[Any]`）处理，
        # 保留运行时软删除过滤（`objects` 即 `SoftDeleteManager`）。AR-1：按实测修。
        existing = model.objects.filter(**{LOOKUP_KEY[model]: fields[LOOKUP_KEY[model]]}).first()
        if existing is not None:
            self.stdout.write(f"  ✓ {label} — 已存在")
            return existing, False
        if dry_run:
            self.stdout.write(f"  ○ {label} — 将创建")
            return model(**fields), True
        created = model.objects.create(**fields)
        self.stdout.write(f"  + {label} — 已创建")
        return created, True

    def _reset(self) -> None:
        """按 `DEMO-` 前缀软删除既有演示数据

        顺序有讲究：先删 `Asset`（引用类型/仓库），最后删 `AssetType`（被 Asset PROTECT）。
        用软删除（`is_deleted=True`）而非硬删：条件唯一约束 `*_not_deleted` 会随
        `is_deleted` 释放，故二次 `--reset` + 铺入仍可正常重建；硬删则会在有业务引用时
        撞 PROTECT 外键而失败。
        """
        self.stdout.write(self.style.WARNING("\n[0/3] 清理既有演示数据..."))
        targets: tuple[tuple[type[Any], str], ...] = (
            (Asset, "asset_code__startswith"),
            (Storage, "storage_code__startswith"),
            (Contract, "contract_code__startswith"),
            (AssetType, "type_code__startswith"),
            (Employee, "employee_jobcode__startswith"),
            (Department, "department_code__startswith"),
        )
        for model, lookup in targets:
            count = model.objects.filter(**{lookup: DEMO_PREFIX}).update(is_deleted=True)
            self.stdout.write(f"  - {model._meta.db_table}: 软删除 {count} 行")

    def _report(self, stats: dict[str, int], dry_run: bool) -> None:
        """汇总输出

        刻意只打印**计数**，不打印任何字段值：资产价格、员工手机号等即便在演示库里
        也不该出现在命令输出（可能进 CI 日志或用户截图）。OC-3 的脱敏精神。
        """
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("-" * 56))
        self.stdout.write(self.style.SUCCESS(" 演示数据就绪:" if not dry_run else " [dry-run] 将铺入:"))
        for label, count in stats.items():
            self.stdout.write(f"  {label}: {count} 条新建")
        self.stdout.write(f"  矩阵应有资产总数: {total_asset_count()} 条")
        self.stdout.write(f"  分组数: {len(ASSET_GROUPS)} 组（无合同哨兵组恒排末）")
        self.stdout.write("")
        self.stdout.write(" 验证入口:")
        self.stdout.write("   GET /api/v1/assets/grouped/")
        self.stdout.write("   GET /api/v1/assets/group_children/?group_key=<上一步返回的 group_key>")
        self.stdout.write(self.style.SUCCESS("=" * 56))
