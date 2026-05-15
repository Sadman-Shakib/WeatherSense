"""
WeatherSense Flask API – Weather Prediction System
SQLite DB, sensor ingestion, latest + forecast, ML training, dataset download

Run locally: cd flask_backend && pip install -r requirements.txt && python app.py
Then open http://localhost:5000
"""
#For Debuging start
import threading
import serial
import json
#For Debuging end

import io
import logging
import csv
from datetime import datetime, timedelta
from pathlib import Path

import time
from flask import Flask, request, jsonify, send_file, render_template, Response

from database import (
    init_db,
    get_connection,
    insert_sensor_row,
    insert_csv_training_rows,
    get_latest,
    get_all_data,
    get_balanced_data,
    get_all_training_data,
    get_recent_for_forecast,
    get_last_n_rows,
    get_chart_data_24h,
    delete_sensor_data,
)
from ml_utils import (
    predict_weather,
    predict_forecast,
    train_from_csv,
    train_from_sqlite_rows,
    train_from_validated_rows,
    train_from_combined_rows,
    validate_and_parse_csv,
    backup_models,
    restore_models,
)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


def error_response(message, status=400):
    return jsonify({"error": message}), status


def _filter_rows(rows, last_days=None, last_rows=None):
    """Filter rows by last_days or last_rows."""
    if last_days and last_days > 0:
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
    if last_rows and last_rows > 0 and len(rows) > last_rows:
        rows = rows[-last_rows:]
    return rows


@app.route("/api/sensor", methods=["POST"])
def receive_sensor():
    """Receive JSON from ESP32 and store in sensor_data."""
    try:
        data = request.get_json(force=True, silent=False)
    except Exception:
        return error_response("Invalid JSON body", 400)

    if not data:
        return error_response("Empty or invalid JSON", 400)

    timestamp = data.get("timestamp")
    temperature = data.get("temperature")
    humidity = data.get("humidity")
    pressure = data.get("pressure")
    rain = data.get("rain")

    if timestamp is None:
        return error_response("Missing required field: timestamp", 400)

    try:
        temperature = float(temperature) if temperature is not None else None
    except (TypeError, ValueError):
        temperature = None
    try:
        humidity = float(humidity) if humidity is not None else None
    except (TypeError, ValueError):
        humidity = None
    try:
        pressure = float(pressure) if pressure is not None else None
    except (TypeError, ValueError):
        pressure = None
    rain = bool(rain) if rain is not None else False

    try:
        with get_connection() as conn:
            insert_sensor_row(conn, timestamp, temperature, humidity, pressure, rain)
    except Exception as e:
        return error_response(f"Database error: {str(e)}", 500)

    return jsonify({"status": "ok", "message": "Data saved"}), 200


@app.route("/api/latest", methods=["GET"])
def api_latest():
    """Return current (latest) readings plus weather classification."""
    try:
        with get_connection() as conn:
            rows = get_latest(conn, limit=1)
    except Exception as e:
        return error_response(f"Database error: {str(e)}", 500)

    if not rows:
        return jsonify({
            "readings": None,
            "classification": None,
            "message": "No sensor data yet",
        }), 200

    r = rows[0]
    temp = r.get("temperature")
    hum = r.get("humidity")
    pres = r.get("pressure")
    rain = bool(r.get("rain", 0))

    classification = predict_weather(temp, hum, pres)

    return jsonify({
        "readings": {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "temperature": temp,
            "humidity": hum,
            "pressure": pres,
            "rain": rain,
        },
        "classification": classification,
    }), 200


@app.route("/api/forecast", methods=["GET"])
def api_forecast():
    """Return 3-hour forecast for temperature, humidity, pressure."""
    try:
        with get_connection() as conn:
            recent = get_recent_for_forecast(conn)
    except Exception as e:
        return error_response(f"Database error: {str(e)}", 500)

    if not recent:
        return jsonify({
            "forecast": [],
            "message": "Insufficient data for forecast",
        }), 200

    predictions = predict_forecast(recent)
    return jsonify({"forecast": predictions}), 200


@app.route("/api/train", methods=["POST"])
def api_train():
    """
    Upload CSV to train ML models. Expects 'file' in form-data.
    CSV columns: timestamp,temperature,humidity,pressure,rain[,weather]
    Returns: rows_used, rows_skipped, missing_columns, stats.
    Stores valid rows in csv_training_data for retrain. Backs up models before training.
    """
    if "file" not in request.files:
        return error_response("No file in request. Use form field 'file'.", 400)
    f = request.files["file"]
    if not f or f.filename == "":
        return error_response("No file selected", 400)
    fn = (f.filename or "").lower()
    if not fn.endswith(".csv"):
        return error_response("Invalid file type. Only CSV files are accepted.", 400)
    try:
        content = f.read().decode("utf-8")
    except UnicodeDecodeError:
        return error_response("File must be UTF-8 encoded", 400)

    # Validate CSV
    v = validate_and_parse_csv(content)
    if not v["valid"]:
        err = v["error"] or "Invalid CSV"
        payload = {"error": err, "rows_used": 0, "rows_skipped": v.get("rows_skipped", 0)}
        if v.get("missing_columns"):
            payload["missing_columns"] = v["missing_columns"]
        return jsonify(payload), 400

    rows = v["valid_rows"]
    last_days = request.args.get("last_days", type=int)
    last_rows = request.args.get("last_rows", type=int)
    balanced = request.args.get("balanced", "1").lower() in ("1", "true", "yes")

    # Filter by last_days / last_rows (optional)
    if last_days and last_days > 0:
        cutoff = datetime.utcnow() - timedelta(days=last_days)
        kept = []
        for r in rows:
            try:
                s = (r.get("timestamp", "") or "").replace("Z", "").split(".")[0].strip()
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
    if last_rows and last_rows > 0 and len(rows) > last_rows:
        rows = rows[-last_rows:]

    if len(rows) < 10:
        return error_response("Need at least 10 valid rows to train (after filters)", 400)

    # Backup and train; restore on failure
    backup_models()
    try:
        stats = train_from_validated_rows(rows, balanced=balanced)
        # Store in csv_training_data for retrain
        with get_connection() as conn:
            insert_csv_training_rows(conn, rows)
    except Exception as e:
        logger.exception("CSV training failed")
        restore_models()
        return error_response(f"Training failed: {str(e)}. Previous models restored.", 500)

    return jsonify({
        "status": "ok",
        "message": "Models retrained and saved to models/",
        "rows_used": stats["rows_used"],
        "rows_skipped": v.get("rows_skipped", 0),
        "missing_columns": [],
        "stats": stats,
    }), 200


@app.route("/api/download_dataset", methods=["GET"])
def api_download_dataset():
    """Download full or balanced dataset. ?balanced=1&last_days=N&last_rows=M"""
    balanced = request.args.get("balanced", "").lower() in ("1", "true", "yes")
    last_days = request.args.get("last_days", type=int)
    last_rows = request.args.get("last_rows", type=int)

    try:
        with get_connection() as conn:
            if balanced:
                rows = get_balanced_data(conn, last_days=last_days, last_rows=last_rows)
            else:
                rows = get_all_data(conn)
                if last_days or last_rows:
                    rows = _filter_rows(rows, last_days, last_rows)
    except Exception as e:
        return error_response(f"Database error: {str(e)}", 500)

    if not rows:
        return jsonify({"message": "No data to download", "rows": 0}), 200

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "timestamp", "temperature", "humidity", "pressure", "rain"])
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "id": r["id"],
            "timestamp": r["timestamp"],
            "temperature": r["temperature"],
            "humidity": r["humidity"],
            "pressure": r["pressure"],
            "rain": 1 if r["rain"] else 0,
        })

    buf.seek(0)
    filename = "weather_balanced.csv" if balanced else "weather_full.csv"
    return send_file(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


# --- SSE Stream ---

@app.route("/api/stream")
def api_stream():
    """Server-Sent Events endpoint to notify frontend of new sensor data."""
    def event_stream():
        last_id = -1
        while True:
            try:
                with get_connection() as conn:
                    latest = get_latest(conn, limit=1)
                
                if latest:
                    current_id = latest[0]["id"]
                    if last_id == -1:
                        last_id = current_id
                    elif current_id > last_id:
                        last_id = current_id
                        yield "data: update\n\n"
            except Exception as e:
                logger.error(f"Stream error: {e}")
                
            time.sleep(1)

    return Response(event_stream(), mimetype="text/event-stream")


# --- Page routes ---

@app.route("/")
def index():
    return render_template("dashboard.html")


@app.route("/dashboard")
def page_dashboard():
    return render_template("dashboard.html")


@app.route("/dataset")
def page_dataset():
    return render_template("dataset.html")


@app.route("/training")
def page_training():
    return render_template("training.html")


# --- API for dashboard/dataset ---

@app.route("/api/chart/24h")
def api_chart_24h():
    """Last 24h data for Chart.js."""
    try:
        with get_connection() as conn:
            data = get_chart_data_24h(conn)
        return jsonify(data), 200
    except Exception as e:
        return error_response(str(e), 500)


@app.route("/api/dataset_preview")
def api_dataset_preview():
    """Last 50 rows for dataset preview."""
    n = request.args.get("n", 50, type=int)
    n = min(max(1, n), 100)
    try:
        with get_connection() as conn:
            rows = get_last_n_rows(conn, n=n)
        return jsonify({"rows": rows}), 200
    except Exception as e:
        return error_response(str(e), 500)


@app.route("/api/sensor_logs", methods=["DELETE"])
def api_delete_sensor_logs():
    """Delete all ESP32-collected sensor rows."""
    try:
        with get_connection() as conn:
            deleted = delete_sensor_data(conn)
        return jsonify({
            "status": "ok",
            "message": "Sensor logs deleted",
            "deleted": deleted,
        }), 200
    except Exception as e:
        return error_response(f"Database error: {str(e)}", 500)


@app.route("/api/retrain", methods=["POST"])
def api_retrain():
    """
    Retrain models using ALL sensor_data + csv_training_data.
    Optional: balanced=1 (default) or full dataset.
    Backs up models before training; restores on failure.
    """
    balanced = request.args.get("balanced", "1").lower() in ("1", "true", "yes")
    try:
        with get_connection() as conn:
            rows = get_all_training_data(conn)
        if len(rows) < 10:
            return error_response("Not enough data to train models. Need at least 10 rows from sensor data and/or uploaded CSVs.", 400)
        backup_models()
        stats = train_from_combined_rows(rows, balanced=balanced)
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception("Retrain failed")
        restore_models()
        return error_response(f"Training failed: {str(e)}. Previous models restored.", 500)

    return jsonify({
        "status": "ok",
        "message": "Models retrained and saved to models/",
        "stats": stats,
    }), 200


@app.route("/api/train_sqlite", methods=["POST"])
def api_train_sqlite():
    """Train from collected sensor logs in SQLite. No CSV upload."""
    balanced = request.args.get("balanced", "1").lower() in ("1", "true", "yes")
    last_days = request.args.get("last_days", type=int)
    last_rows = request.args.get("last_rows", type=int)
    try:
        with get_connection() as conn:
            if balanced:
                rows = get_balanced_data(conn, last_days=last_days, last_rows=last_rows)
            else:
                rows = get_all_data(conn)
                if last_days or last_rows:
                    rows = _filter_rows(rows, last_days, last_rows)
        if len(rows) < 10:
            return error_response("Need at least 10 rows in database", 400)
        backup_models()
        stats = train_from_sqlite_rows(rows, balanced=balanced)
        return jsonify({
            "status": "ok",
            "message": "Models trained from Sensor Logs and saved to models/",
            "stats": stats,
        }), 200
    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.exception("SQLite training failed")
        restore_models()
        return error_response(f"Training failed: {str(e)}. Previous models restored.", 500)



#For Debuging start
def serial_reader():
    PORT = "COM5"   # CHANGE THIS
    BAUD = 115200

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        print("USB Serial Connected")
    except Exception as e:
        print("Serial connection failed:", e)
        return

    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()

            if not line:
                continue

            print("RAW:", line)

            data = json.loads(line)

            with get_connection() as conn:
                insert_sensor_row(
                    conn,
                    # data.get("timestamp"),
                    datetime.utcnow().isoformat(),
                    data.get("temperature"),
                    data.get("humidity"),
                    data.get("pressure"),
                    data.get("rain", False),
                )

        except Exception as e:
            print("Serial Error:", e)

#For Debuging end


if __name__ == "__main__":
    init_db()

    # For Debuging start
    t = threading.Thread(target=serial_reader, daemon=True)
    t.start()
    print("Flask + Serial system started")
    # For Debuging end

    app.run(host="0.0.0.0", port=5000, debug=True)
