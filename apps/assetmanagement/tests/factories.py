"""factory_boy 工厂（MA-23 包 1a）：AssetType / Storage / Contract / Asset。

设计约束（MA-23 v1.1 拍板）：
- 默认值全静态（禁 Faker 随机），保证用例确定性；
- **仅对 NOT NULL 外键用 ``SubFactory``**（``Asset.asset_type_recordcode`` 是必填，
  不建则 IntegrityError）；其余可空外键一律默认 ``None``，不自动多造关联对象 ——
  这是「存量用例零改动」的等价性前提（``asset_contract_recordcode`` /
  ``asset_storage_recordcode`` / ``asset_entry_person_recordcode`` /
  ``asset_applicant_recordcode`` / ``asset_manager_recordcode`` 均 ``null=True``）；
- 状态/类型字段用模型 ``TextChoices`` 常量，不写字面量。

⚠️ ``python_files = test_*.py``（pytest.ini:3），本模块不会被收集为测试文件。
"""

from __future__ import annotations

from datetime import date

import factory
from factory.django import DjangoModelFactory

from apps.assetmanagement.models import Asset, AssetType, Contract, Storage


class AssetTypeFactory(DjangoModelFactory[AssetType]):
    """资产类型工厂（默认顶级：parent/path 走模型默认）。"""

    class Meta:
        model = AssetType

    type_code = factory.Sequence(lambda n: f"ATFACT{n:04d}")
    type_name = factory.Sequence(lambda n: f"工厂类型{n:04d}")


class StorageFactory(DjangoModelFactory[Storage]):
    """仓库工厂。

    仅填模型必填字段（``storage_code`` / ``storage_name`` / ``storage_address``）；
    ``storage_location`` / ``storage_capacity`` / ``storage_manager`` 是可空字段，
    **不设工厂默认值** —— 保持与模型默认（``None``）一致，避免「裸建仓库」时
    悄悄多出位置/容量数据（存量 unregisteredasset 的 storage 夹具即裸建）。
    """

    class Meta:
        model = Storage

    storage_code = factory.Sequence(lambda n: f"SFACT{n:04d}")
    storage_name = factory.Sequence(lambda n: f"工厂仓库{n:04d}")
    storage_address = "测试地点"


class ContractFactory(DjangoModelFactory[Contract]):
    """合同工厂。

    ``contract_type`` / ``contract_status`` 是必填（模型无默认），给静态默认；
    ``contract_start_date`` / ``contract_end_date`` 可空但合同业务上必须成对给出，
    沿用 assetmanagement contract 夹具的固定区间。
    """

    class Meta:
        model = Contract

    contract_code = factory.Sequence(lambda n: f"CFACT{n:04d}")
    contract_name = factory.Sequence(lambda n: f"工厂合同{n:04d}")
    contract_amount = 10000.00
    contract_status = Contract.ContractStatus.PURCHASING
    contract_type = Contract.ContractType.SERVICE
    contract_start_date = date(2024, 1, 1)
    contract_end_date = date(2025, 1, 1)


class AssetFactory(DjangoModelFactory[Asset]):
    """资产工厂。

    ``asset_type_recordcode`` 必填 → ``SubFactory``；其余关联默认 ``None``
    （含 ``asset_storage_recordcode`` —— 模型 ``null=True``，不自动建仓库）。
    需要仓库/入库人/合同归属时由调用方显式传入。
    """

    class Meta:
        model = Asset

    asset_code = factory.Sequence(lambda n: f"AFACT{n:06d}")
    asset_name = factory.Sequence(lambda n: f"工厂资产{n:04d}")
    asset_purchase_price = 1000.00
    asset_purchase_date = date(2024, 1, 1)
    asset_entry_date = date(2024, 1, 15)
    asset_type_recordcode = factory.SubFactory(AssetTypeFactory)
    asset_storage_recordcode = None
    asset_entry_person_recordcode = None
    asset_applicant_recordcode = None
    asset_manager_recordcode = None
    asset_contract_recordcode = None
    asset_current_status = Asset.AssetStatus.IN_STORE
