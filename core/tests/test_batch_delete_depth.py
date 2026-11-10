"""M-03/X′ 批删链架构层深度契约护栏(BR-7 v1.24 归层口径; 纯 AST 零 DB)。

背景: 审计曾按「符号跳数」判批删链为 6 层违规。v1.24 BR-7 归层口径(§0 P3)明确——
core/ 框架 Mixin、process_fn 回调、闭包与同类私有方法按其**定义所属架构层**归并计数,
符号跳数不作为 BR-7 口径。本护栏把该口径固化为可执行断言,防同型误判复发。

四条断言(全部基于 AST import map 全路径解析,禁类名正则/字符串白名单——(c)-2):
(a) 跨层深度 ≤ 3: 层 = View/Service/Selector,core/ 框架函数、闭包、同类私有方法
    归并到调用方所属层(View→Service→Selector 为标准深度);
(b) 无 Service→Service 批删调用: 不同 Service 模块间 batch_delete_* → batch_delete_*
    即违规;同类方法委托(asset_lifecycle_mixin 内部)不算;
(c)① ORM 仅扫 batch_delete* 可达路径上的 View 方法: 禁止 Model.objects.*,
    允许 self.get_queryset()/Selector 调用,豁免名单为空;
(d) 输出符号链跳数与跨层深度并列——预期 6 与 3,
    注释「BR-7 不计此维度,留档防同型误判复发」。
"""

import ast
from collections import deque
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]

# 批删链可达性分析范围(View 层 + 框架 + Service 层 + Selector 层)
SCAN_DIRS = (
    BACKEND_ROOT / "apps" / "assetmanagement" / "views",
    BACKEND_ROOT / "apps" / "assetmanagement" / "services",
    BACKEND_ROOT / "apps" / "assetmanagement" / "selectors",
    BACKEND_ROOT / "core",
)

ENTRY = "core.batch_mixins:BatchDeleteViewMixin.batch_delete"
MAX_CROSS_LAYER_DEPTH = 3  # BR-7: View→Service→Selector 标准深度

_FUNCS: dict[str, ast.AST] = {}
_IMPORTS: dict[str, dict[str, str]] = {}
_WIRED: dict[str, str] = {}  # batch_delete_service 属性接线: service 方法全限定 → 注册键


def _module_of(path: Path) -> str:
    rel = path.relative_to(BACKEND_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _layer_of(qualified: str) -> str:
    module = qualified.split(":", 1)[0]
    if module.startswith("apps.") and ".views" in module:
        return "view"
    if module.startswith("apps.") and ".services" in module:
        return "service"
    if module.startswith("apps.") and ".selectors" in module:
        return "selector"
    return "framework"  # core/ 框架层: 归并调用方所属层


def _register(tree: ast.Module, module: str) -> None:
    """注册全部函数/方法/闭包 → f"{module}:{限定名}"(类限定,防同名误绑)。"""

    def walk_body(body: list[ast.stmt], prefix: str) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = f"{prefix}.{node.name}" if prefix else node.name
                _FUNCS[f"{module}:{qual}"] = node
                walk_body(node.body, qual)
            elif isinstance(node, ast.ClassDef):
                walk_body(node.body, f"{prefix}.{node.name}" if prefix else node.name)
            elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
                walk_body(node.body, prefix)

    walk_body(tree.body, "")


def _import_map(tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                out[alias.asname or alias.name] = f"{node.module}.{alias.asname or alias.name}"
    return out


def _resolve_full(dotted: str) -> str | None:
    """全限定点分名 → 注册键(试每个拆分点 + 包级导入回退到具体子模块)。"""
    parts = dotted.split(".")
    for i in range(1, len(parts)):
        cand = f"{'.'.join(parts[:i])}:{'.'.join(parts[i:])}"
        if cand in _FUNCS:
            return cand
    # 包级导入回退: import 落在包("apps.x.services")而注册键在具体子模块
    # ("apps.x.services.asset_service")——按尾段精确匹配 + 前缀限定
    for i in range(1, len(parts)):
        prefix = ".".join(parts[:i])
        tail = ".".join(parts[i:])
        hits = [k for k in _FUNCS if k.split(":", 1)[1] == tail and k.split(":", 1)[0].startswith(prefix)]
        if len(hits) == 1:
            return hits[0]
    return None


def _iter_callees(func: ast.AST, cur_qual: str) -> list[str]:
    """解析函数体内调用 → 注册键候选(尽力解析;闭包/接线边经 cur_qual/类属性)。"""
    module = cur_qual.split(":", 1)[0]
    imports = _IMPORTS.get(module, {})
    cls_part = cur_qual.split(":", 1)[1].split(".")[0] if ":" in cur_qual else ""
    callees: list[str] = []

    def add(cand: str | None) -> None:
        if cand and cand in _FUNCS:
            callees.append(cand)

    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            # getattr(Cls, 动态方法名)(...) → 展开该类全部方法(保守上界,lifecycle 单删闭包形态)
            if (
                isinstance(node.func, ast.Call)
                and isinstance(node.func.func, ast.Name)
                and node.func.func.id == "getattr"
            ):
                if node.func.args and isinstance(node.func.args[0], ast.Name):
                    cls_q = _resolve_full(imports.get(node.func.args[0].id, node.func.args[0].id))
                    if cls_q:
                        callees.extend(k for k in _FUNCS if k.startswith(cls_q + "."))
            # 回调关键字: process_fn=_delete_one(闭包随宿主注册)
            for kw in node.keywords:
                if kw.arg == "process_fn" and isinstance(kw.value, ast.Name):
                    add(f"{cur_qual}.{kw.value.id}")
                    add(f"{module}:{kw.value.id}")
            f = node.func
            if isinstance(f, ast.Attribute):
                if isinstance(f.value, ast.Name):
                    base = f.value.id
                    if base == "self":
                        add(f"{module}:{cls_part}.{f.attr}")
                        add(f"{module}:{f.attr}")
                    elif base in imports:
                        add(_resolve_full(f"{imports[base]}.{f.attr}"))
                    else:
                        add(f"{module}:{base}")
                elif isinstance(f.value, ast.Call):
                    inner = f.value.func
                    if isinstance(inner, ast.Attribute) and isinstance(inner.value, ast.Name):
                        base = inner.value.id
                        add(_resolve_full(f"{imports.get(base, '')}.{inner.attr}" if base in imports else ""))
            elif isinstance(f, ast.Name):
                add(f"{module}:{cls_part}.{f.id}" if cls_part else "")
                add(f"{module}:{f.id}")
                if f.id in imports:
                    add(_resolve_full(imports[f.id]))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            # 方法体内接线(self.wired = Cls.method 形态,如 lifecycle 基类)
            target, value = node.targets[0], node.value
            if isinstance(target, ast.Attribute) and isinstance(value, ast.Attribute):
                if isinstance(value.value, ast.Name) and value.value.id in imports:
                    resolved = _resolve_full(f"{imports[value.value.id]}.{value.attr}")
                    if resolved:
                        _WIRED[f"{cur_qual}.{target.attr}"] = resolved
    return callees


def _build_index() -> None:
    if _FUNCS:
        return
    for scan_dir in SCAN_DIRS:
        for path in scan_dir.rglob("*.py"):
            if "tests" in path.parts or "migrations" in path.parts:
                continue
            module = _module_of(path)
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            _register(tree, module)
            _IMPORTS[module] = _import_map(tree)
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
                for stmt in cls.body:
                    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
                        target, value = stmt.targets[0], stmt.value
                        if isinstance(target, ast.Name) and isinstance(value, ast.Attribute):
                            if isinstance(value.value, ast.Name):
                                full = _IMPORTS[module].get(value.value.id, "") + "." + value.attr
                                resolved = _resolve_full(full)
                                if resolved:
                                    _WIRED[f"{module}.{cls.name}.{target.id}"] = resolved
                                else:
                                    _WIRED[f"{module}.{cls.name}.{target.id}"] = full


def _wired_targets_for(cur_qual: str) -> list[str]:
    """调用点接线: core Mixin batch_delete_invoke → 各 ViewSet batch_delete_service 目标。"""
    out: list[str] = []
    for key, target in _WIRED.items():
        if key.split(".")[-1] == "batch_delete_service" and "batch_delete_invoke" in cur_qual:
            resolved = _resolve_full(target)
            if resolved:
                out.append(resolved)
    # 方法体内接线(self.wired 属性调用点): self.delete_service_method 等
    for key, target in _WIRED.items():
        if key.startswith(cur_qual + "."):
            resolved = _resolve_full(target)
            if resolved and resolved not in out:
                out.append(resolved)
    return out


def _callees_of(qual: str) -> list[str]:
    node = _FUNCS.get(qual)
    if node is None:
        return []
    callees = list(_iter_callees(node, qual))
    if qual.endswith("batch_delete_invoke"):
        callees += [t for t in _wired_targets_for(qual) if t not in callees]
    # 子类覆写边: core Mixin 经 self.X 分发到各 ViewSet 的覆写实现
    # (如 asset_view.batch_delete_prefilter——(c)① 的扫描对象),保持"可达"语义完整
    if qual.startswith("core.batch_mixins:"):
        leaf = qual.rsplit(":", 1)[1].rsplit(".", 1)[-1]
        if leaf in ("batch_delete", "batch_delete_prefilter", "batch_delete_invoke"):
            callees += _viewset_override_targets(leaf, exclude=leaf == "batch_delete_invoke")
    return callees


def _viewset_override_targets(method_leaf: str, exclude: bool = False) -> list[str]:
    """所有持有 batch_delete_service 接线的 ViewSet(即继承 Mixin 的域)中该方法的覆写实现。"""
    targets: list[str] = []
    for key in _WIRED:
        if not key.endswith(".batch_delete_service"):
            continue
        module, cls, _ = key.rsplit(".", 2)
        for cand in (f"{module}:{cls}.{method_leaf}", f"{module}:{method_leaf}"):
            if cand in _FUNCS and cand not in targets:
                targets.append(cand)
    if exclude:
        targets = [t for t in targets if not t.startswith("core.")]
    return targets


def _batch_entries() -> list[str]:
    """入口: 共用 core Mixin action + View 层手写批删 action(如 recycle 域手动编排)。"""
    entries = [ENTRY]
    for qualified in _FUNCS:
        _module, name = qualified.rsplit(":", 1)
        if _layer_of(qualified) == "view" and "batch_delete" in name.split(".")[-1]:
            entries.append(qualified)
    return entries


def _reachable(entries: list[str]) -> set[str]:
    seen: set[str] = set(entries)
    q: deque[str] = deque(entries)
    while q:
        cur = q.popleft()
        for callee in _callees_of(cur):
            if callee not in seen:
                seen.add(callee)
                q.append(callee)
    return seen


def _propagate(entries: list[str]) -> dict[str, tuple[str, int]]:
    """层传播 BFS: framework 归并调用方层。返回 qual → (层, 层深)。

    层深按 BR-7「层」计数(View→Service→Selector = 3 层),入口即第 1 层。
    """
    layer: dict[str, tuple[str, int]] = dict.fromkeys(entries, ("view", 1))
    q: deque[str] = deque(entries)
    while q:
        cur = q.popleft()
        cur_layer, cur_depth = layer[cur]
        for callee in _callees_of(cur):
            fl = _layer_of(callee)
            if fl == "framework":
                new = (cur_layer, cur_depth)
            elif fl != cur_layer:
                new = (fl, cur_depth + 1)
            else:
                new = (cur_layer, cur_depth)
            prev = layer.get(callee)
            if prev is None or new[1] > prev[1]:
                layer[callee] = new
                q.append(callee)
    return layer


def _symbol_hops(entries: list[str]) -> dict[str, int]:
    """符号跳数(审计口径): 不做层归并的 BFS 最大节点链长,仅用于 (d) 输出对照。"""
    depth: dict[str, int] = dict.fromkeys(entries, 1)
    q: deque[str] = deque(entries)
    while q:
        cur = q.popleft()
        for callee in _callees_of(cur):
            nd = depth[cur] + 1
            if nd > depth.get(callee, 0):
                depth[callee] = nd
                q.append(callee)
    return depth


def _service_batch_edges() -> list[tuple[str, str]]:
    bad: list[tuple[str, str]] = []
    for qualified, _node in _FUNCS.items():
        module, name = qualified.rsplit(":", 1)
        leaf = name.split(".")[-1]
        if not leaf.startswith("batch_delete") or not (module.startswith("apps.") and ".services" in module):
            continue
        for callee in _callees_of(qualified):
            cm, cname = callee.rsplit(":", 1)
            cleaf = cname.split(".")[-1]
            if cleaf.startswith("batch_delete") and cm != module and cm.startswith("apps.") and ".services" in cm:
                bad.append((qualified, callee))
    return bad


def _view_orm_violations(reachable: set[str]) -> list[str]:
    """(c)① batch_delete* 专属 View 方法内的 Model.objects.* 违规。

    扫描面 = 可达且叶子名含 batch_delete 的 View 方法(批删专属面: action/覆写/手动编排);
    共享 get_queryset 定义体是全读面单点,不在批删专属面内(其上调用 self.get_queryset()
    本身被 (c)① 允许)。
    """
    violations: list[str] = []
    for qualified in sorted(reachable):
        if _layer_of(qualified) != "view":
            continue
        leaf = qualified.rsplit(":", 1)[1].split(".")[-1]
        if "batch_delete" not in leaf:
            continue
        module = qualified.split(":", 1)[0]
        for n in ast.walk(_FUNCS[qualified]):
            if isinstance(n, ast.Attribute) and n.attr == "objects" and isinstance(n.value, ast.Name):
                full = _IMPORTS.get(module, {}).get(n.value.id, "")
                if ".models." in full:
                    violations.append(f"{qualified}: {n.value.id}.objects (→ {full})")
    return violations


def setup_module() -> None:
    _build_index()


# ── 断言用例 ────────────────────────────────────────────────────────────────────


def _batch_reachable() -> set[str]:
    assert ENTRY in _FUNCS, "BatchDeleteViewMixin.batch_delete 入口丢失(框架重构需同步本护栏)"
    entries = _batch_entries()
    reachable = _reachable(entries)
    assert any(_layer_of(q) == "service" for q in reachable), (
        "批删链可达集未触达 Service 层——属性接线解析失效,禁静默假绿"
    )
    assert any(_layer_of(q) == "view" for q in reachable), "批删链可达集未含 View 层,解析可能失效"
    return reachable


def test_batch_delete_cross_layer_depth_within_br7():
    """(a) 跨层深度 ≤3: framework/闭包/同类私有方法按定义所属层归并(v1.24 BR-7 归层口径)。"""
    reachable = _batch_reachable()
    layer = _propagate(sorted(reachable & set(_batch_entries())))
    depth = max(d for _, d in layer.values())
    assert depth <= MAX_CROSS_LAYER_DEPTH, (
        f"批删链跨层深度 {depth} > {MAX_CROSS_LAYER_DEPTH}(BR-7 违规);归层口径: framework/闭包按定义所属层归并"
    )


def test_no_service_to_service_batch_delete_call():
    """(b) 不同 Service 模块间 batch_delete_* → batch_delete_* 即违规;同类委托不算。"""
    bad = _service_batch_edges()
    assert not bad, f"Service→Service 批删调用(跨模块) {len(bad)} 处:\n" + "\n".join(f"{a} → {b}" for a, b in bad)


def test_no_model_objects_in_batch_reachable_view_methods():
    """(c)① batch_delete* 可达 View 方法禁 Model.objects.*;允许 self.get_queryset()/Selector,豁免名单为空。"""
    reachable = _batch_reachable()
    bad = _view_orm_violations(reachable)
    assert not bad, "可达 View 方法存在 Model.objects.* 直查(违反 (c)①):\n" + "\n".join(bad)


def test_symbol_chain_hop_count_recorded_with_cross_layer(capsys):
    """(d) 符号链跳数与跨层深度并列输出,留档防同型误判复发(审计口径=符号跳数,非 BR-7 口径)。

    实测跳数为**保守上界**(getattr 动态分发展开为类方法全集);审计 canonical 链为
    View.batch_delete → core.invoke → Service.batch_delete_* → _delete_one → delete_*
    → Selector = 6。两组数字并列留档: BR-7 不计符号跳数维度。
    """
    _batch_reachable()
    entries = _batch_entries()
    layer = _propagate(entries)
    depth = max(d for _, d in layer.values())
    hops = max(_symbol_hops(entries).values())
    print(
        f"[M-03/X′] 批删链: 符号链跳数 实测上界 {hops}(canonical 链 6) 与跨层深度 {depth} 并列"
        f"(BR-7 不计此维度,留档防同型误判复发)"
    )
    assert depth <= MAX_CROSS_LAYER_DEPTH
    assert hops >= depth  # 归并规则保证: 符号跳数恒 ≥ 跨层深度
