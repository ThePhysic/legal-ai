from alembic import context
from sqlalchemy import create_engine, pool

from api.config import Settings
from api.models import Base

target_metadata = Base.metadata
settings = Settings()
settings.runtime_dir.mkdir(parents=True, exist_ok=True)
url = settings.database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=url.startswith("sqlite"))
        with context.begin_transaction():
            context.run_migrations()
