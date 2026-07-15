# d:\CodeDemo\Python\asset_management_backend\apps\assetmanagement\tests\test_services.py
"""
资产服务测试
"""

from datetime import date

import pytest

from apps.assetmanagement.services import AssetService, OutAssetService, RecycleAssetService


@pytest.mark.django_db
class TestAssetService:
    """
    资产服务测试
    """

    def test_create_asset(self, storage, asset_type):
        """
        测试创建资产服务

        【AGENTS 规范】asset_code 由后端自动生成，返回 List[Asset]。
        验证返回列表格式和自动生成的编码格式。
        """
        asset_data = {
            "asset_name": "新资产",
            "asset_purchase_price": 2000.00,
            "asset_purchase_date": "2024-01-01",
            "asset_entry_date": "2024-01-15",
            "asset_storage_recordcode": storage,
            "asset_current_status": "in_store",
            "asset_type_recordcode": asset_type,
            "asset_purchase_number": 1,
        }

        assets = AssetService.create_asset(asset_data)

        # 【AGENTS 规范】返回统一数组格式
        assert isinstance(assets, list)
        assert len(assets) == 1

        asset = assets[0]
        # 验证编码格式：ASSET-{category}-{type_code}-{YYYYMMDD}-{6位随机}-{4位序号}
        assert asset.asset_code.startswith(f"{asset_type.type_code}-")
        assert asset.asset_name == "新资产"

    def test_create_asset_batch(self, storage, asset_type):
        """
        测试批量创建资产

        【AGENTS 规范】purchase_number > 1 时创建多条记录，
        编码序号连续递增。
        """
        asset_data = {
            "asset_name": "批量资产",
            "asset_purchase_price": 2000.00,
            "asset_purchase_date": "2024-01-01",
            "asset_entry_date": "2024-01-15",
            "asset_storage_recordcode": storage,
            "asset_current_status": "in_store",
            "asset_type_recordcode": asset_type,
            "asset_purchase_number": 3,
        }

        assets = AssetService.create_asset(asset_data)

        assert isinstance(assets, list)
        assert len(assets) == 3

        # 验证序号连续递增（格式：{type_code}-{uuid_hex}{seq:04d}）
        codes = [a.asset_code for a in assets]
        assert codes[0].endswith("0001")
        assert codes[1].endswith("0002")
        assert codes[2].endswith("0003")

    def test_create_asset_duplicate_code(self, asset, storage, asset_type):
        """
        测试创建重复编码资产

        【AGENTS 规范】asset_code 由后端自动生成，
        不再校验前端传入的编码，改为校验生成后的唯一性。
        由于自动生成机制，此测试改为验证编码唯一性保证。
        """
        asset_data = {
            "asset_name": "重复资产",
            "asset_purchase_price": 3000.00,
            "asset_purchase_date": "2024-01-01",
            "asset_entry_date": "2024-01-15",
            "asset_storage_recordcode": storage,
            "asset_type_recordcode": asset_type,
            "asset_purchase_number": 1,
        }

        # 创建第一条
        assets1 = AssetService.create_asset(asset_data)
        assert len(assets1) == 1
        code1 = assets1[0].asset_code

        # 创建第二条，编码应不同
        assets2 = AssetService.create_asset(asset_data)
        assert len(assets2) == 1
        code2 = assets2[0].asset_code

        assert code1 != code2

    def test_get_asset_statistics(self, asset):
        """
        测试获取资产统计

        【修复】对齐 AssetSelector.get_asset_statistics() 实际返回结构：
        {'total_count', 'total_value', 'status_distribution'}
        """
        stats = AssetService.get_asset_statistics()

        assert stats["total_count"] >= 1
        assert stats["total_value"] >= 0
        assert "status_distribution" in stats
        assert "in_store" in stats["status_distribution"]


@pytest.mark.django_db
class TestOutAssetService:
    """
    出库服务测试
    """

    def test_create_outasset(self, asset, user):
        """
        测试创建出库记录

        【修复】出库后需 refresh_from_db 才能获取更新后的资产状态
        【AGENTS 规范 - 去除冗余】人员/地点信息改为通过 Asset FK 关联查询
        """
        # 【AGENTS 规范 - 去除冗余】将人员/地点信息设置到 Asset 模型
        asset.asset_applicant_recordcode = user
        asset.asset_manager_recordcode = user
        asset.asset_using_location = "新地点"
        asset.save(update_fields=["asset_applicant_recordcode", "asset_manager_recordcode", "asset_using_location"])

        outasset_data = {
            "asset_recordcode": asset,
            "outasset_date": "2024-01-01",
        }

        outasset = OutAssetService.create_outasset(outasset_data)

        assert outasset.asset_recordcode == asset
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"

    def test_create_outasset_invalid_status(self, asset, user):
        """
        测试对非在库资产创建出库记录

        【修复】OutAssetService.create_outasset 抛出的是 AppValidationError，非 BusinessLogicError
        【AGENTS 规范 - 去除冗余】人员/地点信息改为通过 Asset FK 关联查询
        """
        from core.exceptions import AppValidationError

        asset.asset_current_status = "in_use"
        asset.save()

        outasset_data = {
            "asset_recordcode": asset,
            "outasset_date": "2024-01-01",
        }

        with pytest.raises(AppValidationError):
            OutAssetService.create_outasset(outasset_data)


@pytest.mark.django_db
class TestRecycleAssetService:
    """
    回收服务测试

    【AGENTS 规范】验证回收时清空 asset_applicant、asset_manager、asset_using_location
    """

    def test_create_recycle_asset_clears_fields(self, asset, user, outasset):
        """
        测试回收资产时清空申请人、保管人、使用地点

        【P0 修复】回收后 asset_applicant、asset_manager、asset_using_location 应被清空
        """
        # 验证出库后字段有值
        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode is not None
        assert asset.asset_manager_recordcode is not None
        assert asset.asset_using_location == "使用地点"
        assert asset.asset_current_status == "in_use"

        # 创建回收记录
        recycle_data = {
            "outasset_recordcode": outasset,
            "recycle_asset_date": date.today().isoformat(),
        }

        recycle_asset = RecycleAssetService.create_recycle_asset(
            recycle_data=recycle_data,
            operator_jobcode=user.employee_jobcode,
            operator_name=user.employee_name,
        )

        # 验证回收记录创建成功
        assert recycle_asset is not None
        assert recycle_asset.outasset_recordcode == outasset

        # 验证资产状态变更
        asset.refresh_from_db()
        assert asset.asset_current_status == "recycled_pending"

        # 【P0 修复】验证字段被清空
        assert asset.asset_applicant_recordcode is None, "回收后 asset_applicant_recordcode 应被清空"
        assert asset.asset_manager_recordcode is None, "回收后 asset_manager_recordcode 应被清空"
        assert asset.asset_using_location is None, "回收后 asset_using_location 应被清空"
