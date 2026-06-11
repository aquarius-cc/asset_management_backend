

    @staticmethod
    def batch_create_asset(
        asset_data_list: List[Dict[str, Any]],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量创建资产（逐条独立执行，返回详细结果）

        Returns:
            {
                "total": 3,
                "success_count": 2,
                "fail_count": 1,
                "success_items": [Asset, ...],
                "fail_items": [
                    {
                        "index": 2,
                        "row_number": 5,
                        "input_data": {...},
                        "error_code": "DUPLICATE_ASSET_NAME",
                        "error_message": "资产名称 'xxx' 已存在"
                    }
                ]
            }
        """
        success_items: List[Asset] = []
        fail_items: List[Dict[str, Any]] = []

        for idx, asset_data in enumerate(asset_data_list):
            try:
                result = AssetService.create_asset(
                    asset_name=asset_data['asset_name'],
                    asset_type_code=asset_data['asset_type_code'],
                    asset_purchase_price=asset_data.get('asset_purchase_price'),
                    asset_purchase_date=asset_data.get('asset_purchase_date'),
                    asset_entry_date=asset_data.get('asset_entry_date'),
                    asset_storage_code=asset_data.get('asset_storage_code'),
                    asset_contract_code=asset_data.get('asset_contract_code'),
                    asset_purchase_number=asset_data.get('asset_purchase_number', 1),
                    asset_remark=asset_data.get('asset_remark', ''),
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                    department_code=asset_data.get('asset_department_code'),
                    employee_jobcode=asset_data.get('asset_employee_jobcode'),
                )
                if isinstance(result, list):
                    success_items.extend(result)
                else:
                    success_items.append(result)
            except AppValidationError as e:
                error_code = _map_asset_error_code(str(e.detail))
                fail_items.append({
                    "index": idx,
                    "row_number": asset_data.get('row_number'),
                    "input_data": asset_data,
                    "error_code": error_code,
                    "error_message": str(e.detail)
                })
            except Exception:
                fail_items.append({
                    "index": idx,
                    "row_number": asset_data.get('row_number'),
                    "input_data": asset_data,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(asset_data_list),
            "success_count": len(success_items),
            "fail_count": len(fail_items),
            "success_items": success_items,
            "fail_items": fail_items
        }

    @staticmethod
    def batch_delete_asset(
        asset_codes: List[str],
        operator_jobcode: Optional[str] = None,
        operator_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量删除资产（软删除，逐条独立执行）

        前置校验：
        - 资产状态必须为 in_store
        - 资产不存在关联出库记录
        - 资产不存在待报废记录

        Returns:
            {
                "total": 3,
                "success_count": 2,
                "fail_count": 1,
                "success_ids": ["ASSET-xxx", ...],
                "fail_items": [
                    {
                        "id": "ASSET-xxx",
                        "error_code": "ASSET_IN_USE",
                        "error_message": "资产当前状态为 in_use，不允许删除"
                    }
                ]
            }
        """
        success_ids: List[str] = []
        fail_items: List[Dict[str, Any]] = []

        for asset_code in asset_codes:
            try:
                asset = AssetSelector.get_asset_by_code(asset_code)
                if not asset:
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "NOT_FOUND",
                        "error_message": f"资产 {asset_code} 不存在"
                    })
                    continue

                if asset.asset_current_status != 'in_store':
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "ASSET_IN_USE",
                        "error_message": f"资产当前状态为 {asset.asset_current_status}，不允许删除"
                    })
                    continue

                if OutAsset.objects.filter(outasset_code=asset, is_deleted=False).exists():
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "HAS_OUTASSET_RECORDS",
                        "error_message": "资产存在关联出库记录，不允许删除"
                    })
                    continue

                if WasteAsset.objects.filter(wasteasset_code=asset, is_deleted=False).exclude(wasteasset_status='completed').exists():
                    fail_items.append({
                        "id": asset_code,
                        "error_code": "HAS_DAMAGED_RECORDS",
                        "error_message": "资产存在待报废记录，不允许删除"
                    })
                    continue

                AuditLogger.log_asset_delete(
                    asset_code=asset.asset_code,
                    asset_name=asset.asset_name,
                    operator_jobcode=operator_jobcode,
                    operator_name=operator_name,
                )

                asset.delete()
                success_ids.append(asset_code)

            except Exception:
                fail_items.append({
                    "id": asset_code,
                    "error_code": "INTERNAL_ERROR",
                    "error_message": "服务器内部错误，请稍后重试"
                })

        return {
            "total": len(asset_codes),
            "success_count": len(success_ids),
            "fail_count": len(fail_items),
            "success_ids": success_ids,
            "fail_items": fail_items
        }


def _map_asset_error_code(error_detail: str) -> str:
    """将错误详情映射为错误码"""
    msg = str(error_detail).lower()
    if "已存在" in msg and "名称" in msg:
        return "DUPLICATE_ASSET_NAME"
    elif "已存在" in msg and "编码" in msg:
        return "DUPLICATE_ASSET_CODE"
    elif "不存在" in msg and "类型" in msg:
        return "ASSET_TYPE_NOT_FOUND"
    elif "不存在" in msg and "仓库" in msg:
        return "STORAGE_NOT_FOUND"
    elif "不存在" in msg and "合同" in msg:
        return "CONTRACT_NOT_FOUND"
    elif "状态" in msg:
        return "STATUS_NOT_ALLOWED"
    return "VALIDATION_ERROR"
