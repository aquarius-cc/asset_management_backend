"""M-CONC-02 合同删除 TOCTOU 竞态 + 5A 写侧守卫回归测试(CT-4 回归用例)

范围:
- A 组(逻辑守卫,SQLite 可跑): create/update/batch 挂已软删合同 → CONTRACT_NOT_FOUND;
  不挂合同创建守卫零调用(无额外查询)
- B 组(真并发): 合同删除 vs 资产挂接双向竞态——先删后挂/先挂后删,恰一方成立
- C 组(锁形态): delete_contract 强锁 FOR UPDATE;5A 守卫弱锁 FOR NO KEY UPDATE

PG 来源注记: B/C 组仅 PostgreSQL 生效(requires_row_lock 挡 SQLite),
本地可 Docker PG 直连或以 CI 执行为准,SQLite 下 skip 不视为失败。
"""

import threading
import time
from collections.abc import Callable

import pytest
from django.db import connection, connections, transaction
from django.test.utils import CaptureQueriesContext

from apps.assetmanagement.models import Asset, AssetOperationLog
from apps.assetmanagement.selectors import ContractSelector
from apps.assetmanagement.services.asset_service import AssetService
from apps.assetmanagement.services.contract_service import ContractService
from core.exceptions import AppValidationError


# SQLite 不支持 select_for_update 行级锁,真并发/锁形态用例守卫(CI 为 Postgres 照常执行)
requires_row_lock = pytest.mark.skipif(
    connection.vendor == "sqlite",
    reason="SQLite 不支持 select_for_update 行级锁,跳过真并发/锁形态用例(CI 为 Postgres)",
)


def run_in_thread(target: Callable[[], None], errors: list[str]) -> threading.Thread:
    """独立线程执行 target;异常收口进 errors 由主线程断言"""

    def _target() -> None:
        try:
            target()
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
        finally:
            connections.close_all()  # 关闭本线程 DB 连接,防悬挂会话阻塞测试库销毁(跨轮干扰源)

    thread = threading.Thread(target=_target)
    thread.start()
    return thread


def _asset_payload(storage, asset_type, name: str, **overrides):
    data: dict = {
        "asset_name": name,
        "asset_purchase_price": 100.00,
        "asset_purchase_date": "2024-01-01",
        "asset_entry_date": "2024-01-01",
        "asset_storage_recordcode": storage,
        "asset_type_recordcode": asset_type,
    }
    data.update(overrides)
    return data


@pytest.mark.django_db
class TestContractWriteGuard:
    """A 组: 5A 写侧守卫逻辑(SQLite 可跑,竞态防护由 B 组真并发覆盖)"""

    def test_create_asset_stale_contract_rejected(self, contract, storage, asset_type, full_scope_user):
        """create_asset 挂已软删合同 → CONTRACT_NOT_FOUND(守卫在编码生成前抛出,零资产)"""
        contract.delete()
        payload = _asset_payload(storage, asset_type, "挂已删合同", asset_contract_recordcode=contract)

        with pytest.raises(AppValidationError) as exc_info:
            AssetService.create_asset(payload, user=full_scope_user)

        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"
        assert Asset.objects.count() == 0

    def test_update_asset_stale_contract_rejected(self, asset, contract, full_scope_user):
        """update_asset 改挂已软删合同 → CONTRACT_NOT_FOUND,资产不落任何变更"""
        contract.delete()

        with pytest.raises(AppValidationError) as exc_info:
            AssetService.update_asset(
                asset.asset_code,
                {"asset_contract_recordcode": contract},
                user=full_scope_user,
            )

        assert exc_info.value.error_code == "CONTRACT_NOT_FOUND"
        asset.refresh_from_db()
        assert asset.asset_contract_recordcode is None

    def test_batch_create_mixed_stale_contract(self, contract, storage, asset_type, full_scope_user):
        """batch_create_asset 混合一条坏合同 → 该条 fail_items(CONTRACT_NOT_FOUND),其余成功"""
        contract.delete()
        payloads = [
            _asset_payload(storage, asset_type, "批量好1"),
            _asset_payload(storage, asset_type, "批量坏", asset_contract_recordcode=contract),
            _asset_payload(storage, asset_type, "批量好2"),
        ]

        result = AssetService.batch_create_asset(payloads, user=full_scope_user)

        assert result["success_count"] == 2
        assert result["fail_count"] == 1
        assert result["fail_items"][0]["error_code"] == "CONTRACT_NOT_FOUND"
        assert Asset.objects.count() == 2

    def test_create_without_contract_guard_noop(self, monkeypatch, storage, asset_type, full_scope_user):
        """不挂合同创建 → 成功且守卫零调用(无额外查询)"""
        calls: list = []
        monkeypatch.setattr(ContractSelector, "get_contract_for_update_by_instance", lambda c: calls.append(c))

        created = AssetService.create_asset(_asset_payload(storage, asset_type, "无合同资产"), user=full_scope_user)

        assert len(created) == 1
        assert calls == []


@pytest.mark.django_db(transaction=True)
@requires_row_lock
class TestContractDeleteRace:
    """B 组: 合同删除 vs 资产挂接真并发(确定性握手——持锁方先行,另一方确实撞锁)"""

    def test_delete_then_attach_rejected(self, contract, storage, asset_type, full_scope_user):
        """先删后挂: 删除方持强锁先提交 → 挂接方 CONTRACT_NOT_FOUND、零资产零审计"""
        code = contract.contract_code
        errors: list[str] = []
        results: list[str] = []
        ev_locked = threading.Event()
        hold = threading.Event()
        payload = _asset_payload(storage, asset_type, "竞态挂接", asset_contract_recordcode=contract)

        def deleter_work() -> None:
            with transaction.atomic():
                ContractSelector.get_contract_for_update(code)  # 持强锁,制造确定性竞态窗口
                ev_locked.set()
                hold.wait(timeout=5)
                ContractService.delete_contract(code, operator_jobcode="U001", operator_name="删除方")
                results.append("ok")  # 成功方结果须入列(list.append 为原子操作)

        def creator_work() -> None:
            ev_locked.wait(timeout=5)
            time.sleep(0.3)  # 等删除方持锁后才发起,保证确实撞锁
            try:
                AssetService.create_asset(payload, user=full_scope_user)
                results.append("ok")
            except AppValidationError as exc:
                results.append(exc.error_code)

        t_deleter = run_in_thread(deleter_work, errors)
        assert ev_locked.wait(timeout=5), "删除方未能取得合同行锁"
        t_creator = run_in_thread(creator_work, errors)
        time.sleep(0.5)  # 等挂接方阻塞于行锁
        hold.set()
        t_deleter.join(timeout=30)
        t_creator.join(timeout=30)

        assert errors == []
        assert sorted(results) == ["CONTRACT_NOT_FOUND", "ok"]
        assert Asset.objects.count() == 0
        assert AssetOperationLog.objects.count() == 0

    def test_attach_then_delete_rejected(self, contract, storage, asset_type, full_scope_user):
        """先挂后删: 挂接方持弱锁先提交 → 删除方 HAS_RELATED_ASSETS、合同未删、资产存在"""
        code = contract.contract_code
        errors: list[str] = []
        results: list[str] = []
        ev_locked = threading.Event()
        hold = threading.Event()
        payload = _asset_payload(storage, asset_type, "竞态挂接", asset_contract_recordcode=contract)

        def creator_work() -> None:
            with transaction.atomic():
                ContractSelector.get_contract_for_update_by_instance(contract)  # 持弱锁
                ev_locked.set()
                hold.wait(timeout=5)
                AssetService.create_asset(payload, user=full_scope_user)
                results.append("ok")  # 成功方结果须入列(list.append 为原子操作)

        def deleter_work() -> None:
            ev_locked.wait(timeout=5)
            time.sleep(0.3)  # 等挂接方持锁后才发起,保证确实撞锁
            try:
                ContractService.delete_contract(code, operator_jobcode="U002", operator_name="删除方")
                results.append("ok")
            except AppValidationError as exc:
                results.append(exc.error_code)

        t_creator = run_in_thread(creator_work, errors)
        assert ev_locked.wait(timeout=5), "挂接方未能取得合同行锁"
        t_deleter = run_in_thread(deleter_work, errors)
        time.sleep(0.5)  # 等删除方阻塞于行锁
        hold.set()
        t_creator.join(timeout=30)
        t_deleter.join(timeout=30)

        assert errors == []
        assert sorted(results) == ["HAS_RELATED_ASSETS", "ok"]
        assert ContractSelector.get_contract_by_code(code) is not None
        assert Asset.objects.count() == 1


@pytest.mark.django_db
@requires_row_lock
class TestContractLockSqlShape:
    """C 组: 锁形态断言(CaptureQueriesContext 捕获 SQL 锁子句,无需 EXPLAIN)"""

    def test_delete_contract_strong_lock_shape(self, contract):
        """delete_contract 强锁: FOR UPDATE 且不含 NO KEY"""
        with CaptureQueriesContext(connection) as ctx, transaction.atomic():
            ContractService.delete_contract(contract.contract_code, operator_jobcode="U001", operator_name="锁形态")
        lock_sql = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        assert lock_sql, "delete_contract 未发出 FOR UPDATE 强锁"
        assert all("NO KEY" not in sql for sql in lock_sql)

    def test_write_guard_weak_lock_shape(self, asset, contract, full_scope_user):
        """5A 守卫弱锁: FOR NO KEY UPDATE"""
        with CaptureQueriesContext(connection) as ctx, transaction.atomic():
            AssetService.update_asset(
                asset.asset_code,
                {"asset_contract_recordcode": contract},
                user=full_scope_user,
            )
        weak_sql = [q["sql"] for q in ctx.captured_queries if "FOR NO KEY UPDATE" in q["sql"]]
        assert weak_sql, "5A 守卫未发出 FOR NO KEY UPDATE 弱锁"
