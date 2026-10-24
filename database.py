
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    "instance/competitorpulse.db"
)


@contextmanager
def get_connection():
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(str(db_path), timeout=20)
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
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS competitors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL UNIQUE,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_scanned_at TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                published_at TEXT,
                keywords TEXT,
                search_volume INTEGER,
                first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_seen_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(competitor_id, url),
                FOREIGN KEY (competitor_id)
                    REFERENCES competitors(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_id INTEGER NOT NULL,
                page_url TEXT NOT NULL,
                product_name TEXT,
                price REAL NOT NULL,
                currency TEXT,
                checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (competitor_id)
                    REFERENCES competitors(id)
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS scan_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                competitor_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                new_articles INTEGER DEFAULT 0,
                scanned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (competitor_id)
                    REFERENCES competitors(id)
            )
        """)

    print("Database initialized successfully.")
