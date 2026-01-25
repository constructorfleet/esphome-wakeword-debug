import sqlite3
from pathlib import Path
from typing import Iterable, Optional


LABEL_UNKNOWN = "Unknown"
LABEL_POSITIVE = "Positive"
LABEL_FALSE_POSITIVE = "False Positive"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL UNIQUE,
                timestamp TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT 'Unknown',
                assistant_id TEXT,
                duration REAL,
                sample_rate INTEGER
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_clips_timestamp ON clips(timestamp)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_label ON clips(label)")


def insert_clip(
    db_path: Path,
    filename: str,
    timestamp: str,
    assistant_id: Optional[str],
    duration: Optional[float],
    sample_rate: Optional[int],
    label: str = LABEL_UNKNOWN,
) -> int:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO clips (filename, timestamp, label, assistant_id, duration, sample_rate)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (filename, timestamp, label, assistant_id, duration, sample_rate),
        )
        row = conn.execute(
            "SELECT id FROM clips WHERE filename = ?",
            (filename,),
        ).fetchone()
        return int(row["id"])


def list_clips(
    db_path: Path,
    start: Optional[str] = None,
    end: Optional[str] = None,
    label: Optional[str] = None,
) -> Iterable[sqlite3.Row]:
    clauses = []
    params = []
    if start:
        clauses.append("timestamp >= ?")
        params.append(start)
    if end:
        clauses.append("timestamp <= ?")
        params.append(end)
    if label:
        clauses.append("label = ?")
        params.append(label)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"SELECT * FROM clips {where} ORDER BY timestamp DESC"

    with _connect(db_path) as conn:
        return conn.execute(query, params).fetchall()


def get_clip(db_path: Path, clip_id: int) -> Optional[sqlite3.Row]:
    with _connect(db_path) as conn:
        return conn.execute(
            "SELECT * FROM clips WHERE id = ?",
            (clip_id,),
        ).fetchone()


def update_label(db_path: Path, clip_id: int, label: str) -> bool:
    with _connect(db_path) as conn:
        result = conn.execute(
            "UPDATE clips SET label = ? WHERE id = ?",
            (label, clip_id),
        )
        return result.rowcount > 0
