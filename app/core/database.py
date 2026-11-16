from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.core import config

_db_url = config.DATABASE_URL
for _prefix in ("postgres://", "postgresql://", "postgresql+psycopg://"):
    if _db_url.startswith(_prefix):
        _db_url = "postgresql+psycopg2://" + _db_url[len(_prefix):]
        break

_connect_args = {"check_same_thread": False} if "sqlite" in _db_url else {}
engine = create_engine(_db_url, connect_args=_connect_args, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@contextmanager
def session_scope():
    """Satu sesi DB per blok `with`; rollback otomatis jika error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Buat tabel + isi data awal (COA, kas, user, kolam) bila masih kosong."""
    import app.models  # noqa: F401  (daftarkan semua model)
    from app.core.seeder import seed_database
    Base.metadata.create_all(bind=engine)
    with session_scope() as db:
        seed_database(db)
