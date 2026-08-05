import os
from urllib.parse import quote

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()


# Local SQLite file used when PostgreSQL is unresponsive. Lives next to the
# database package so it is stable regardless of the process working directory.
_SQLITE_PATH = os.path.join(os.path.dirname(__file__), "fallback.db")

# Schema mirrored from create_table.py so the SQLite fallback is drop-in
# compatible with the Postgres table (same columns, same dedupe query).
_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS financial_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company VARCHAR(100),
    year VARCHAR(10),
    revenue TEXT,
    net_income TEXT,
    operating_income TEXT,
    cash_flow TEXT,
    total_assets TEXT,
    total_liabilities TEXT,
    risk_factors TEXT,
    growth_drivers TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_engine(database: str | None = None):
    """
    Create PostgreSQL connection.

    Args:
        database: Database name. Defaults to POSTGRES_DATABASE from .env.
    """
    if database is None:
        database = os.getenv("POSTGRES_DATABASE")

    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")

    # URL-encode credentials to handle special characters (e.g., @ in password)
    encoded_user = quote(user, safe="")
    encoded_password = quote(password, safe="")

    connection_string = (
        f"postgresql+psycopg2://"
        f"{encoded_user}:{encoded_password}@{host}:{port}/{database}"
        "?sslmode=require"
    )

    return create_engine(connection_string)


def get_sqlite_engine():
    """
    Create the local SQLite fallback engine and ensure the financial_metrics
    table exists. Used when PostgreSQL is unreachable.
    """
    engine = create_engine(f"sqlite:///{_SQLITE_PATH}")
    with engine.begin() as connection:
        connection.execute(text(_SQLITE_SCHEMA))
    return engine


def get_resilient_engine(database: str | None = None):
    """
    Return a working SQLAlchemy engine using a Postgres-first fallback chain:

    1. Try PostgreSQL (primary). A short connection is opened to confirm the
       server is actually reachable, not just that the URL is well-formed.
    2. If Postgres is unconfigured or unresponsive, fall back to a local
       SQLite database (schema mirrored from create_table.py).

    All app read/write paths should call this instead of get_engine() directly
    so a Postgres outage degrades to SQLite instead of erroring.
    """
    if os.getenv("POSTGRES_HOST"):
        try:
            engine = get_engine(database)
            # Force a real connection so an unreachable host fails HERE (and we
            # fall back), rather than later at query time.
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return engine
        except Exception as exc:
            print(f"[fallback] PostgreSQL unresponsive ({type(exc).__name__}: {exc}); using SQLite fallback.")
    else:
        print("[fallback] PostgreSQL not configured; using SQLite fallback.")

    return get_sqlite_engine()


def create_database() -> None:
    """
    Create the target database if it does not exist.
    
    Uses psycopg2 directly with autocommit to bypass SQLAlchemy transaction wrapping.
    """
    target_db = os.getenv("POSTGRES_DATABASE")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT")
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    
    try:
        # Connect to default 'postgres' database using psycopg2 directly
        conn = psycopg2.connect(
            host=host,
            port=port,
            database="postgres",
            user=user,
            password=password,
            sslmode="require"
        )
        # Enable autocommit mode before executing CREATE DATABASE
        conn.autocommit = True
        
        cursor = conn.cursor()
        try:
            # Check if database exists
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (target_db,)
            )
            
            if not cursor.fetchone():
                print(f"Database '{target_db}' does not exist. Creating...")
                cursor.execute(f"CREATE DATABASE {target_db}")
                print(f"Database '{target_db}' created successfully.")
            else:
                print(f"Database '{target_db}' already exists.")
        finally:
            cursor.close()
            conn.close()
    except Exception as exc:
        print(f"Failed to create database: {exc}")
        raise
