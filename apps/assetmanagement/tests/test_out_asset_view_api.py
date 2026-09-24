"""
出库资产管理 ViewSet API 测试

测试 OutAssetViewSet 的 API 端点:
- list
- create
- retrieve
- update
- partial_update
- destroy
- 自定义 actions: recyclable, batch_create, batch_delete, by_asset, by_applicant, cancel_outasset, statistics
"""

from unittest import mock

import pytest
from django.urls import reverse
from rest_framework import status

from apps.assetmanagement.models import Asset, OutAsset
from apps.assetmanagement.views.out_asset_view import OutAssetViewSet


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


@pytest.fixture
def asset2(db, storage, asset_type):
    """第二条独立 in_store 资产(批量创建成功用例需两条不同资产)"""
    return Asset.objects.create(
        asset_code="A002",
        asset_name="测试资产2",
        asset_purchase_price=1000.00,
        asset_purchase_date="2024-01-01",
        asset_entry_date="2024-01-15",
        asset_storage_recordcode=storage,
        asset_type_recordcode=asset_type,
        asset_current_status="in_store",
    )


@pytest.mark.django_db
class TestOutAssetViewSet:
    """OutAssetViewSet API 测试"""

    def test_list_out_assets(self, authenticated_client, outasset):
        """测试获取出库记录列表"""
        url = reverse("out-assets-list")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]
        assert len(response.data["data"]["results"]) == 1

    def test_create_out_asset(self, admin_authenticated_client, asset):
        """测试创建出库记录"""
        url = reverse("out-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "outasset_date": "2024-03-01",
            "outasset_type": "receive",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        assert response.data["data"]["asset_recordcode"] == asset.recordcode

    def test_retrieve_out_asset(self, authenticated_client, outasset):
        """测试获取出库记录详情"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["recordcode"] == outasset.recordcode

    def test_update_out_asset(self, admin_authenticated_client, outasset):
        """测试更新出库记录"""
        from apps.assetmanagement.models import AssetOperationLog

        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_date": "2024-04-01"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["outasset_date"] == "2024-04-01"
        log = AssetOperationLog.objects.filter(
            asset_code=outasset.asset_recordcode.asset_code,
            operation_type="update",
        ).first()
        assert log is not None, "更新出库记录应产生操作日志"
        assert log.operator_jobcode is not None, "操作日志应记录操作人工号"
        assert log.operator_jobcode == "adminuser"

    def test_partial_update_out_asset(self, admin_authenticated_client, outasset):
        """测试部分更新出库记录"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_date": "2024-05-01"}
        response = admin_authenticated_client.patch(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["outasset_date"] == "2024-05-01"

    def test_update_out_asset_invalid_date_rejected(self, admin_authenticated_client, outasset):
        """B8 输入门禁: 出库日期格式错误应返回 400,不得落 Service"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_date": "bad-date"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        outasset.refresh_from_db()
        assert outasset.outasset_date != "bad-date"

    def test_update_out_asset_using_location(self, admin_authenticated_client, outasset):
        """B8 Gap A 决策升级(A): outasset_using_location 保留可写 → OutAsset 与 Asset 主表同步落库"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_using_location": "新地点-3号仓库"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        outasset.refresh_from_db()
        asset = outasset.asset_recordcode
        assert outasset.outasset_using_location == "新地点-3号仓库"
        asset.refresh_from_db()
        assert asset.asset_using_location == "新地点-3号仓库"

    def test_update_out_asset_unknown_field_ignored(self, admin_authenticated_client, outasset):
        """B8 Gap B 决策(契约变更留痕): 未知字段静默忽略, 原 FIELD_NOT_ALLOWED 分支不可达"""
        from datetime import date

        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_date": "2024-06-01", "foo": "bar"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        outasset.refresh_from_db()
        assert outasset.outasset_date == date(2024, 6, 1)

    def test_create_out_asset_with_people_and_location(self, admin_authenticated_client, asset, user, employee):
        """A: create 携带申请人/保管人(jobcode)与使用地点 → OutAsset FK + Asset 主表同步落库"""
        url = reverse("out-assets-list")
        data = {
            "asset_recordcode": asset.recordcode,
            "outasset_date": "2024-03-01",
            "outasset_type": "receive",
            "outasset_applicant": user.employee_jobcode,
            "outasset_manager": employee.employee_jobcode,
            "outasset_using_location": "使用地点A",
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["code"] == 0
        created = OutAsset.objects.get(recordcode=response.data["data"]["recordcode"])
        assert created.outasset_applicant_recordcode == user
        assert created.outasset_manager_recordcode == employee
        assert created.outasset_using_location == "使用地点A"
        asset.refresh_from_db()
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_manager_recordcode == employee
        assert asset.asset_using_location == "使用地点A"
        assert created.outasset_snapshot["applicant"]["jobcode"] == user.employee_jobcode
        assert created.outasset_snapshot["using_location"] == "使用地点A"

    def test_update_out_asset_with_people_and_location(self, admin_authenticated_client, outasset, user, employee):
        """A: update 变更申请人/保管人(jobcode)+使用地点 → OutAsset + Asset 主表双同步,快照不重写"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        asset = outasset.asset_recordcode
        original_snapshot = outasset.outasset_snapshot
        data = {
            "outasset_applicant": user.employee_jobcode,
            "outasset_manager": employee.employee_jobcode,
            "outasset_using_location": "新地点-更新后",
        }
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        outasset.refresh_from_db()
        asset.refresh_from_db()
        assert outasset.outasset_applicant_recordcode == user
        assert outasset.outasset_manager_recordcode == employee
        assert outasset.outasset_using_location == "新地点-更新后"
        assert asset.asset_applicant_recordcode == user
        assert asset.asset_manager_recordcode == employee
        assert asset.asset_using_location == "新地点-更新后"
        assert outasset.outasset_snapshot == original_snapshot  # 快照不重写(保历史)

    def test_update_out_asset_jobcode_not_found_rejected(self, admin_authenticated_client, outasset):
        """A: 申请人 jobcode 不存在 → 400(DRF 校验),不得落 Service"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        data = {"outasset_applicant": "NO_SUCH_JOBCODE"}
        response = admin_authenticated_client.put(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_destroy_out_asset(self, admin_authenticated_client, outasset):
        """测试删除出库记录"""
        url = reverse("out-assets-detail", kwargs={"recordcode": outasset.recordcode})
        response = admin_authenticated_client.delete(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert not OutAsset.objects.filter(recordcode=outasset.recordcode).exists()

    def test_recyclable(self, authenticated_client, outasset):
        """测试获取可回收出库记录——契约锁：无分页参数时强制返回第一页的分页 envelope（#30 回归护栏）"""
        url = reverse("out-assets-recyclable")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        data = response.data["data"]
        assert isinstance(data, dict)
        assert "count" in data and "results" in data
        assert isinstance(data["count"], int)
        assert isinstance(data["results"], list)

    def test_recyclable_unpaginated_branch_returns_envelope(self, authenticated_client, outasset):
        """#30 分支对称：paginate_queryset 返回 None（无分页）时，recyclable 与 list 一致返回 {count, results}"""
        url = reverse("out-assets-recyclable")
        with mock.patch.object(OutAssetViewSet, "paginate_queryset", return_value=None):
            response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        data = response.data["data"]
        assert isinstance(data, dict)
        assert data["count"] >= 0
        assert isinstance(data["results"], list)

    def test_batch_create(self, admin_authenticated_client, asset, asset2, employee, user):
        """批量创建:outasset_asset 键名归一 → 两条全成功,FK 落库 + Asset 主表联动 IN_USE"""
        url = reverse("out-assets-batch-create")
        data = {
            "items": [
                {
                    "outasset_asset": asset.asset_code,
                    "outasset_date": "2024-06-01",
                    "outasset_type": "receive",
                    "outasset_applicant": user.employee_jobcode,
                    "outasset_manager": employee.employee_jobcode,
                    "outasset_using_location": "使用地点A",
                },
                {
                    "outasset_asset": asset2.asset_code,
                    "outasset_date": "2024-06-02",
                    "outasset_type": "receive",
                    "outasset_applicant": user.employee_jobcode,
                    "outasset_manager": employee.employee_jobcode,
                    "outasset_using_location": "使用地点B",
                },
            ]
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 2
        assert response.data["data"]["fail_count"] == 0
        assert response.data["data"]["fail_items"] == []
        records = OutAsset.objects.filter(asset_recordcode__in=[asset, asset2])
        assert records.count() == 2
        assert records.get(asset_recordcode=asset).outasset_applicant_recordcode == user
        assert records.get(asset_recordcode=asset2).outasset_manager_recordcode == employee
        asset.refresh_from_db()
        asset2.refresh_from_db()
        assert asset.asset_current_status == Asset.AssetStatus.IN_USE
        assert asset2.asset_current_status == Asset.AssetStatus.IN_USE

    def test_batch_create_duplicate_asset_rejected(self, admin_authenticated_client, asset, employee, user):
        """同资产重复提交 → serializer 层 400(validate_items 去重,不落到 Service)"""
        url = reverse("out-assets-batch-create")
        data = {
            "items": [
                {
                    "outasset_asset": asset.asset_code,
                    "outasset_type": "receive",
                    "outasset_applicant": user.employee_jobcode,
                    "outasset_manager": employee.employee_jobcode,
                    "outasset_using_location": "使用地点A",
                },
                {
                    "outasset_asset": asset.asset_code,
                    "outasset_type": "receive",
                    "outasset_applicant": user.employee_jobcode,
                    "outasset_manager": employee.employee_jobcode,
                    "outasset_using_location": "使用地点B",
                },
            ]
        }
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "存在重复的资产编码" in str(response.data)

    def test_batch_delete(self, admin_authenticated_client, outasset):
        """测试批量删除出库记录"""
        url = reverse("out-assets-batch-delete")
        data = {"ids": [outasset.recordcode]}
        response = admin_authenticated_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert response.data["data"]["success_count"] == 1

    def test_by_asset(self, authenticated_client, outasset, asset):
        """测试按资产查询出库记录"""
        url = reverse("out-assets-by-asset", kwargs={"asset_code": asset.asset_code})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]

    def test_by_applicant(self, authenticated_client, outasset, user):
        """测试按申请人查询出库记录"""
        url = reverse("out-assets-by-applicant", kwargs={"applicant_jobcode": user.employee_jobcode})
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
        assert "results" in response.data["data"]

    def test_cancel_outasset(self, admin_authenticated_client, outasset):
        """测试取消出库"""
        url = reverse("out-assets-cancel-outasset", kwargs={"recordcode": outasset.recordcode})
        response = admin_authenticated_client.post(url, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0

    def test_statistics(self, authenticated_client):
        """测试出库统计"""
        url = reverse("out-assets-statistics")
        response = authenticated_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["code"] == 0
