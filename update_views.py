import sys

with open('apps/assetmanagement/views.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. 添加导入
old_import = """    AssetCreateSerializer,
    OutAssetSerializer,"""
new_import = """    AssetCreateSerializer,
    AssetBatchCreateSerializer,
    AssetBatchDeleteSerializer,
    OutAssetSerializer,"""
content = content.replace(old_import, new_import)

# 2. 在 AssetViewSet 末尾添加 action（在 class OutAssetViewSet 之前）
old_class = """        serializer = ContractDetailSerializer(contract)
        return success_response(data=serializer.data, message='查询成功')


class OutAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):"""

new_class = """        serializer = ContractDetailSerializer(contract)
        return success_response(data=serializer.data, message='查询成功')

    @action(detail=False, methods=['post'], url_path='batch-create')
    def batch_create(self, request):
        \"\"\"批量创建资产\"\"\"
        serializer = AssetBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AssetService.batch_create_asset(
            serializer.validated_data['items'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        success_serializer = AssetDetailSerializer(result['success_items'], many=True)

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_items': success_serializer.data,
                'fail_items': result['fail_items']
            },
            message=f"批量创建完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )

    @action(detail=False, methods=['post'], url_path='batch-delete')
    def batch_delete(self, request):
        \"\"\"批量删除资产\"\"\"
        serializer = AssetBatchDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = AssetService.batch_delete_asset(
            serializer.validated_data['ids'],
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )

        return success_response(
            data={
                'total': result['total'],
                'success_count': result['success_count'],
                'fail_count': result['fail_count'],
                'success_ids': result['success_ids'],
                'fail_items': result['fail_items']
            },
            message=f"批量删除完成，成功 {result['success_count']} 条，失败 {result['fail_count']} 条"
        )


class OutAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):"""

content = content.replace(old_class, new_class)

with open('apps/assetmanagement/views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('views.py updated successfully')
