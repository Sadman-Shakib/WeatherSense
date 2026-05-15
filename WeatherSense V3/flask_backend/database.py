"""SQLite database setup and helpers for WeatherSense."""
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "weather.db"


def _label_row(r):
    """Label row as Sunny/Cloudy/Rainy for balanced selection."""
    rain = bool(r.get("rain", 0))
    p = r.get("pressure")
    h = r.get("humidity")
    if rain:
        return "Rainy"
    if p is not None and p < 1008:
        return "Cloudy"
    if h is not None and h > 75:
        return "Cloudy"
    return "Sunny"


def init_db():
    """Create weather.db and tables if not exists."""
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL,
                humidity REAL,
                pressure REAL,
                rain INTEGER NOT NULL
            )
        """)
        # Stores rows from uploaded CSVs for retrain (includes weather column)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS csv_training_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                temperature REAL NOT NULL,
                humidity REAL NOT NULL,
                pressure REAL NOT NULL,
                rain INTEGER NOT NULL,
                weather TEXT NOT NULL
            )
        """)
        conn.commit()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_sensor_row(conn, timestamp, temperature, humidity, pressure, rain):
    conn.execute(
        "INSERT INTO sensor_data (timestamp, temperature, humidity, pressure, rain) VALUES (?, ?, ?, ?, ?)",
        (timestamp, temperature, humidity, pressure, 1 if rain else 0)
    )
    conn.commit()


def get_latest(conn, limit=1):
    cur = conn.execute(
        "SELECT * FROM sensor_data ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    return [dict(row) for row in cur.fetchall()]


def get_all_data(conn):
    cur = conn.execute(
        "SELECT id, timestamp, temperature, humidity, pressure, rain FROM sensor_data ORDER BY id"
    )
    return [dict(row) for row in cur.fetchall()]


def get_balanced_data(conn, last_days=None, last_rows=None, random_seed=42):
    """
    Balanced dataset for training:
    - Include ALL rainy samples (rare events)
    - Equal number of Sunny and Cloudy
    - last_days=N: only rows from last N days
    - last_rows=M: only last M rows (before balancing)
    """
    cur = conn.execute(
        "SELECT id, timestamp, temperature, humidity, pressure, rain FROM sensor_data ORDER BY id"
    )
    rows = [dict(row) for row in cur.fetchall()]
    if not rows:
        return []

    for r in rows:
        r["_label"] = _label_row(r)

    if last_days is not None and last_days > 0:
        cutoff = datetime.utcnow() - timedelta(days=last_days)
        kept = []
        for r in rows:
            try:
                s = (r.get("timestamp") or "").replace("Z", "").split(".")[0].strip()
                if not s:
                    kept.append(r)
                    continue
                dt = datetime.fromisoformat(s)
                if getattr(dt, "tzinfo", None):
                    dt = dt.replace(tzinfo=None)
                if dt >= cutoff:
                    kept.append(r)
            except Exception:
                kept.append(r)
        rows = kept

    if last_rows is not None and last_rows > 0 and len(rows) > last_rows:
        rows = rows[-last_rows:]

    rainy = [r for r in rows if r["_label"] == "Rainy"]
    sunny = [r for r in rows if r["_label"] == "Sunny"]
    cloudy = [r for r in rows if r["_label"] == "Cloudy"]

    n_keep = min(len(sunny), len(cloudy)) if (sunny and cloudy) else max(len(sunny), len(cloudy))
    rng = random.Random(random_seed)
    if n_keep > 0:
        if len(sunny) >= n_keep:
            sunny = rng.sample(sunny, n_keep)
        if len(cloudy) >= n_keep:
            cloudy = rng.sample(cloudy, n_keep)

    result = rainy + sunny + cloudy
    rng.shuffle(result)
    for r in result:
        r.pop("_label", None)
    return result


def get_recent_for_forecast(conn, hours_back=24, min_rows=10):
    cur = conn.execute(
        """
        SELECT temperature, humidity, pressure
        FROM sensor_data
        WHERE temperature IS NOT NULL AND humidity IS NOT NULL AND pressure IS NOT NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(min_rows, hours_back * 12),)  # ~5 min intervals
    )
    return [dict(row) for row in cur.fetchall()]


def get_last_n_rows(conn, n=50):
    """Last N rows for dataset preview, newest first."""
    cur = conn.execute(
        "SELECT id, timestamp, temperature, humidity, pressure, rain FROM sensor_data ORDER BY id DESC LIMIT ?",
        (n,)
    )
    rows = [dict(row) for row in cur.fetchall()]
    rows.reverse()  # chronological order for display
    return rows


def delete_sensor_data(conn):
    """Delete all ESP32-collected sensor rows and return deleted count."""
    cur = conn.execute("SELECT COUNT(*) AS total FROM sensor_data")
    total = cur.fetchone()["total"]
    conn.execute("DELETE FROM sensor_data")
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'sensor_data'")
    conn.commit()
    return total


def insert_csv_training_rows(conn, rows):
    """Insert validated CSV rows into csv_training_data for retrain."""
    for r in rows:
        conn.execute(
            """INSERT INTO csv_training_data (timestamp, temperature, humidity, pressure, rain, weather)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                r.get("timestamp", ""),
                float(r["temperature"]),
                float(r["humidity"]),
                float(r["pressure"]),
                1 if r.get("rain") else 0,
                r.get("weather", "Sunny"),
            ),
        )
    conn.commit()


def get_all_training_data(conn):
    """
    Union sensor_data + csv_training_data for retrain.
    Returns list of dicts: temperature, humidity, pressure, rain, weather.
    For sensor_data, weather is derived from _label_row.
    """
    sensor_rows = get_all_data(conn)
    for r in sensor_rows:
        r["weather"] = _label_row(r)

    cur = conn.execute(
        """SELECT timestamp, temperature, humidity, pressure, rain, weather
           FROM csv_training_data ORDER BY id"""
    )
    csv_rows = [dict(row) for row in cur.fetchall()]
    for r in csv_rows:
        r["rain"] = bool(r["rain"])

    result = []
    for r in sensor_rows:
        if r.get("temperature") is not None and r.get("humidity") is not None and r.get("pressure") is not None:
            result.append({
                "timestamp": r["timestamp"],
                "temperature": r["temperature"],
                "humidity": r["humidity"],
                "pressure": r["pressure"],
                "rain": r["rain"],
                "weather": r["weather"],
            })
    for r in csv_rows:
        result.append({
            "timestamp": r["timestamp"],
            "temperature": r["temperature"],
            "humidity": r["humidity"],
            "pressure": r["pressure"],
            "rain": r["rain"],
            "weather": r.get("weather", "Sunny"),
        })
    return result


def get_chart_data_24h(conn, min_rows=10):
    """Last 24h of data for Chart.js: labels (timestamps), temp, humidity, pressure arrays."""
    cur = conn.execute(
        """
        SELECT timestamp, temperature, humidity, pressure
        FROM sensor_data
        WHERE temperature IS NOT NULL AND humidity IS NOT NULL AND pressure IS NOT NULL
        ORDER BY id DESC
        LIMIT 300
        """
    )
    rows = [dict(row) for row in cur.fetchall()]
    if len(rows) < min_rows:
        return {"labels": [], "temperature": [], "humidity": [], "pressure": []}
    rows.reverse()  # chronological
    return {
        "labels": [r["timestamp"][:16].replace("T", " ") for r in rows],
        "temperature": [r["temperature"] for r in rows],
        "humidity": [r["humidity"] for r in rows],
        "pressure": [r["pressure"] for r in rows],
    }
