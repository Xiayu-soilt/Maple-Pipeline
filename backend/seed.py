import json
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import LOGS_DIR
from app.engine.dag import start_run
from app.engine.executor import _test_metrics
from app.engine import gate as gate_engine
from app.models import NodeRun, Pipeline, PipelineRun

PIPELINE_1 = {
    "name": "mall-api · 主干流水线",
    "description": "商城后端服务：构建 → 测试/安全扫描并行 → 质量门禁 → 部署",
    "repo": "git@github.com:demo/mall-api.git",
    "branch": "main",
    "dag": {
        "nodes": [
            {"id": "n1", "name": "拉取代码", "type": "checkout", "x": 80, "y": 200, "config": {}},
            {"id": "n2", "name": "构建镜像", "type": "build", "x": 320, "y": 200, "config": {}},
            {"id": "n3", "name": "单元/接口测试", "type": "test", "x": 560, "y": 110, "config": {"command": "pytest"}},
            {"id": "n4", "name": "安全扫描", "type": "scan", "x": 560, "y": 290, "config": {}},
            {"id": "n5", "name": "质量门禁", "type": "gate", "x": 800, "y": 200,
             "config": {"pass_rate_min": 100, "coverage_min": 80}},
            {"id": "n6", "name": "部署 Staging", "type": "deploy", "x": 1040, "y": 200, "config": {"environment": "staging"}},
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n2", "target": "n4"},
            {"source": "n3", "target": "n5"},
            {"source": "n4", "target": "n5"},
            {"source": "n5", "target": "n6"},
        ],
    },
}

PIPELINE_2 = {
    "name": "web-portal · 前端发布流水线",
    "description": "官网前端：构建 → E2E 测试 → 门禁 → 生产发布",
    "repo": "git@github.com:demo/web-portal.git",
    "branch": "release",
    "dag": {
        "nodes": [
            {"id": "n1", "name": "拉取代码", "type": "checkout", "x": 80, "y": 200, "config": {}},
            {"id": "n2", "name": "依赖安装与构建", "type": "build", "x": 320, "y": 200, "config": {}},
            {"id": "n3", "name": "Playwright E2E", "type": "test", "x": 560, "y": 200, "config": {"command": "playwright test"}},
            {"id": "n4", "name": "质量门禁", "type": "gate", "x": 800, "y": 200,
             "config": {"pass_rate_min": 100, "coverage_min": 70}},
            {"id": "n5", "name": "发布生产", "type": "deploy", "x": 1040, "y": 200, "config": {"environment": "prod"}},
        ],
        "edges": [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
            {"source": "n3", "target": "n4"},
            {"source": "n4", "target": "n5"},
        ],
    },
}

COMMITS = [
    ("feat: 订单模块支持优惠券叠加", "zhang.dev"),
    ("fix: 修复购物车数量校验", "li.qa"),
    ("refactor: 用户服务拆分", "wang.dev"),
    ("chore: 升级 fastapi 0.115", "zhang.dev"),
    ("test: 补充支付回调用例", "li.qa"),
    ("perf: 商品搜索接口加缓存", "chen.dev"),
]


def _write_logs(run_id: int, pipeline: Pipeline, fail: bool, start: datetime) -> None:
    events = [{"type": "run_status", "run_id": run_id, "status": "running",
               "ts": start.isoformat()}]
    now = start
    for node in pipeline.dag["nodes"]:
        events.append({"type": "node_status", "node_id": node["id"], "name": node["name"],
                       "status": "running", "duration_ms": 0, "metrics": {}, "gate_result": None,
                       "ts": now.isoformat()})
        events.append({"type": "log", "node_id": node["id"], "node_name": node["name"],
                       "level": "INFO", "message": f"▶ 开始执行 [{node['type']}] {node['name']}",
                       "ts": now.isoformat()})
        now += timedelta(seconds=random.randint(4, 14))
    events.append({"type": "run_status", "run_id": run_id,
                   "status": "failed" if fail else "success",
                   "ts": now.isoformat()})
    with open(LOGS_DIR / f"{run_id}.jsonl", "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _fake_run(db: Session, pipeline: Pipeline, days_ago: int, fail: bool) -> None:
    start = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(1, 9))
    msg, author = random.choice(COMMITS)
    run = PipelineRun(
        pipeline_id=pipeline.id, status="failed" if fail else "success",
        trigger=random.choice(["webhook", "schedule", "manual"]),
        commit_msg=msg, commit_author=author,
        started_at=start, finished_at=start + timedelta(seconds=random.randint(50, 90)),
    )
    db.add(run)
    db.flush()

    test_fail = fail
    for node in pipeline.dag["nodes"]:
        status, metrics, gate_result = "success", {}, None
        if node["type"] == "test":
            metrics = _test_metrics(test_fail)
            status = "failed" if test_fail else "success"
        elif node["type"] == "gate":
            gate_result = gate_engine.evaluate(node.get("config", {}), metrics if test_fail else _test_metrics(False))
            status = "failed" if not gate_result["passed"] else "success"
            metrics = {}
        elif node["type"] == "deploy" and fail:
            status = "skipped"
        db.add(NodeRun(
            run_id=run.id, node_id=node["id"], name=node["name"], node_type=node["type"],
            status=status, started_at=start, finished_at=start,
            duration_ms=random.randint(3000, 18000), metrics=metrics, gate_result=gate_result,
        ))

    passed = sum(1 for n in pipeline.dag["nodes"] if n["type"] != "deploy")
    run.stats = {
        "total_nodes": len(pipeline.dag["nodes"]),
        "passed_nodes": passed - (2 if fail else 0),
        "failed_nodes": 1 if fail else 0,
        "skipped_nodes": 1 if fail else 0,
        "duration_ms": random.randint(52000, 88000),
        **({"pass_rate": 97.6, "coverage": 76.8} if fail else {"pass_rate": 100.0, "coverage": 84.2}),
    }
    db.commit()
    _write_logs(run.id, pipeline, fail, start)


def seed_if_empty(db: Session) -> bool:
    if db.query(Pipeline).count() > 0:
        return False
    p1 = Pipeline(**{k: v for k, v in PIPELINE_1.items()})
    p2 = Pipeline(**{k: v for k, v in PIPELINE_2.items()})
    db.add_all([p1, p2])
    db.commit()

    _fake_run(db, p1, 6, False)
    _fake_run(db, p1, 5, True)
    _fake_run(db, p2, 5, False)
    _fake_run(db, p1, 4, False)
    _fake_run(db, p2, 3, True)
    _fake_run(db, p1, 3, False)
    _fake_run(db, p2, 2, False)
    _fake_run(db, p1, 2, False)
    _fake_run(db, p1, 1, True)
    _fake_run(db, p2, 1, False)
    return True


def run_live_demo(db: Session) -> None:
    """首次启动时真实执行两条流水线，立即产生可回放的实时日志。"""
    p1 = db.query(Pipeline).filter(Pipeline.name == PIPELINE_1["name"]).first()
    p2 = db.query(Pipeline).filter(Pipeline.name == PIPELINE_2["name"]).first()
    if p1:
        start_run(db, p1, "manual", "feat: 订单模块支持优惠券叠加", "zhang.dev", fail_node_id=None)
    if p2:
        start_run(db, p2, "webhook", "fix: 修复首页在低版本浏览器的白屏", "wang.dev", fail_node_id="n3")
