"""
合同管理 ViewSet API 测试

测试 ContractViewSet 的 API 端点:
- list
- create
- retrieve
- update
- partial_update
- destroy
- 自定义 actions: batch_create, batch_delete, getcontractByname, statistics, update_settlement_status,
  payment_record, payment_record_batch, global_search
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import Contract
from core.models_audit import AuditLog


@pytest.fixture
def authenticated_client(api_client, auth_user):
    """已认证的用户客户端"""
    api_client.force_authenticate(user=auth_user)
    return api_client


@pytest.fixture
def admin_authenticated_client(api_client, admin_auth_user):
    """管理员用户客户端"""
    api_client.force_authenticate(user=admin_auth_user)
    return api_client


@pytest.mark.django_db
class TestContractViewSet:
    """ContractViewSet API 测试"""

    def test_list_contracts(self, authenticated_client, contract):
        """测试获取合同列表"""
        url = reverse("contracts-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_contract(self, admin_authenticated_client):
        """测试创建合同"""
        url = reverse("contracts-list")
        data = {
            "contract_code": "C002",
            "contract_name": "新合同",
            "contract_amount": 20000.00,
            "contract_status": "purchasing",
            "contract_type": "service",
            "contract_start_date": "2024-03-01",
            "contract_end_date": "2025-03-01",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        assert response.data["data"]["contract_code"] == "C002"

    def test_retrieve_contract(self, authenticated_client, contract):
        """测试获取合同详情"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract_code"] == contract.contract_code

    def test_update_contract(self, admin_authenticated_client, contract):
        """测试更新合同"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        data = {"contract_name": "更新后的合同名称"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract_name"] == "更新后的合同名称"

    def test_partial_update_contract(self, admin_authenticated_client, contract):
        """测试部分更新合同"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        data = {"contract_name": "部分更新后的合同名称"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract_name"] == "部分更新后的合同名称"

    def test_destroy_contract(self, admin_authenticated_client, contract):
        """测试删除合同"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not Contract.objects.filter(recordcode=contract.recordcode).exists()

    def test_destroy_nonexistent_contract_returns_404(self, admin_authenticated_client):
        """【CT-4 回归屏障】删除不存在的合同应返回 404 而非 500,验证全局异常处理器接管 Http404"""
        url = reverse("contracts-detail", kwargs={"recordcode": "CT-NOT-EXIST"})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_batch_create(self, admin_authenticated_client):
        """测试批量创建合同"""
        url = reverse("contracts-batch-create")
        data = {
            "items": [
                {
                    "contract_code": "BATCH001",
                    "contract_name": "批量合同1",
                    "contract_amount": 30000.00,
                    "contract_status": "purchasing",
                    "contract_type": "service",
                    "contract_start_date": "2024-04-01",
                    "contract_end_date": "2025-04-01",
                },
            ]
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1

    def test_batch_delete(self, admin_authenticated_client, contract):
        """测试批量删除合同"""
        url = reverse("contracts-batch-delete")
        data = {"ids": [contract.contract_code]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1

    def test_getcontractByname(self, authenticated_client, contract):
        """测试按名称搜索合同"""
        url = reverse("contracts-getcontractByname", kwargs={"name": contract.contract_name})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]

    def test_statistics(self, authenticated_client):
        """测试合同统计"""
        url = reverse("contracts-statistics")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0

    def test_update_settlement_status(self, admin_authenticated_client, contract):
        """测试更新结算状态(需遵循合同状态机流转规则)"""
        url = reverse("contracts-update-settlement-status", kwargs={"recordcode": contract.recordcode})
        # 从 purchasing 合法流转到 purchase_finished
        data = {"status": "purchase_finished"}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract"]["contract_status"] == "purchase_finished"

    def test_payment_record(self, admin_authenticated_client, contract):
        """测试添加付款记录"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        data = {"amount": 5000.00, "description": "测试付款"}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract"]["amount_paid"] == "5000.00"

    def test_payment_record_cumulative_precision(self, admin_authenticated_client, contract):
        """【CT-4 回归屏障】三次 0.1 付款必须精确累计为 0.3,禁止二进制浮点漂移"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        for _ in range(3):
            response = admin_authenticated_client.post(url, {"amount": "0.1"}, format="json")
            assert response.status_code == status.HTTP_200_OK
        contract.refresh_from_db()
        assert contract.amount_paid == Decimal("0.3")

    def test_payment_record_rejects_garbage(self, admin_authenticated_client, contract):
        """【CT-4 回归屏障】非数值金额返回 400 而非 500"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(url, {"amount": "abc"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] != 0

    def test_payment_record_rejects_nan(self, admin_authenticated_client, contract):
        """【CT-4 回归屏障】NaN 金额必须被 is_finite 拦截为 400,禁止穿透落库"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(url, {"amount": "nan"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_record_rejects_inf(self, admin_authenticated_client, contract):
        """【CT-4 回归屏障】Inf 金额必须被 is_finite 拦截为 400,禁止穿透落库"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(url, {"amount": "inf"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_record_rejects_overflow(self, admin_authenticated_client, contract):
        """【CT-4 回归屏障】超 DecimalField(max_digits=12) 上限的金额必须 400,禁止 DB DataError 500"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(url, {"amount": "1e10"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_global_search(self, authenticated_client, contract):
        """测试全局搜索合同"""
        url = reverse("contracts-global-search")
        response = authenticated_client.get(url, {"keyword": contract.contract_name})
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]

    def test_payment_record_accepts_date_and_method(self, admin_authenticated_client, contract):
        """BF-054:历史付款可回填真实发生日期与支付方式"""
        url = reverse("contracts-payment-record", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(
            url,
            {"amount": "1000.00", "payment_date": "2023-05-01", "payment_method": "check"},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        entry = json.loads(contract.__class__.objects.get(recordcode=contract.recordcode).paid_record)["payments"][0]
        assert entry["date"] == "2023-05-01"
        assert entry["payment_method"] == "check"

    def test_payment_record_batch_backfill_lands_approved(self, admin_authenticated_client, contract):
        """BF-054:批量回填一次请求完成,条目内部 add→approve 落 approved"""
        url = reverse("contracts-payment-record-batch", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(
            url,
            {"items": [{"amount": "1000.00", "description": "首付款"}, {"amount": "2000.00"}]},
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 2
        assert response.data["data"]["fail_count"] == 0
        assert response.data["data"]["contract"]["amount_paid"] == "3000.00"
        payments = json.loads(response.data["data"]["contract"]["paid_record"])["payments"]
        assert [p["status"] for p in payments] == ["approved", "approved"]

    def test_payment_record_batch_rejects_status_param(self, admin_authenticated_client, contract):
        """Q-C:status 不开放为入参,客户端无法伪造审批状态"""
        url = reverse("contracts-payment-record-batch", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(
            url, {"items": [{"amount": "1000.00", "status": "approved"}]}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        payments = json.loads(response.data["data"]["contract"]["paid_record"])["payments"]
        assert payments[0]["status"] == "approved"

    def test_payment_record_batch_rejects_bad_date(self, admin_authenticated_client, contract):
        """日期格式非法必须 400,禁止静默落库"""
        url = reverse("contracts-payment-record-batch", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.post(
            url, {"items": [{"amount": "1000.00", "payment_date": "05/01/2023"}]}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_payment_record_batch_requires_admin(self, authenticated_client, contract):
        """写操作须 IsSystemAdmin+,与既有 payment_record 端点同档"""
        url = reverse("contracts-payment-record-batch", kwargs={"recordcode": contract.recordcode})
        response = authenticated_client.post(url, {"items": [{"amount": "1.00"}]}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_payment_record_batch_requires_auth(self, api_client, contract):
        url = reverse("contracts-payment-record-batch", kwargs={"recordcode": contract.recordcode})
        response = api_client.post(url, {"items": [{"amount": "1.00"}]}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_contract_amount_paid_becomes_opening_record(self, admin_authenticated_client):
        """2a:创建时 amount_paid 为期初已付输入,落为一条 approved 期初记录"""
        url = reverse("contracts-list")
        response = admin_authenticated_client.post(
            url,
            {
                "contract_code": "C-OPEN-001",
                "contract_name": "期初已付合同",
                "contract_amount": "10000.00",
                "amount_paid": "3000.00",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["amount_paid"] == "3000.00"
        assert response.data["data"]["amount_unpaid"] == "7000.00"

    def test_update_contract_amount_paid_is_read_only(self, admin_authenticated_client, contract):
        """Q-B:Update 入口三字段全只读,直写应被拒绝而非静默生效"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.patch(
            url, {"amount_paid": "9999.00", "amount_unpaid": "1.00"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        contract.refresh_from_db()
        assert contract.amount_paid == Decimal("0")


@pytest.mark.django_db
class TestContractAuditLogOperator:
    def test_destroy_records_operator(self, admin_authenticated_client, contract):
        """删除合同后审计日志应记录操作人"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        log = AuditLog.objects.filter(
            record_code=contract.contract_code,
            operation_type="delete",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.operator_jobcode is not None

    def test_batch_delete_records_operator(self, admin_authenticated_client, contract):
        """批量删除合同后审计日志应记录操作人"""
        url = reverse("contracts-batch-delete")
        data = {"ids": [contract.contract_code]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        log = AuditLog.objects.filter(
            record_code=contract.contract_code,
            operation_type="delete",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.operator_jobcode is not None

    def test_create_records_operator(self, admin_authenticated_client):
        """单条创建必须经 Service,创建审计日志不得缺失(B-5 同型)"""
        url = reverse("contracts-list")
        response = admin_authenticated_client.post(
            url,
            {"contract_code": "C-AUDIT-001", "contract_name": "审计合同", "contract_amount": "1000.00"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        log = AuditLog.objects.filter(
            record_code="C-AUDIT-001",
            operation_type="create",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.operator_jobcode is not None

    def test_update_settlement_status_records_operator(self, admin_authenticated_client, contract):
        """更新合同状态后审计日志应记录操作人"""
        url = reverse("contracts-update-settlement-status", kwargs={"recordcode": contract.recordcode})
        data = {"status": "purchase_finished"}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        log = AuditLog.objects.filter(
            record_code=contract.contract_code,
            operation_type="update",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.operator_jobcode is not None
