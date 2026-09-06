from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Pipeline, PipelineRun, Upload
from app.schemas import PipelineCreate, PipelineOut, PipelineUpdate

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


def _get_or_404(db: Session, pid: int) -> Pipeline:
    p = db.query(Pipeline).filter(Pipeline.id == pid).first()
    if not p:
        raise HTTPException(404, "流水线不存在")
    return p


def _resolve_upload(db: Session, source_type: str, upload_id: int) -> str:
    if source_type != "upload":
        return ""
    up = db.query(Upload).filter(Upload.id == upload_id).first()
    if not up:
        raise HTTPException(400, "上传文件不存在，请重新上传")
    return up.filename


@router.get("", response_model=list[PipelineOut])
def list_pipelines(db: Session = Depends(get_db)):
    return db.query(Pipeline).order_by(Pipeline.id).all()


@router.post("", response_model=PipelineOut)
def create_pipeline(payload: PipelineCreate, db: Session = Depends(get_db)):
    if db.query(Pipeline).filter(Pipeline.name == payload.name).first():
        raise HTTPException(400, "同名流水线已存在")
    upload_name = _resolve_upload(db, payload.source_type, payload.upload_id)
    p = Pipeline(
        name=payload.name, description=payload.description,
        repo=payload.repo, branch=payload.branch,
        source_type=payload.source_type, upload_id=payload.upload_id,
        upload_name=upload_name,
        dag=payload.dag.model_dump(),
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{pid}", response_model=PipelineOut)
def get_pipeline(pid: int, db: Session = Depends(get_db)):
    return _get_or_404(db, pid)


@router.put("/{pid}", response_model=PipelineOut)
def update_pipeline(pid: int, payload: PipelineUpdate, db: Session = Depends(get_db)):
    p = _get_or_404(db, pid)
    data = payload.model_dump(exclude_none=True)
    if "dag" in data:
        if not payload.dag.nodes:
            raise HTTPException(400, "DAG 至少需要一个节点，不允许保存空流水线")
        data["dag"] = payload.dag.model_dump()
    if "upload_id" in data:
        data["upload_name"] = _resolve_upload(db, data.get("source_type", p.source_type), data["upload_id"])
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{pid}")
def delete_pipeline(pid: int, db: Session = Depends(get_db)):
    p = _get_or_404(db, pid)
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.get("/{pid}/last-run")
def last_run(pid: int, db: Session = Depends(get_db)):
    run = (db.query(PipelineRun).filter(PipelineRun.pipeline_id == pid)
           .order_by(PipelineRun.id.desc()).first())
    if not run:
        return None
    return {"id": run.id, "status": run.status, "finished_at": run.finished_at}
