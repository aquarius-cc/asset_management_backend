"""M-03 回归: Dashboard「即将到期」先截断后过滤缺陷 + 维护提醒截断等价性锁定。

先红后绿口径:
- TestExpiringAssetsWindow.test_beyond_first_50_candidates_are_returned 在**修复前必红**:
  旧实现 order_by(asset_purchase_date)[:50] 取走最老 50 条, 其中无一条合格 → 返回空列表
- 其余用例为锁定用例, 修复前后均绿: 防修复破坏既有语义 / 封顶 / 行级隔离
- TestMaintenanceRemindersTruncation: 合格条件(入库满 24 月)与排序键(入库日期升序)同向,
  截断与过滤等价, 维护提醒分支非缺陷(merge-audit M-03 订正), 本类锁定该事实
"""

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from apps.assetmanagement.models import Asset
from apps.assetmanagement.selectors import DashboardSelector
from apps.authusermanagement.models import AuthUser
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


pytestmark = pytest.mark.django_db


def _bulk_assets(storage, asset_type, specs):
    """按 (code, purchase, warranty, entry, status) 批量造资产。

    recordcode 显式赋值: bulk_create 不走 save(), 无法依赖 BaseModel 自动生成。
    """
    return Asset.objects.bulk_create(
        [
            Asset(
                recordcode=f"ASSET-FIX-{code}",
                asset_code=code,
                asset_name=f"资产{code}",
                asset_purchase_price=100,
                asset_purchase_date=purchase,
                asset_warranty_period=warranty,
                asset_entry_date=entry,
                asset_storage_recordcode=storage,
                asset_type_recordcode=asset_type,
                asset_current_status=status,
            )
            for code, purchase, warranty, entry, status in specs
        ]
    )


class TestExpiringAssetsWindow:
    def test_beyond_first_50_candidates_are_returned(self, storage, asset_type, full_scope_user):
        """55 条已过期资产占据最老名次, 4 条即将到期落在 51+ 名次, 均须正确入选。"""
        today = date.today()
        expired = [
            (f"EXP-OLD-{i:03d}", today - relativedelta(years=3), 1, today - relativedelta(years=3), "in_store")
            for i in range(55)
        ]
        offsets = [3, 7, 20, 29]
        hot = [
            (f"EXP-HOT-{d:03d}", today - relativedelta(years=1) + timedelta(days=d), 1, today, "in_store")
            for d in offsets
        ]
        _bulk_assets(storage, asset_type, expired + hot)

        result = DashboardSelector.get_expiring_assets(full_scope_user, days=30)

        assert {item["asset_code"] for item in result} == {spec[0] for spec in hot}
        assert [item["days_until_expire"] for item in result] == sorted(offsets)

    def test_boundary_days_inclusive(self, storage, asset_type, full_scope_user):
        """days=3: 剩 3 天入选, 剩 4 天与已过期(-1 天)排除。"""
        today = date.today()
        _bulk_assets(
            storage,
            asset_type,
            [
                ("EXP-B-D3", today - relativedelta(years=1) + timedelta(days=3), 1, today, "in_store"),
                ("EXP-B-D4", today - relativedelta(years=1) + timedelta(days=4), 1, today, "in_store"),
                ("EXP-B-NEG", today - relativedelta(years=1) - timedelta(days=1), 1, today, "in_store"),
            ],
        )
        codes = {i["asset_code"] for i in DashboardSelector.get_expiring_assets(full_scope_user, days=3)}
        assert codes == {"EXP-B-D3"}

    def test_multi_year_warranty_window_scaling(self, storage, asset_type, full_scope_user):
        """max_warranty=2 时窗口须按 2 年回溯: 保修 2 年、采购于 23 个月前的资产

        到期日在 1 个月后, 必须入选(锁死 12*max_warranty 缩放, 防退化为固定 12)。
        若窗口只回溯 12 个月, 该行在 DB 段即被裁掉 → 红(CT-4 缩放回归屏障)。
        """
        today = date.today()
        _bulk_assets(
            storage,
            asset_type,
            [("EXP-W2", today - relativedelta(months=23), 2, today, "in_store")],
        )
        codes = {i["asset_code"] for i in DashboardSelector.get_expiring_assets(full_scope_user, days=31)}
        assert codes == {"EXP-W2"}

    def test_caps_at_alert_limit(self, storage, asset_type, full_scope_user):
        """60 条全合格时, 响应仍封顶 50 条(防止修复把载荷放大到全表)。"""
        today = date.today()
        _bulk_assets(
            storage,
            asset_type,
            [
                (f"EXP-CAP-{i:03d}", today - relativedelta(years=1) + timedelta(days=5), 1, today, "in_store")
                for i in range(60)
            ],
        )
        result = DashboardSelector.get_expiring_assets(full_scope_user, days=30)
        assert len(result) == 50

    def test_no_warranty_assets_returns_empty(self, storage, asset_type, full_scope_user):
        """无保修资产时 Max 聚合为 None, 走早返回分支(修复新增分支覆盖)。"""
        today = date.today()
        _bulk_assets(
            storage,
            asset_type,
            [("NO-WARRANTY", today - relativedelta(years=1), 0, today, "in_store")],
        )
        assert DashboardSelector.get_expiring_assets(full_scope_user) == []

    def test_respects_department_scope(self, storage, asset_type, user, department):
        """dept_manager 只能看到本部门的到期预警(修复不得绕过行级隔离)。"""
        other_dept = Department.objects.create(department_code="D002", department_name="其他部门")
        other_emp = Employee.objects.create(
            employee_jobcode="E-D002",
            employee_name="他部员工",
            employee_department=other_dept,
            employee_phone="13800131099",
            role=EmployeeRole.ASSET_ADMIN,
        )
        scoped_user = AuthUser.objects.create_user(
            auth_username="deptmgr", password=TEST_PASSWORD, auth_phone="13800131098"
        )
        Employee.objects.create(
            employee_jobcode="deptmgr",
            employee_name="部门经理",
            employee_department=department,
            employee_phone="13800131097",
            role=EmployeeRole.DEPT_MANAGER,
        )

        purchase = date.today() - relativedelta(years=1) + timedelta(days=5)
        common = {
            "asset_purchase_price": 1,
            "asset_purchase_date": purchase,
            "asset_warranty_period": 1,
            "asset_entry_date": purchase,
            "asset_storage_recordcode": storage,
            "asset_type_recordcode": asset_type,
        }
        Asset.objects.create(
            recordcode="ASSET-FIX-OWN",
            asset_code="OWN-01",
            asset_name="本部门",
            asset_entry_person_recordcode=user,
            **common,
        )
        Asset.objects.create(
            recordcode="ASSET-FIX-OTH",
            asset_code="OTH-01",
            asset_name="他部门",
            asset_entry_person_recordcode=other_emp,
            **common,
        )

        codes = {i["asset_code"] for i in DashboardSelector.get_expiring_assets(scoped_user)}
        assert codes == {"OWN-01"}


class TestMaintenanceRemindersTruncation:
    def test_keep_all_qualifying_rows(self, storage, asset_type, full_scope_user):
        """合格条件(入库满 24 月)与排序键(入库日期升序)同向: 最老 50 条即合格集合前 50 名。

        10 条入库 26 月(合格) + 50 条入库 12 月(不合格): 截断不丢行(非 Bug 锁定)。
        """
        today = date.today()
        old = [
            (f"MNT-OLD-{i:03d}", today - relativedelta(years=1), 0, today - relativedelta(months=26), "in_use")
            for i in range(10)
        ]
        young = [
            (f"MNT-YNG-{i:03d}", today - relativedelta(years=1), 0, today - relativedelta(months=12), "in_use")
            for i in range(50)
        ]
        _bulk_assets(storage, asset_type, old + young)

        result = DashboardSelector.get_maintenance_reminders(full_scope_user)
        assert {item["asset_code"] for item in result} == {spec[0] for spec in old}
