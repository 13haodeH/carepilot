import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


local_env_file = Path(os.getenv("CARE_PILOT_ENV_FILE", Path(__file__).resolve().parents[1] / ".env.local"))
load_dotenv(local_env_file, override=not bool(os.getenv("DATABASE_URL")))

configured_database_url = os.getenv("DATABASE_URL")
if not configured_database_url and any(
    os.getenv(name)
    for name in (
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
        "SUPABASE_JWKS_URL",
    )
):
    raise RuntimeError(
        "DATABASE_URL is required when Supabase settings are present. "
        "This API uses a server-only PostgreSQL connection, not Supabase REST keys."
    )

DATABASE_URL = configured_database_url or "sqlite:///./carepilot.db"


def uses_sqlite() -> bool:
    return DATABASE_URL.startswith("sqlite")


class Base(DeclarativeBase):
    pass


engine_options: dict = {}
if uses_sqlite():
    engine_options["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def ensure_sqlite_dev_schema() -> None:
    """Upgrade only the disposable SQLite fallback; Supabase uses numbered SQL migrations."""
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        def add_columns(table: str, definitions: tuple[tuple[str, str], ...]) -> None:
            columns = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in definitions:
                if name not in columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

        add_columns("policy_sources", (
            ("publisher", "VARCHAR(160)"),
            ("source_url", "TEXT"),
            ("source_scope", "VARCHAR(48) NOT NULL DEFAULT 'SELF_AUTHORED_SIMULATION'"),
            ("source_version_label", "VARCHAR(200)"),
            ("source_published_at", "DATETIME"),
            ("current_checksum", "VARCHAR(64)"),
            ("last_verified_at", "DATETIME"),
        ))
        add_columns("policy_versions", (("source_snapshot_id", "INTEGER"),))
        add_columns("tickets", (
            ("customer_id", "VARCHAR(48)"),
            ("order_id", "VARCHAR(48)"),
            ("request_text", "TEXT"),
            ("execution_mode", "VARCHAR(32) NOT NULL DEFAULT 'FIXTURE_SIMULATION'"),
        ))
        add_columns("action_proposals", (
            ("customer_message", "TEXT"),
            ("confidence", "FLOAT"),
            ("permission_decision", "VARCHAR(32)"),
            ("policy_citations_json", "TEXT"),
            ("agent_run_id", "VARCHAR(48)"),
        ))
        add_columns("tool_executions", (
            ("tool_version", "VARCHAR(32) NOT NULL DEFAULT 'v1'"),
            ("input_json", "TEXT"),
            ("output_json", "TEXT"),
            ("caller", "VARCHAR(48) NOT NULL DEFAULT 'system'"),
            ("started_at", "DATETIME"),
            ("completed_at", "DATETIME"),
            ("state_impact", "VARCHAR(64)"),
        ))
        add_columns("evidence_assets", (
            ("model_id", "VARCHAR(120)"),
            ("prompt_version", "VARCHAR(80)"),
            ("vision_run_id", "VARCHAR(48)"),
            ("model_needs_human_review", "BOOLEAN"),
            ("review_gate_reasons_json", "TEXT NOT NULL DEFAULT '[]'"),
        ))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
