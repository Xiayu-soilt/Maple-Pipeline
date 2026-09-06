import json

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.database import get_db
from app.engine.dag import start_run
from app.models import Pipeline, PipelineRun
from app.schemas import NodeRunOut, RunOut, RunTrigger
from app.services.security import decode_token
from app.services.ws import log_store, manager

router = APIRouter(prefix="/api", tags=["runs"])
ws_router = APIRouter(tags=["runs-ws"])


@router.post("/pipelines/{pid}/run", response_model=RunOut)
async def trigger_run(pid: int, payload: RunTrigger, db: Session = Depends(get_db)):
    pipeline = db.query(Pipeline).filter(Pipeline.id == pid).first()
    if not pipeline:
        raise HTTPException(404, "流水线不存在")
    if not pipeline.dag.get("nodes"):
        raise HTTPException(400, "流水线未配置任何节点")
    run = start_run(db, pipeline, "manual", payload.commit_msg, payload.commit_author,
                    payload.fail_node_id, payload.fail_mode)
    return run


@router.get("/runs", response_model=list[RunOut])
def list_runs(pipeline_id: int | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(PipelineRun)
    if pipeline_id:
        q = q.filter(PipelineRun.pipeline_id == pipeline_id)
    runs = q.order_by(PipelineRun.id.desc()).limit(limit).all()
    for r in runs:
        r.pipeline_name = r.pipeline.name if r.pipeline else ""
    return runs


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    run = db.query(PipelineRun).filter(PipelineRun.id == rid).first()
    if not run:
        raise HTTPException(404, "执行记录不存在")
    nodes = [NodeRunOut.model_validate(nr) for nr in run.node_runs]
    return {
        **RunOut.model_validate(run).model_dump(),
        "pipeline_name": run.pipeline.name if run.pipeline else "",
        "nodes": nodes,
        "report_md": run.report_md,
        "ai_analysis": run.ai_analysis,
    }


@router.get("/runs/{rid}/logs")
def run_logs(rid: int):
    return log_store.history(rid)


@ws_router.websocket("/ws/runs/{rid}")
async def run_ws(ws: WebSocket, rid: int):
    """WS 无法带 Authorization header，改用 ?token= 校验，失败拒绝握手。"""
    if decode_token(ws.query_params.get("token") or "") is None:
        await ws.close(code=4401)
        return
    await manager.connect(rid, ws)
    try:
        for event in log_store.history(rid):
            await ws.send_text(json.dumps(event, ensure_ascii=False))
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(rid, ws)
