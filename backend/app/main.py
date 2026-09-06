from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.auth_db import AuthBase, auth_engine
from app.database import Base, SessionLocal, engine
from app.routers import ai, auth, dashboard, pipelines, reports, runs, uploads
from app.routers.auth import require_auth
from seed import run_live_demo, seed_if_empty


def _migrate_columns() -> None:
    """SQLite 轻量迁移：create_all 只建新表，这里给已有表补齐新增列。"""
    migrations = {
        "pipelines": {
            "source_type": "VARCHAR(20) DEFAULT 'git' NOT NULL",
            "upload_id": "INTEGER DEFAULT 0 NOT NULL",
            "upload_name": "VARCHAR(300) DEFAULT '' NOT NULL",
        },
        "pipeline_runs": {
            "report_md": "TEXT",
            "ai_analysis": "JSON",
        },
    }
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in migrations.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for col, ddl in cols.items():
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _migrate_columns()
    AuthBase.metadata.create_all(bind=auth_engine)
    db = SessionLocal()
    try:
        if seed_if_empty(db):
            run_live_demo(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Maple Pipeline", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
_protected = [Depends(require_auth)]
app.include_router(pipelines.router, dependencies=_protected)
app.include_router(runs.router, dependencies=_protected)
app.include_router(ai.router, dependencies=_protected)
app.include_router(dashboard.router, dependencies=_protected)
app.include_router(uploads.router, dependencies=_protected)
app.include_router(reports.router, dependencies=_protected)
app.include_router(runs.ws_router)


@app.get("/")
def root():
    return {"app": "Maple Pipeline", "docs": "/docs"}
