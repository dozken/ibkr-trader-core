import logging
import os
import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)
_slow_logger = logging.getLogger("ops.sql.slow")
_SLOW_QUERY_MS = float(os.getenv("LOG_SQL_SLOW_MS", "500"))

def get_database_url() -> str:
    """
    Returns the database URL. If not explicitly set via DATABASE_URL,
    it automatically switches filenames based on the IBKR_PORT to prevent
    mixing live and paper trading data.
    """
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        if env_url.startswith("postgres://"):
            return env_url.replace("postgres://", "postgresql://", 1)
        return env_url

    # Default logic: detect live vs paper via port
    # TWS Live: 7496, Gateway Live: 4001
    live_ports = {"7496", "4001"}
    port = os.environ.get("IBKR_PORT", "7497")
    
    # Path is relative to the root of the app in Docker or Local
    data_dir = "./ibkr_core/data"
    if port in live_ports:
        return f"sqlite:///{data_dir}/trading_live.db"
    return f"sqlite:///{data_dir}/trading_paper.db"


DATABASE_URL = get_database_url()

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)

if DATABASE_URL.startswith("sqlite"):
    from sqlalchemy import event as _sa_event
    @_sa_event.listens_for(engine, "connect")
    def _set_wal(conn, _):
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "before_cursor_execute")
def _sql_before(conn, cursor, statement, parameters, context, executemany):
    context._query_start_ts = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _sql_after(conn, cursor, statement, parameters, context, executemany):
    start = getattr(context, "_query_start_ts", None)
    if start is None:
        return
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if elapsed_ms >= _SLOW_QUERY_MS:
        _slow_logger.warning(
            "slow query %.1fms: %s",
            elapsed_ms,
            statement.replace("\n", " ")[:500],
            extra={"elapsed_ms": elapsed_ms},
        )


def init_db():
    """Run pending Alembic migrations. Safe to call on every startup.

    Locates alembic.ini from candidate paths (CWD first — the deploy entrypoint
    runs from the project root where alembic.ini lives — then relative to this
    package for source checkouts). When core is installed as a wheel there is no
    alembic.ini next to the package, so a missing file is expected and skipped:
    the container entrypoint owns migrations in that case.
    """
    try:
        from alembic.config import Config
        from alembic import command

        candidates = [
            os.path.join(os.getcwd(), "alembic.ini"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "alembic.ini")),
        ]
        ini = next((p for p in candidates if os.path.isfile(p)), None)
        if ini is None:
            logger.info("No alembic.ini found (wheel install) — skipping in-process migrate; "
                        "entrypoint handles migrations.")
            return

        alembic_cfg = Config(ini)
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully (%s).", ini)
    except Exception as e:
        logger.error(f"Alembic migration failed: {e}")
        # Don't crash the app — run with existing schema (entrypoint already migrated).


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
