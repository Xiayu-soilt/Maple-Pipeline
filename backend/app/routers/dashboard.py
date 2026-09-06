from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import NodeRun, Pipeline, PipelineRun

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    total_pipelines = db.query(Pipeline).count()
    total_runs = db.query(PipelineRun).count()
    success_runs = db.query(PipelineRun).filter(PipelineRun.status == "success").count()
    failed_runs = db.query(PipelineRun).filter(PipelineRun.status == "failed").count()
    avg_duration = db.query(func.avg(
        (func.julianday(PipelineRun.finished_at) - func.julianday(PipelineRun.started_at)) * 86400000
    )).filter(PipelineRun.status.in_(("success", "failed"))).scalar()

    since = datetime.utcnow() - timedelta(days=6)
    runs = (db.query(PipelineRun)
            .filter(PipelineRun.started_at >= since)
            .order_by(PipelineRun.id.desc()).all())
    trend = []
    for i in range(6, -1, -1):
        day = (datetime.utcnow() - timedelta(days=i)).date()
        day_runs = [r for r in runs if r.started_at and r.started_at.date() == day]
        trend.append({
            "date": day.strftime("%m-%d"),
            "total": len(day_runs),
            "success": sum(1 for r in day_runs if r.status == "success"),
            "failed": sum(1 for r in day_runs if r.status == "failed"),
        })

    recent = (db.query(PipelineRun).order_by(PipelineRun.id.desc()).limit(8).all())
    recent_out = [{
        "id": r.id, "pipeline_id": r.pipeline_id,
        "pipeline_name": r.pipeline.name if r.pipeline else "",
        "status": r.status, "commit_msg": r.commit_msg,
        "commit_author": r.commit_author, "trigger": r.trigger,
        "finished_at": r.finished_at, "stats": r.stats,
    } for r in recent]

    hot_nodes = (db.query(NodeRun.name, func.count().label("fail_count"))
                 .filter(NodeRun.status == "failed")
                 .group_by(NodeRun.name)
                 .order_by(func.count().desc()).limit(5).all())

    return {
        "cards": {
            "pipelines": total_pipelines,
            "runs": total_runs,
            "success_rate": round(success_runs / total_runs * 100, 1) if total_runs else 0,
            "avg_duration_s": round(avg_duration / 1000, 1) if avg_duration else 0,
        },
        "success_runs": success_runs,
        "failed_runs": failed_runs,
        "trend": trend,
        "recent": recent_out,
        "hot_nodes": [{"name": n, "fail_count": c} for n, c in hot_nodes],
    }
