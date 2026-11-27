"""乐观锁版本号杀伤用例(Asset.save 四分支 + update_asset CAS)

分支口径(models/asset.py Asset.save):
1. 新建(adding=True) → 不自增,version 停默认 1;
2. 全量 save(update_fields is None) → 自增;
3. 显式 update_fields 命中 ASSET_VERSIONED_FIELDS → 自增,且 "version" 追加进写字段集;
4. 其余显式 update_fields(纯状态流转/软删) → 不自增。

递增断言一律 refresh_from_db 取库值,防内存假增: 分支3 若漏追加 "version",
内存 +1 而库内不变,只有取库值才能杀伤该变异。
"""

import pytest

from apps.assetmanagement.models import Asset
from apps.assetmanagement.services.asset_service import AssetService
from core.exceptions import ResourceConflictError


@pytest.mark.django_db
class TestSaveVersionFourBranches:
    """Asset.save 四分支逐支杀伤"""

    def test_branch1_create_leaves_version_at_one(self, storage, asset_type):
        created = Asset.objects.create(
            asset_code="VER-B1",
            asset_name="分支1新建",
            asset_purchase_price=1,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-02",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
        )
        created.refresh_from_db()
        assert created.version == 1

    def test_branch2_full_save_increments_version(self, asset):
        asset.asset_name = "全量改名"
        asset.save()
        asset.refresh_from_db()
        assert asset.version == 2
        assert asset.asset_name == "全量改名"

    def test_branch3_update_fields_hit_increments_and_persists(self, asset):
        """命中版本集: 自增且 version 随写字段集落库(取库值杀伤"漏追加"变异)"""
        asset.asset_name = "分支3改名"
        asset.save(update_fields=["asset_name"])
        asset.refresh_from_db()
        assert asset.version == 2
        assert asset.asset_name == "分支3改名"

    def test_branch3_service_change_employee_increments_version(self, asset, employee, admin_auth_user):
        """change_outasset_employee 写 applicant/manager(均在版本集) → 自增"""
        AssetService.change_outasset_employee(
            asset_code=asset.asset_code,
            applicant_jobcode=employee.employee_jobcode,
            manager_jobcode=employee.employee_jobcode,
            user=admin_auth_user,
        )
        asset.refresh_from_db()
        assert asset.version == 2

    def test_branch4_change_status_does_not_increment(self, asset, admin_auth_user):
        """纯状态流转(asset_current_status 刻意排除版本集) → 不自增"""
        AssetService.change_asset_status(asset_code=asset.asset_code, new_status="in_use", user=admin_auth_user)
        asset.refresh_from_db()
        assert asset.asset_current_status == "in_use"
        assert asset.version == 1

    def test_branch4_soft_delete_does_not_increment(self, asset, admin_auth_user):
        """软删只写 is_deleted/updated_at → 不自增"""
        AssetService.delete_asset(asset_code=asset.asset_code, user=admin_auth_user)
        deleted = Asset.all_objects.get(asset_code=asset.asset_code)
        assert deleted.is_deleted is True
        assert deleted.version == 1


@pytest.mark.django_db
class TestUpdateAssetVersionCas:
    """update_asset 乐观锁比对(compare-and-swap)语义"""

    def test_update_asset_service_increments_version(self, asset, admin_auth_user):
        result = AssetService.update_asset(
            asset_code=asset.asset_code,
            update_data={"asset_name": "服务改名", "version": asset.version},
            user=admin_auth_user,
        )
        result.refresh_from_db()
        assert result.version == 2
        assert result.asset_name == "服务改名"

    def test_stale_version_rejected_as_version_conflict(self, asset, admin_auth_user):
        with pytest.raises(ResourceConflictError) as exc:
            AssetService.update_asset(
                asset_code=asset.asset_code,
                update_data={"asset_name": "并发覆盖", "version": asset.version + 999},
                user=admin_auth_user,
            )
        assert exc.value.error_code == "VERSION_CONFLICT"
        assert exc.value.detail == f"资产 {asset.asset_code} 已被其他用户修改,请刷新后重试"
        asset.refresh_from_db()
        assert asset.asset_name == "测试资产"

    def test_version_token_consumed_by_cas_not_immutable_check(self, asset, admin_auth_user):
        """语义迁移锚点: version="HACKED" 走 CAS 比对(VERSION_CONFLICT),
        不再路由不可变集 FIELD_NOT_ALLOWED(原 TestImmutableFieldsKill[version] 语义)。"""
        with pytest.raises(ResourceConflictError) as exc:
            AssetService.update_asset(
                asset_code=asset.asset_code,
                update_data={"version": "HACKED"},
                user=admin_auth_user,
            )
        assert exc.value.error_code == "VERSION_CONFLICT"

    def test_missing_version_treated_as_conflict(self, asset, admin_auth_user):
        """服务层缺 version → CAS 视为不匹配(409 兜底);API 层必填由序列化器卡口"""
        with pytest.raises(ResourceConflictError) as exc:
            AssetService.update_asset(
                asset_code=asset.asset_code,
                update_data={"asset_name": "无令牌改名"},
                user=admin_auth_user,
            )
        assert exc.value.error_code == "VERSION_CONFLICT"
