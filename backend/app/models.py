from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(500), default="")
    repo: Mapped[str] = mapped_column(String(300), default="")
    branch: Mapped[str] = mapped_column(String(100), default="main")
    source_type: Mapped[str] = mapped_column(String(20), default="git")  # git / upload
    upload_id: Mapped[int] = mapped_column(Integer, default=0)
    upload_name: Mapped[str] = mapped_column(String(300), default="")
    dag: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs: Mapped[list["PipelineRun"]] = relationship(back_populates="pipeline", cascade="all, delete-orphan")


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    size_kb: Mapped[int] = mapped_column(Integer, default=0)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/success/failed
    trigger: Mapped[str] = mapped_column(String(30), default="manual")  # manual/webhook/schedule
    commit_msg: Mapped[str] = mapped_column(String(300), default="")
    commit_author: Mapped[str] = mapped_column(String(100), default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    ai_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    report_md: Mapped[str | None] = mapped_column(Text, nullable=True)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="runs")
    node_runs: Mapped[list["NodeRun"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class NodeRun(Base):
    __tablename__ = "node_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("pipeline_runs.id"))
    node_id: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(120))
    node_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/running/success/failed/skipped
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    gate_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    run: Mapped["PipelineRun"] = relationship(back_populates="node_runs")


class GateRule(Base):
    __tablename__ = "gate_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(Integer, default=0)  # 0 表示全局默认
    name: Mapped[str] = mapped_column(String(120))
    metric: Mapped[str] = mapped_column(String(50))  # pass_rate / coverage
    op: Mapped[str] = mapped_column(String(10), default=">=")
    threshold: Mapped[float] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(String(300), default="")
