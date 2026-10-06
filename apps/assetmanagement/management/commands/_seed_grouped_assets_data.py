"""
`seed_grouped_assets` 命令的**数据矩阵**（唯一事实源，DR-1）

命令逻辑在 `seed_grouped_assets.py`，测试也从此处导入同一份矩阵 ——
若测试另写一份期望值，就等于用「第二套组键语义」验证「第一套组键语义」，
数据一改测试就假绿或假红。故此处的 `ASSET_GROUPS` 是场景覆盖的唯一声明。

⚠️ **本文档（矩阵）与 `docs/资产分组展开表格-实施方案-v2.3.md` §阶段5 的一处刻意偏差**：
方案场景 5 写「组内 >100」，本矩阵取 **25** 条。理由：验证组内分页只需跨过
`DEFAULT_PAGE_SIZE = 20`（`core/constants.py`，唯一来源）即可出现第二页，
造 101 条与 25 条的**分页行为完全等价**，却让开发库多 4 倍数据、
清单页翻页要滚很久。25 是够用且不浪费的下界。

## 组矩阵设计

排序为 `-asset_count → contract_code ASC nulls_last → 其余组键`（决策 13）。
**`nulls_last` 只在 `asset_count` 相同的组之间才可见**，故哨兵组（无合同）
必须配一个条数相同的**有合同**组，否则场景 2 的「排序置末」根本无法肉眼验证 ——
这是 G4 与 G5 都取 4 条的原因，不是随手凑数。

| 组 | 场景 | 合同 | 名称 | 规格 | 品牌 | 条数 | 单价 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| G1 | 5 + 7 | C001 | 会议平板 | 75寸/4K | 华为 | 25 | 区间 |
| G4 | 3 + 2对照 | C002 | 显示器 | **null** | 戴尔 | 4 | 单值 |
| G5 | 2 + 3 | **null** | 旧设备 | **null** | **null** | 4 | 单值 |
| G2 | 6 + 8 | C001 | 笔记本电脑 | 14寸/i5 | 联想 | 3 | 单值 |
| G3 | 4 | C002 | 打印机 | A4/激光 | 惠普 | 1 | 单值 |
| G6 | 数量口径反例 | C002 | 服务器 | 2U/机架 | 浪潮 | 1 | 单值 |

排序后实际次序：G1(25) → G4(4,C002) → G5(4,null) → G2(3) → G3(1) → G6(1)。
G4 在 G5 之前即为 `nulls_last` 生效的直接证据。

**场景 3（null 独立成组）** 由 G4（规格 null）与 G5（规格+品牌双 null）覆盖，
且二者与 G1/G2 的同名字段非空组构成对照 —— 能验证「null 自成一组」而非被合并。

**场景 8 的反直觉之处**（G6）：`asset_purchase_number=5` 却只有 **1** 条记录。
这不是数据脏，而是刻意让「汇总 `asset_count`（条数口径）」与
「导出实物数量（`asset_purchase_number` 求和口径）」产生肉眼可见的差异。
若二者恒等，场景 8 要验证的数量语义链就退化成了无法证伪的同义反复。
对照组 G2 则是 3 条记录 × 每条 1 台（=3 台），符合「录入 N 台 → N 条明细」的契约。
"""

from typing import NamedTuple


class AssetTypeSpec(NamedTuple):
    """资产类型参照数据"""

    type_code: str
    type_name: str


class StorageSpec(NamedTuple):
    """仓库参照数据"""

    storage_code: str
    storage_name: str
    storage_type: str


class ContractSpec(NamedTuple):
    """合同参照数据"""

    contract_code: str
    contract_name: str
    contract_type: str


class AssetGroupSpec(NamedTuple):
    """一个分组（组键四元组 + 若干条资产）

    `prices` 长度为 1 时全组同价（单值态）；长度为 `count` 时逐条取用（区间态）。
    这样「同价」与「异价」在数据里显式可见，无需靠运行时推导。

    ⚠️ 两个字段**刻意避开 `tuple` 自带名**（`contract` / `count`）：NamedTuple 会为
    每个字段生成同名 `_tuplegetter` 描述符，`mypy --strict` 会把它们判为「覆写
    `tuple.count` 等既有方法」并报 assignment 冲突。故改为 `contract_code` /
    `total_count`。这是 mypy 的保守推断所致，非运行时错误（AR-1：按实测结论修正，不猜测）。
    """

    name: str
    spec: str | None
    brand: str | None
    contract_code: str | None
    asset_type: str
    storage: str
    total_count: int
    prices: tuple[str, ...]
    purchase_number: int = 1
    intent: str = ""


DEMO_PREFIX = "DEMO-"

# 参照数据：场景 1 要求 ≥2 合同 + ≥3 资产类型 + ≥2 仓库，此处 2 / 6 / 2 均已超出
ASSET_TYPES: tuple[AssetTypeSpec, ...] = (
    AssetTypeSpec("DEMO-T01", "会议平板"),
    AssetTypeSpec("DEMO-T02", "笔记本电脑"),
    AssetTypeSpec("DEMO-T03", "打印机"),
    AssetTypeSpec("DEMO-T04", "显示器"),
    AssetTypeSpec("DEMO-T05", "旧设备"),
    AssetTypeSpec("DEMO-T06", "服务器"),
)

STORAGES: tuple[StorageSpec, ...] = (
    StorageSpec("DEMO-S01", "主仓", "newasset"),
    StorageSpec("DEMO-S02", "备件仓", "newasset"),
)

CONTRACTS: tuple[ContractSpec, ...] = (
    ContractSpec("DEMO-C001", "2026年会议设备采购合同", "purchase"),
    ContractSpec("DEMO-C002", "2026年IT设备采购合同", "purchase"),
)

# G1 的 25 条刻意含 3 档不同单价，使 `price_display` 落在区间态且跨第二页分页
_G1_PRICES = ("8000.00", "12000.00", "15000.00")

ASSET_GROUPS: tuple[AssetGroupSpec, ...] = (
    AssetGroupSpec(
        name="会议平板",
        spec="75寸/4K",
        brand="华为",
        contract_code="DEMO-C001",
        asset_type="DEMO-T01",
        storage="DEMO-S01",
        total_count=25,
        prices=_G1_PRICES,
        intent="场景5组内分页(25>page_size 20)+场景7区间态",
    ),
    AssetGroupSpec(
        name="显示器",
        spec=None,
        brand="戴尔",
        contract_code="DEMO-C002",
        asset_type="DEMO-T04",
        storage="DEMO-S02",
        total_count=4,
        prices=("1500.00",),
        intent="场景3规格null独立成组+场景2排序对照(同条数有合同)",
    ),
    AssetGroupSpec(
        name="旧设备",
        spec=None,
        brand=None,
        contract_code=None,
        asset_type="DEMO-T05",
        storage="DEMO-S02",
        total_count=4,
        prices=("300.00",),
        intent="场景2哨兵组(无合同,排序置末)+场景3规格品牌双null",
    ),
    AssetGroupSpec(
        name="笔记本电脑",
        spec="14寸/i5",
        brand="联想",
        contract_code="DEMO-C001",
        asset_type="DEMO-T02",
        storage="DEMO-S01",
        total_count=3,
        prices=("4500.00",),
        intent="场景6单值态+场景8数量语义链(3条明细每条1台)",
    ),
    AssetGroupSpec(
        name="打印机",
        spec="A4/激光",
        brand="惠普",
        contract_code="DEMO-C002",
        asset_type="DEMO-T03",
        storage="DEMO-S01",
        total_count=1,
        prices=("1200.00",),
        intent="场景4 asset_count==1 自动展开",
    ),
    AssetGroupSpec(
        name="服务器",
        spec="2U/机架",
        brand="浪潮",
        contract_code="DEMO-C002",
        asset_type="DEMO-T06",
        storage="DEMO-S01",
        total_count=1,
        prices=("30000.00",),
        purchase_number=5,
        intent="数量口径反例:1条记录但实物5台,故 asset_count(1) != 导出实物数量(5)",
    ),
)

# 所有种子资产的 recordcode 前缀；`--reset` 按此精确定位，绝不误伤业务数据
ASSET_CODE_PREFIX = "DEMO-A"


def total_asset_count() -> int:
    """矩阵应有的资产总条数（测试与命令输出的交叉校验基准）"""
    return sum(group.total_count for group in ASSET_GROUPS)
