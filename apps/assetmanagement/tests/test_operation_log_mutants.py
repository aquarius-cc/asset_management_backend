"""C批 B2-A/B2-B：operation_log_service 存活 mutant 定向杀伤（CT-4 回归屏障）。

B2-A（首版，杀 114/181）：before/after 精确 dict + description 文案 + related 字段。
B2-B（补刀）补杀根因：
- conftest asset 未设 asset_specification（None）→ spec=None 类变异等价。
  补刀法：调用前把 spec 置为非空值再断言 log.asset_specification。
- 断言漏了 log.asset_name / log.ip_address / operator_name 顶层字段。
- logger.info/error 无 mock → 补 patch 断言调用消息内容。
- 查询侧缺时间窗与「同 jobcode 双资产」用例 → asset_code/start/end 透传杀不掉。
- get_user_operations 缺「NULL jobcode 干扰项」用例 → operator_jobcode→None 等价。
- log_asset_delete 缺「无 storage 资产」用例 → `if storage or True` 条件改写杀不掉。
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.assetmanagement.models import Asset, AssetOperationLog, AssetType, Storage
from apps.assetmanagement.services.operation_log_service import (
    OperationLogQueryService,
    OperationLogService,
    _to_json_safe,
)
from apps.usermanagement.models import Department, Employee, EmployeeRole
from core.tests import TEST_PASSWORD


User = get_user_model()

SERVICE_LOGGER = "apps.assetmanagement.services.operation_log_service.logger"
SPEC = "规格-TEST-XYZ"


def _asset_with_spec(asset) -> Asset:
    """把 asset_specification 置为非空——否则 spec=None 变异与原版等价（B2-B 补刀依据）。"""
    asset.asset_specification = SPEC
    asset.save(update_fields=["asset_specification"])
    return asset


# ────────────────────────── log_asset_out ──────────────────────────


@pytest.mark.django_db
class TestLogAssetOutMutants:
    """log_asset_out：before/after 状态对 + related 字段 + asset_name/spec/ip 顶层透传。"""

    def test_out_full_field_assertions(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_out(
            asset,
            recordcode="OUT-001",
            operator_jobcode="OP001",
            operator_name="张三",
            ip_address="127.0.0.1",
        )
        assert log.before_data == {"asset_current_status": "in_store"}
        assert log.after_data == {"asset_current_status": "in_use"}
        assert log.operation_type == AssetOperationLog.OperationType.OUT
        assert log.description == "资产出库发放: OUT-001"
        assert log.related_record_code == "OUT-001"
        assert log.related_record_type == "out"
        assert log.operator_jobcode == "OP001"
        assert log.operator_name == "张三"
        assert log.ip_address == "127.0.0.1"
        assert log.asset_code == asset.asset_code
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC


# ────────────────────────── log_asset_delete ──────────────────────────


@pytest.mark.django_db
class TestLogAssetDeleteMutants:
    """log_asset_delete：双分支 + storage 条件改写（需无 storage 资产）+ 顶层透传。"""

    def test_delete_with_asset_builds_before_data(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_delete(
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            asset=asset,
            operator_jobcode="OP002",
            operator_name="李四",
            ip_address="10.1.1.1",
        )
        assert log.before_data == {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "asset_current_status": "in_store",
            "asset_storage": str(asset.asset_storage_recordcode),
        }
        assert log.asset_specification == SPEC
        assert log.asset_name == asset.asset_name
        assert log.ip_address == "10.1.1.1"
        assert log.description == f"资产删除(软删除): {asset.asset_name}"
        assert log.operation_type == AssetOperationLog.OperationType.DELETE
        assert log.operator_jobcode == "OP002"
        assert log.operator_name == "李四"

    def test_delete_without_asset_keeps_none(self):
        log = OperationLogService.log_asset_delete(
            asset_code="GONE-001",
            asset_name="已消失资产",
            asset=None,
            operator_jobcode="OP003",
            ip_address="10.1.1.2",
        )
        assert log.before_data is None
        assert log.asset_specification is None
        assert log.asset_name == "已消失资产"
        assert log.ip_address == "10.1.1.2"
        assert log.description == "资产删除(软删除): 已消失资产"
        assert log.operator_jobcode == "OP003"

    def test_delete_asset_without_storage_yields_none_storage(self, db, asset_type):
        """杀 `if storage else None` → `if (storage) or True else None`：无 storage 时原版 None、变异 'None'。"""
        no_storage_asset = Asset.objects.create(
            asset_code="A-NOSTORE-DEL",
            asset_name="无仓库资产",
            asset_purchase_price=1.0,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_type_recordcode=asset_type,
            asset_storage_recordcode=None,
            asset_current_status="in_store",
        )
        log = OperationLogService.log_asset_delete(
            asset_code=no_storage_asset.asset_code,
            asset_name=no_storage_asset.asset_name,
            asset=no_storage_asset,
        )
        assert log.before_data["asset_storage"] is None


# ────────────────────────── log_asset_create ──────────────────────────


@pytest.mark.django_db
class TestLogAssetCreateMutants:
    """log_asset_create：after_data 四字段 + storage 三态分支 + 顶层透传。"""

    def test_create_with_storage_serializes_storage_str(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_create(
            asset, operator_jobcode="OP004", operator_name="王五", ip_address="10.2.2.2"
        )
        assert log.after_data == {
            "asset_code": asset.asset_code,
            "asset_name": asset.asset_name,
            "asset_current_status": "in_store",
            "asset_storage": str(asset.asset_storage_recordcode),
        }
        assert log.description == f"资产入库: {asset.asset_name}"
        assert log.operation_type == AssetOperationLog.OperationType.CREATE
        assert log.operator_jobcode == "OP004"
        assert log.operator_name == "王五"
        assert log.ip_address == "10.2.2.2"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC

    def test_create_without_storage_keeps_none(self, db, asset_type):
        no_storage_asset = Asset.objects.create(
            asset_code="A-NOSTORE",
            asset_name="无仓库资产",
            asset_purchase_price=1.0,
            asset_purchase_date="2024-01-01",
            asset_entry_date="2024-01-01",
            asset_type_recordcode=asset_type,
            asset_storage_recordcode=None,
            asset_current_status="in_store",
        )
        log = OperationLogService.log_asset_create(no_storage_asset)
        assert log.after_data == {
            "asset_code": "A-NOSTORE",
            "asset_name": "无仓库资产",
            "asset_current_status": "in_store",
            "asset_storage": None,
        }
        assert log.asset_name == "无仓库资产"


# ────────────────────────── log_asset_update ──────────────────────────


@pytest.mark.django_db
class TestLogAssetUpdateMutants:
    """log_asset_update：changed_fields 推导 + 描述拼接 + 顶层透传。"""

    def test_update_lists_only_changed_fields(self, asset):
        _asset_with_spec(asset)
        before = {"asset_name": "旧名", "asset_current_status": "in_store"}
        after = {"asset_name": "新名", "asset_current_status": "in_store"}
        log = OperationLogService.log_asset_update(
            asset,
            before_data=before,
            after_data=after,
            operator_jobcode="OP005",
            operator_name="赵六",
            ip_address="10.3.3.3",
        )
        assert log.description == "资产信息更新: asset_name"
        assert log.before_data == before
        assert log.after_data == after
        assert log.operation_type == AssetOperationLog.OperationType.UPDATE
        assert log.operator_jobcode == "OP005"
        assert log.operator_name == "赵六"
        assert log.ip_address == "10.3.3.3"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC

    def test_update_no_change_uses_generic_description(self, asset):
        snapshot = {"asset_name": "同名", "asset_current_status": "in_store"}
        log = OperationLogService.log_asset_update(asset, before_data=snapshot, after_data=dict(snapshot))
        assert log.description == "资产信息更新"

    def test_update_multiple_changed_fields_order_follows_after_data(self, asset):
        before = {"b": 1, "a": 1, "c": 1}
        after = {"b": 2, "a": 2, "c": 1}
        log = OperationLogService.log_asset_update(asset, before_data=before, after_data=after)
        assert log.description == "资产信息更新: b, a"


# ────────────────── recycle / damaged / waste 状态对 ──────────────────


@pytest.mark.django_db
class TestLogAssetRecycleMutants:
    """log_asset_recycle：硬编码 IN_USE→RECYCLED_PENDING + 顶层透传。"""

    def test_recycle_status_pair_and_related(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_recycle(
            asset,
            recordcode="RC-001",
            operator_jobcode="OP006",
            operator_name="钱七",
            ip_address="10.4.4.4",
        )
        assert log.before_data == {"asset_current_status": "in_use"}
        assert log.after_data == {"asset_current_status": "recycled_pending"}
        assert log.description == "资产回收: RC-001"
        assert log.related_record_code == "RC-001"
        assert log.related_record_type == "recycle"
        assert log.operation_type == AssetOperationLog.OperationType.RECYCLE
        assert log.operator_jobcode == "OP006"
        assert log.operator_name == "钱七"
        assert log.ip_address == "10.4.4.4"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC


@pytest.mark.django_db
class TestLogAssetDamagedMutants:
    """log_asset_damaged：before 取资产实时状态，after 硬编码 DAMAGED + 全参透传。"""

    def test_damaged_uses_live_status_then_damaged(self, asset):
        _asset_with_spec(asset)
        asset.asset_current_status = "in_use"
        asset.save(update_fields=["asset_current_status"])
        log = OperationLogService.log_asset_damaged(
            asset,
            damaged_record_code="DM-001",
            operator_jobcode="OP007",
            operator_name="孙八",
            ip_address="10.5.5.5",
        )
        assert log.before_data == {"asset_current_status": "in_use"}
        assert log.after_data == {"asset_current_status": "damaged"}
        assert log.description == "提交报废申请: DM-001"
        assert log.related_record_code == "DM-001"
        assert log.related_record_type == "damaged"
        assert log.operation_type == AssetOperationLog.OperationType.DAMAGED
        assert log.operator_jobcode == "OP007"
        assert log.operator_name == "孙八"
        assert log.ip_address == "10.5.5.5"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC


@pytest.mark.django_db
class TestLogAssetWasteMutants:
    """log_asset_waste：硬编码 DAMAGED→SCRAPPED（与资产实际状态无关）+ 全参透传。"""

    def test_waste_hardcoded_pair_even_if_asset_not_damaged(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_waste(
            asset,
            waste_record_code="WS-001",
            operator_jobcode="OP008",
            operator_name="周九",
            ip_address="10.6.6.6",
        )
        assert log.before_data == {"asset_current_status": "damaged"}
        assert log.after_data == {"asset_current_status": "scrapped"}
        assert log.description == "资产报废完成: WS-001"
        assert log.related_record_code == "WS-001"
        assert log.related_record_type == "waste"
        assert log.operation_type == AssetOperationLog.OperationType.WASTE
        assert log.operator_jobcode == "OP008"
        assert log.operator_name == "周九"
        assert log.ip_address == "10.6.6.6"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC


# ────────────────────────── approve / transfer ──────────────────────────


@pytest.mark.django_db
class TestLogAssetApproveMutants:
    """log_asset_approve：result_display 三元分支 + 顶层透传。"""

    def test_approve_approved_description(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_approve(
            asset, approval_result="approved", operator_jobcode="OP009", operator_name="吴十"
        )
        assert log.description == "报废审批通过"
        assert log.operation_type == AssetOperationLog.OperationType.APPROVE
        assert log.operator_jobcode == "OP009"
        assert log.operator_name == "吴十"
        assert log.before_data is None
        assert log.after_data is None
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC

    def test_approve_rejected_description(self, asset):
        log = OperationLogService.log_asset_approve(asset, approval_result="rejected", operator_jobcode="OP010")
        assert log.description == "报废审批拒绝"
        assert log.operator_jobcode == "OP010"


@pytest.mark.django_db
class TestLogAssetTransferMutants:
    """log_asset_transfer：storage 前后对 + 箭头文案 + 顶层透传。"""

    def test_transfer_storage_pair_and_description(self, asset):
        _asset_with_spec(asset)
        log = OperationLogService.log_asset_transfer(
            asset,
            from_storage="仓A",
            to_storage="仓B",
            operator_jobcode="OP011",
            operator_name="郑十一",
        )
        assert log.before_data == {"asset_storage": "仓A"}
        assert log.after_data == {"asset_storage": "仓B"}
        assert log.description == "资产转移: 仓A → 仓B"
        assert log.operation_type == AssetOperationLog.OperationType.TRANSFER
        assert log.operator_jobcode == "OP011"
        assert log.operator_name == "郑十一"
        assert log.asset_name == asset.asset_name
        assert log.asset_specification == SPEC

    def test_transfer_none_storage_pair(self, asset):
        log = OperationLogService.log_asset_transfer(asset, from_storage=None, to_storage="仓C")
        assert log.before_data == {"asset_storage": None}
        assert log.after_data == {"asset_storage": "仓C"}
        assert log.description == "资产转移: None → 仓C"


# ────────────────── _insert_operation_log 全字段落库 + logger ──────────────────


@pytest.mark.django_db
class TestInsertOperationLogMutants:
    """_insert_operation_log：全字段落库逐字段断言 + logger.info/error mock。"""

    def test_all_fields_persisted_verbatim(self):
        before = {"k": "v1"}
        after = {"k": "v2"}
        log = OperationLogService.log_operation(
            asset_code="FULL-001",
            operation_type=AssetOperationLog.OperationType.UPDATE,
            description="全字段落库",
            asset_name="全字段资产",
            asset_specification="规格-X",
            operator_jobcode="OP012",
            operator_name="吴十",
            before_data=before,
            after_data=after,
            related_record_code="REL-001",
            related_record_type="update",
            ip_address="10.0.0.1",
        )
        assert log.asset_code == "FULL-001"
        assert log.asset_name == "全字段资产"
        assert log.asset_specification == "规格-X"
        assert log.description == "全字段落库"
        assert log.operator_jobcode == "OP012"
        assert log.operator_name == "吴十"
        assert log.before_data == before
        assert log.after_data == after
        assert log.related_record_code == "REL-001"
        assert log.related_record_type == "update"
        assert log.ip_address == "10.0.0.1"

    def test_operation_type_rejected_when_invalid(self):
        with pytest.raises(ValueError) as ei:
            OperationLogService.log_operation(asset_code="X", operation_type="not_a_type", description="d")
        assert "无效的操作类型" in str(ei.value)

    def test_empty_asset_code_rejected(self):
        with pytest.raises(ValueError) as ei:
            OperationLogService.log_operation(asset_code="", operation_type="create", description="d")
        assert str(ei.value) == "资产编码不能为空"

    def test_logger_info_message_contains_context(self):
        """杀 logger.info(f"...{asset_code}...") → logger.info(None)。"""
        with patch(SERVICE_LOGGER) as mock_logger:
            OperationLogService.log_operation(
                asset_code="LOG-001",
                operation_type="create",
                description="d",
                operator_jobcode="OP-LOG",
            )
            mock_logger.info.assert_called_once()
            msg = mock_logger.info.call_args[0][0]
            assert "LOG-001" in msg
            assert "OP-LOG" in msg

    def test_logger_error_message_reraises(self):
        """杀 logger.error(f"...{e}") → logger.error(None)：patch create 抛错，断言 error 消息含异常文本。"""
        with patch.object(AssetOperationLog.objects, "create", side_effect=RuntimeError("boom")):
            with patch(SERVICE_LOGGER) as mock_logger:
                with pytest.raises(RuntimeError, match="boom"):
                    OperationLogService.log_operation(asset_code="ERR-001", operation_type="create", description="d")
                mock_logger.error.assert_called_once()
                assert "boom" in mock_logger.error.call_args[0][0]


# ────────────────────────── _to_json_safe ──────────────────────────


class TestToJsonSafeMutants:
    """_to_json_safe：四类归一 + 幂等。"""

    def test_dict_recurses_into_items(self):
        payload = {"a": {"b": Decimal("1.50")}, "c": date(2024, 1, 2)}
        assert _to_json_safe(payload) == {"a": {"b": "1.50"}, "c": "2024-01-02"}

    def test_list_and_tuple_recurses_preserving_type(self):
        items = [Decimal("2.5"), date(2024, 3, 4)]
        assert _to_json_safe(items) == ["2.5", "2024-03-04"]
        assert _to_json_safe((Decimal("3.5"),)) == ["3.5"]

    def test_pk_bearing_object_uses_recordcode(self):
        class _Rec:
            pk = 9
            recordcode = "RC-PK"

        assert _to_json_safe({"owner": _Rec()}) == {"owner": "RC-PK"}

    def test_pk_bearing_object_falls_back_to_pk(self):
        class _NoRec:
            pk = 42

        assert _to_json_safe({"owner": _NoRec()}) == {"owner": "42"}

    def test_scalar_decimals_dates_datetimes_uuid(self):
        now = datetime(2024, 5, 6, 7, 8, 9)
        uid = uuid4()
        result = _to_json_safe({"d": Decimal("9.99"), "dt": now, "u": uid, "plain": "s", "n": None})
        assert result == {"d": "9.99", "dt": str(now), "u": str(uid), "plain": "s", "n": None}

    def test_idempotent_on_already_safe_input(self):
        safe = {"a": "1", "b": ["2", "3"]}
        assert _to_json_safe(safe) == safe

    def test_list_inside_dict_with_fk_like_values(self):
        class _Rec:
            pk = 1
            recordcode = "FK1"

        assert _to_json_safe({"owners": [_Rec(), _Rec()]}) == {"owners": ["FK1", "FK1"]}


# ────────────────────────── 查询委托 ──────────────────────────


def _make_scoped_user(username: str, department: Department, phone: str):
    """AuthUser + Employee(regular_user)：部门级行级过滤主体。"""
    user = User.objects.create_user(auth_username=username, password=TEST_PASSWORD)
    Employee.objects.create(
        employee_jobcode=username,
        employee_name=f"{username}员工",
        employee_department=department,
        role=EmployeeRole.REGULAR_USER,
        employee_phone=phone,
    )
    return user


def _make_unrestricted_user(username: str, phone: str):
    """无 Employee 记录的 AuthUser：范围 None（不过滤）。"""
    return User.objects.create_user(auth_username=username, password=TEST_PASSWORD)


def _make_foreign_dept_asset(dept_code: str, dept_name: str, asset_code: str, phone: str):
    """经 storage_manager 三路径归属到指定部门的资产。"""
    dept = Department.objects.create(department_code=dept_code, department_name=dept_name)
    manager = Employee.objects.create(
        employee_jobcode=f"MGR-{dept_code}",
        employee_name=f"{dept_name}仓管",
        employee_department=dept,
        role=EmployeeRole.ASSET_ADMIN,
        employee_phone=phone,
    )
    storage = Storage.objects.create(
        storage_code=f"S-{dept_code}",
        storage_name=f"{dept_name}仓",
        storage_address=f"{dept_name}地址",
        storage_manager=manager,
    )
    atype = AssetType.objects.create(type_code=f"T-{dept_code}", type_name=f"{dept_name}类型")
    return Asset.objects.create(
        asset_code=asset_code,
        asset_name=f"{dept_name}资产",
        asset_purchase_price=1.0,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-01",
        asset_type_recordcode=atype,
        asset_storage_recordcode=storage,
        asset_current_status="in_store",
    )


@pytest.mark.django_db
class TestQueryOperationLogsMutants:
    """query_operation_logs：真实调用 + 过滤断言（含 asset_code/时间窗透传杀伤）。"""

    def test_filters_by_operation_type_and_materializes_list(self, db):
        unrestricted = _make_unrestricted_user("q_admin", "13700000001")
        AssetOperationLog.objects.create(asset_code="Q1", operation_type="create", description="c1")
        AssetOperationLog.objects.create(asset_code="Q2", operation_type="out", description="o1")
        result = OperationLogQueryService.query_operation_logs(unrestricted, operation_type="create")
        assert isinstance(result, list)
        assert [log.asset_code for log in result] == ["Q1"]

    def test_filters_by_asset_code_even_when_operator_matches_both(self, db):
        """杀 asset_code=None/删参：两条同 jobcode，仅按 asset_code 区分。"""
        unrestricted = _make_unrestricted_user("q_admin3", "13700000010")
        AssetOperationLog.objects.create(
            asset_code="QA", operation_type="create", description="d", operator_jobcode="SAME"
        )
        AssetOperationLog.objects.create(
            asset_code="QB", operation_type="create", description="d", operator_jobcode="SAME"
        )
        result = OperationLogQueryService.query_operation_logs(unrestricted, asset_code="QA", operator_jobcode="SAME")
        assert [log.asset_code for log in result] == ["QA"]

    def test_start_time_filters_out_older_logs(self, db):
        """杀 start_time=None/删参：早于窗口的日志必须被排除。"""
        unrestricted = _make_unrestricted_user("q_admin4", "13700000011")
        old_log = AssetOperationLog.objects.create(asset_code="OLD-W", operation_type="create", description="old")
        AssetOperationLog.objects.filter(pk=old_log.pk).update(operation_time=timezone.now() - timedelta(days=3))
        new_log = AssetOperationLog.objects.create(asset_code="NEW-W", operation_type="create", description="new")
        start = timezone.now() - timedelta(days=1)
        result = OperationLogQueryService.query_operation_logs(unrestricted, start_time=start)
        assert [log.pk for log in result] == [new_log.pk]

    def test_end_time_filters_out_newer_logs(self, db):
        """杀 end_time=None/删参：晚于窗口的日志必须被排除。"""
        unrestricted = _make_unrestricted_user("q_admin5", "13700000012")
        old_log = AssetOperationLog.objects.create(asset_code="OLD-E", operation_type="create", description="old")
        AssetOperationLog.objects.filter(pk=old_log.pk).update(operation_time=timezone.now() - timedelta(days=3))
        AssetOperationLog.objects.create(asset_code="NEW-E", operation_type="create", description="new")
        end = timezone.now() - timedelta(days=1)
        result = OperationLogQueryService.query_operation_logs(unrestricted, end_time=end)
        assert [log.pk for log in result] == [old_log.pk]


@pytest.mark.django_db
class TestQueryOperationLogsQuerysetMutants:
    """query_operation_logs_queryset：user→None 会解除行级过滤；时间窗透传。"""

    def test_scoped_user_only_sees_own_department_logs(self, department, db):
        scoped = _make_scoped_user("sc_q", department, "13700000003")
        foreign_asset = _make_foreign_dept_asset("D-FOREIGN", "外部部门", "AF-001", "13700000004")
        AssetOperationLog.objects.create(
            asset_code=foreign_asset.asset_code, operation_type="create", description="外部"
        )
        qs = OperationLogQueryService.query_operation_logs_queryset(scoped)
        assert list(qs) == []

    def test_scoped_user_sees_in_department_log(self, department, asset, user, db):
        scoped = _make_scoped_user("sc_q2", department, "13700000005")
        asset.asset_entry_person_recordcode = user
        asset.save(update_fields=["asset_entry_person_recordcode"])
        AssetOperationLog.objects.create(asset_code=asset.asset_code, operation_type="create", description="本部门")
        qs = OperationLogQueryService.query_operation_logs_queryset(scoped)
        assert [log.asset_code for log in qs] == [asset.asset_code]

    def test_queryset_start_end_time_window(self, db):
        """杀 queryset 层 start_time/end_time=None 或删参。"""
        unrestricted = _make_unrestricted_user("sc_q3", "13700000013")
        old_log = AssetOperationLog.objects.create(asset_code="QS-OLD", operation_type="create", description="old")
        AssetOperationLog.objects.filter(pk=old_log.pk).update(operation_time=timezone.now() - timedelta(days=3))
        AssetOperationLog.objects.create(asset_code="QS-NEW", operation_type="create", description="new")
        qs = OperationLogQueryService.query_operation_logs_queryset(
            unrestricted,
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(hours=1),
        )
        assert [log.asset_code for log in qs] == ["QS-NEW"]


@pytest.mark.django_db
class TestGetRecentOperationsMutants:
    """get_recent_operations：days 默认值 7→8 漂移边界杀伤。"""

    def test_default_days_excludes_older_than_one_week(self, db):
        unrestricted = _make_unrestricted_user("recent_u", "13700000006")
        old_log = AssetOperationLog.objects.create(asset_code="OLD-LOG", operation_type="create", description="old")
        AssetOperationLog.objects.filter(pk=old_log.pk).update(
            operation_time=timezone.now() - timedelta(days=7, hours=12)
        )
        AssetOperationLog.objects.create(asset_code="NEW-LOG", operation_type="create", description="new")
        codes = [log.asset_code for log in OperationLogQueryService.get_recent_operations(unrestricted)]
        assert "NEW-LOG" in codes
        assert "OLD-LOG" not in codes

    def test_explicit_days_widens_window(self, db):
        unrestricted = _make_unrestricted_user("recent_u2", "13700000007")
        old_log = AssetOperationLog.objects.create(asset_code="OLD-LOG2", operation_type="create", description="old")
        AssetOperationLog.objects.filter(pk=old_log.pk).update(
            operation_time=timezone.now() - timedelta(days=7, hours=12)
        )
        codes = [log.asset_code for log in OperationLogQueryService.get_recent_operations(unrestricted, days=8)]
        assert "OLD-LOG2" in codes


@pytest.mark.django_db
class TestGetUserOperationsMutants:
    """get_user_operations：operator_jobcode→None 会改查 NULL 干扰项。"""

    def test_unrestricted_filters_by_jobcode_exactly(self, db):
        unrestricted = _make_unrestricted_user("uo_admin", "13700000014")
        AssetOperationLog.objects.create(
            asset_code="U1", operation_type="create", description="a", operator_jobcode="SAME-OP"
        )
        AssetOperationLog.objects.create(
            asset_code="U2", operation_type="create", description="b", operator_jobcode="OTHER-OP"
        )
        result = OperationLogQueryService.get_user_operations(unrestricted, "SAME-OP")
        assert [log.asset_code for log in result] == ["U1"]

    def test_scoped_user_respects_department_scope(self, department, db):
        scoped = _make_scoped_user("uo_u", department, "13700000008")
        foreign_asset = _make_foreign_dept_asset("D-FO2", "外部二部", "AF-002", "13700000009")
        AssetOperationLog.objects.create(
            asset_code=foreign_asset.asset_code,
            operation_type="create",
            description="外部",
            operator_jobcode="SAME-OP",
        )
        result = OperationLogQueryService.get_user_operations(scoped, "SAME-OP")
        assert result == []
