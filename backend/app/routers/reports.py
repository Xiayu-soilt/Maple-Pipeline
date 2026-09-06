from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PipelineRun

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(limit: int = 100, db: Session = Depends(get_db)):
    """报告中心：聚合所有已生成 AI 报告/归因的执行记录。"""
    runs = (db.query(PipelineRun)
            .filter(or_(PipelineRun.report_md.isnot(None),
                        PipelineRun.ai_analysis.isnot(None)))
            .order_by(PipelineRun.id.desc())
            .limit(limit).all())
    return [
        {
            "run_id": r.id,
            "pipeline_id": r.pipeline_id,
            "pipeline_name": r.pipeline.name if r.pipeline else "",
            "status": r.status,
            "stats": r.stats or {},
            "commit_msg": r.commit_msg,
            "commit_author": r.commit_author,
            "finished_at": r.finished_at,
            "has_report": bool(r.report_md),
            "has_analysis": bool(r.ai_analysis),
            "report_md": r.report_md or "",
            "ai_analysis": r.ai_analysis,
        }
        for r in runs
    ]


@router.get("/{run_id}")
def report_detail(run_id: int, db: Session = Depends(get_db)):
    r = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not r:
        raise HTTPException(404, "执行记录不存在")
    return {
        "run_id": r.id,
        "pipeline_id": r.pipeline_id,
        "pipeline_name": r.pipeline.name if r.pipeline else "",
        "status": r.status,
        "stats": r.stats or {},
        "finished_at": r.finished_at,
        "report_md": r.report_md or "",
        "ai_analysis": r.ai_analysis,
    }
