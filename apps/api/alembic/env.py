import os
from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import get_settings
from app.models import Base

url = os.environ.get("MIGRATION_DATABASE_URL") or get_settings().database_url
if url.startswith(("postgresql://", "postgres://")):
    url = "postgresql+psycopg://" + url.split("://", 1)[1]


def run():
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


run()
