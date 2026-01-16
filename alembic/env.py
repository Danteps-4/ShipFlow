from logging.config import fileConfig

from sqlalchemy import engine_from_config, text
from sqlalchemy import pool

# ... (omitted)

def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    # Pass PGOPTIONS to the engine connection if present, BUT only for Postgres
    connect_args = {}
    url = get_url()
    if url.startswith("postgresql"):
        pg_options = os.getenv("PGOPTIONS")
        if pg_options:
            connect_args["options"] = pg_options

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args, # Ensure engine uses the search_path
    )
    
    schema = get_schema_from_env()

    with connectable.connect() as connection:
        # Auto-create schema if needed (Postgres only)
        if schema and connection.dialect.name == "postgresql":
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.commit()

        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            version_table_schema=schema, # Ensure alembic_version table goes to 'auth' if schema is 'auth'
            include_schemas=True if schema else False
        )

        with context.begin_transaction():
            context.run_migrations()

from alembic import context
from sqlmodel import SQLModel
from app.models import * # Import all models to register them

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.

import os
from dotenv import load_dotenv
load_dotenv()

def get_url():
    url = os.getenv("DATABASE_URL")
    if not url:
        return "sqlite:///./local_dev.db" # Fallback
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url

def get_schema_from_env():
    """
    Extracts schema from PGOPTIONS if set (e.g. '-c search_path=auth').
    Returns None if not found or if PGOPTIONS is missing.
    """
    pg_options = os.getenv("PGOPTIONS")
    if pg_options and "search_path=" in pg_options:
        # Example: "-c search_path=auth" -> "auth"
        try:
            # Split by 'search_path=' and take the second part, then split by space/end
            # This is a basic parser, assumes standard format
            parts = pg_options.split("search_path=")
            if len(parts) > 1:
                schema = parts[1].strip().split(" ")[0]
                return schema
        except Exception:
            pass
    return None

def run_migrations_offline():
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    schema = get_schema_from_env()
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=schema, # Set explicit schema for alembic_version (None = default)
        include_schemas=True if schema else False # If specific schema is targeted, you might want this
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    # Pass PGOPTIONS to the engine connection if present, BUT only for Postgres
    connect_args = {}
    url = get_url()
    if url.startswith("postgresql"):
        pg_options = os.getenv("PGOPTIONS")
        if pg_options:
            connect_args["options"] = pg_options

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args, # Ensure engine uses the search_path
    )
    
    schema = get_schema_from_env()

    with connectable.connect() as connection:
        # Auto-create schema if needed (Postgres only)
        if schema and connection.dialect.name == "postgresql":
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.commit()

        context.configure(
            connection=connection, 
            target_metadata=target_metadata,
            version_table_schema=schema, # Ensure alembic_version table goes to 'auth' if schema is 'auth'
            include_schemas=True if schema else False
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
