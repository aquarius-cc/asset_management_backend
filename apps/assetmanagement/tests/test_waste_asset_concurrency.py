"""M-CONC-01 报废取消并发一致性回归测试(CT-4 回归用例)

范围:
- B 组(真并发): 报废取消双请求——服务层 + 单条 DELETE 端点,恰一成功、DELETE 审计恰 1 条
- C 组(锁形态): cancel_waste_asset 行锁 SQL 含 FOR UPDATE 且不含 NO KEY
- 路由回归: 单条 DELETE 端点走 Service 并写业务审计(此前 DRF 默认删除无锁无审计)

竞态口径留痕: 竞态下失败方返回 400 WASTE_ASSET_NOT_FOUND(非 404;404 仅来自
get_object 路径),端点断言按 4xx 口径,防后续误判缺陷。
PG 来源注记: 真并发/锁形态用例仅 PostgreSQL 生效(requires_row_lock 挡 SQLite),
本地可 Docker PG 直连或以 CI 执行为准,SQLite 下 skip 不视为失败。
"""

import threading
import time
from collections.abc import Callable
from datetime import date

import pytest
from django.db import connection, connections, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.assetmanagement.models import Asset, AssetOperationLog, DamagedAsset, WasteAsset
from apps.assetmanagement.selectors.waste_asset_selector import WasteAssetSelector
from apps.assetmanagement.services.waste_asset_service import WasteAssetService
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


@pytest.fixture
def scrapped_waste_asset(storage, asset_type):
    """已报废(scrapped)资产 + WasteAsset 记录"""
    asset = Asset.objects.create(
        asset_code="A_CONC_W",
        asset_name="并发取消报废资产",
        asset_purchase_price=100.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-01",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="scrapped",
    )
    damaged = DamagedAsset.objects.create(asset_recordcode=asset, damaged_asset_number=1, approval_status="approved")
    WasteAsset.objects.create(
        asset_recordcode=asset,
        damaged_recordcode=damaged,
        waste_asset_number=1,
        waste_asset_date=date.today(),
    )
    return asset


@pytest.mark.django_db(transaction=True)
class TestWasteCancelConcurrency:
    """B 组: 双请求并发竞态(确定性握手——胜者持行锁后败者才发起,保证确实撞锁)"""

    @requires_row_lock
    def test_concurrent_cancel_service_single_audit(self, scrapped_waste_asset, full_scope_user):
        """服务层双请求取消报废 → 恰一成功、失败方 WASTE_ASSET_NOT_FOUND、DELETE 审计恰 1 条"""
        code = scrapped_waste_asset.asset_code
        errors: list[str] = []
        results: list[str] = []
        ev_locked = threading.Event()
        hold = threading.Event()

        def winner_work() -> None:
            with transaction.atomic():
                WasteAssetSelector.get_for_update_by_asset_code(code)  # 持行锁,制造确定性竞态窗口
                ev_locked.set()
                hold.wait(timeout=5)
                WasteAssetService.cancel_waste_asset(
                    code, operator_jobcode="U001", operator_name="胜者", user=full_scope_user
                )
                results.append("ok")  # 胜者成功结果须入列(list.append 为原子操作)

        def loser_work() -> None:
            ev_locked.wait(timeout=5)
            time.sleep(0.3)  # 等胜者持锁后才发起,保证挑战者确实撞锁
            try:
                WasteAssetService.cancel_waste_asset(
                    code, operator_jobcode="U002", operator_name="败者", user=full_scope_user
                )
                results.append("ok")
            except AppValidationError as exc:
                results.append(exc.error_code)

        t_winner = run_in_thread(winner_work, errors)
        assert ev_locked.wait(timeout=5), "胜者未能取得行锁"
        t_loser = run_in_thread(loser_work, errors)
        time.sleep(0.5)  # 等败者阻塞于行锁
        hold.set()
        t_winner.join(timeout=30)
        t_loser.join(timeout=30)

        assert errors == []
        assert sorted(results) == ["WASTE_ASSET_NOT_FOUND", "ok"]
        assert WasteAsset.all_objects.get(asset_recordcode__asset_code=code).is_deleted is True
        assert AssetOperationLog.objects.filter(asset_code=code, operation_type="delete").count() == 1

    @requires_row_lock
    def test_concurrent_delete_endpoint_200_and_4xx(self, scrapped_waste_asset, full_scope_user):
        """单条 DELETE 端点双请求 → 1×200、1×4xx、审计恰 1 条、恰一次软删"""
        code = scrapped_waste_asset.asset_code
        url = reverse("waste-assets-detail", kwargs={"asset_recordcode__asset_code": code})
        errors: list[str] = []
        results: dict[str, int] = {}
        results_lock = threading.Lock()
        ev_locked = threading.Event()
        hold = threading.Event()

        def winner_work() -> None:
            with transaction.atomic():
                WasteAssetSelector.get_for_update_by_asset_code(code)  # 持行锁,制造确定性竞态窗口
                ev_locked.set()
                hold.wait(timeout=5)
                client = APIClient()
                client.force_authenticate(user=full_scope_user)
                status_code = client.delete(url).status_code  # 请求须在 results_lock 外发起,防与行锁形成锁序死锁
                with results_lock:
                    results["winner"] = status_code

        def loser_work() -> None:
            ev_locked.wait(timeout=5)
            time.sleep(0.3)  # 等胜者持锁后才发起,保证挑战者确实撞锁
            client = APIClient()
            client.force_authenticate(user=full_scope_user)
            status_code = client.delete(url).status_code  # 发起请求必须在 results_lock 外
            with results_lock:
                results["loser"] = status_code

        t_winner = run_in_thread(winner_work, errors)
        assert ev_locked.wait(timeout=5), "胜者未能取得行锁"
        t_loser = run_in_thread(loser_work, errors)
        time.sleep(0.5)  # 等败者阻塞于行锁
        hold.set()
        t_winner.join(timeout=30)
        t_loser.join(timeout=30)

        assert errors == []
        assert results.get("winner") == 200
        assert results.get("loser") is not None
        assert 400 <= results["loser"] < 500  # 竞态失败方 4xx(400 WASTE_ASSET_NOT_FOUND),非 404
        assert WasteAsset.all_objects.get(asset_recordcode__asset_code=code).is_deleted is True
        assert AssetOperationLog.objects.filter(asset_code=code, operation_type="delete").count() == 1

    @requires_row_lock
    def test_cancel_lock_sql_shape(self, scrapped_waste_asset, full_scope_user):
        """C 组: cancel_waste_asset 行锁 SQL 形态——强锁 FOR UPDATE 且不含 NO KEY"""
        code = scrapped_waste_asset.asset_code
        with CaptureQueriesContext(connection) as ctx, transaction.atomic():
            WasteAssetService.cancel_waste_asset(
                code, operator_jobcode="U001", operator_name="锁形态", user=full_scope_user
            )
        lock_sql = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"]]
        assert lock_sql, "cancel_waste_asset 未发出 FOR UPDATE 行锁"
        assert all("NO KEY" not in sql for sql in lock_sql)


@pytest.mark.django_db
class TestWasteDeleteEndpointRouting:
    """路由回归: 单条 DELETE 端点此前走 DRF 默认 instance.delete()(无锁无审计)"""

    def test_delete_route_writes_business_audit(self, scrapped_waste_asset, full_scope_user):
        """DELETE 后写业务审计恰好 1 条,响应 200 信封契约不变"""
        code = scrapped_waste_asset.asset_code
        client = APIClient()
        client.force_authenticate(user=full_scope_user)
        url = reverse("waste-assets-detail", kwargs={"asset_recordcode__asset_code": code})

        resp = client.delete(url)

        assert resp.status_code == 200
        assert WasteAsset.all_objects.get(asset_recordcode__asset_code=code).is_deleted is True
        assert AssetOperationLog.objects.filter(asset_code=code, operation_type="delete").count() == 1
