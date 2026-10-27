"""
Database connection and session factory.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Cloud DB providers (Supabase, Neon, Railway) supply a single DATABASE_URL.
# Individual vars (DB_USER, DB_HOST, etc.) are used for local Docker Compose.
DATABASE_URL = os.environ.get('DATABASE_URL') or (
    f"postgresql+psycopg2://"
    f"{os.environ.get('DB_USER', 'evuser')}:"
    f"{os.environ.get('DB_PASSWORD', 'password')}@"
    f"{os.environ.get('DB_HOST', 'db')}:"
    f"{os.environ.get('DB_PORT', '5432')}/"
    f"{os.environ.get('DB_NAME', 'ev_infra')}"
)

# Supabase connection strings use postgres:// — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql+psycopg2://', 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
