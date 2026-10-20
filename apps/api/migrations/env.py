"""Single migration environment. DATABASE_URL is never stored in alembic.ini."""

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.db.metadata import Base
from app.core.db.session import load_database_url

url = load_database_url()
if url is None:
    raise RuntimeError("DATABASE_URL is required for migrations")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
