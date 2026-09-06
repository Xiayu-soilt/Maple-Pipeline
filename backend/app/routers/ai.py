import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models import Pipeline, PipelineRun
from app.services import deepseek
from app.services.ws import log_store

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _persist(run_id: int, field: str, value: str) -> None:
    """流式响应生成器执行时请求级 session 已被依赖清理关闭，
    这里用独立 session 写库，保证报告/归因可持久化到报告中心。"""
    db = SessionLocal()
    try:
        r = db.get(PipelineRun, run_id)
        if r:
            setattr(r, field, value)
            db.commit()
    finally:
        db.close()


class PipelineGenRequest(BaseModel):
    prompt: str


class GateAdviceRequest(BaseModel):
    pipeline_id: int


class CommandGenRequest(BaseModel):
    node_type: str
    node_name: str = ""
    requirement: str


def _sse_event(event_type: str, data) -> str:
    return f"data: {json.dumps({'type': event_type, 'data': data}, ensure_ascii=False)}\n\n"


def _collect_failure_context(run: PipelineRun) -> str:
    events = log_store.history(run.id)
    lines = []
    for ev in events:
        if ev.get("type") == "log" and ev.get("level") in ("ERROR", "WARN"):
            lines.append(f"[{ev['node_name']}] {ev['message']}")
    nodes_summary = "\n".join(
        f"- {nr.name}({nr.node_type}): {nr.status} "
        f"{('指标: ' + json.dumps(nr.metrics, ensure_ascii=False)) if nr.metrics else ''}"
        f"{('门禁: ' + json.dumps(nr.gate_result, ensure_ascii=False)) if nr.gate_result else ''}"
        for nr in run.node_runs
    )
    return (
        f"流水线: {run.pipeline.name}\n提交: {run.commit_msg} (by {run.commit_author})\n"
        f"执行结果: {run.status}\n统计: {json.dumps(run.stats, ensure_ascii=False)}\n\n"
        f"节点执行情况:\n{nodes_summary}\n\n"
        f"失败/告警日志:\n" + ("\n".join(lines) if lines else "（无 ERROR 日志）")
    )


def _collect_report_context(run: PipelineRun) -> str:
    """执行报告专用上下文：节点明细 + 门禁检查 + 分节点告警日志 + 检出信息。"""
    events = log_store.history(run.id)
    warn_by_node: dict[str, list[str]] = {}
    for ev in events:
        if ev.get("type") == "log" and ev.get("level") in ("ERROR", "WARN"):
            warn_by_node.setdefault(ev["node_name"], []).append(f"[{ev['level']}] {ev['message']}")

    nodes_lines = []
    for nr in run.node_runs:
        m = nr.metrics or {}
        m_str = "，".join(f"{k}={v}" for k, v in m.items()) or "无"
        gate = ""
        if nr.gate_result:
            checks = " / ".join(
                f"{c['name']}: {c['actual']} {c['op']} {c['threshold']} {'通过' if c['passed'] else '未通过'}"
                for c in nr.gate_result.get("checks", []))
            gate = f"\n  门禁检查: {checks} → {'整体通过' if nr.gate_result.get('passed') else '整体未通过'}"
        nodes_lines.append(
            f"- {nr.name}（类型: {nr.node_type}，状态: {nr.status}，"
            f"耗时: {nr.duration_ms}ms，指标: {m_str}）{gate}")

    stats = run.stats or {}
    warn_section = "\n\n".join(
        f"【{name}】\n" + "\n".join(msgs)
        for name, msgs in warn_by_node.items()) or "（本次执行无 WARN/ERROR 日志）"

    return (
        f"流水线: {run.pipeline.name}（run #{run.id}）\n"
        f"触发方式: {run.trigger} | 提交: {run.commit_msg}（by {run.commit_author}）\n"
        f"整体状态: {run.status}\n"
        f"统计: {json.dumps(stats, ensure_ascii=False)}\n\n"
        f"节点执行明细:\n" + "\n".join(nodes_lines) + "\n\n"
        f"WARN/ERROR 日志（按节点）:\n{warn_section}"
    )


@router.post("/analyze-failure/{run_id}")
async def analyze_failure(run_id: int, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "执行记录不存在")
    if run.status not in ("failed", "success"):
        raise HTTPException(400, "执行尚未结束，无法分析")
    context = _collect_failure_context(run)

    async def gen():
        full = []
        try:
            async for chunk in deepseek.chat_stream([
                {"role": "system", "content": (
                    "你是资深测试开发工程师，负责分析 CI 流水线失败。请基于给定日志用简体中文输出：\n"
                    "## 失败归因\n（1-3 条，指出根因与证据日志）\n"
                    "## 修复建议\n（可执行的修复步骤，含代码/命令示例）\n"
                    "## 防回归建议\n（补充哪些测试用例或门禁规则）\n"
                    "语气专业简洁，面向工程团队。"
                )},
                {"role": "user", "content": f"以下是本次流水线执行的完整上下文：\n\n{context}"},
            ]):
                full.append(chunk)
                yield _sse_event("chunk", chunk)
            text = "".join(full)
            _persist(run.id, "ai_analysis", text)
            yield _sse_event("done", text)
        except deepseek.DeepSeekError as e:
            yield _sse_event("error", str(e))

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/generate-command")
async def generate_command(req: CommandGenRequest):
    type_hint = {
        "test": "单元/集成测试，常用 pytest/unittest，建议带覆盖率参数",
        "api_test": "接口自动化测试，常用 pytest + requests/httpx，建议带 allure 报告",
        "e2e_test": "端到端 UI 测试，常用 Playwright/Cypress",
        "perf_test": "性能测试，常用 locust/jmeter/wrk",
        "code_lint": "静态代码检查，常用 ruff/flake8/eslint",
        "scan": "安全扫描，常用 bandit/pip-audit/npm audit/trivy",
        "build": "构建打包，常用 pip/npm/docker/maven",
        "db_migration": "数据库迁移，常用 alembic/flyway",
        "artifact": "制品发布，常用 docker push/twine upload",
        "health_check": "部署后冒烟检查，常用 curl",
        "notify": "通知推送，常用 curl 调 webhook",
        "custom": "自定义脚本任务",
    }.get(req.node_type, "CI 流水线任务")

    async def gen():
        full = []
        try:
            async for chunk in deepseek.chat_stream([
                {"role": "system", "content": (
                    "你是 CI/CD 专家。根据节点类型和用户需求，生成可直接在流水线节点中执行的 shell 命令。\n"
                    "严格输出 JSON（不要输出任何其他文字）：\n"
                    '{"command": "单条可执行命令，可用 && 串联多个步骤", '
                    '"explanation": "命令设计说明，1-2 句中文", '
                    '"alternatives": ["备选方案命令，最多 2 个"], '
                    '"tips": "使用该命令的注意事项，1 句中文"}\n'
                    "命令必须是 Linux shell 语法，参数要具体合理，考虑常见工程实践。"
                )},
                {"role": "user", "content": (
                    f"节点类型: {req.node_type}（{type_hint}）\n"
                    f"节点名称: {req.node_name or '未命名'}\n"
                    f"我的需求: {req.requirement}"
                )},
            ], temperature=0.3):
                full.append(chunk)
                yield _sse_event("chunk", chunk)
            yield _sse_event("done", "".join(full))
        except deepseek.DeepSeekError as e:
            yield _sse_event("error", str(e))

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/generate-pipeline")
async def generate_pipeline(req: PipelineGenRequest):
    node_types = (
        "checkout(拉取代码) / code_lint(代码检查) / build(构建) / db_migration(数据库迁移) / "
        "test(自动化测试) / api_test(接口测试) / e2e_test(UI自动化) / perf_test(性能测试) / "
        "scan(安全扫描) / gate(质量门禁) / approval(人工审批) / artifact(制品发布) / "
        "deploy(部署) / health_check(冒烟检查) / notify(通知) / custom(自定义脚本)"
    )
    try:
        raw = await deepseek.chat([
            {"role": "system", "content": (
                "你是 CI 流水线架构师。根据用户描述生成流水线 DAG 配置，严格输出 JSON，不要输出其他内容。\n"
                "格式: {\"name\": \"流水线名\", \"description\": \"一句话描述\", \"dag\": {\"nodes\": [...], \"edges\": [...]}}\n"
                f"每个 node: {{\"id\": \"n1\"递增, \"name\": \"中文节点名\", \"type\": \"{node_types}\", "
                "\"x\": 递增的横坐标(每列间隔240), \"y\": 200, \"config\": {}}}\n"
                "test/api_test/e2e_test/perf_test 等测试类节点 config 可含 {\"command\": \"pytest\"}; "
                "gate 节点 config 可含 {\"pass_rate_min\": 100, \"coverage_min\": 80}; deploy 节点 config 可含 {\"environment\": \"staging\"}\n"
                "edges: [{\"source\": \"n1\", \"target\": \"n2\"}]，必须是无环、尽量串行的主链路，允许合理并行分支（如 scan 与 test 并行）。\n"
                "所有 x/y 为整数坐标，用于前端画布布局，从 x=80 开始。"
            )},
            {"role": "user", "content": req.prompt},
        ], temperature=0.2, json_mode=True)
        result = deepseek._extract_json(raw)
        if "dag" not in result or "nodes" not in result["dag"]:
            raise ValueError("返回结构缺少 dag.nodes")
        for i, n in enumerate(result["dag"]["nodes"]):
            n.setdefault("id", f"n{i+1}")
            n.setdefault("name", n.get("type", "custom"))
            n.setdefault("type", "custom")
            n.setdefault("x", 80 + i * 240)
            n.setdefault("y", 200)
            n.setdefault("config", {})
        result["dag"].setdefault("edges", [])
        return result
    except deepseek.DeepSeekError as e:
        raise HTTPException(502, str(e))
    except (ValueError, json.JSONDecodeError) as e:
        raise HTTPException(502, f"AI 返回的结构无法解析: {e}")


@router.post("/gate-advice")
async def gate_advice(req: GateAdviceRequest, db: Session = Depends(get_db)):
    runs = (db.query(PipelineRun)
            .filter(PipelineRun.pipeline_id == req.pipeline_id)
            .order_by(PipelineRun.id.desc()).limit(10).all())
    if not runs:
        raise HTTPException(404, "该流水线暂无执行历史")
    history = "\n".join(
        f"- run#{r.id} [{r.status}] 通过率 {r.stats.get('pass_rate', '-')}% "
        f"覆盖率 {r.stats.get('coverage', '-')}% 失败节点 {r.stats.get('failed_nodes', 0)}"
        for r in reversed(runs)
    )
    try:
        raw = await deepseek.chat([
            {"role": "system", "content": (
                "你是质量效能专家。基于流水线最近执行数据，给出质量门禁阈值建议。"
                "严格输出 JSON: {\"advice\": \"整体建议(2-3句)\", \"rules\": [{\"metric\": \"pass_rate|coverage\", "
                "\"threshold\": 数字, \"reason\": \"原因\"}], \"risk\": \"当前风险点\"}"
            )},
            {"role": "user", "content": f"流水线执行历史:\n{history}"},
        ], temperature=0.2, json_mode=True)
        return deepseek._extract_json(raw)
    except deepseek.DeepSeekError as e:
        raise HTTPException(502, str(e))
    except json.JSONDecodeError:
        raise HTTPException(502, "AI 返回内容无法解析为 JSON")


@router.post("/report/{run_id}")
async def generate_report(run_id: int, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        raise HTTPException(404, "执行记录不存在")
    if run.status not in ("failed", "success"):
        raise HTTPException(400, "执行尚未结束，无法生成报告")
    context = _collect_report_context(run)

    async def gen():
        full = []
        try:
            async for chunk in deepseek.chat_stream([
                {"role": "system", "content": (
                    "你是资深测试经理，为 CI 流水线执行结果撰写一份内容充实、结构完整的简体中文 Markdown 报告。"
                    "严格按以下章节输出：\n"
                    "# 执行报告：<流水线名>\n"
                    "## 一、执行摘要\n"
                    "用 2-3 句话概括本次执行结论，然后用一个 Markdown 表格呈现关键数字："
                    "| 指标 | 数值 |（至少含 总节点数、成功/失败/被阻断节点数、测试通过率、代码覆盖率、总耗时、触发方式）\n"
                    "## 二、节点执行明细\n"
                    "将每个节点整理成 Markdown 表格：| 节点 | 类型 | 状态 | 耗时 | 关键指标 |，"
                    "表后用 1-2 句点评关键节点的表现（如检出文件数、测试规模、门禁结论）。\n"
                    "## 三、质量指标分析\n"
                    "结合门禁检查明细，解读通过率与覆盖率是否健康、余量多大、短板在哪。没有门禁时基于测试指标分析。\n"
                    "## 四、问题与风险\n"
                    "如有 WARN/ERROR 日志，逐条归因并说明影响；全部通过时也要基于数据指出潜在风险"
                    "（覆盖率余量小、某节点耗时异常、无安全扫描环节等）。\n"
                    "## 五、改进建议\n"
                    "给出 2-4 条可落地的行动建议（补充测试场景、调整门禁阈值、优化耗时节点、完善流水线环节等）。\n"
                    "要求：专业客观、面向工程团队与管理者；只使用提供数据中的真实数字，禁止编造；总长度 600-900 字。"
                )},
                {"role": "user", "content": f"以下是本次流水线执行的完整数据：\n\n{context}"},
            ], temperature=0.3):
                full.append(chunk)
                yield _sse_event("chunk", chunk)
            text = "".join(full)
            _persist(run.id, "report_md", text)
            yield _sse_event("done", text)
        except deepseek.DeepSeekError as e:
            yield _sse_event("error", str(e))

    return StreamingResponse(gen(), media_type="text/event-stream")
