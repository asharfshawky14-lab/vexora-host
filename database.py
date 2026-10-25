
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager

BASE_DIR = Path(__file__).resolve().parent

DATABASE_PATH = Path(
    os.environ.get(
        "DATABASE_PATH",
        str(BASE_DIR / "instance" / "vexora.sqlite3"),
    )
)


def ensure_database_directory():
    DATABASE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


@contextmanager
def get_db():
    ensure_database_directory()

    connection = sqlite3.connect(
        str(DATABASE_PATH),
        timeout=10,
    )
    connection.row_factory = sqlite3.Row

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with get_db() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                runtime TEXT NOT NULL DEFAULT 'python',
                status TEXT NOT NULL DEFAULT 'stopped',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


if __name__ == "__main__":
    init_db()
    print("VEXORA HOST database initialized successfully.")
    print(f"Database location: {DATABASE_PATH}")
