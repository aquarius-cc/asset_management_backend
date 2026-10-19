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
from apps.assetmanagement.services import ContractService
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


@pytest.mark.django_db
class TestCreateContractStatusGateHTTP:
    """【BF-107 / AUD-04】创建期状态收口 HTTP 层: 合法终态放行 + 状态入创建审计 + 非法态 400"""

    def test_create_terminal_status_accepted_and_audited(self, admin_authenticated_client):
        """方案②: 创建允许终态(导入回填历史状态),但须落状态审计"""
        url = reverse("contracts-list")
        data = {
            "contract_code": "C-BF107",
            "contract_name": "BF-107 终态合同",
            "contract_amount": 1000.00,
            "contract_status": "project_finished",
            "contract_type": "service",
            "contract_start_date": "2024-04-01",
            "contract_end_date": "2025-04-01",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        log = AuditLog.objects.filter(
            record_code="C-BF107",
            operation_type="create",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.after_data is not None
        assert log.after_data["contract_status"] == "project_finished"

    def test_create_invalid_status_rejected(self, admin_authenticated_client):
        """非法状态由序列化器 ChoiceField 拦截为 400"""
        url = reverse("contracts-list")
        data = {
            "contract_code": "C-BF107X",
            "contract_name": "BF-107 非法状态",
            "contract_amount": 1000.00,
            "contract_status": "bogus",
            "contract_type": "service",
            "contract_start_date": "2024-04-01",
            "contract_end_date": "2025-04-01",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_batch_create_terminal_status_shared_path(self, admin_authenticated_client):
        """批量端点共享 create_contract 路径,终态经闸并记审计"""
        url = reverse("contracts-batch-create")
        data = {
            "items": [
                {
                    "contract_code": "BATCH-BF107",
                    "contract_name": "BF-107 批量终态",
                    "contract_amount": 30000.00,
                    "contract_status": "project_finished",
                    "contract_type": "service",
                    "contract_start_date": "2024-04-01",
                    "contract_end_date": "2025-04-01",
                },
            ]
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["success_count"] == 1
        log = AuditLog.objects.filter(
            record_code="BATCH-BF107",
            operation_type="create",
            app_label="contract",
        ).first()
        assert log is not None
        assert log.after_data is not None
        assert log.after_data["contract_status"] == "project_finished"


@pytest.mark.django_db
class TestPutContractStatusRouting:
    """【P1-01】PUT/PATCH 携带 contract_status 必须改路由 ContractService.update_settlement_status

    修复前: ContractUpdateSerializer 的 contract_status 可写且不在 read_only_fields,
    前端 ContractForm 编辑恒提交该字段 → 生产路径上任意状态跳转均被接受:
    不过 ContractFSM.transition、不落 GenericAuditService.log_update、
    状态变更不触发 _recalc_paid_amounts(amount_unpaid 滞留旧口径)。
    """

    @pytest.fixture
    def admin_client(self, api_client, admin_auth_user):
        api_client.force_authenticate(user=admin_auth_user)
        return api_client

    @pytest.fixture
    def project_settlement_contract(self, db):
        """project_settlement 状态 + 结算价 8000 + 已付 3000,用于验证状态变更触发金额重算"""
        c = ContractService.create_contract(
            {
                "contract_code": "C-PUT-001",
                "contract_name": "P1-01 合同",
                "contract_type": "service",
                "contract_amount": Decimal("10000.00"),
                "settlemented_price": Decimal("8000.00"),
                "supplier_name": "供应商A",
                "contract_start_date": "2024-01-01",
                "contract_end_date": "2024-12-31",
                "contract_status": "purchase_finished",
            }
        )
        for target in ("receive_check", "initial_check", "project_settlement"):
            ContractService.update_settlement_status(c.contract_code, target)
        ContractService.add_payment_record(c.contract_code, Decimal("3000.00"), "首付款")
        c.refresh_from_db()
        return c

    @staticmethod
    def _update_logs(contract: Contract):
        return AuditLog.objects.filter(
            record_code=contract.contract_code,
            operation_type="update",
            app_label="contract",
        )

    def test_put_status_change_routed_with_audit_and_recalc(self, admin_client, project_settlement_contract):
        """合法状态变更:走 Service(FSM+审计+重算),同批落其余字段,响应带新状态"""
        assert project_settlement_contract.amount_unpaid == Decimal("7000.00")  # 非结算口径 10000-3000
        url = reverse("contracts-detail", kwargs={"recordcode": project_settlement_contract.recordcode})
        response = admin_client.put(
            url, {"contract_status": "settlement_done", "contract_name": "改名后的P1-01"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["contract_status"] == "settlement_done"
        assert response.data["data"]["contract_name"] == "改名后的P1-01"

        project_settlement_contract.refresh_from_db()
        # 状态进入结算口径 → _recalc_paid_amounts 以 settlemented_price 重算
        assert project_settlement_contract.amount_unpaid == Decimal("5000.00")
        log = (
            self._update_logs(project_settlement_contract)
            .filter(after_data={"contract_status": "settlement_done"})
            .first()
        )
        assert log is not None
        assert log.before_data == {"contract_status": "project_settlement"}
        assert log.operator_jobcode is not None

    def test_put_illegal_transition_400_and_rolls_back(self, admin_client, project_settlement_contract):
        """非法跳转:400 + INVALID_CONTRACT_TRANSITION,且同请求其余字段不部分落库"""
        baseline_logs = self._update_logs(project_settlement_contract).count()  # 夹具推进状态已产生 3 条
        url = reverse("contracts-detail", kwargs={"recordcode": project_settlement_contract.recordcode})
        response = admin_client.put(
            url, {"contract_status": "purchasing", "contract_name": "非法跳转带入的改名"}, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] != 0
        assert response.data["data"]["error_code"] == "INVALID_CONTRACT_TRANSITION"
        assert "合同状态转换不合法" in response.data["message"]

        project_settlement_contract.refresh_from_db()
        assert project_settlement_contract.contract_status == "project_settlement"
        assert project_settlement_contract.contract_name == "P1-01 合同"  # 事务回滚,未部分落库
        assert project_settlement_contract.amount_unpaid == Decimal("7000.00")
        assert self._update_logs(project_settlement_contract).count() == baseline_logs

    def test_put_without_status_field_is_plain_edit(self, admin_client, project_settlement_contract):
        """不含状态字段的 PUT:行为与现状一致(纯编辑,不产生状态审计)"""
        baseline_logs = self._update_logs(project_settlement_contract).count()
        url = reverse("contracts-detail", kwargs={"recordcode": project_settlement_contract.recordcode})
        response = admin_client.put(url, {"contract_name": "纯编辑改名"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        project_settlement_contract.refresh_from_db()
        assert project_settlement_contract.contract_name == "纯编辑改名"
        assert project_settlement_contract.contract_status == "project_settlement"
        assert project_settlement_contract.amount_unpaid == Decimal("7000.00")
        assert self._update_logs(project_settlement_contract).count() == baseline_logs

    def test_put_same_status_skips_transition_audit(self, admin_client, project_settlement_contract):
        """同状态提交(无实际变更):跳过状态路由,避免无意义审计记录"""
        baseline_logs = self._update_logs(project_settlement_contract).count()
        url = reverse("contracts-detail", kwargs={"recordcode": project_settlement_contract.recordcode})
        response = admin_client.put(
            url, {"contract_status": "project_settlement", "contract_name": "同状态改名"}, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        project_settlement_contract.refresh_from_db()
        assert project_settlement_contract.contract_name == "同状态改名"
        assert project_settlement_contract.contract_status == "project_settlement"
        assert self._update_logs(project_settlement_contract).count() == baseline_logs

    def test_put_walks_entire_contract_fsm(self, admin_client, db):
        """【CT-3】经 PUT 收口路径走完 ContractFSM 全部 7 条合法边,终态后再流转必须 400"""
        c = ContractService.create_contract(
            {
                "contract_code": "C-PUT-FSM",
                "contract_name": "CT-3 全路径合同",
                "contract_type": "service",
                "contract_amount": Decimal("10000.00"),
                "contract_status": "purchasing",
            }
        )
        url = reverse("contracts-detail", kwargs={"recordcode": c.recordcode})
        legal_path = [
            "purchase_finished",
            "receive_check",
            "initial_check",
            "project_settlement",
            "settlement_done",
            "final_check",
            "project_finished",
        ]
        for target in legal_path:
            response = admin_client.put(url, {"contract_status": target}, format="json")
            assert response.status_code == status.HTTP_200_OK, target
            c.refresh_from_db()
            assert c.contract_status == target
        # 7 条合法边各产生且仅产生一条状态审计
        assert self._update_logs(c).count() == len(legal_path)

        # project_finished 为终态,再流转一律拒绝且不留审计
        response = admin_client.put(url, {"contract_status": "purchasing"}, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["data"]["error_code"] == "INVALID_CONTRACT_TRANSITION"
        assert self._update_logs(c).count() == len(legal_path)


@pytest.mark.django_db
class TestAllowedNextStatesField:
    """【P3-04】allowed_next_states 展示字段下发口径

    ContractDetailSerializer 经 FSM 单实现取合法出边;PUT/PATCH 走
    ContractUpdateSerializer 不含该字段(前端不得依赖 update 响应刷新出边)。
    """

    @pytest.fixture
    def client(self, api_client, auth_user):
        api_client.force_authenticate(user=auth_user)
        return api_client

    @pytest.fixture
    def admin_client(self, api_client, admin_auth_user):
        api_client.force_authenticate(user=admin_auth_user)
        return api_client

    def test_retrieve_returns_single_edge(self, client, contract):
        """非终态详情:返回唯一合法下一状态"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["allowed_next_states"] == ["purchase_finished"]

    @pytest.mark.parametrize(
        ("walk_to", "expected"),
        [
            ("purchase_finished", ["receive_check"]),
            ("project_settlement", ["settlement_done"]),
            ("final_check", ["project_finished"]),
        ],
    )
    def test_retrieve_returns_expected_edge_per_state(self, client, db, walk_to, expected):
        """【参数化 3 点】中途各状态详情出边与状态机表一致"""
        c = ContractService.create_contract(
            {
                "contract_code": f"C-ANS-{walk_to}",
                "contract_name": "P3-04 出边合同",
                "contract_type": "service",
                "contract_amount": Decimal("10000.00"),
                "contract_status": "purchasing",
            }
        )
        for target in (
            "purchase_finished",
            "receive_check",
            "initial_check",
            "project_settlement",
            "settlement_done",
            "final_check",
        ):
            ContractService.update_settlement_status(c.contract_code, target)
            if target == walk_to:
                break
        url = reverse("contracts-detail", kwargs={"recordcode": c.recordcode})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["contract_status"] == walk_to
        assert response.data["data"]["allowed_next_states"] == expected

    def test_terminal_state_returns_empty_list(self, client, db):
        """终态详情:出边为空数组(前端据此禁用下拉)"""
        c = ContractService.create_contract(
            {
                "contract_code": "C-ANS-TERM",
                "contract_name": "P3-04 终态合同",
                "contract_type": "service",
                "contract_amount": Decimal("10000.00"),
                "contract_status": "purchasing",
            }
        )
        for target in (
            "purchase_finished",
            "receive_check",
            "initial_check",
            "project_settlement",
            "settlement_done",
            "final_check",
            "project_finished",
        ):
            ContractService.update_settlement_status(c.contract_code, target)
        url = reverse("contracts-detail", kwargs={"recordcode": c.recordcode})
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["allowed_next_states"] == []

    def test_settlement_endpoint_response_includes_field(self, admin_client, contract):
        """连带下发点:update_settlement_status 响应(ContractDetailSerializer)同样携带出边"""
        url = reverse("contracts-update-settlement-status", kwargs={"recordcode": contract.recordcode})
        response = admin_client.post(url, {"status": "purchase_finished"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["contract"]["allowed_next_states"] == ["receive_check"]

    def test_put_response_excludes_field(self, admin_client, contract):
        """【口径锁定】PUT 响应走 ContractUpdateSerializer,不含 allowed_next_states——前端禁止依赖 update 响应回填出边"""
        url = reverse("contracts-detail", kwargs={"recordcode": contract.recordcode})
        response = admin_client.put(url, {"contract_name": "改名"}, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert "allowed_next_states" not in response.data["data"]
