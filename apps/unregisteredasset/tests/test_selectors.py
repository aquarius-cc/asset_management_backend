"""
未登记资产选择器测试

测试 UnregisteredAssetSelector 的:
- 根据编码获取
- 根据 ID 获取
- 列表筛选
- 存在性检查
"""

from datetime import date

import pytest

from apps.unregisteredasset.models import UnregisteredAsset
from apps.unregisteredasset.selectors import UnregisteredAssetSelector
from apps.usermanagement.models import Employee, EmployeeRole


@pytest.mark.django_db
class TestUnregisteredAssetSelector:
    """
    未登记资产选择器测试类
    """

    def test_get_by_code_exists(self, unregistered_asset_s1):
        """
        测试根据编码获取存在的记录
        """
        result = UnregisteredAssetSelector.get_by_code(unregistered_asset_s1.unregistered_code)

        assert result is not None
        assert result.id == unregistered_asset_s1.id

    def test_get_by_code_not_exists(self):
        """
        测试根据编码获取不存在的记录
        """
        result = UnregisteredAssetSelector.get_by_code("UNR-NOTEXIST")
        assert result is None

    def test_get_by_code_soft_deleted(self, unregistered_asset_s1):
        """
        测试根据编码获取已软删除的记录
        """
        code = unregistered_asset_s1.unregistered_code
        unregistered_asset_s1.delete()

        result = UnregisteredAssetSelector.get_by_code(code)
        assert result is None

    def test_get_by_id_exists(self, unregistered_asset_s1):
        """
        测试根据 ID 获取存在的记录
        """
        result = UnregisteredAssetSelector.get_by_id(unregistered_asset_s1.id)

        assert result is not None
        assert result.unregistered_code == unregistered_asset_s1.unregistered_code

    def test_get_by_id_not_exists(self):
        """
        测试根据 ID 获取不存在的记录
        """
        result = UnregisteredAssetSelector.get_by_id(99999)
        assert result is None

    def test_list_by_filters_empty(self, db):
        """
        测试无筛选条件返回所有记录
        """
        queryset = UnregisteredAssetSelector.list_by_filters()
        assert queryset.count() == 0

    def test_list_by_filters_scenario_type(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试按场景类型筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(scenario_type="s1_no_record")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_list_by_filters_approval_status(self, unregistered_asset_s1, approved_unregistered_asset):
        """
        测试按审批状态筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(approval_status="pending")

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_by_filters_discovery_person(self, unregistered_asset_s1, employee):
        """
        测试按发现人筛选
        """
        queryset = UnregisteredAssetSelector.list_by_filters(discovery_person=employee.employee_jobcode)

        assert queryset.count() == 1
        assert queryset.first().discovery_person == employee

    def test_list_by_filters_combined(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试组合筛选条件
        """
        queryset = UnregisteredAssetSelector.list_by_filters(scenario_type="s1_no_record", approval_status="pending")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_list_by_discovery_person(self, unregistered_asset_s1, employee):
        """
        测试按发现人获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_discovery_person(discovery_person=employee.employee_jobcode)

        assert queryset.count() == 1

    def test_list_by_discovery_person_with_status(self, unregistered_asset_s1, approved_unregistered_asset, employee):
        """
        测试按发现人和状态获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_discovery_person(
            discovery_person=employee.employee_jobcode, approval_status="pending"
        )

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_pending(self, unregistered_asset_s1, approved_unregistered_asset):
        """
        测试获取待审批列表
        """
        queryset = UnregisteredAssetSelector.list_pending()

        assert queryset.count() == 1
        assert queryset.first().approval_status == "pending"

    def test_list_by_scenario(self, unregistered_asset_s1, unregistered_asset_s2):
        """
        测试按场景类型获取列表
        """
        queryset = UnregisteredAssetSelector.list_by_scenario("s1_no_record")

        assert queryset.count() == 1
        assert queryset.first().scenario_type == "s1_no_record"

    def test_exists_by_code_true(self, unregistered_asset_s1):
        """
        测试存在性检查 - 存在
        """
        exists = UnregisteredAssetSelector.exists_by_code(unregistered_asset_s1.unregistered_code)
        assert exists is True

    def test_exists_by_code_false(self):
        """
        测试存在性检查 - 不存在
        """
        exists = UnregisteredAssetSelector.exists_by_code("UNR-NOTEXIST")
        assert exists is False

    def test_exists_by_code_soft_deleted(self, unregistered_asset_s1):
        """
        测试存在性检查 - 已软删除
        """
        code = unregistered_asset_s1.unregistered_code
        unregistered_asset_s1.delete()

        exists = UnregisteredAssetSelector.exists_by_code(code)
        assert exists is False

    def test_ordering_by_created_at_desc(self, employee, storage):
        """
        测试按创建时间倒序排列
        """
        # 创建两个记录
        asset1 = UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 1),
            discovery_location="地点1",
            discovery_person=employee,
            asset_name="资产1",
            unregistered_asset_storage=storage,
        )

        asset2 = UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 2),
            discovery_location="地点2",
            discovery_person=employee,
            asset_name="资产2",
            unregistered_asset_storage=storage,
        )

        queryset = UnregisteredAssetSelector.list_by_filters()

        # 验证倒序排列
        assert queryset.first().id == asset2.id
        assert queryset.last().id == asset1.id


@pytest.mark.django_db
class TestGetQuerysetForUser:
    """B12 + 4.5 行级隔离规则1-4 的 Selector 单测(CT-1)"""

    @staticmethod
    def _make_record(discovery_employee, storage, name: str = "行级记录") -> UnregisteredAsset:
        return UnregisteredAsset.objects.create(
            scenario_type="s1_no_record",
            discovery_date=date(2024, 6, 1),
            discovery_location="会议室",
            discovery_person=discovery_employee,
            asset_name=name,
            unregistered_asset_storage=storage,
        )

    def test_system_admin_sees_all(self, db, make_role_user, make_dept, make_plain_employee, storage):
        dept = make_dept("SEL_ROOT")
        emp_in = make_plain_employee("sel_emp_in", dept)
        emp_out = make_plain_employee("sel_emp_out")
        rec_in = self._make_record(emp_in, storage, "本部门")
        rec_out = self._make_record(emp_out, storage, "范围外")
        user = make_role_user("sel_sys", EmployeeRole.SYSTEM_ADMIN)

        qs = UnregisteredAssetSelector.get_queryset_for_user(user)
        assert set(qs.values_list("id", flat=True)) == {rec_in.id, rec_out.id}

    def test_dept_manager_dept_scope_with_descendants(
        self, db, make_role_user, make_dept, make_plain_employee, storage
    ):
        """规则2: 本部门+下级可见; 兄弟部门不可见"""
        parent = make_dept("SEL_PARENT")
        child = make_dept("SEL_CHILD", parent=parent)
        other = make_dept("SEL_OTHER")
        rec_parent = self._make_record(make_plain_employee("sel_e_p", parent), storage, "本部门")
        rec_child = self._make_record(make_plain_employee("sel_e_c", child), storage, "下级")
        rec_other = self._make_record(make_plain_employee("sel_e_o", other), storage, "范围外")
        user = make_role_user("sel_dm", EmployeeRole.DEPT_MANAGER, parent)

        qs = set(UnregisteredAssetSelector.get_queryset_for_user(user).values_list("id", flat=True))
        assert rec_parent.id in qs
        assert rec_child.id in qs
        assert rec_other.id not in qs

    def test_asset_admin_own_dept_and_self_only(self, db, make_role_user, make_dept, make_plain_employee, storage):
        dept = make_dept("SEL_AA")
        other = make_dept("SEL_AA_OTHER")
        rec_dept = self._make_record(make_plain_employee("sel_e_d", dept), storage, "本部门他人")
        rec_other = self._make_record(make_plain_employee("sel_e_x", other), storage, "范围外")
        user = make_role_user("sel_aa", EmployeeRole.ASSET_ADMIN, dept)
        own_emp = Employee.objects.get(employee_jobcode="sel_aa")
        rec_self = self._make_record(own_emp, storage, "本人提交")

        qs = set(UnregisteredAssetSelector.get_queryset_for_user(user).values_list("id", flat=True))
        assert rec_dept.id in qs
        assert rec_self.id in qs
        assert rec_other.id not in qs

    def test_asset_admin_no_dept_sees_only_own(self, db, make_role_user, make_plain_employee, storage):
        """规则1: 无部门 aa 部门码收敛空集; 规则3: 本人提交恒可见"""
        other = make_plain_employee("sel_e_nd")
        rec_other = self._make_record(other, storage, "他人记录")
        user = make_role_user("sel_ndaa", EmployeeRole.ASSET_ADMIN, department=None)
        own_emp = Employee.objects.get(employee_jobcode="sel_ndaa")
        rec_self = self._make_record(own_emp, storage, "本人提交")

        qs = set(UnregisteredAssetSelector.get_queryset_for_user(user).values_list("id", flat=True))
        assert qs == {rec_self.id}
        assert rec_other.id not in qs

    @pytest.mark.parametrize("role", [EmployeeRole.REGULAR_USER, EmployeeRole.AUDITOR])
    def test_regular_and_auditor_see_none(self, db, make_role_user, make_dept, make_plain_employee, storage, role):
        """矩阵 ❌: regular/auditor 不可见(防御纵深)"""
        dept = make_dept(f"SEL_R_{role[:4]}")
        self._make_record(make_plain_employee(f"sel_e_{role[:4]}", dept), storage)
        user = make_role_user(f"sel_u_{role[:4]}", role, dept)

        assert UnregisteredAssetSelector.get_queryset_for_user(user).count() == 0

    def test_user_without_employee_sees_none(self, db, auth_user, storage, employee):
        """无 Employee 记录 → 空集"""
        self._make_record(employee, storage)
        assert UnregisteredAssetSelector.get_queryset_for_user(auth_user).count() == 0

    def test_superuser_sees_all(self, db, auth_user, storage, employee):
        auth_user.is_superuser = True
        auth_user.save()
        rec = self._make_record(employee, storage)
        qs = UnregisteredAssetSelector.get_queryset_for_user(auth_user)
        assert qs.filter(id=rec.id).exists()

    def test_get_by_code_for_user_in_scope(self, db, make_role_user, make_dept, make_plain_employee, storage):
        dept = make_dept("SEL_G")
        rec = self._make_record(make_plain_employee("sel_eg", dept), storage)
        user = make_role_user("sel_gaa", EmployeeRole.ASSET_ADMIN, dept)

        result = UnregisteredAssetSelector.get_by_code_for_user(user, rec.unregistered_code)
        assert result is not None
        assert result.id == rec.id

    def test_get_by_code_for_user_out_of_scope_returns_none(self, db, make_role_user, make_plain_employee, storage):
        """语义4: 越权与不存在同构(均返回 None → View 转 404)"""
        rec = self._make_record(make_plain_employee("sel_ego"), storage)
        user = make_role_user("sel_gaa2", EmployeeRole.ASSET_ADMIN, department=None)

        assert UnregisteredAssetSelector.get_by_code_for_user(user, rec.unregistered_code) is None
        assert UnregisteredAssetSelector.get_by_code_for_user(user, "UNR-NOTEXIST") is None
