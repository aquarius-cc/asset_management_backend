"""
资产选择器测试
"""

from uuid import uuid4

import pytest

from apps.assetmanagement.models import Asset, Storage
from apps.assetmanagement.selectors.asset_selector import AssetSelector, AssetTypeSelector
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee
from core.tests import TEST_PASSWORD


@pytest.mark.django_db
class TestAssetSelector:
    """资产选择器测试类"""

    def test_get_queryset_for_user_system_admin(self, asset):
        """系统管理员应看到所有资产"""
        # 创建系统管理员用户
        employee = Employee.objects.create(
            employee_jobcode="ADMIN001",
            employee_name="系统管理员",
            employee_department=Department.objects.first(),
            employee_phone="13800132001",
        )
        # 模拟系统管理员权限(is_superuser=True)
        auth_user = AuthUser.objects.create_superuser(auth_username="admin", password=TEST_PASSWORD)
        employee.auth_user = auth_user
        employee.save()

        queryset = AssetSelector.get_queryset_for_user(auth_user)
        assert queryset.count() >= 1

    def test_get_queryset_for_user_regular_user(self, asset, user):
        """普通用户应只能看到本部门资产"""
        # 创建另一个部门
        other_department = Department.objects.create(
            department_code="D002",
            department_name="其他部门",
        )
        # employee_jobcode 必须匹配 auth_username,否则 get_employee_for_user 查不到
        _ = Employee.objects.create(
            employee_jobcode="other",
            employee_name="其他用户",
            employee_department=other_department,
            employee_phone="13800132002",
        )
        other_user = AuthUser.objects.create_user(auth_username="other", password=TEST_PASSWORD)

        # 普通用户应看不到资产(因为资产在测试部门)
        queryset = AssetSelector.get_queryset_for_user(other_user)
        assert queryset.count() == 0

    def test_get_all_assets(self, asset):
        """应返回所有未删除的资产"""
        queryset = AssetSelector.get_all_assets()
        assert queryset.count() == 1
        assert queryset.first().asset_code == "A001"

    def test_get_assets_for_list(self, asset):
        """应返回列表视图的资产"""
        queryset = AssetSelector.get_assets_for_list()
        assert queryset.count() == 1

    def test_get_assets_with_all_relations(self, asset):
        """应返回包含所有关联关系的资产"""
        queryset = AssetSelector.get_assets_with_all_relations()
        assert queryset.count() == 1

    def test_get_available_assets(self, asset, admin_auth_user):
        """应返回可用资产(in_store 或 recycled_pending)"""
        queryset = AssetSelector.get_available_assets(user=admin_auth_user)
        # 当前资产状态是 in_store,应该返回
        assert queryset.count() == 1

    def test_get_available_assets_with_code_filter(self, asset, admin_auth_user):
        """按资产编码过滤可用资产"""
        queryset = AssetSelector.get_available_assets(asset_code="A001", user=admin_auth_user)
        assert queryset.count() == 1

    def test_get_available_assets_with_name_filter(self, asset, admin_auth_user):
        """按资产名称过滤可用资产"""
        queryset = AssetSelector.get_available_assets(asset_name="测试", user=admin_auth_user)
        assert queryset.count() == 1

    def test_get_assets_by_status(self, asset, admin_auth_user):
        """按状态获取资产"""
        queryset = AssetSelector.get_assets_by_status("in_store", user=admin_auth_user)
        assert queryset.count() == 1

    def test_get_asset_by_code(self, asset, admin_auth_user):
        """按编码获取资产"""
        result = AssetSelector.get_asset_by_code("A001", user=admin_auth_user)
        assert result is not None
        assert result.asset_code == "A001"

    def test_get_asset_by_code_not_found(self, admin_auth_user):
        """按编码获取不存在的资产"""
        result = AssetSelector.get_asset_by_code("NOTEXIST", user=admin_auth_user)
        assert result is None

    def test_get_asset_detail_by_code(self, asset, admin_auth_user):
        """按编码获取资产详情"""
        result = AssetSelector.get_asset_detail_by_code("A001", user=admin_auth_user)
        assert result is not None
        assert result.asset_code == "A001"

    def test_get_asset_detail_by_code_not_found(self, admin_auth_user):
        """按编码获取不存在的资产详情"""
        result = AssetSelector.get_asset_detail_by_code("NOTEXIST", user=admin_auth_user)
        assert result is None

    def test_search_assets(self, asset, admin_auth_user):
        """搜索资产"""
        queryset = AssetSelector.search_assets(keyword="测试", user=admin_auth_user)
        assert queryset.count() == 1

    def test_search_assets_by_status(self, asset, admin_auth_user):
        """按状态搜索资产"""
        queryset = AssetSelector.search_assets(status="in_store", user=admin_auth_user)
        assert queryset.count() == 1

    def test_search_assets_by_type(self, asset, asset_type, admin_auth_user):
        """按类型搜索资产"""
        queryset = AssetSelector.search_assets(asset_type="AT001", user=admin_auth_user)
        assert queryset.count() == 1

    def test_search_assets_by_storage(self, asset, storage, admin_auth_user):
        """按仓库搜索资产"""
        queryset = AssetSelector.search_assets(storage_code="S001", user=admin_auth_user)
        assert queryset.count() == 1

    def test_get_asset_statistics(self, asset):
        """获取资产统计信息"""
        stats = AssetSelector.get_asset_statistics()
        assert "total_count" in stats
        assert "total_value" in stats
        assert "status_distribution" in stats
        assert stats["total_count"] == 1

    def test_get_assets_by_type(self, asset, asset_type, admin_auth_user):
        """按类型获取资产"""
        queryset = AssetSelector.get_assets_by_type("AT001", user=admin_auth_user)
        assert queryset.count() == 1

    def test_exists_by_code(self, asset):
        """检查资产编码是否存在"""
        assert AssetSelector.exists_by_code("A001") is True
        assert AssetSelector.exists_by_code("NOTEXIST") is False

    def test_get_assets_by_storage(self, asset, storage, admin_auth_user):
        """按仓库获取资产"""
        queryset = AssetSelector.get_assets_by_storage("S001", user=admin_auth_user)
        assert queryset.count() == 1

    def test_combine_search(self, asset):
        """组合搜索"""
        queryset = AssetSelector.combine_search(field_filters={"asset_code": "A001"}, exact_filters={})
        assert queryset.count() == 1


@pytest.mark.django_db
class TestAssetTypeSelector:
    """资产类型选择器测试类"""

    def test_get_all_asset_types(self, asset_type):
        """获取所有资产类型"""
        queryset = AssetTypeSelector.get_all_asset_types()
        assert queryset.count() == 1

    def test_get_asset_type_by_code(self, asset_type):
        """按类型代码获取资产类型"""
        result = AssetTypeSelector.get_asset_type_by_code("AT001")
        assert result is not None
        assert result.type_code == "AT001"

    def test_get_asset_type_by_code_not_found(self):
        """按类型代码获取不存在的资产类型"""
        result = AssetTypeSelector.get_asset_type_by_code("NOTEXIST")
        assert result is None

    def test_get_asset_type_by_recordcode(self, asset_type):
        """按 recordcode 获取资产类型"""
        result = AssetTypeSelector.get_asset_type_by_recordcode(asset_type.recordcode)
        assert result is not None
        assert result.recordcode == asset_type.recordcode

    def test_get_asset_type_by_recordcode_not_found(self):
        """按 recordcode 获取不存在的资产类型"""
        result = AssetTypeSelector.get_asset_type_by_recordcode("notexist")
        assert result is None

    def test_exists_by_code(self, asset_type):
        """检查类型代码是否存在"""
        assert AssetTypeSelector.exists_by_code("AT001") is True
        assert AssetTypeSelector.exists_by_code("NOTEXIST") is False

    def test_get_root_types(self, asset_type):
        """获取顶级资产类型"""
        queryset = AssetTypeSelector.get_root_types()
        # 测试用的 asset_type 是顶级类型
        assert queryset.count() == 1

    def test_get_children(self, asset_type):
        """获取子类型"""
        queryset = AssetTypeSelector.get_children("AT001")
        # 当前没有子类型
        assert queryset.count() == 0

    def test_get_children_not_found(self):
        """获取不存在类型的子类型"""
        queryset = AssetTypeSelector.get_children("NOTEXIST")
        assert queryset.count() == 0

    def test_get_all_descendants(self, asset_type):
        """获取所有后代类型"""
        descendants = AssetTypeSelector.get_all_descendants("AT001")
        # 当前没有后代
        assert len(descendants) == 0

    def test_get_all_descendants_not_found(self):
        """获取不存在类型的所有后代"""
        descendants = AssetTypeSelector.get_all_descendants("NOTEXIST")
        assert len(descendants) == 0

    def test_get_type_path(self, asset_type):
        """获取类型路径"""
        # get_type_path 解析 path 中的 type_code 片段,path 格式为 /type_code1/type_code2
        asset_type.path = f"/{asset_type.type_code}"
        asset_type.save()

        path = AssetTypeSelector.get_type_path("AT001")
        # 当前类型是顶级,路径应只包含自身
        assert len(path) == 1
        assert path[0].type_code == "AT001"

    def test_get_type_path_not_found(self):
        """获取不存在类型的路径"""
        path = AssetTypeSelector.get_type_path("NOTEXIST")
        assert len(path) == 0


@pytest.mark.django_db
class TestAssetSelectorPublicScan:
    def test_get_asset_for_public_scan_found(self, asset):
        result = AssetSelector.get_asset_for_public_scan(asset.recordcode)
        assert result is not None
        assert result.asset_code == "A001"
        assert hasattr(result, "asset_type_recordcode")
        assert hasattr(result, "asset_storage_recordcode")

    def test_get_asset_for_public_scan_not_found(self):
        result = AssetSelector.get_asset_for_public_scan("nonexistent")
        assert result is None

    def test_get_asset_for_public_scan_deleted(self, asset):
        asset.is_deleted = True
        asset.save(update_fields=["is_deleted"])
        result = AssetSelector.get_asset_for_public_scan(asset.recordcode)
        assert result is None


@pytest.mark.django_db
class TestReferencedEmployeeRecordcodes:
    """AssetSelector.referenced_employee_recordcodes 单元测试(B-20 守卫收敛)"""

    @staticmethod
    def _create_employee(department: Department, jobcode: str) -> Employee:
        return Employee.objects.create(
            employee_jobcode=jobcode,
            employee_name=f"关联员工{jobcode}",
            employee_department=department,
            employee_phone="137" + uuid4().hex[:8],
        )

    @staticmethod
    def _create_asset(
        storage: Storage,
        asset_type,
        *,
        applicant: Employee | None = None,
        manager: Employee | None = None,
    ) -> Asset:
        return Asset.objects.create(
            asset_code=f"REF-{uuid4().hex[:8].upper()}",
            asset_name="引用检查资产",
            asset_purchase_price=1000.00,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-15",
            asset_storage_recordcode=storage,
            asset_type_recordcode=asset_type,
            asset_current_status="in_store",
            asset_applicant_recordcode=applicant,
            asset_manager_recordcode=manager,
        )

    def test_empty_candidates(self):
        assert AssetSelector.referenced_employee_recordcodes([]) == set()

    def test_applicant_hit(self, department, storage, asset_type):
        employee = self._create_employee(department, "REF-EMP-01")
        self._create_asset(storage, asset_type, applicant=employee)
        assert AssetSelector.referenced_employee_recordcodes([employee.recordcode]) == {
            employee.recordcode
        }

    def test_manager_hit(self, department, storage, asset_type):
        employee = self._create_employee(department, "REF-EMP-02")
        self._create_asset(storage, asset_type, manager=employee)
        assert AssetSelector.referenced_employee_recordcodes([employee.recordcode]) == {
            employee.recordcode
        }

    def test_both_roles_dedup(self, department, storage, asset_type):
        applicant = self._create_employee(department, "REF-EMP-03")
        manager = self._create_employee(department, "REF-EMP-04")
        self._create_asset(storage, asset_type, applicant=applicant)
        self._create_asset(storage, asset_type, manager=manager)
        result = AssetSelector.referenced_employee_recordcodes(
            [applicant.recordcode, manager.recordcode]
        )
        assert result == {applicant.recordcode, manager.recordcode}

    def test_soft_deleted_asset_excluded(self, department, storage, asset_type):
        employee = self._create_employee(department, "REF-EMP-05")
        asset = self._create_asset(storage, asset_type, applicant=employee)
        asset.is_deleted = True
        asset.save(update_fields=["is_deleted"])
        assert AssetSelector.referenced_employee_recordcodes([employee.recordcode]) == set()

    def test_unreferenced_excluded(self, department, storage, asset_type):
        linked = self._create_employee(department, "REF-EMP-06")
        unrelated = self._create_employee(department, "REF-EMP-07")
        self._create_asset(storage, asset_type, applicant=linked)
        assert AssetSelector.referenced_employee_recordcodes(
            [linked.recordcode, unrelated.recordcode]
        ) == {linked.recordcode}
