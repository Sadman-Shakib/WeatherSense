"""ML integration: Sunny/Cloudy/Rainy classification + 3-hour forecast regression."""
import json
import random
import shutil
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)
BACKUP_DIR = MODELS_DIR / "backups"
BACKUP_DIR.mkdir(exist_ok=True)

CLASSIFIER_PATH = MODELS_DIR / "classifier.joblib"
FORECAST_PATH = MODELS_DIR / "forecast.joblib"
CLASS_NAMES_PATH = MODELS_DIR / "class_names.json"

# weather is optional; if missing, derived from rain/temp/humidity/pressure
REQUIRED_CSV_COLUMNS = ["timestamp", "temperature", "humidity", "pressure", "rain"]
WEATHER_CLASSES = ["Sunny", "Cloudy", "Rainy"]


def backup_models():
    """Backup current models to models/backups/ before retraining."""
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    for name, p in [
        ("classifier", CLASSIFIER_PATH),
        ("forecast", FORECAST_PATH),
        ("class_names", CLASS_NAMES_PATH),
    ]:
        if p.exists():
            ext = ".json" if name == "class_names" else ".joblib"
            shutil.copy2(p, BACKUP_DIR / f"{name}_{stamp}{ext}")


def restore_models():
    """Restore most recent backup when training fails."""
    backups = sorted(BACKUP_DIR.glob("classifier_*.joblib"), reverse=True)
    if not backups:
        return False
    stamp = backups[0].stem.replace("classifier_", "")
    for name, path, ext in [
        ("classifier", CLASSIFIER_PATH, ".joblib"),
        ("forecast", FORECAST_PATH, ".joblib"),
        ("class_names", CLASS_NAMES_PATH, ".json"),
    ]:
        bp = BACKUP_DIR / f"{name}_{stamp}{ext}"
        if bp.exists():
            shutil.copy2(bp, path)
    return True


def validate_and_parse_csv(content):
    """
    Validate CSV and parse valid rows.
    Returns: {
        "valid": bool,
        "error": str | None,
        "missing_columns": list,
        "rows_used": int,
        "rows_skipped": int,
        "valid_rows": list of dicts
    }
    """
    import csv as csv_module
    from io import StringIO

    result = {
        "valid": False,
        "error": None,
        "missing_columns": [],
        "rows_used": 0,
        "rows_skipped": 0,
        "valid_rows": [],
    }
    try:
        reader = csv_module.DictReader(StringIO(content))
        if reader.fieldnames is None:
            result["error"] = "No data found"
            return result
        headers = [h.strip().lower() for h in reader.fieldnames] if reader.fieldnames else []
        missing = [c for c in REQUIRED_CSV_COLUMNS if c.lower() not in headers]
        if missing:
            result["missing_columns"] = missing
            result["error"] = f"Missing required columns: {', '.join(missing)}"
            return result
        valid = []
        skipped = 0
        for row in reader:
            try:
                t = float(row.get("temperature", row.get("Temperature", "")))
                h = float(row.get("humidity", row.get("Humidity", "")))
                p = float(row.get("pressure", row.get("Pressure", 1013)))
                rain_val = row.get("rain", row.get("Rain", "0"))
                rain = 1 if str(rain_val).lower() in ("1", "true", "yes") else 0
                weather = str(row.get("weather", row.get("Weather", ""))).strip()
                if not weather or weather not in WEATHER_CLASSES:
                    weather = _label_weather(t, h, p, rain)
                ts = row.get("timestamp", row.get("Timestamp", ""))
                valid.append({
                    "t": t, "h": h, "p": p, "rain": rain, "label": weather,
                    "timestamp": ts, "temperature": t, "humidity": h, "pressure": p, "weather": weather,
                })
            except (ValueError, TypeError, KeyError):
                skipped += 1
        if not valid:
            result["error"] = "No data found"
            result["rows_skipped"] = skipped
            return result
        result["valid"] = True
        result["rows_used"] = len(valid)
        result["rows_skipped"] = skipped
        result["valid_rows"] = valid
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def _rule_classify(temperature, humidity, pressure):
    """Rule-based fallback: Sunny / Cloudy / Rainy."""
    t = temperature or 20
    h = humidity or 50
    p = pressure or 1013
    if h > 85 or (p < 1005 and h > 70):
        return "Rainy"
    if p < 1008 or h > 75:
        return "Cloudy"
    return "Sunny"


def predict_weather(temperature, humidity, pressure):
    """
    Classification: Sunny / Cloudy / Rainy.
    Inputs: temperature (°C), humidity (%), pressure (hPa).
    Returns: str (e.g. 'Sunny', 'Cloudy', 'Rainy').
    """
    t = float(temperature) if temperature is not None else 0
    h = float(humidity) if humidity is not None else 0
    p = float(pressure) if pressure is not None else 1013

    try:
        import joblib
        clf = joblib.load(CLASSIFIER_PATH)
        X = np.array([[t, h, p]], dtype=np.float64)
        idx = int(clf.predict(X)[0])
        if CLASS_NAMES_PATH.exists():
            with open(CLASS_NAMES_PATH) as f:
                names = json.load(f)
            return str(names[idx])
        return WEATHER_CLASSES[idx] if 0 <= idx < 3 else "Sunny"
    except Exception:
        pass
    return _rule_classify(t, h, p)


def predict_forecast(latest_records):
    """
    Regression: 3-hour forecast for temperature, humidity, pressure.
    Input: list of dicts with keys temperature, humidity, pressure.
    Returns: list of 3 dicts, e.g. [{"hour":1,"temperature":...,"humidity":...,"pressure":...}, ...].
    """
    if not latest_records:
        return []

    rows = [
        r for r in latest_records
        if r.get("temperature") is not None and r.get("humidity") is not None and r.get("pressure") is not None
    ]
    if not rows:
        return []

    try:
        import joblib
        model = joblib.load(FORECAST_PATH)
        latest = rows[0]
        X = np.array([[latest["temperature"], latest["humidity"], latest["pressure"]]], dtype=np.float64)
        pred = np.atleast_2d(model.predict(X))
        values = pred[0].tolist()
        if len(values) >= 9:
            forecast = [
                {"hour": 1, "temperature": round(float(values[0]), 1), "humidity": round(float(values[1]), 1), "pressure": round(float(values[2]), 1)},
                {"hour": 2, "temperature": round(float(values[3]), 1), "humidity": round(float(values[4]), 1), "pressure": round(float(values[5]), 1)},
                {"hour": 3, "temperature": round(float(values[6]), 1), "humidity": round(float(values[7]), 1), "pressure": round(float(values[8]), 1)},
            ]
            if _forecast_is_sane(forecast):
                return forecast
        if len(values) >= 3:
            t, h, p = values[0], values[1], values[2]
            forecast = [
                {"hour": 1, "temperature": round(float(t), 1), "humidity": round(float(h), 1), "pressure": round(float(p), 1)},
                {"hour": 2, "temperature": round(float(t), 1), "humidity": round(float(h), 1), "pressure": round(float(p), 1)},
                {"hour": 3, "temperature": round(float(t), 1), "humidity": round(float(h), 1), "pressure": round(float(p), 1)},
            ]
            if _forecast_is_sane(forecast):
                return forecast
    except Exception:
        pass

    return _trend_forecast(rows)


def _label_weather(t, h, p, rain):
    """Map sensor values to Sunny / Cloudy / Rainy."""
    if rain:
        return "Rainy"
    if p is not None and p < 1008:
        return "Cloudy"
    if h is not None and h > 75:
        return "Cloudy"
    return "Sunny"


def _trend_forecast(rows):
    """Simple fallback forecast using recent movement when no trained model exists."""
    chronological = list(reversed(rows[:24]))
    latest = chronological[-1]
    if len(chronological) >= 4:
        earlier = chronological[max(0, len(chronological) - 7)]
        span = max(1, len(chronological) - max(0, len(chronological) - 7) - 1)
    else:
        earlier = chronological[0]
        span = max(1, len(chronological) - 1)

    dt = (latest["temperature"] - earlier["temperature"]) / span
    dh = (latest["humidity"] - earlier["humidity"]) / span
    dp = (latest["pressure"] - earlier["pressure"]) / span

    forecast = []
    for hour in (1, 2, 3):
        factor = hour
        forecast.append({
            "hour": hour,
            "temperature": round(float(latest["temperature"] + dt * factor), 1),
            "humidity": round(float(np.clip(latest["humidity"] + dh * factor, 0, 100)), 1),
            "pressure": round(float(latest["pressure"] + dp * factor), 1),
        })
    return forecast


def _forecast_is_sane(forecast):
    for item in forecast:
        t = item.get("temperature")
        h = item.get("humidity")
        p = item.get("pressure")
        if not all(np.isfinite(v) for v in (t, h, p)):
            return False
        if not -20 <= t <= 60:
            return False
        if not 0 <= h <= 100:
            return False
        if not 930 <= p <= 1060:
            return False
    return True


def _parse_timestamp(value):
    if not value:
        return None
    try:
        s = str(value).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if getattr(dt, "tzinfo", None):
            dt = dt.replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _chronological_rows(rows):
    indexed = []
    for i, r in enumerate(rows):
        dt = _parse_timestamp(r.get("timestamp"))
        indexed.append((dt is None, dt or datetime.min, i, r))
    indexed.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in indexed]


def _forecast_training_pairs(rows):
    """Build current-to-future pairs for +1h, +2h, +3h forecast regression."""
    clean = [
        r for r in _chronological_rows(rows)
        if r.get("t") is not None and r.get("h") is not None and r.get("p") is not None
    ]
    if len(clean) < 8:
        return None, None, []

    timestamps = [_parse_timestamp(r.get("timestamp")) for r in clean]
    deltas = [
        (timestamps[i] - timestamps[i - 1]).total_seconds()
        for i in range(1, len(timestamps))
        if timestamps[i] and timestamps[i - 1] and (timestamps[i] - timestamps[i - 1]).total_seconds() > 0
    ]
    if deltas:
        median_seconds = float(np.median(deltas))
        steps_per_hour = max(1, int(round(3600 / median_seconds)))
    else:
        steps_per_hour = 1

    horizons = [steps_per_hour, steps_per_hour * 2, steps_per_hour * 3]
    if horizons[-1] >= len(clean):
        max_step = max(1, (len(clean) - 6) // 3)
        horizons = [max_step, max_step * 2, max_step * 3]
    if horizons[-1] >= len(clean):
        return None, None, []

    X_f = []
    y_f = []
    for i in range(0, len(clean) - horizons[-1]):
        X_f.append([clean[i]["t"], clean[i]["h"], clean[i]["p"]])
        target = []
        for step in horizons:
            target.extend([clean[i + step]["t"], clean[i + step]["h"], clean[i + step]["p"]])
        y_f.append(target)

    if len(X_f) < 5:
        return None, None, []
    return np.array(X_f, dtype=np.float64), np.array(y_f, dtype=np.float64), horizons


def _select_balanced(rows, random_seed=42):
    """
    Balanced dataset for training:
    - Include ALL rainy samples (rare events)
    - Equal number of Sunny and Cloudy (undersample majority)
    """
    rng = random.Random(random_seed)
    rainy = [r for r in rows if r["label"] == "Rainy"]
    sunny = [r for r in rows if r["label"] == "Sunny"]
    cloudy = [r for r in rows if r["label"] == "Cloudy"]

    n_sunny = len(sunny)
    n_cloudy = len(cloudy)
    n_keep = min(n_sunny, n_cloudy) if (n_sunny and n_cloudy) else max(n_sunny, n_cloudy)

    if n_keep > 0:
        if n_sunny >= n_keep:
            sunny = rng.sample(sunny, n_keep)
        if n_cloudy >= n_keep:
            cloudy = rng.sample(cloudy, n_keep)

    result = rainy + sunny + cloudy
    rng.shuffle(result)
    return result


def _do_train(rows, balanced, random_seed=42):
    """Core training logic. rows have t,h,p,label. Returns stats dict."""
    import joblib
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import LabelEncoder

    if len(rows) < 10:
        raise ValueError("Need at least 10 valid rows to train")
    forecast_rows = list(rows)
    if balanced:
        classifier_rows = _select_balanced(rows, random_seed=random_seed)
    else:
        classifier_rows = list(rows)
    if len(classifier_rows) < 5:
        raise ValueError("Too few rows after balancing")

    X = np.array([[r["t"], r["h"], r["p"]] for r in classifier_rows])
    labels = [r["label"] for r in classifier_rows]
    le = LabelEncoder()
    y_class = le.fit_transform(labels)

    clf = RandomForestClassifier(n_estimators=80, random_state=random_seed)
    clf.fit(X, y_class)
    joblib.dump(clf, CLASSIFIER_PATH)
    with open(CLASS_NAMES_PATH, "w") as f:
        json.dump(le.classes_.tolist(), f)

    X_f, y_f, horizons = _forecast_training_pairs(forecast_rows)
    forecast_trained = X_f is not None and y_f is not None
    if forecast_trained:
        reg = RandomForestRegressor(n_estimators=120, random_state=random_seed)
        reg.fit(X_f, y_f)
        joblib.dump(reg, FORECAST_PATH)

    dist = dict(Counter(y_class))
    class_dist = {str(le.classes_[i]): int(dist.get(i, 0)) for i in range(len(le.classes_))}
    return {
        "rows_used": len(classifier_rows),
        "forecast_rows_used": int(len(X_f)) if forecast_trained else 0,
        "forecast_horizon_steps": horizons,
        "class_distribution": class_dist,
        "classifier_trained": True,
        "forecast_trained": forecast_trained,
    }


def train_from_validated_rows(valid_rows, balanced=True, random_seed=42):
    """
    Train from validated CSV rows (have t, h, p, label).
    Returns stats dict. Call backup_models() before, restore_models() on exception.
    """
    return _do_train(valid_rows, balanced, random_seed)


def train_from_combined_rows(rows, balanced=True, random_seed=42):
    """
    Train from combined sensor_data + csv_training_data.
    rows have: temperature, humidity, pressure, rain, weather.
    Returns stats dict. Backup/restore handled by caller.
    """
    data = []
    for r in rows:
        try:
            t = float(r.get("temperature", 0))
            h = float(r.get("humidity", 0))
            p = float(r.get("pressure", 1013))
            rain = 1 if r.get("rain") else 0
            label = str(r.get("weather", "")).strip()
            if label not in WEATHER_CLASSES:
                label = _label_weather(t, h, p, rain)
            data.append({
                "t": t, "h": h, "p": p, "rain": rain, "label": label,
                "timestamp": r.get("timestamp", ""),
            })
        except (ValueError, TypeError, KeyError):
            continue
    if len(data) < 10:
        raise ValueError("Not enough data to train models")
    return _do_train(data, balanced, random_seed)


def train_from_csv(
    csv_path,
    last_days=None,
    last_rows=None,
    balanced=True,
    random_seed=42,
):
    """
    Train classifier and forecast from CSV file.
    CSV columns: timestamp,temperature,humidity,pressure,rain[,weather]
    Returns stats dict. Use validate_and_parse_csv for validation+feedback.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        content = f.read()
    v = validate_and_parse_csv(content)
    if not v["valid"]:
        raise ValueError(v["error"] or "Invalid CSV")
    rows = v["valid_rows"]

    # Filter by last N days
    if last_days is not None and last_days > 0:
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
    if last_rows is not None and last_rows > 0 and len(rows) > last_rows:
        rows = rows[-last_rows:]

    if len(rows) < 10:
        raise ValueError("Need at least 10 valid rows to train (after filters)")
    return _do_train(rows, balanced, random_seed)


def train_from_sqlite_rows(rows, balanced=True, random_seed=42):
    """Train from sensor_data rows. Converts to format for _do_train."""
    data = []
    for r in rows:
        try:
            t = float(r.get("temperature", 0))
            h = float(r.get("humidity", 0))
            p = float(r.get("pressure", 1013))
            rain = 1 if r.get("rain") else 0
            label = _label_weather(t, h, p, rain)
            data.append({
                "t": t, "h": h, "p": p, "rain": rain, "label": label,
                "timestamp": r.get("timestamp", ""),
            })
        except (ValueError, TypeError, KeyError):
            continue
    if len(data) < 10:
        raise ValueError("Need at least 10 valid rows from SQLite")
    return _do_train(data, balanced, random_seed)
