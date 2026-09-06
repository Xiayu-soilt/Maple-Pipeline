import asyncio
import os
import random
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

STATUS_SUCCESS = "success"
STATUS_FAILED = "failed"

_test_fail_log = [
    "=================================== FAILURES ===================================",
    "_________________ TestOrder.test_create_order_invalid_stock __________________",
    "    def test_create_order_invalid_stock(self):",
    "        resp = self.client.post('/api/orders', json=self.invalid_stock_payload)",
    ">       assert resp.status_code == 400",
    "E       AssertionError: 预期返回 400，实际返回 200",
    "tests/test_order.py:58: AssertionError",
    "___________________ TestOrder.test_cancel_after_paid _________________________",
    "    def test_cancel_after_paid(self):",
    "        resp = self.client.post('/api/orders/1024/cancel')",
    ">       assert resp.json()['code'] == 'NOT_ALLOWED'",
    "E       KeyError: 'code'",
    "tests/test_order.py:112: AssertionError",
]


def _test_metrics(fail: bool, degraded: bool = False) -> dict:
    if degraded:
        return {
            "total": 86, "passed": 86, "failed": 0, "skipped": 0,
            "pass_rate": 100.0, "coverage": 76.8,
        }
    if fail:
        return {
            "total": 86, "passed": 82, "failed": 2, "skipped": 2,
            "pass_rate": 97.6, "coverage": 76.8,
        }
    return {
        "total": 86, "passed": 84, "failed": 0, "skipped": 2,
        "pass_rate": 100.0, "coverage": 84.2,
    }


def _api_test_metrics(fail: bool, degraded: bool = False) -> dict:
    if degraded:
        return {"total": 42, "passed": 42, "failed": 0, "skipped": 0,
                "pass_rate": 100.0, "coverage": 72.5}
    if fail:
        return {"total": 42, "passed": 39, "failed": 3, "skipped": 0,
                "pass_rate": 92.9, "coverage": 78.6}
    return {"total": 42, "passed": 42, "failed": 0, "skipped": 0,
            "pass_rate": 100.0, "coverage": 86.4}


def _e2e_test_metrics(fail: bool, degraded: bool = False) -> dict:
    if degraded:
        return {"total": 18, "passed": 18, "failed": 0, "skipped": 0,
                "pass_rate": 100.0, "coverage": 70.2}
    if fail:
        return {"total": 18, "passed": 16, "failed": 2, "skipped": 0,
                "pass_rate": 88.9, "coverage": 81.0}
    return {"total": 18, "passed": 18, "failed": 0, "skipped": 0,
            "pass_rate": 100.0, "coverage": 83.5}


def _checkout_lines(repo: str, branch: str, commit: str) -> list[tuple[str, str]]:
    return [
        ("INFO", f"$ git clone -b {branch} {repo}"),
        ("INFO", "Cloning into 'workspace'..."),
        ("INFO", "remote: Enumerating objects: 4521, done."),
        ("INFO", "remote: Counting objects: 100% (4521/4521), done."),
        ("INFO", "Receiving objects: 100% (4521/4521), 8.34 MiB | 6.21 MiB/s, done."),
        ("INFO", f"HEAD is now at {commit}"),
        ("INFO", "工作区准备完成 workspace/"),
    ]


_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

_PROXY_PORTS = (7897, 7890, 10809, 1080, 2080, 8118)
_NET_ERR_HINTS = ("unable to access", "Connection was reset", "Could not resolve",
                  "timed out", "Failed to connect", "SSL", "TLS", "ERR_")


def _is_safe_member(name: str) -> bool:
    return not name.startswith(("/", "\\")) and ".." not in name.replace("\\", "/")


def _detect_local_proxy() -> str | None:
    """探测常见本地代理端口（Clash/V2Ray 等），直连 GitHub 不稳定时自动走代理。"""
    import socket
    for port in _PROXY_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return f"http://127.0.0.1:{port}"
        except OSError:
            continue
    return None


def _proxy_env(proxy: str) -> dict[str, str]:
    env = dict(os.environ)
    env["HTTPS_PROXY"] = env["https_proxy"] = proxy
    env["HTTP_PROXY"] = env["http_proxy"] = proxy
    return env


async def _run_cmd(args: list[str], timeout: int,
                   env: dict[str, str] | None = None) -> tuple[int, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        creationflags=_NO_WINDOW,
        env=env,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"命令执行超时（{timeout}s）: {' '.join(args[:4])}…")
    return proc.returncode, (out or b"").decode("utf-8", "replace")


def _workspace_stats(ws: Path) -> tuple[list[Path], list[Path], float]:
    all_files = [p for p in ws.rglob("*") if p.is_file() and ".git" not in p.parts]
    py_files = [p for p in all_files if p.suffix == ".py"]
    size_kb = round(sum(p.stat().st_size for p in all_files) / 1024, 1)
    return all_files, py_files, size_kb


async def _real_checkout(node: dict, ctx: dict) -> dict:
    """真实检出：git 源执行真实 git clone，上传源真实解压到工作区。"""
    from app.services.ws import make_log_event

    node_id, node_name = node["id"], node["name"]
    emit = ctx["emit"]

    async def log(level: str, msg: str) -> None:
        await emit(make_log_event(node_id, node_name, level, msg))
        await asyncio.sleep(0.1)

    start = time.time()
    workdir = Path(tempfile.mkdtemp(prefix="maple_ws_"))
    ws = workdir / "workspace"
    source_type = ctx.get("source_type", "git")

    try:
        if source_type == "upload":
            src = Path(ctx["upload_path"])
            await log("INFO", f"📦 检出上传代码包: {ctx.get('upload_name', src.name)}")
            if src.suffix.lower() == ".zip":
                await log("INFO", f"$ unzip {src.name} -d workspace/")
                with zipfile.ZipFile(src) as zf:
                    members = [m for m in zf.infolist() if not m.is_dir() and _is_safe_member(m.filename)]
                    if not members:
                        raise RuntimeError("压缩包内没有有效文件")
                    for m in members:
                        dest = ws / m.filename
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(m))
                for m in members[:15]:
                    await log("INFO", f"  inflating: {m.filename}")
                if len(members) > 15:
                    await log("INFO", f"  … 及其余 {len(members) - 15} 个文件")
            else:
                await log("INFO", f"$ cp {src.name} → workspace/")
                ws.mkdir(parents=True, exist_ok=True)
                (ws / src.name).write_bytes(src.read_bytes())
            all_files, py_files, size_kb = _workspace_stats(ws)
            await log("INFO", f"✓ 检出完成: {len(all_files)} 个文件"
                              f"（{len(py_files)} 个 Python 文件），{size_kb} KB")
            ctx["workspace"] = str(ws)
            metrics = {"files": len(all_files), "py_files": len(py_files),
                       "size_kb": size_kb, "mode": "upload"}
        else:
            repo, branch = ctx.get("repo", ""), ctx.get("branch", "")
            branch_arg = f"-b {branch} " if branch else ""
            await log("INFO", f"$ git clone --depth 1 {branch_arg}{repo}".replace("  ", " "))
            await log("INFO", "Cloning into 'workspace'...")
            args = ["git", "clone", "--depth", "1"]
            if branch:
                args += ["-b", branch]
            args += [repo, str(ws)]
            rc, out = await _run_cmd(args, timeout=150)
            if rc != 0 and any(h in out for h in _NET_ERR_HINTS):
                proxy = _detect_local_proxy()
                if proxy:
                    await log("WARN", f"直连仓库失败（网络被重置/超时），检测到本地代理 {proxy}，自动走代理重试…")
                    rc, out = await _run_cmd(args, timeout=150, env=_proxy_env(proxy))
            for line in out.splitlines():
                if line.strip():
                    await log("INFO", line.strip()[:300])
            if rc != 0:
                tail = out.strip()[-400:]
                raise RuntimeError(
                    f"git clone 失败（exit={rc}）"
                    + (f"：{tail}" if tail else "：仓库地址错误/私有，或当前网络无法访问该仓库"))
            _, commit_line = await _run_cmd(
                ["git", "-C", str(ws), "log", "-1", "--pretty=format:%h %s (by %an)"], timeout=15)
            commit_line = commit_line.strip()
            if commit_line:
                await log("INFO", f"HEAD is now at {commit_line}")
            all_files, py_files, size_kb = _workspace_stats(ws)
            for f in sorted(all_files, key=str)[:15]:
                await log("INFO", f"  {f.relative_to(ws).as_posix()}")
            if len(all_files) > 15:
                await log("INFO", f"  … 及其余 {len(all_files) - 15} 个文件")
            await log("INFO", f"✓ 检出完成: {len(all_files)} 个文件"
                              f"（{len(py_files)} 个 Python 文件），{size_kb} KB")
            ctx["workspace"] = str(ws)
            metrics = {"files": len(all_files), "py_files": len(py_files),
                       "size_kb": size_kb, "mode": "git",
                       "commit": commit_line.split()[0] if commit_line else "-"}
        return {"status": STATUS_SUCCESS, "metrics": metrics,
                "duration_ms": int((time.time() - start) * 1000)}
    except FileNotFoundError:
        await log("ERROR", "✕ 检出失败: 未检测到 git 命令，请先安装 Git 并加入 PATH")
        await log("ERROR", "或在流水线设置中改用「上传本地代码」方式提供代码")
    except (RuntimeError, zipfile.BadZipFile, OSError) as e:
        detail = str(e).strip() or "(无详细错误消息)"
        await log("ERROR", f"✕ 检出失败 [{type(e).__name__}]: {detail}")
        await log("ERROR", "可检查仓库地址/网络连通性，或改用「上传本地代码」方式")
    return {"status": STATUS_FAILED, "metrics": {}, "duration_ms": int((time.time() - start) * 1000)}


def _build_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ pip install -r requirements.txt -q"),
        ("INFO", "Successfully installed fastapi-0.115.6 uvicorn-0.34.0 sqlalchemy-2.0.36"),
        ("INFO", "$ python -m build --wheel"),
        ("INFO", "creating build/bdist..."),
        ("INFO", "compileall: 128 source files compiled"),
    ]
    if fail:
        lines += [
            ("ERROR", "build/lib/app/services/order.py:42: SyntaxError: invalid syntax"),
            ("ERROR", "构建失败: 语法错误 order.py:42"),
        ]
    else:
        lines += [("INFO", "构建产物: dist/mall_api-1.4.2-py3-none-any.whl (2.8 MB)")]
    return lines


def _test_lines(fail: bool, degraded: bool = False) -> list[tuple[str, str]]:
    m = _test_metrics(fail, degraded)
    lines = [
        ("INFO", "$ pytest tests/ --alluredir=reports/allure --cov=app --cov-report=term"),
        ("INFO", "============================= test session starts ============================="),
        ("INFO", "platform win32 -- Python 3.10.11, pytest-7.4.3, pluggy-1.3.0"),
        ("INFO", "rootdir: D:\\workspace\\mall-api"),
        ("INFO", "plugins: allure-pytest-2.13.5, cov-5.0.0"),
        ("INFO", f"collected {m['total']} items"),
        ("INFO", ""),
        ("INFO", "tests/test_login.py ..........                                     [ 11%]"),
        ("INFO", "tests/test_cart.py ............                                    [ 26%]"),
    ]
    if degraded:
        lines += [
            ("INFO", "tests/test_order.py ............                                   [ 33%]"),
            ("INFO", "tests/test_pay.py .............                                    [ 48%]"),
            ("INFO", "tests/test_user.py ..................                              [ 69%]"),
            ("INFO", "tests/test_coupon.py .........                                     [ 80%]"),
            ("INFO", "tests/test_search.py ........                                       [ 91%]"),
            ("INFO", "tests/test_report.py ......                                        [100%]"),
            ("INFO", ""),
            ("INFO", f"{'=' * 20} {m['passed']} passed in {random.randint(38, 52)}.4s {'=' * 20}"),
            ("WARN", f"语句覆盖率: {m['coverage']}% — 新增优惠券叠加分支未覆盖"),
            ("INFO", "Allure 报告已生成: reports/allure (index.html)"),
        ]
        return lines
    if fail:
        lines += [
            ("WARN", "tests/test_order.py ........F.                                     [ 33%]"),
            ("INFO", "tests/test_pay.py .............                                    [ 48%]"),
            ("INFO", "tests/test_user.py ..................                              [ 69%]"),
            ("INFO", "tests/test_coupon.py .........                                     [ 80%]"),
            ("INFO", "tests/test_search.py ........                                       [ 91%]"),
            ("INFO", "tests/test_report.py ......                                        [100%]"),
            ("ERROR", ""),
            *[("ERROR", l) for l in _test_fail_log],
        ]
    else:
        lines += [
            ("INFO", "tests/test_order.py ...........                                    [ 33%]"),
            ("INFO", "tests/test_pay.py .............                                    [ 48%]"),
            ("INFO", "tests/test_user.py ..................                              [ 69%]"),
            ("INFO", "tests/test_coupon.py .........                                     [ 80%]"),
            ("INFO", "tests/test_search.py ........                                       [ 91%]"),
            ("INFO", "tests/test_report.py ......                                        [100%]"),
        ]
    summary = (
        f"{'2 failed, ' if fail else ''}{m['passed']} passed, {m['skipped']} skipped in {random.randint(38, 52)}.4s"
    )
    lines += [
        ("ERROR" if fail else "INFO", f"{'=' * 20} {summary} {'=' * 20}"),
        ("INFO", f"语句覆盖率: {m['coverage']}%"),
        ("INFO", f"Allure 报告已生成: reports/allure (index.html)"),
    ]
    return lines


def _scan_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ bandit -r app/ -f json -o reports/bandit.json && pip-audit -q"),
        ("INFO", "[main] INFO    profile include tests: none"),
        ("INFO", "Running rules generation: 421 rules"),
        ("INFO", "扫描 128 个源文件..."),
    ]
    if fail:
        lines += [
            ("WARN", "Issue: [B106] hardcoded_password_funcarg  app/services/auth.py:88"),
            ("WARN", "Issue: [B608] hardcoded_sql_expressions   app/dao/order.py:31"),
            ("ERROR", "发现 2 个中风险问题，安全扫描未通过"),
        ]
    else:
        lines += [
            ("INFO", "未发现高风险问题 (0 high, 0 medium)"),
            ("INFO", "依赖审计: 68 个依赖无已知漏洞"),
        ]
    return lines


def _deploy_lines(env: str, fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", f"$ docker build -t mall-api:1.4.2 ."),
        ("INFO", f"Step 1/7 : FROM python:3.10-slim"),
        ("INFO", f" ---> Using cache"),
        ("INFO", f"Successfully built 8f2a91c3d4e1"),
        ("INFO", f"$ kubectl set image deploy/mall-api api=mall-api:1.4.2 -n {env}"),
    ]
    if fail:
        lines += [
            ("ERROR", f"Error from server: deployment 'mall-api' not found in namespace {env}"),
            ("ERROR", "部署失败: 目标环境不存在"),
        ]
    else:
        lines += [
            ("INFO", f"deployment.apps/mall-api image updated"),
            ("INFO", f"waiting for rollout... 3/3 pods available"),
            ("INFO", f"部署完成: {env} 环境已更新至 1.4.2"),
        ]
    return lines


def _custom_lines(name: str, fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", f"$ bash scripts/{name}.sh"),
        ("INFO", "执行自定义脚本..."),
        ("INFO", "step 1/3 完成"),
        ("INFO", "step 2/3 完成"),
    ]
    if fail:
        lines += [("ERROR", f"脚本 {name}.sh 退出码 1"), ("ERROR", "自定义任务失败")]
    else:
        lines += [("INFO", "step 3/3 完成"), ("INFO", "自定义任务执行成功")]
    return lines


def _code_lint_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ ruff check app/ --statistics && npx eslint src/ --quiet"),
        ("INFO", "ruff: 检查 128 个 Python 文件..."),
        ("INFO", "eslint: 检查 64 个 TS/Vue 文件..."),
    ]
    if fail:
        lines += [
            ("WARN", "app/services/order.py:12:8 F401 `json` imported but unused"),
            ("WARN", "app/dao/cart.py:88:89 E501 line too long (118 > 100)"),
            ("ERROR", "ruff: 发现 2 个 error（1 个可自动修复）"),
            ("ERROR", "代码检查未通过，请运行 ruff check --fix"),
        ]
    else:
        lines += [
            ("INFO", "ruff: 0 error, 2 warning (均为可忽略的样式提示)"),
            ("INFO", "eslint: 0 error, 0 warning"),
            ("INFO", "代码检查通过"),
        ]
    return lines


def _api_test_lines(fail: bool, degraded: bool = False) -> list[tuple[str, str]]:
    m = _api_test_metrics(fail, degraded)
    lines = [
        ("INFO", "$ pytest tests/api/ --alluredir=reports/allure-api -q"),
        ("INFO", "============================= test session starts ============================="),
        ("INFO", "base_url: https://staging-mall.internal/api  (requests 2.32.3)"),
        ("INFO", f"collected {m['total']} items"),
        ("INFO", ""),
        ("INFO", "tests/api/test_login_api.py ......                                   [ 14%]"),
        ("INFO", "tests/api/test_cart_api.py ........                                  [ 33%]"),
    ]
    if degraded:
        lines += [
            ("INFO", "tests/api/test_order_api.py ..........                             [ 60%]"),
            ("INFO", "tests/api/test_pay_api.py ..........                                 [ 85%]"),
            ("INFO", "tests/api/test_coupon_api.py ......                                  [100%]"),
            ("INFO", f"{'=' * 20} {m['passed']} passed in {random.randint(18, 30)}.2s {'=' * 20}"),
            ("WARN", f"接口覆盖率: {m['coverage']}% — 优惠券叠加接口分支未覆盖"),
        ]
        return lines
    if fail:
        lines += [
            ("WARN", "tests/api/test_order_api.py ...F.F...                              [ 60%]"),
            ("INFO", "tests/api/test_pay_api.py ..........                                 [ 85%]"),
            ("INFO", "tests/api/test_coupon_api.py ......                                  [100%]"),
            ("ERROR", "tests/api/test_order_api.py::test_create_order_invalid_sku 预期 400 实际 200"),
            ("ERROR", "tests/api/test_order_api.py::test_cancel_order_paid 预期 code=NOT_ALLOWED 实际 OK"),
            ("ERROR", f"{'=' * 20} {m['failed']} failed, {m['passed']} passed in {random.randint(18, 30)}.2s {'=' * 20}"),
        ]
    else:
        lines += [
            ("INFO", "tests/api/test_order_api.py ..........                              [ 60%]"),
            ("INFO", "tests/api/test_pay_api.py ..........                                 [ 85%]"),
            ("INFO", "tests/api/test_coupon_api.py ......                                  [100%]"),
            ("INFO", f"{'=' * 20} {m['passed']} passed in {random.randint(18, 30)}.2s {'=' * 20}"),
            ("INFO", f"接口覆盖率: {m['coverage']}%"),
        ]
    return lines


def _e2e_test_lines(fail: bool, degraded: bool = False) -> list[tuple[str, str]]:
    m = _e2e_test_metrics(fail, degraded)
    lines = [
        ("INFO", "$ npx playwright test tests/e2e/ --reporter=line"),
        ("INFO", f"Running {m['total']} tests using 4 workers"),
    ]
    if degraded:
        lines += [
            ("INFO", f"  {m['passed']} passed ({random.randint(40, 70)}.5s)"),
            ("WARN", f"E2E 覆盖场景: {m['coverage']}% — 移动端结算流程未覆盖"),
        ]
        return lines
    if fail:
        lines += [
            ("WARN", "  2 flaky, 2 failed"),
            ("ERROR", "  1) [chromium] checkout.spec.ts:42CheckoutFlow › 结算页优惠券抵扣金额错误"),
            ("ERROR", "     Error: expect(received).toBe(expected) // 25.00 !== 19.00"),
            ("ERROR", "  2) [chromium] login.spec.ts:18LoginFlow › 手机验证码登录超时"),
            ("ERROR", f"  {m['failed']} failed, {m['passed']} passed ({random.randint(60, 90)}.1s)"),
        ]
    else:
        lines += [
            ("INFO", f"  {m['passed']} passed ({random.randint(45, 75)}.3s)"),
            ("INFO", f"E2E 覆盖场景: {m['coverage']}%"),
        ]
    return lines


def _perf_test_lines(fail: bool) -> list[tuple[str, str]]:
    metrics = (
        {"rps": 1240, "p95_ms": 230, "error_rate": 0.4} if not fail
        else {"rps": 460, "p95_ms": 1890, "error_rate": 8.2}
    )
    lines = [
        ("INFO", "$ locust -f locustfile.py --headless -u 200 -r 20 -t 60s --csv reports/locust"),
        ("INFO", "Type     Name          # reqs      # fails |    Avg     Min     Max  P95"),
        ("INFO", "GET      /api/products    38210     0 (0.0%) |    92      41     640  180"),
        ("INFO", "POST     /api/orders       9150    " + (f"750 ({metrics['error_rate']}%)" if fail else "4 (0.0%)") +
                  f" |   {metrics['p95_ms'] // 2}      88    4200  {metrics['p95_ms']}"),
    ]
    if fail:
        lines += [
            ("ERROR", f"聚合 RPS {metrics['rps']} < 目标 1000，P95 {metrics['p95_ms']}ms 超过 SLA 500ms"),
            ("ERROR", "性能测试未达标，建议检查下单接口慢查询"),
        ]
    else:
        lines += [
            ("INFO", f"聚合 RPS {metrics['rps']} (目标 1000) | P95 {metrics['p95_ms']}ms (SLA 500ms) | 错误率 {metrics['error_rate']}%"),
            ("INFO", "性能测试通过，报告: reports/locust/index.html"),
        ]
    return lines


def _db_migration_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ alembic upgrade head"),
        ("INFO", "INFO  [alembic.runtime.migration] Context impl SqliteImpl."),
        ("INFO", "INFO  [alembic.runtime.migration] Will assume non-transactional DDL."),
        ("INFO", "INFO  [alembic.runtime.migration] Running upgrade 2f3a1b4c -> 7c9d2e5f, add coupon table"),
    ]
    if fail:
        lines += [
            ("ERROR", "sqlalchemy.exc.OperationalError: duplicate column name 'coupon_id'"),
            ("ERROR", "迁移失败: 数据库结构与迁移脚本冲突，已回滚"),
        ]
    else:
        lines += [
            ("INFO", "INFO  [alembic.runtime.migration] 执行 DDL: CREATE TABLE coupon ..."),
            ("INFO", "迁移完成: 当前版本 7c9d2e5f (3 条迁移全部成功)"),
        ]
    return lines


def _artifact_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ docker build -t registry.internal/mall-api:1.4.2 ."),
        ("INFO", "Step 1/7 : FROM python:3.10-slim"),
        ("INFO", " ---> Using cache"),
        ("INFO", "Successfully built 8f2a91c3d4e1"),
        ("INFO", "$ docker push registry.internal/mall-api:1.4.2"),
    ]
    if fail:
        lines += [
            ("ERROR", "denied: requested access to the resource is denied"),
            ("ERROR", "推送失败: 无 registry 写权限，请检查凭据"),
        ]
    else:
        lines += [
            ("INFO", "1.4.2: digest: sha256:9f2c8ab3 size: 528MB"),
            ("INFO", "制品发布完成: registry.internal/mall-api:1.4.2"),
        ]
    return lines


def _approval_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "提交发布审批: mall-api 1.4.2 → staging"),
        ("INFO", "审批人: qa-lead@example.com, release-manager@example.com"),
        ("INFO", "等待审批中... (演示环境自动审批)"),
    ]
    if fail:
        lines += [
            ("ERROR", "✕ 审批被驳回: 回归测试范围不足，需补充订单退款场景"),
        ]
    else:
        lines += [
            ("INFO", "✓ 审批通过: qa-lead 已确认 (2026-09-05 14:32)"),
        ]
    return lines


def _health_check_lines(fail: bool) -> list[tuple[str, str]]:
    lines = [
        ("INFO", "$ curl -sf http://mall-api-staging.internal/healthz"),
        ("INFO", '{"status": "healthy", "version": "1.4.2", "uptime": "3m12s"}'),
        ("INFO", "冒烟检查: GET /api/products ... 200 OK (96ms)"),
        ("INFO", "冒烟检查: POST /api/auth/login ... 200 OK (141ms)"),
    ]
    if fail:
        lines += [
            ("ERROR", "冒烟检查: GET /api/orders ... 503 Service Unavailable (重试 3 次失败)"),
            ("ERROR", "冒烟检查未通过: 1/3 核心接口异常"),
        ]
    else:
        lines += [
            ("INFO", "冒烟检查: GET /api/orders ... 200 OK (187ms)"),
            ("INFO", "冒烟检查通过: 3/3 核心接口正常"),
        ]
    return lines


def _notify_lines() -> list[tuple[str, str]]:
    return [
        ("INFO", "$ python scripts/notify.py --channel dingtalk --template pipeline-done"),
        ("INFO", "渲染通知模板: mall-api #{{run_id}} 执行完成"),
        ("INFO", "钉钉机器人推送成功: #mall-发布群"),
        ("INFO", "邮件通知已发送: qa-team@example.com (3 人)"),
    ]


class NodeExecutor:
    """节点执行器。演示环境使用高仿真模拟执行（真实模式可扩展为 subprocess 运行 command）。"""

    METRIC_TEST_TYPES = ("test", "api_test", "e2e_test")

    async def execute(self, node: dict, ctx: dict) -> dict:
        node_type = node["type"]
        cfg = node.get("config", {})
        node_id = node["id"]
        fail = node_id == ctx.get("fail_node_id") or cfg.get("simulate") == "fail"
        degraded = (ctx.get("fail_mode") == "degraded" and node_id == ctx.get("fail_node_id")
                    and node_type in self.METRIC_TEST_TYPES)
        repo = ctx.get("repo", "git@github.com:demo/mall-api.git")
        branch = ctx.get("branch", "main")
        commit = ctx.get("commit_hash", "a1b2c3d")

        if node_type == "checkout":
            if fail or cfg.get("simulate") == "fail":
                lines, metrics = _checkout_lines(repo, branch, commit), {}
            else:
                return await _real_checkout(node, ctx)
        elif node_type == "build":
            lines, metrics = _build_lines(fail), {}
        elif node_type == "test":
            lines, metrics = _test_lines(fail, degraded), _test_metrics(fail, degraded)
        elif node_type == "api_test":
            lines, metrics = _api_test_lines(fail, degraded), _api_test_metrics(fail, degraded)
        elif node_type == "e2e_test":
            lines, metrics = _e2e_test_lines(fail, degraded), _e2e_test_metrics(fail, degraded)
        elif node_type == "perf_test":
            metrics = ({"rps": 460, "p95_ms": 1890, "error_rate": 8.2} if fail
                       else {"rps": 1240, "p95_ms": 230, "error_rate": 0.4})
            lines, metrics = _perf_test_lines(fail), metrics
        elif node_type == "code_lint":
            lines, metrics = _code_lint_lines(fail), {}
        elif node_type == "scan":
            lines, metrics = _scan_lines(fail), {}
        elif node_type == "db_migration":
            lines, metrics = _db_migration_lines(fail), {}
        elif node_type == "deploy":
            lines, metrics = _deploy_lines(cfg.get("environment", "staging"), fail), {}
        elif node_type == "artifact":
            lines, metrics = _artifact_lines(fail), {}
        elif node_type == "approval":
            lines, metrics = _approval_lines(fail), {}
        elif node_type == "health_check":
            lines, metrics = _health_check_lines(fail), {}
        elif node_type == "notify":
            lines, metrics = _notify_lines(), {}
        else:
            lines, metrics = _custom_lines(node.get("name", "task"), fail), {}

        from app.services.ws import make_log_event

        start = time.time()
        for level, message in lines:
            await asyncio.sleep(random.uniform(0.3, 0.8))
            await ctx["emit"](make_log_event(node_id, node["name"], level, message))
        duration_ms = int((time.time() - start) * 1000)

        status = STATUS_FAILED if fail and any(l[0] == "ERROR" for l in lines) else STATUS_SUCCESS
        return {"status": status, "metrics": metrics, "duration_ms": duration_ms}
