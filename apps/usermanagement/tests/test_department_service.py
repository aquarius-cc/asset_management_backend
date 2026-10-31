"""
部门服务覆盖率测试
"""

import threading

import pytest
from django.db import connection, transaction

from apps.usermanagement.models import MAX_DEPARTMENT_LEVEL, Department
from apps.usermanagement.selectors import DepartmentSelector
from apps.usermanagement.services import DepartmentService
from core.exceptions import AppValidationError, BusinessLogicError


ValidationError = AppValidationError

# 【M-27】SQLite 不支持 select_for_update 行级锁,跳过真并发用例(CI 是 Postgres)
requires_row_lock = pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite 不支持 select_for_update 行级锁,跳过真并发用例(CI 是 Postgres)",
)


@pytest.mark.django_db
class TestDepartmentServiceExtra:
    """部门服务边界路径"""

    def test_create_department_duplicate_code(self, department):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": department.department_code,
                    "department_name": "重复部门",
                }
            )
        assert exc_info.value.error_code == "DUPLICATE_DEPARTMENT_CODE"

    def test_create_department_parent_code_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": "D101",
                    "department_name": "子部门",
                    "parent_department_code": "NO_SUCH_PARENT",
                }
            )
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_create_department_parent_rc_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.create_department(
                {
                    "department_code": "D102",
                    "department_name": "子部门",
                    "parent": "NO_SUCH_RECORDCODE",
                }
            )
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_move_department_not_found(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department("NO_SUCH_DEPT", None)
        assert exc_info.value.error_code == "DEPARTMENT_NOT_FOUND"

    def test_move_department_target_not_found(self, department):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department(department.department_code, "NO_SUCH_TARGET")
        assert exc_info.value.error_code == "PARENT_DEPARTMENT_NOT_FOUND"

    def test_move_department_to_self(self, department):
        with pytest.raises(BusinessLogicError) as exc_info:
            DepartmentService.move_department(department.department_code, department.department_code)
        assert exc_info.value.error_code == "CIRCULAR_REFERENCE"

    def test_department_clean_self_parent_rejected(self, department):
        """【CT-4 真缺陷锚】parent FK 指向 recordcode,自引用校验须比对 recordcode 而非 pk。

        修复前 parent_id(str) == pk(int) 恒 False,该校验从未生效。
        """
        from django.core.exceptions import ValidationError as DjangoValidationError

        department.parent = department
        with pytest.raises(DjangoValidationError) as exc_info:
            department.clean()
        assert "不能将自己设为上级部门" in str(exc_info.value)

    def test_move_department_level_exceeded(self, db):
        root = Department.objects.create(
            department_code="LROOT", department_name="根", department_information="", level=0, path="/LROOT"
        )
        moving = Department.objects.create(
            department_code="LMOVE",
            department_name="待移",
            department_information="",
            level=0,
            path="/LMOVE",
        )
        parent = moving
        parent_path = moving.path
        for i in range(MAX_DEPARTMENT_LEVEL + 1):
            child = Department.objects.create(
                department_code=f"LC{i}",
                department_name=f"子{i}",
                department_information="",
                parent=parent,
                level=i + 1,
                path=f"{parent_path}/LC{i}",
            )
            parent = child
            parent_path = child.path

        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.move_department("LMOVE", root.department_code)
        assert exc_info.value.error_code == "DEPARTMENT_LEVEL_EXCEEDED"

    def test_move_department_empty_path_children(self, db):
        target = Department.objects.create(
            department_code="EMPTY_TARGET",
            department_name="目标部门",
            department_information="",
            level=0,
            path="/EMPTY_TARGET",
        )
        empty_path_dept = Department.objects.create(
            department_code="EMPTY1",
            department_name="空路径",
            department_information="",
            parent=target,
            level=1,
            path="",
        )
        assert empty_path_dept.pk is not None

        moved = DepartmentService.move_department("EMPTY1", "EMPTY_TARGET")

        assert moved.parent == target
        assert moved.level == 1
        assert moved.path == "/EMPTY_TARGET/EMPTY1"

    def test_move_department_updates_children(self, db):
        root_a = Department.objects.create(
            department_code="RA", department_name="根A", department_information="", level=0, path="/RA"
        )
        dept_b = Department.objects.create(
            department_code="RB",
            department_name="部门B",
            department_information="",
            parent=root_a,
            level=1,
            path="/RA/RB",
        )
        Department.objects.create(
            department_code="RC",
            department_name="子C",
            department_information="",
            parent=dept_b,
            level=2,
            path="/RA/RB/RC",
        )
        root_x = Department.objects.create(
            department_code="RX", department_name="根X", department_information="", level=0, path="/RX"
        )

        moved = DepartmentService.move_department("RB", root_x.department_code)

        assert moved.path == "/RX/RB"
        child = Department.objects.get(department_code="RC")
        assert child.path == "/RX/RB/RC"
        assert child.level == 2

    def test_batch_update_sort_order_exceed_size(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_update_sort_order(
                [{"department_code": f"D{i}", "sort_order": i} for i in range(101)]
            )
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_create_department_success(self):
        result = DepartmentService.batch_create_department(
            [
                {"department_code": "BC201", "department_name": "批量一"},
                {"department_code": "BC202", "department_name": "批量二"},
            ]
        )

        assert result["success_count"] == 2
        assert result["fail_count"] == 0

    def test_batch_create_department_exceed_size(self):
        items = [{"department_code": f"BC{i:03d}", "department_name": f"部门{i}"} for i in range(101)]

        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_create_department(items)
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_create_department_mixed(self):
        result = DepartmentService.batch_create_department(
            [
                {"department_code": "BC211", "department_name": "有效"},
                {"department_code": "BC211", "department_name": "重复"},
            ]
        )

        assert result["success_count"] == 1
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DUPLICATE_DEPARTMENT_CODE"

    def test_batch_create_department_internal_error(self):
        result = DepartmentService.batch_create_department(
            [{"department_code": "BC221", "department_name": "异常", "invalid_field": "boom"}]
        )

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"

    def test_batch_delete_department_success(self):
        dept = Department.objects.create(department_code="BD301", department_name="待删部门")
        assert dept.pk is not None

        result = DepartmentService.batch_delete_department(["BD301"])

        assert result["success_count"] == 1
        assert Department.objects.filter(department_code="BD301").count() == 0

    def test_batch_delete_department_exceed_size(self):
        with pytest.raises(ValidationError) as exc_info:
            DepartmentService.batch_delete_department([f"D{i}" for i in range(101)])
        assert exc_info.value.error_code == "BATCH_SIZE_EXCEEDED"

    def test_batch_delete_department_not_found(self):
        result = DepartmentService.batch_delete_department(["NO_SUCH_DEPT"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "NOT_FOUND"

    def test_batch_delete_department_has_employees(self, department, test_employee):
        result = DepartmentService.batch_delete_department([department.department_code])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "DEPT_HAS_EMPLOYEES"

    def test_batch_delete_department_has_children(self, department, child_department):
        result = DepartmentService.batch_delete_department([department.department_code])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "HAS_CHILD_DEPARTMENTS"

    def test_batch_delete_department_internal_error(self, monkeypatch):
        dept = Department.objects.create(department_code="BD311", department_name="异常删除")
        assert dept.pk is not None
        original_delete = Department.delete

        def raising_delete(self, *args, **kwargs):
            if self.department_code == "BD311":
                raise RuntimeError("boom")
            return original_delete(self, *args, **kwargs)

        monkeypatch.setattr(Department, "delete", raising_delete)

        result = DepartmentService.batch_delete_department(["BD311"])

        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "INTERNAL_ERROR"


@pytest.mark.django_db
class TestMoveDepartmentRowLock:
    """【M-27】移动部门行锁 + 前态复检"""

    def test_lock_rows_for_move_returns_both_rows(self, db):
        Department.objects.create(
            department_code="LOCKA", department_name="锁A", department_information="", level=0, path="/LOCKA"
        )
        Department.objects.create(
            department_code="LOCKB", department_name="锁B", department_information="", level=0, path="/LOCKB"
        )

        locked = DepartmentSelector.lock_rows_for_move("LOCKA", "LOCKB")

        assert set(locked) == {"LOCKA", "LOCKB"}
        assert locked["LOCKA"].path == "/LOCKA"
        assert locked["LOCKB"].path == "/LOCKB"

    def test_lock_rows_for_move_single_row_when_moving_to_root(self, db):
        Department.objects.create(
            department_code="LOCKR", department_name="锁根", department_information="", level=0, path="/LOCKR"
        )

        locked = DepartmentSelector.lock_rows_for_move("LOCKR", None)

        assert set(locked) == {"LOCKR"}

    def test_lock_rows_for_move_missing_target_absent_from_mapping(self, db):
        Department.objects.create(
            department_code="LOCKM", department_name="锁M", department_information="", level=0, path="/LOCKM"
        )

        locked = DepartmentSelector.lock_rows_for_move("LOCKM", "GHOST_TARGET")

        assert set(locked) == {"LOCKM"}

    def test_move_department_acquires_row_lock(self, department, child_department, monkeypatch):
        """【回归屏障】move_department 必须经 lock_rows_for_move 行锁入口,
        手植去掉锁调用即红。"""
        calls: list[tuple[str, str | None]] = []
        original = DepartmentSelector.lock_rows_for_move

        def spy(department_code: str, target_parent_code: str | None):
            calls.append((department_code, target_parent_code))
            return original(department_code, target_parent_code)

        monkeypatch.setattr(DepartmentSelector, "lock_rows_for_move", spy)

        DepartmentService.move_department(child_department.department_code, department.department_code)

        assert calls == [(child_department.department_code, department.department_code)]

    @requires_row_lock
    def test_move_department_sql_emits_for_update(self, department, child_department):
        """【回归屏障】移动查询必须携带 FOR UPDATE(去掉 select_for_update 即红)"""
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            DepartmentService.move_department(child_department.department_code, department.department_code)

        assert any("FOR UPDATE" in q["sql"] for q in ctx.captured_queries), "行锁查询未发出 FOR UPDATE"


@pytest.mark.django_db(transaction=True)
class TestMoveDepartmentConcurrency:
    """【M-27】互换移动真并发(PG)"""

    @requires_row_lock
    def test_concurrent_swap_move_cannot_form_cycle(self):
        """A→B 与 B→A 并发:定序行锁串行化 + 锁内复检,
        恰一方成功、另一方 CIRCULAR_REFERENCE,终态无环。"""
        Department.objects.create(
            department_code="SWA", department_name="甲部门", department_information="", level=0, path="/SWA"
        )
        Department.objects.create(
            department_code="SWB", department_name="乙部门", department_information="", level=0, path="/SWB"
        )

        results: list[str] = []

        def move(src: str, dst: str) -> None:
            try:
                with transaction.atomic():
                    DepartmentService.move_department(src, dst)
                results.append(f"{src}->{dst}:ok")
            except Exception as exc:
                results.append(f"{src}->{dst}:{type(exc).__name__}:{getattr(exc, 'error_code', '')}")

        t1 = threading.Thread(target=move, args=("SWA", "SWB"))
        t2 = threading.Thread(target=move, args=("SWB", "SWA"))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        ok = [r for r in results if r.endswith(":ok")]
        failed = [r for r in results if not r.endswith(":ok")]
        assert len(ok) == 1, f"互换移动应恰一方成功: {results}"
        assert len(failed) == 1 and "CIRCULAR_REFERENCE" in failed[0], results

        # 终态无环:沿 parent 链走到根,不得自闭合
        node = Department.objects.get(department_code="SWA")
        seen: set[str] = set()
        while node is not None:
            assert node.department_code not in seen, f"终态存在环: {results}"
            seen.add(node.department_code)
            node = node.parent


@pytest.mark.django_db
class TestCollectAncestorRecordcodesLogging:
    """BF-160/M-47: 祖先收集 DoesNotExist 分支补 warning 日志(原裸 pass)"""

    def test_missing_ancestor_logs_warning(self, caplog):
        import logging

        from apps.usermanagement.services.department_service import logger as svc_logger

        with caplog.at_level(logging.WARNING, logger=svc_logger.name):
            codes = DepartmentService._collect_ancestor_recordcodes("/no/such/path")
        assert codes == []
        records = [r for r in caplog.records if "祖先部门不存在" in r.getMessage()]
        assert len(records) >= 1
        assert "ancestor_path=/no" in records[0].getMessage()

    def test_existing_ancestor_no_warning(self, department, caplog):
        import logging

        from apps.usermanagement.services.department_service import logger as svc_logger

        parent = Department.objects.create(
            department_code="DEPT_LOG_PARENT",
            department_name="日志父部门",
            path=f"/{department.recordcode}" if hasattr(department, "recordcode") else "/P1",
            level=1,
        )
        path = f"/{parent.path.strip('/')}/CHILD"
        with caplog.at_level(logging.WARNING, logger=svc_logger.name):
            DepartmentService._collect_ancestor_recordcodes(path)
        assert not [r for r in caplog.records if "祖先部门不存在" in r.getMessage()]


@pytest.mark.django_db
class TestDepartmentSaveCacheInvalidation:
    """[M-11] models.save 祖先缓存批量失效（save 后失效，竞态自愈口径）

    缺陷史：原内联循环拼 ancestor_path 缺前导 '/' → Department.objects.get 永不命中
    → except DoesNotExist: pass 吞异常 → 祖先缓存从未失效（每次整树重查）。
    修复：save 后经 DepartmentService._collect_ancestor_recordcodes + _invalidate_ancestors_cache
    （delete_many 唯一失效点，DR-1）。
    """

    def test_save_invalidates_ancestor_descendants_cache(self, department):
        from django.core.cache import cache

        parent = Department.objects.create(
            department_code="M11_PARENT",
            department_name="M11父部门",
            path=f"/{department.recordcode}",
            level=1,
        )
        child = Department(
            department_code="M11_CHILD",
            department_name="M11子部门",
            parent=parent,
            path=f"/{department.recordcode}/{parent.recordcode}",
            level=2,
        )
        child.save()
        # 预置祖先与自身的后代缓存
        ancestor_key = f"dept:{parent.recordcode}:descendants"
        cache.set(ancestor_key, ["stale-ancestor-list"])
        cache.set(f"dept:{child.recordcode}:descendants", ["stale-self-list"])

        child.save()  # 触发 save 缓存失效逻辑

        # 红：原实现 ancestor_path 缺前导 '/' → 祖先键从未被清
        assert cache.get(ancestor_key) is None
        assert cache.get(f"dept:{child.recordcode}:descendants") is None

    def test_save_with_dirty_path_logs_warning(self, caplog):
        import logging

        from apps.usermanagement.services.department_service import logger as svc_logger

        orphan = Department(
            department_code="M11_ORPHAN",
            department_name="M11脏路径部门",
            path="/no/such/ancestor/ORPHAN",
            level=3,
        )
        with caplog.at_level(logging.WARNING, logger=svc_logger.name):
            orphan.save()
        records = [r for r in caplog.records if "祖先部门不存在" in r.getMessage()]
        assert len(records) >= 1
        assert "ancestor_path=/no" in records[0].getMessage()
