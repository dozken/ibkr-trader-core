import logging
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ibkr_core.core.models import Base

config = context.config

# Only let alembic reconfigure logging when running standalone (CLI).
# When invoked programmatically at app boot (init_db -> command.upgrade),
# the app has already called setup_logging() and installed its stdout +
# RotatingFileHandler. alembic's fileConfig() defaults to
# disable_existing_loggers=True and replaces the root handlers with its own
# stderr-only console handler — which silently kills all app logging for the
# rest of the process lifetime. Skip it if handlers are already present.
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url: return url
    
    from ibkr_core.core.database import get_database_url
    return get_database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
