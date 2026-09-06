from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NodeConfig(BaseModel):
    id: str
    name: str
    type: str
    x: int = 0
    y: int = 0
    config: dict[str, Any] = Field(default_factory=dict)


class Edge(BaseModel):
    source: str
    target: str


class DAG(BaseModel):
    nodes: list[NodeConfig]
    edges: list[Edge]


class PipelineCreate(BaseModel):
    name: str
    description: str = ""
    repo: str = ""
    branch: str = "main"
    source_type: str = "git"
    upload_id: int = 0
    dag: DAG


class PipelineUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repo: str | None = None
    branch: str | None = None
    source_type: str | None = None
    upload_id: int | None = None
    dag: DAG | None = None


class PipelineOut(BaseModel):
    id: int
    name: str
    description: str
    repo: str
    branch: str
    source_type: str = "git"
    upload_id: int = 0
    upload_name: str = ""
    dag: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    id: int
    pipeline_id: int
    pipeline_name: str = ""
    status: str
    trigger: str
    commit_msg: str
    commit_author: str
    started_at: datetime | None
    finished_at: datetime | None
    stats: dict
    ai_analysis: dict | None = None

    model_config = {"from_attributes": True}


class NodeRunOut(BaseModel):
    id: int
    node_id: str
    name: str
    node_type: str
    status: str
    duration_ms: int
    metrics: dict
    gate_result: dict | None = None

    model_config = {"from_attributes": True}


class RunTrigger(BaseModel):
    commit_msg: str = "feat: update order module"
    commit_author: str = "qa-engineer"
    fail_node_id: str | None = Field(None, description="指定让某个节点失败，用于演示门禁拦截")
    fail_mode: str | None = Field("fail", description="fail=节点执行失败；degraded=测试通过但覆盖率不达标")


class GateRuleCreate(BaseModel):
    name: str
    metric: str
    threshold: float
    op: str = ">="
    description: str = ""


class GateRuleOut(BaseModel):
    id: int
    pipeline_id: int
    name: str
    metric: str
    op: str
    threshold: float
    enabled: bool
    description: str

    model_config = {"from_attributes": True}
