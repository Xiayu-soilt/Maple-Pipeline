import asyncio
import random
import string
from collections import defaultdict
from datetime import datetime

from sqlalchemy.orm import Session

from app.engine import gate as gate_engine
from app.engine.executor import NodeExecutor
from app.models import NodeRun, Pipeline, PipelineRun
from app.services.ws import manager, make_log_event

# 产出通过率/覆盖率指标的测试节点类型（参与质量门禁聚合）
METRIC_TEST_TYPES = ("test", "api_test", "e2e_test")


def topo_layers(nodes: list[dict], edges: list[dict]) -> list[list[str]]:
    indeg = {n["id"]: 0 for n in nodes}
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["source"] in indeg and e["target"] in indeg:
            indeg[e["target"]] += 1
            children[e["source"]].append(e["target"])
    layer = [nid for nid, d in indeg.items() if d == 0]
    layers: list[list[str]] = []
    while layer:
        layers.append(sorted(layer))
        nxt = []
        for nid in layer:
            for c in children[nid]:
                indeg[c] -= 1
                if indeg[c] == 0:
                    nxt.append(c)
        layer = nxt
    if sum(len(l) for l in layers) != len(nodes):
        raise ValueError("DAG 中检测到环，无法调度")
    return layers


def _descendants(edges: list[dict], nid: str) -> set[str]:
    children: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        children[e["source"]].append(e["target"])
    seen: set[str] = set()
    stack = list(children.get(nid, []))
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(children.get(cur, []))
    return seen


class DagRunner:
    def __init__(self, db: Session, run: PipelineRun, pipeline: Pipeline):
        self.db = db
        self.run = run
        self.pipeline = pipeline
        self.node_run_map: dict[str, NodeRun] = {}
        self.metrics: dict[str, dict] = {}
        self.node_status: dict[str, str] = {}

    async def emit(self, event: dict) -> None:
        await manager.broadcast(self.run.id, event)

    async def _set_node(self, node: dict, status: str, duration_ms: int = 0,
                        metrics: dict | None = None, gate_result: dict | None = None) -> None:
        nr = self.node_run_map[node["id"]]
        nr.status = status
        if status in ("running",):
            nr.started_at = datetime.utcnow()
        if status in ("success", "failed", "skipped"):
            nr.finished_at = datetime.utcnow()
            nr.duration_ms = duration_ms
        if metrics:
            nr.metrics = metrics
            self.metrics[node["id"]] = metrics
        if gate_result:
            nr.gate_result = gate_result
        self.node_status[node["id"]] = status
        self.db.commit()
        await self.emit({
            "type": "node_status",
            "node_id": node["id"],
            "name": node["name"],
            "status": status,
            "duration_ms": duration_ms,
            "metrics": metrics or {},
            "gate_result": gate_result,
        })

    async def _run_gate_node(self, node: dict) -> dict:
        test_metrics = [m for nid, m in self.metrics.items()
                        if self.node_run_map[nid].node_type in METRIC_TEST_TYPES
                        and self.node_status.get(nid) in ("success", "failed")]
        merged: dict | None = None
        if test_metrics:
            total = sum(m.get("total", 0) for m in test_metrics)
            passed = sum(m.get("passed", 0) for m in test_metrics)
            failed = sum(m.get("failed", 0) for m in test_metrics)
            skipped = sum(m.get("skipped", 0) for m in test_metrics)
            executed = passed + failed
            merged = {
                "total": total, "passed": passed, "failed": failed, "skipped": skipped,
                "pass_rate": round(passed / executed * 100, 2) if executed else 100.0,
                "coverage": round(min(m.get("coverage", 100.0) for m in test_metrics), 1),
            }
        result = gate_engine.evaluate(node.get("config", {}), merged)
        nid, name = node["id"], node["name"]
        await self.emit(make_log_event(nid, name, "INFO", "┌─ 质量门禁评估"))
        if merged is None:
            await self.emit(make_log_event(nid, name, "WARN", result["message"]))
        else:
            await self.emit(make_log_event(
                nid, name, "INFO",
                f"│ 汇总指标: 通过率 {merged['pass_rate']}% | 覆盖率 {merged['coverage']}% "
                f"({merged['passed']} passed / {merged['failed']} failed / {merged['skipped']} skipped)"))
            for c in result["checks"]:
                mark = "PASS" if c["passed"] else "FAIL"
                await self.emit(make_log_event(
                    nid, name, "INFO" if c["passed"] else "ERROR",
                    f"│ [{mark}] {c['name']}: 实际 {c['actual']} {c['op']} 阈值 {c['threshold']}"))
        await self.emit(make_log_event(
            nid, name, "INFO" if result["passed"] else "ERROR",
            f"└─ 门禁结论: {'通过，放行到下游' if result['passed'] else '未通过，已阻断下游部署'}"))
        return result

    async def execute(self, ctx: dict) -> None:
        for nr in self.run.node_runs:
            self.node_run_map[nr.node_id] = nr
        dag = self.pipeline.dag
        nodes = {n["id"]: n for n in dag["nodes"]}
        edges = dag["edges"]
        executor = NodeExecutor()
        start_time = datetime.utcnow()
        self.run.status = "running"
        self.run.started_at = start_time
        self.db.commit()
        await self.emit({"type": "run_status", "run_id": self.run.id, "status": "running"})

        try:
            layers = topo_layers(dag["nodes"], edges)
        except ValueError as e:
            await self.emit({"type": "run_status", "run_id": self.run.id, "status": "failed", "stats": {}, "error": str(e)})
            self.run.status = "failed"
            self.run.finished_at = datetime.utcnow()
            self.db.commit()
            return

        blocked: set[str] = set()
        for layer in layers:
            tasks = []
            for nid in layer:
                node = nodes[nid]
                if nid in blocked:
                    await self._set_node(node, "skipped")
                    await self.emit(make_log_event(nid, node["name"], "WARN", "上游失败，节点被阻断跳过"))
                    continue
                tasks.append(self._exec_one(node, executor, ctx))
            await asyncio.gather(*tasks)
            for nid in layer:
                if self.node_status.get(nid) == "failed":
                    blocked.update(_descendants(edges, nid))

        duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        failed_nodes = [nid for nid, s in self.node_status.items() if s == "failed"]
        self.run.status = "failed" if failed_nodes else "success"
        self.run.finished_at = datetime.utcnow()
        self.run.stats = self._build_stats(duration_ms)
        self.db.commit()
        await self.emit({
            "type": "run_status", "run_id": self.run.id,
            "status": self.run.status, "stats": self.run.stats,
        })

    async def _exec_one(self, node: dict, executor: NodeExecutor, ctx: dict) -> None:
        await self._set_node(node, "running")
        await self.emit(make_log_event(node["id"], node["name"], "INFO", f"▶ 开始执行 [{node['type']}] {node['name']}"))
        if node["type"] == "gate":
            await asyncio.sleep(0.6)
            result = await self._run_gate_node(node)
            status = "success" if result["passed"] else "failed"
            await self._set_node(node, status, 600, {}, result)
            return
        outcome = await executor.execute(node, ctx)
        await self._set_node(node, outcome["status"], outcome["duration_ms"], outcome["metrics"])

    def _build_stats(self, duration_ms: int) -> dict:
        statuses = list(self.node_status.values())
        merged = self._merged_test_metrics()
        return {
            "total_nodes": len(statuses),
            "passed_nodes": statuses.count("success"),
            "failed_nodes": statuses.count("failed"),
            "skipped_nodes": statuses.count("skipped"),
            "duration_ms": duration_ms,
            **({"pass_rate": merged["pass_rate"], "coverage": merged["coverage"]} if merged else {}),
        }

    def _merged_test_metrics(self) -> dict | None:
        test_metrics = [m for nid, m in self.metrics.items()
                        if self.node_run_map[nid].node_type in METRIC_TEST_TYPES
                        and self.node_status.get(nid) in ("success", "failed")]
        if not test_metrics:
            return None
        total = sum(m.get("total", 0) for m in test_metrics)
        passed = sum(m.get("passed", 0) for m in test_metrics)
        failed = sum(m.get("failed", 0) for m in test_metrics)
        executed = passed + failed
        return {
            "pass_rate": round(passed / executed * 100, 2) if executed else 100.0,
            "coverage": round(min(m.get("coverage", 100.0) for m in test_metrics), 1),
        }


def random_commit() -> str:
    return "".join(random.choices(string.hexdigits.lower(), k=7))


def start_run(db: Session, pipeline: Pipeline, trigger: str, commit_msg: str,
              commit_author: str, fail_node_id: str | None = None,
              fail_mode: str | None = "fail") -> PipelineRun:
    from app.database import SessionLocal
    from app.models import Upload

    run = PipelineRun(
        pipeline_id=pipeline.id, status="pending", trigger=trigger,
        commit_msg=commit_msg, commit_author=commit_author,
    )
    db.add(run)
    db.flush()
    for node in pipeline.dag["nodes"]:
        db.add(NodeRun(
            run_id=run.id, node_id=node["id"], name=node["name"],
            node_type=node["type"], status="pending",
        ))
    db.commit()
    run_id, pipeline_id = run.id, pipeline.id
    repo = pipeline.repo or "git@github.com:demo/mall-api.git"
    branch = pipeline.branch
    source_type = pipeline.source_type or "git"
    upload_path, upload_name = None, None
    if source_type == "upload" and pipeline.upload_id:
        up = db.query(Upload).filter(Upload.id == pipeline.upload_id).first()
        if up:
            upload_path, upload_name = up.stored_path, up.filename

    async def _background():
        bg_db = SessionLocal()
        try:
            bg_run = bg_db.get(PipelineRun, run_id)
            bg_pipeline = bg_db.get(Pipeline, pipeline_id)
            if not bg_run or not bg_pipeline:
                return
            runner = DagRunner(bg_db, bg_run, bg_pipeline)
            ctx = {
                "fail_node_id": fail_node_id,
                "fail_mode": fail_mode or "fail",
                "repo": repo,
                "branch": branch,
                "source_type": source_type,
                "upload_path": upload_path,
                "upload_name": upload_name,
                "commit_hash": random_commit(),
                "emit": runner.emit,
            }
            try:
                await runner.execute(ctx)
            except Exception:
                import traceback
                traceback.print_exc()
                bg_run.status = "failed"
                bg_run.finished_at = datetime.utcnow()
                bg_db.commit()
        finally:
            bg_db.close()

    asyncio.create_task(_background())
    db.refresh(run)
    return run
