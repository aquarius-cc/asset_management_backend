# Asset Broken/Lost 状态调整详细方案

> 版本: v6.0 | 日期: 2026-06-29 | 状态: 待审批

---

## 1. 背景与目标

为Asset模型新增`broken`（已损坏）和`lost`（已遗失）两个状态，完善资产全生命周期管理。

**核心规则**：
- 所有进入damaged的路径必须经过broken或lost
- 审批拒绝根据原状态回退到broken或lost
- lost状态不可直接删除，必须走报废流程
- damaged状态下仅允许approve/reject和仓库位置修改
- broken操作直接生效，无需审批
- lost找回需单独记录FoundAsset
- 每个模型按Action分离序列化器：List/Create/Update/Detail

## 2. 状态流转图

```
                         ┌───────────────────────────────────────────┐
                         │                                           │
                         ▼                                           │
in_store ──outasset──→ in_use ──recycle──→ recycled_pending
    │      │              │                    │
    │      │              │                    │
    └──broken/lost────────┴──broken/lost───────┘
              │                    │
              │                    └──── outasset ────→ in_use
              ▼
           damaged ──approve──→ scrapped(终态)
              │
              └──reject──→ broken/lost
```

## 3. 新增模型

### 3.1 BrokenAsset模型

```python
class BrokenAsset(BaseModel):
    """已损坏资产管理模型"""
    RECORDCODE_PREFIX = "BROKEN"
    
    asset_recordcode = models.OneToOneField(
        Asset, to_field="recordcode", related_name="broken_asset",
        on_delete=models.SET_NULL, null=True, blank=True
    )
    broken_date = models.DateField(default=timezone.now)
    operator_employee = models.ForeignKey(
        Employee, to_field="recordcode", related_name="broken_assets_operator",
        on_delete=models.SET_NULL, null=True, blank=True
    )
    broken_reason = models.CharField(max_length=100)
    broken_description = models.TextField(blank=True, null=True)
    version = models.IntegerField(default=1)
    
    class Meta:
        db_table = "am_broken_asset"
```

### 3.2 LostAsset模型

```python
class LostAsset(BaseModel):
    """已遗失资产管理模型"""
    RECORDCODE_PREFIX = "LOST"
    
    asset_recordcode = models.OneToOneField(
        Asset, to_field="recordcode", related_name="lost_asset",
        on_delete=models.SET_NULL, null=True, blank=True
    )
    lost_date = models.DateField(default=timezone.now)
    operator_employee = models.ForeignKey(
        Employee, to_field="recordcode", related_name="lost_assets_operator",
        on_delete=models.SET_NULL, null=True, blank=True
    )
    last_known_location = models.CharField(max_length=200, blank=True, null=True)
    lost_reason = models.CharField(max_length=100)
    lost_description = models.TextField(blank=True, null=True)
    version = models.IntegerField(default=1)
    
    class Meta:
        db_table = "am_lost_asset"
```

### 3.3 FoundAsset模型

```python
class FoundAsset(BaseModel):
    """资产找回记录模型"""
    RECORDCODE_PREFIX = "FOUND"
    
    lost_asset_recordcode = models.OneToOneField(
        LostAsset, to_field="recordcode", related_name="found_record",
        on_delete=models.CASCADE
    )
    asset_recordcode = models.ForeignKey(
        Asset, to_field="recordcode", related_name="found_assets",
        on_delete=models.PROTECT
    )
    found_date = models.DateField(default=timezone.now)
    found_location = models.CharField(max_length=200, blank=True, null=True)
    operator_employee = models.ForeignKey(
        Employee, to_field="recordcode", related_name="found_assets_operator",
        on_delete=models.SET_NULL, null=True, blank=True
    )
    found_description = models.TextField(blank=True, null=True)
    version = models.IntegerField(default=1)
    
    class Meta:
        db_table = "am_found_asset"
```

### 3.4 RecycleAsset模型变更

```python
is_broken = models.BooleanField(default=False, verbose_name="是否损坏回收")
is_lost = models.BooleanField(default=False, verbose_name="是否遗失回收")
```

### 3.5 DamagedAsset模型变更

```python
original_status = models.CharField(max_length=20, verbose_name="原状态", blank=True, null=True)
```

## 4. QuerySet层（3个新增）

### 4.1 BrokenAssetQuerySet

```python
class BrokenAssetQuerySet(models.QuerySet):
    def for_list(self):
        return self.select_related('asset_recordcode', 'operator_employee')
    
    def with_asset_details(self):
        return self.select_related(
            'asset_recordcode', 'operator_employee',
            'asset_recordcode__asset_type_recordcode',
            'asset_recordcode__asset_contract_recordcode',
            'asset_recordcode__asset_storage_recordcode',
        )
```

### 4.2 LostAssetQuerySet

```python
class LostAssetQuerySet(models.QuerySet):
    def for_list(self):
        return self.select_related('asset_recordcode', 'operator_employee')
    
    def with_asset_details(self):
        return self.select_related(
            'asset_recordcode', 'operator_employee',
            'asset_recordcode__asset_type_recordcode',
            'asset_recordcode__asset_contract_recordcode',
            'asset_recordcode__asset_storage_recordcode',
        )
```

### 4.3 FoundAssetQuerySet

```python
class FoundAssetQuerySet(models.QuerySet):
    def for_list(self):
        return self.select_related('lost_asset_recordcode', 'asset_recordcode', 'operator_employee')
    
    def with_asset_details(self):
        return self.select_related(
            'lost_asset_recordcode', 'asset_recordcode', 'operator_employee',
            'asset_recordcode__asset_type_recordcode',
            'asset_recordcode__asset_contract_recordcode',
        )
```

## 5. 序列化器设计（12个）

### 5.1 BrokenAsset序列化器（4个）

```python
class BrokenAssetListSerializer(serializers.ModelSerializer):
    """损坏记录列表序列化器 - list action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    
    class Meta:
        model = BrokenAsset
        fields = ['recordcode', 'asset_recordcode', 'asset_code', 'asset_name',
                  'broken_date', 'operator_name', 'broken_reason', 'created_at']
        read_only_fields = fields


class BrokenAssetCreateSerializer(serializers.ModelSerializer):
    """损坏记录创建序列化器 - create action"""
    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )
    
    class Meta:
        model = BrokenAsset
        fields = ['recordcode', 'asset_recordcode', 'broken_date', 'broken_reason', 'broken_description']
        extra_kwargs = {'broken_reason': {'required': True}, 'broken_date': {'required': False}}


class BrokenAssetUpdateSerializer(serializers.ModelSerializer):
    """损坏记录更新序列化器 - update/partial_update action"""
    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)
    
    class Meta:
        model = BrokenAsset
        fields = ['recordcode', 'asset_recordcode', 'broken_date', 'broken_reason', 'broken_description']
        extra_kwargs = {'broken_reason': {'required': False}}


class BrokenAssetDetailSerializer(serializers.ModelSerializer):
    """损坏记录详情序列化器 - retrieve action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    asset_specification = serializers.CharField(source='asset_recordcode.asset_specification', read_only=True, allow_null=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    operator_jobcode = serializers.CharField(source='operator_employee.employee_jobcode', read_only=True, allow_null=True)
    
    class Meta:
        model = BrokenAsset
        fields = ['recordcode', 'asset_recordcode', 'asset_code', 'asset_name', 'asset_specification',
                  'broken_date', 'operator_employee', 'operator_name', 'operator_jobcode',
                  'broken_reason', 'broken_description', 'version', 'created_at', 'updated_at']


BrokenAssetSerializer = BrokenAssetListSerializer  # 向后兼容
```

### 5.2 LostAsset序列化器（4个）

```python
class LostAssetListSerializer(serializers.ModelSerializer):
    """遗失记录列表序列化器 - list action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    
    class Meta:
        model = LostAsset
        fields = ['recordcode', 'asset_recordcode', 'asset_code', 'asset_name',
                  'lost_date', 'operator_name', 'lost_reason', 'last_known_location', 'created_at']
        read_only_fields = fields


class LostAssetCreateSerializer(serializers.ModelSerializer):
    """遗失记录创建序列化器 - create action"""
    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )
    
    class Meta:
        model = LostAsset
        fields = ['recordcode', 'asset_recordcode', 'lost_date', 'last_known_location', 'lost_reason', 'lost_description']
        extra_kwargs = {'lost_reason': {'required': True}, 'lost_date': {'required': False}}


class LostAssetUpdateSerializer(serializers.ModelSerializer):
    """遗失记录更新序列化器 - update/partial_update action"""
    recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)
    
    class Meta:
        model = LostAsset
        fields = ['recordcode', 'asset_recordcode', 'lost_date', 'last_known_location', 'lost_reason', 'lost_description']
        extra_kwargs = {'lost_reason': {'required': False}}


class LostAssetDetailSerializer(serializers.ModelSerializer):
    """遗失记录详情序列化器 - retrieve action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    asset_specification = serializers.CharField(source='asset_recordcode.asset_specification', read_only=True, allow_null=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    operator_jobcode = serializers.CharField(source='operator_employee.employee_jobcode', read_only=True, allow_null=True)
    
    class Meta:
        model = LostAsset
        fields = ['recordcode', 'asset_recordcode', 'asset_code', 'asset_name', 'asset_specification',
                  'lost_date', 'operator_employee', 'operator_name', 'operator_jobcode',
                  'last_known_location', 'lost_reason', 'lost_description', 'version', 'created_at', 'updated_at']


LostAssetSerializer = LostAssetListSerializer  # 向后兼容
```

### 5.3 FoundAsset序列化器（4个）

```python
class FoundAssetListSerializer(serializers.ModelSerializer):
    """找回记录列表序列化器 - list action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    lost_asset_code = serializers.CharField(source='lost_asset_recordcode.recordcode', read_only=True)
    
    class Meta:
        model = FoundAsset
        fields = ['recordcode', 'lost_asset_recordcode', 'lost_asset_code', 'asset_recordcode',
                  'asset_code', 'asset_name', 'found_date', 'found_location', 'operator_name', 'created_at']
        read_only_fields = fields


class FoundAssetCreateSerializer(serializers.ModelSerializer):
    """找回记录创建序列化器 - create action"""
    recordcode = serializers.CharField(read_only=True)
    lost_asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=LostAsset.objects.filter(is_deleted=False), write_only=True
    )
    asset_recordcode = serializers.SlugRelatedField(
        slug_field="recordcode", queryset=Asset.objects.filter(is_deleted=False), write_only=True
    )
    
    class Meta:
        model = FoundAsset
        fields = ['recordcode', 'lost_asset_recordcode', 'asset_recordcode', 'found_date', 'found_location', 'found_description']
        extra_kwargs = {'found_date': {'required': False}}


class FoundAssetUpdateSerializer(serializers.ModelSerializer):
    """找回记录更新序列化器 - update/partial_update action"""
    recordcode = serializers.CharField(read_only=True)
    lost_asset_recordcode = serializers.CharField(read_only=True)
    asset_recordcode = serializers.CharField(read_only=True)
    
    class Meta:
        model = FoundAsset
        fields = ['recordcode', 'lost_asset_recordcode', 'asset_recordcode', 'found_date', 'found_location', 'found_description']


class FoundAssetDetailSerializer(serializers.ModelSerializer):
    """找回记录详情序列化器 - retrieve action"""
    asset_code = serializers.CharField(source='asset_recordcode.asset_code', read_only=True)
    asset_name = serializers.CharField(source='asset_recordcode.asset_name', read_only=True)
    asset_specification = serializers.CharField(source='asset_recordcode.asset_specification', read_only=True, allow_null=True)
    operator_name = serializers.CharField(source='operator_employee.employee_name', read_only=True, allow_null=True)
    operator_jobcode = serializers.CharField(source='operator_employee.employee_jobcode', read_only=True, allow_null=True)
    lost_asset_code = serializers.CharField(source='lost_asset_recordcode.recordcode', read_only=True)
    
    class Meta:
        model = FoundAsset
        fields = ['recordcode', 'lost_asset_recordcode', 'lost_asset_code', 'asset_recordcode',
                  'asset_code', 'asset_name', 'asset_specification', 'found_date', 'found_location',
                  'operator_employee', 'operator_name', 'operator_jobcode', 'found_description', 'version', 'created_at', 'updated_at']


FoundAssetSerializer = FoundAssetListSerializer  # 向后兼容
```

## 6. Selector层（3个新增）

### 6.1 BrokenAssetSelector

```python
class BrokenAssetSelector:
    """损坏记录查询选择器"""
    
    @staticmethod
    def get_broken_assets_for_list() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.for_list().all()
    
    @staticmethod
    def get_broken_assets_with_details() -> QuerySet[BrokenAsset]:
        return BrokenAsset.objects.with_asset_details().all()
    
    @staticmethod
    def get_broken_asset_by_recordcode(recordcode: str):
        return BrokenAsset.objects.with_asset_details().filter(recordcode=recordcode).first()
```

### 6.2 LostAssetSelector

```python
class LostAssetSelector:
    """遗失记录查询选择器"""
    
    @staticmethod
    def get_lost_assets_for_list() -> QuerySet[LostAsset]:
        return LostAsset.objects.for_list().all()
    
    @staticmethod
    def get_lost_assets_with_details() -> QuerySet[LostAsset]:
        return LostAsset.objects.with_asset_details().all()
    
    @staticmethod
    def get_lost_asset_by_recordcode(recordcode: str):
        return LostAsset.objects.with_asset_details().filter(recordcode=recordcode).first()
```

### 6.3 FoundAssetSelector

```python
class FoundAssetSelector:
    """找回记录查询选择器"""
    
    @staticmethod
    def get_found_assets_for_list() -> QuerySet[FoundAsset]:
        return FoundAsset.objects.for_list().all()
    
    @staticmethod
    def get_found_assets_with_details() -> QuerySet[FoundAsset]:
        return FoundAsset.objects.with_asset_details().all()
    
    @staticmethod
    def get_found_asset_by_recordcode(recordcode: str):
        return FoundAsset.objects.with_asset_details().filter(recordcode=recordcode).first()
```

## 7. 状态机变更

### 7.1 AssetState枚举

```python
class AssetState(Enum):
    IN_STORE = 'in_store'
    IN_USE = 'in_use'
    RECYCLED_PENDING = 'recycled_pending'
    BROKEN = 'broken'          # 新增
    LOST = 'lost'              # 新增
    DAMAGED = 'damaged'
    SCRAPPED = 'scrapped'
```

### 7.2 _TRANSITIONS规则

```python
_TRANSITIONS = {
    AssetState.IN_STORE: {
        AssetState.IN_USE: 'outasset',
        AssetState.BROKEN: 'mark_broken',
        AssetState.LOST: 'mark_lost',
    },
    AssetState.IN_USE: {
        AssetState.RECYCLED_PENDING: 'recycle',
        AssetState.BROKEN: 'recycle',
        AssetState.LOST: 'recycle',
    },
    AssetState.RECYCLED_PENDING: {
        AssetState.IN_USE: 'outasset',
        AssetState.BROKEN: 'mark_broken',
        AssetState.LOST: 'mark_lost',
    },
    AssetState.BROKEN: {
        AssetState.DAMAGED: 'to_damaged',
    },
    AssetState.LOST: {
        AssetState.DAMAGED: 'to_damaged',
        AssetState.IN_STORE: 'found_and_return',
    },
    AssetState.DAMAGED: {
        AssetState.SCRAPPED: 'approve',
        AssetState.BROKEN: 'reject_to_broken',
        AssetState.LOST: 'reject_to_lost',
    },
    AssetState.SCRAPPED: {},
}
```

### 7.3 新增方法

```python
@classmethod
def mark_broken(cls, asset):
    """标记损坏: (in_store|recycled_pending) → broken"""
    cls._transition(asset, AssetState.BROKEN)

@classmethod
def mark_lost(cls, asset):
    """标记遗失: (in_store|recycled_pending) → lost"""
    cls._transition(asset, AssetState.LOST)

@classmethod
def found_and_return(cls, asset):
    """找回入库: lost → in_store"""
    cls._transition(asset, AssetState.IN_STORE)

@classmethod
def reject_to_broken(cls, asset):
    """审批拒绝(损坏): damaged → broken"""
    cls._transition(asset, AssetState.BROKEN)

@classmethod
def reject_to_lost(cls, asset):
    """审批拒绝(遗失): damaged → lost"""
    cls._transition(asset, AssetState.LOST)
```

## 8. Service层变更

### 8.1 AssetService新增方法

```python
@staticmethod
@transaction.atomic
def mark_asset_broken(
    asset_code: str,
    broken_reason: str,
    broken_description: str = "",
    operator_jobcode: str = "",
    operator_name: str = ""
) -> Asset:
    """标记资产为已损坏"""
    asset = Asset.objects.select_for_update().get(asset_code=asset_code)
    
    if asset.asset_current_status == 'broken':
        return asset
    
    operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()
    
    AssetFSM.mark_broken(asset)
    asset.save(update_fields=['asset_current_status', 'updated_at'])
    
    BrokenAsset.objects.create(
        asset_recordcode=asset,
        broken_reason=broken_reason,
        broken_description=broken_description,
        operator_employee=operator,
    )
    
    AssetOperationLog.objects.create(
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_specification=asset.asset_specification,
        operation_type='broken',
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
        description=f'资产标记为已损坏: {broken_reason}',
    )
    
    return asset


@staticmethod
@transaction.atomic
def mark_asset_lost(
    asset_code: str,
    lost_reason: str,
    last_known_location: str = "",
    lost_description: str = "",
    operator_jobcode: str = "",
    operator_name: str = ""
) -> Asset:
    """标记资产为已遗失"""
    asset = Asset.objects.select_for_update().get(asset_code=asset_code)
    
    if asset.asset_current_status == 'lost':
        return asset
    
    operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()
    
    AssetFSM.mark_lost(asset)
    asset.save(update_fields=['asset_current_status', 'updated_at'])
    
    LostAsset.objects.create(
        asset_recordcode=asset,
        last_known_location=last_known_location,
        lost_reason=lost_reason,
        lost_description=lost_description,
        operator_employee=operator,
    )
    
    AssetOperationLog.objects.create(
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_specification=asset.asset_specification,
        operation_type='lost',
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
        description=f'资产标记为已遗失: {lost_reason}',
    )
    
    return asset


@staticmethod
@transaction.atomic
def find_and_return_asset(
    asset_code: str,
    found_location: str = "",
    found_description: str = "",
    operator_jobcode: str = "",
    operator_name: str = ""
) -> Asset:
    """找回遗失资产并入库"""
    asset = Asset.objects.select_for_update().get(asset_code=asset_code)
    
    lost_record = LostAsset.objects.get(asset_recordcode=asset)
    
    operator = Employee.objects.filter(employee_jobcode=operator_jobcode).first()
    
    AssetFSM.found_and_return(asset)
    asset.save(update_fields=['asset_current_status', 'updated_at'])
    
    FoundAsset.objects.create(
        lost_asset_recordcode=lost_record,
        asset_recordcode=asset,
        found_location=found_location,
        found_description=found_description,
        operator_employee=operator,
    )
    
    AssetOperationLog.objects.create(
        asset_code=asset.asset_code,
        asset_name=asset.asset_name,
        asset_specification=asset.asset_specification,
        operation_type='found',
        operator_jobcode=operator_jobcode,
        operator_name=operator_name,
        description='遗失资产找回并入库',
    )
    
    return asset
```

## 9. 视图层设计

### 9.1 BrokenAssetViewSet

```python
class BrokenAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """已损坏资产视图集"""
    queryset = BrokenAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['asset_recordcode__asset_name', 'broken_reason']
    ordering_fields = ['broken_date', 'created_at']
    ordering = ['-broken_date']
    lookup_field = 'recordcode'
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self) -> Type:
        if self.action == 'list':
            return BrokenAssetListSerializer
        elif self.action == 'create':
            return BrokenAssetCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BrokenAssetUpdateSerializer
        return BrokenAssetDetailSerializer
```

### 9.2 LostAssetViewSet

```python
class LostAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """已遗失资产视图集"""
    queryset = LostAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['asset_recordcode__asset_name', 'lost_reason']
    ordering_fields = ['lost_date', 'created_at']
    ordering = ['-lost_date']
    lookup_field = 'recordcode'
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self) -> Type:
        if self.action == 'list':
            return LostAssetListSerializer
        elif self.action == 'create':
            return LostAssetCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LostAssetUpdateSerializer
        return LostAssetDetailSerializer
```

### 9.3 FoundAssetViewSet

```python
class FoundAssetViewSet(LoggingMixin, ResponseWrapperMixin, ModelViewSet):
    """资产找回记录视图集"""
    queryset = FoundAsset.objects.for_list().all()
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ['asset_recordcode__asset_name']
    ordering_fields = ['found_date', 'created_at']
    ordering = ['-found_date']
    lookup_field = 'recordcode'
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self) -> Type:
        if self.action == 'list':
            return FoundAssetListSerializer
        elif self.action == 'create':
            return FoundAssetCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return FoundAssetUpdateSerializer
        return FoundAssetDetailSerializer
```

### 9.4 AssetViewSet新增action

```python
@action(detail=True, methods=['post'], url_path='mark_broken')
def mark_broken(self, request, pk=None):
    """标记资产为已损坏"""
    asset_code = self.kwargs.get('asset_code')
    try:
        asset = AssetService.mark_asset_broken(
            asset_code=asset_code,
            broken_reason=request.data.get('broken_reason', ''),
            broken_description=request.data.get('broken_description', ''),
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )
        return success_response(data=AssetDetailSerializer(asset).data, message='资产已标记为损坏')
    except AppValidationError as e:
        return error_response(message=str(e), status_code=400)

@action(detail=True, methods=['post'], url_path='mark_lost')
def mark_lost(self, request, pk=None):
    """标记资产为已遗失"""
    asset_code = self.kwargs.get('asset_code')
    try:
        asset = AssetService.mark_asset_lost(
            asset_code=asset_code,
            lost_reason=request.data.get('lost_reason', ''),
            last_known_location=request.data.get('last_known_location', ''),
            lost_description=request.data.get('lost_description', ''),
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )
        return success_response(data=AssetDetailSerializer(asset).data, message='资产已标记为遗失')
    except AppValidationError as e:
        return error_response(message=str(e), status_code=400)

@action(detail=True, methods=['post'], url_path='found_and_return')
def found_and_return(self, request, pk=None):
    """找回遗失资产并入库"""
    asset_code = self.kwargs.get('asset_code')
    try:
        asset = AssetService.find_and_return_asset(
            asset_code=asset_code,
            found_location=request.data.get('found_location', ''),
            found_description=request.data.get('found_description', ''),
            operator_jobcode=request.user.auth_id,
            operator_name=request.user.auth_username
        )
        return success_response(data=AssetDetailSerializer(asset).data, message='遗失资产已找回并入库')
    except AppValidationError as e:
        return error_response(message=str(e), status_code=400)
```

## 10. Admin配置（3个新增）

### 10.1 BrokenAssetAdmin

```python
@admin.register(BrokenAsset)
class BrokenAssetAdmin(admin.ModelAdmin):
    def asset_code_display(self, obj):
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else '-'
    asset_code_display.short_description = '资产编码'
    
    def asset_name(self, obj):
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else '-'
    asset_name.short_description = '资产名称'
    
    def operator_name(self, obj):
        return obj.operator_employee.employee_name if obj.operator_employee else '-'
    operator_name.short_description = '操作人'
    
    list_display = ['recordcode', 'asset_code_display', 'asset_name', 
                    'broken_date', 'operator_name', 'broken_reason']
    search_fields = ['asset_recordcode__asset_name', 'broken_reason']
    list_filter = ['broken_date']
    date_hierarchy = 'broken_date'
    readonly_fields = ['recordcode', 'asset_recordcode', 'operator_employee']
```

### 10.2 LostAssetAdmin

```python
@admin.register(LostAsset)
class LostAssetAdmin(admin.ModelAdmin):
    def asset_code_display(self, obj):
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else '-'
    asset_code_display.short_description = '资产编码'
    
    def asset_name(self, obj):
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else '-'
    asset_name.short_description = '资产名称'
    
    def operator_name(self, obj):
        return obj.operator_employee.employee_name if obj.operator_employee else '-'
    operator_name.short_description = '操作人'
    
    list_display = ['recordcode', 'asset_code_display', 'asset_name',
                    'lost_date', 'operator_name', 'lost_reason', 'last_known_location']
    search_fields = ['asset_recordcode__asset_name', 'lost_reason']
    list_filter = ['lost_date']
    date_hierarchy = 'lost_date'
    readonly_fields = ['recordcode', 'asset_recordcode', 'operator_employee']
```

### 10.3 FoundAssetAdmin

```python
@admin.register(FoundAsset)
class FoundAssetAdmin(admin.ModelAdmin):
    def asset_code_display(self, obj):
        return obj.asset_recordcode.asset_code if obj.asset_recordcode else '-'
    asset_code_display.short_description = '资产编码'
    
    def asset_name(self, obj):
        return obj.asset_recordcode.asset_name if obj.asset_recordcode else '-'
    asset_name.short_description = '资产名称'
    
    def lost_asset_code_display(self, obj):
        return obj.lost_asset_recordcode.recordcode if obj.lost_asset_recordcode else '-'
    lost_asset_code_display.short_description = '关联遗失记录'
    
    def operator_name(self, obj):
        return obj.operator_employee.employee_name if obj.operator_employee else '-'
    operator_name.short_description = '操作人'
    
    list_display = ['recordcode', 'asset_code_display', 'asset_name',
                    'lost_asset_code_display', 'found_date', 'operator_name']
    search_fields = ['asset_recordcode__asset_name']
    list_filter = ['found_date']
    date_hierarchy = 'found_date'
    readonly_fields = ['recordcode', 'lost_asset_recordcode', 'asset_recordcode', 'operator_employee']
```

## 11. 路由配置

```python
router.register(r'broken-assets', BrokenAssetViewSet, basename='broken-assets')
router.register(r'lost-assets', LostAssetViewSet, basename='lost-assets')
router.register(r'found-assets', FoundAssetViewSet, basename='found-assets')
```

## 12. 数据库迁移

```bash
python manage.py makemigrations assetmanagement --name add_broken_lost_found_models
python manage.py migrate
```

迁移内容：
1. Asset表: 更新asset_current_status字段的choices
2. AssetOperationLog表: 更新operation_type字段的choices
3. BrokenAsset表: 新增
4. LostAsset表: 新增
5. FoundAsset表: 新增
6. DamagedAsset表: 新增original_status字段
7. RecycleAsset表: 新增is_broken和is_lost字段

## 13. 文档同步

需更新的文档：
- `docs/资产数据字典.md` — 新增模型和状态定义
- `docs/API.md` — 新增端点说明
- `docs/业务流程说明书.md` — 状态流转说明
- `Tolaria_Fiels/模型字段标准.md` — 同步模型字段标准

## 14. 验证清单

实现完成后需验证：
1. 运行 `python manage.py makemigrations --check` 确认迁移已生成
2. 运行 `python manage.py test` 确认测试通过
3. 运行 `mypy . --strict` 确认类型检查通过
4. 运行 `ruff check .` 确认代码规范通过

---

## 变更文件清单（完整）

| 文件路径 | 变更类型 | 说明 |
|---------|---------|------|
| apps/assetmanagement/models.py | 修改 | 新增3个模型 + 2个模型字段 |
| apps/assetmanagement/querysets.py | 修改 | 新增3个QuerySet类 |
| apps/assetmanagement/state_machine/core.py | 修改 | 新增状态枚举和转换方法 |
| apps/assetmanagement/services/asset_service.py | 修改 | 新增3个方法 |
| apps/assetmanagement/services/recycle_service.py | 修改 | 支持is_broken/is_lost参数 |
| apps/assetmanagement/services/damaged_service.py | 修改 | reject根据original_status回退 |
| apps/assetmanagement/selectors/outasset_selector.py | 修改 | 新增3个Selector类 |
| apps/assetmanagement/selectors/__init__.py | 修改 | 导出新Selector |
| apps/assetmanagement/serializers/base_serializers.py | 修改 | 新增12个序列化器 |
| apps/assetmanagement/serializers/__init__.py | 修改 | 导出新序列化器 |
| apps/assetmanagement/views.py | 修改 | 新增3个ViewSet + 3个action |
| apps/assetmanagement/admin.py | 修改 | 新增3个Admin配置 |
| apps/assetmanagement/urls.py | 修改 | 新增3个路由 |
| core/constants.py | 修改 | 同步新增常量 |
| docs/资产数据字典.md | 修改 | 同步文档 |
| docs/API.md | 修改 | 同步文档 |
| docs/业务流程说明书.md | 修改 | 同步文档 |
