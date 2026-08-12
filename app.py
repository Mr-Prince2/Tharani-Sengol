from __future__ import annotations

import ssl
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except Exception:
    pass

import os
os.environ["HF_HUB_DISABLE_SSL_VERIFICATION"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

try:
    import requests
    requests.packages.urllib3.disable_warnings()
except Exception:
    pass

try:
    import httpx
    orig_client = httpx.Client.__init__
    httpx.Client.__init__ = lambda self, *args, **kwargs: orig_client(self, *args, **dict(kwargs, verify=False))
    
    orig_async = httpx.AsyncClient.__init__
    httpx.AsyncClient.__init__ = lambda self, *args, **kwargs: orig_async(self, *args, **dict(kwargs, verify=False))
except Exception:
    pass

import json
import importlib
import os
import random
import re
import sqlite3
import statistics
import time
from csv import writer
from datetime import datetime, timedelta, timezone
from functools import wraps
from io import StringIO
from math import atan2, cos, exp, radians, sin, sqrt
from pathlib import Path
from threading import Lock, Thread
from queue import Queue
from typing import Optional

from flask import Flask, Response, g, jsonify, make_response, redirect, render_template, request, url_for
from shapely.geometry import LineString, Point, Polygon

try:
    import jwt
except Exception:  # pragma: no cover
    jwt = None

try:
    from sklearn.cluster import KMeans
    from sklearn.ensemble import IsolationForest
except Exception:  # pragma: no cover
    KMeans = None
    IsolationForest = None

try:
    import joblib
except Exception:  # pragma: no cover - optional dependency fallback
    joblib = None

try:
    shap = importlib.import_module("shap")
except Exception:  # pragma: no cover
    shap = None

try:
    import pandas as pd
except Exception:
    pd = None

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "tharani_sengol.db"
WEIGHT_MODEL_PATH = BASE_DIR / "weight_model.pkl"
USERS_FILE = BASE_DIR / "user_accounts.json"
WEIGHT_LIMIT_TONS = 20.0
WEIGHT_LOCK_MIN_DISTANCE_KM = float(os.getenv("THARANI_WEIGHT_LOCK_MIN_DISTANCE_KM", "0.35"))
WEIGHT_LOCK_MIN_TRIP_MINUTES = float(os.getenv("THARANI_WEIGHT_LOCK_MIN_TRIP_MINUTES", "1.2"))
DEFAULT_ROUTE_COUNT = max(100, int(os.getenv("THARANI_ROUTE_COUNT", "120")))
DEFAULT_FLEET_SIZE = max(1000, int(os.getenv("THARANI_FLEET_SIZE", "1000")))
TN_BOUNDS = {
    "lat_min": 8.08,
    "lat_max": 13.56,
    "lon_min": 76.2,
    "lon_max": 80.35,
}
TAMIL_NADU_DISTRICTS = [
    ("Chennai", 13.0827, 80.2707),
    ("Coimbatore", 11.0168, 76.9558),
    ("Madurai", 9.9252, 78.1198),
    ("Tiruchirappalli", 10.7905, 78.7047),
    ("Salem", 11.6643, 78.1460),
    ("Tirunelveli", 8.7139, 77.7567),
    ("Erode", 11.3410, 77.7172),
    ("Vellore", 12.9165, 79.1325),
    ("Thoothukudi", 8.7642, 78.1348),
    ("Thanjavur", 10.7867, 79.1378),
    ("Dindigul", 10.3673, 77.9803),
    ("Villupuram", 11.9426, 79.4977),
    ("Kancheepuram", 12.8342, 79.7036),
    ("Namakkal", 11.2189, 78.1674),
    ("Karur", 10.9601, 78.0766),
    ("Cuddalore", 11.7480, 79.7714),
    ("Ramanathapuram", 9.3706, 78.8335),
    ("Sivaganga", 9.8470, 78.4800),
    ("Virudhunagar", 9.5680, 77.9624),
    ("Kanyakumari", 8.0883, 77.5385),
]
ANOMALY_MIN_BUFFER = 240
ANOMALY_REFIT_INTERVAL = 60
KMEANS_DEFAULT_CLUSTERS = 8
WEIGHT_FEATURE_ORDER = [
    "trip_time",
    "avg_speed",
    "max_speed",
    "stops_count",
    "acceleration_variation",
    "route_distance",
    "trip_number",
    "time_of_day",
]
DB_LOCK = Lock()
STATE_LOCK = Lock()
DB_QUEUE = Queue()


def db_writer_worker():
    while True:
        try:
            job = DB_QUEUE.get()
            if job is None:
                break
            
            jobs = [job]
            while not DB_QUEUE.empty():
                try:
                    jobs.append(DB_QUEUE.get_nowait())
                except Exception:
                    break
            
            with DB_LOCK:
                conn = get_db_connection()
                cursor = conn.cursor()
                try:
                    for j in jobs:
                        # 1. Insert gps_events
                        cursor.execute(
                            """
                            INSERT INTO gps_events(
                                event_time, vehicle_id, route_id, lat, lon, zone_type, zone_name,
                                risk, prediction_label, prediction_probability, predicted_weight, overload_flag
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                j["timestamp"],
                                j["vehicle_id"],
                                j["route_id"],
                                j["lat"],
                                j["lon"],
                                j["zone_type"],
                                j["zone_name"],
                                j["risk"],
                                j["prediction_label"],
                                j["prediction_probability"],
                                j["predicted_weight"],
                                j["overload_flag"],
                            )
                        )
                        gps_event_id = cursor.lastrowid
                        
                        # 2. Insert agent_traces
                        cursor.execute(
                            """
                            INSERT INTO agent_traces (vehicle_id, gps_event_id, timestamp, trace_json)
                            VALUES (?, ?, ?, ?)
                            """,
                            (j["vehicle_id"], gps_event_id, j["timestamp"], json.dumps(j["trace"]))
                        )
                        
                        # 3. Persist snapshot
                        s = j["state_copy"]
                        cursor.execute(
                            """
                            INSERT INTO vehicle_snapshots(
                                vehicle_id, updated_at, route_id, route_name, zone_type, zone_name,
                                trips_total, trips_24h, risk, risk_level, prediction_label,
                                prediction_probability, predicted_weight, average_weight, overload_flag,
                                weight_history_json, weight_prediction_json, profile, last_event
                            )
                            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(vehicle_id) DO UPDATE SET
                                updated_at=excluded.updated_at,
                                route_id=excluded.route_id,
                                route_name=excluded.route_name,
                                zone_type=excluded.zone_type,
                                zone_name=excluded.zone_name,
                                trips_total=excluded.trips_total,
                                trips_24h=excluded.trips_24h,
                                risk=excluded.risk,
                                risk_level=excluded.risk_level,
                                prediction_label=excluded.prediction_label,
                                prediction_probability=excluded.prediction_probability,
                                predicted_weight=excluded.predicted_weight,
                                average_weight=excluded.average_weight,
                                overload_flag=excluded.overload_flag,
                                weight_history_json=excluded.weight_history_json,
                                weight_prediction_json=excluded.weight_prediction_json,
                                profile=excluded.profile,
                                last_event=excluded.last_event
                            """,
                            (
                                j["vehicle_id"],
                                s.get("updated_at") or utc_now().isoformat(),
                                s.get("route_id"),
                                s.get("route_name"),
                                s.get("current_zone"),
                                s.get("current_zone_name"),
                                int(s.get("trips", 0)),
                                int(s.get("trips_24h", 0)),
                                float(s.get("risk", 0.0)),
                                classify_risk(float(s.get("risk", 0.0))),
                                s.get("prediction", {}).get("label", "LOW"),
                                float(s.get("prediction", {}).get("probability", 0.0)),
                                float(s.get("predicted_weight", 0.0) or 0.0),
                                float(s.get("average_weight", 0.0) or 0.0),
                                1 if s.get("overload_flag") else 0,
                                json.dumps(s.get("weight_history", [])[-20:]),
                                json.dumps(s.get("weight_prediction", {})),
                                s.get("profile", "normal"),
                                s.get("last_event", ""),
                            )
                        )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                finally:
                    conn.close()
            
            for _ in jobs:
                DB_QUEUE.task_done()
        except Exception:
            pass


Thread(target=db_writer_worker, daemon=True, name="tharani-db-writer").start()
GPS_QUEUE = Queue()


def gps_processor_worker():
    while True:
        try:
            data = GPS_QUEUE.get()
            if data is None:
                break
            process_gps(data)
            GPS_QUEUE.task_done()
        except Exception:
            pass


for idx in range(4):
    Thread(target=gps_processor_worker, daemon=True, name=f"tharani-gps-processor-{idx}").start()

def background_checks_worker():
    import time
    while True:
        try:
            run_background_checks(utc_now(), force=True)
        except Exception:
            pass
        time.sleep(5.0)

Thread(target=background_checks_worker, daemon=True, name="tharani-bg-checks").start()
WEIGHT_MODEL = None
ANOMALY_MODEL = None
ANOMALY_BUFFER = []
ANOMALY_EVENT_COUNT = 0
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("THARANI_JWT_EXPIRE_HOURS", "12"))
JWT_SECRET = os.getenv("THARANI_JWT_SECRET", "tharani-sengol-dev-secret-change-me")
VALID_ROLES = {"admin", "officer", "owner", "operator", "guest"}
ROLE_RANK = {"admin": 4, "officer": 3, "owner": 2, "operator": 1, "guest": 1}
DEFAULT_GUEST_USER = {"username": "guest", "role": "operator", "vehicle_ids": []}
USER_STORE = {}

from flask_cors import CORS
app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
CORS(app)

def default_users_payload() -> dict:
    return {
        "users": [
            {
                "username": "admin",
                "password": "admin123",
                "role": "admin",
                "vehicle_ids": [],
            },
            {
                "username": "officer1",
                "password": "officer123",
                "role": "officer",
                "vehicle_ids": [],
            },
            {
                "username": "owner1",
                "password": "owner123",
                "role": "owner",
                "vehicle_ids": ["truck_1", "truck_2", "truck_3", "truck_4", "truck_5"],
            },
            {
                "username": "operator1",
                "password": "operator123",
                "role": "operator",
                "vehicle_ids": ["truck_1", "truck_2"],
            },
        ]
    }


def default_users_index() -> dict:
    indexed = {}
    for user in default_users_payload().get("users", []):
        username = str(user.get("username", "")).strip().lower()
        if not username:
            continue
        indexed[username] = {
            "username": username,
            "password": str(user.get("password", "")),
            "role": str(user.get("role", "operator")).strip().lower(),
            "vehicle_ids": [str(v).strip() for v in user.get("vehicle_ids", []) if str(v).strip()],
        }
    return indexed


def ensure_user_store() -> None:
    if USERS_FILE.exists():
        return
    USERS_FILE.write_text(json.dumps(default_users_payload(), indent=2), encoding="utf-8")


def load_user_store() -> None:
    global USER_STORE
    ensure_user_store()
    try:
        payload = json.loads(USERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        payload = default_users_payload()

    users = payload.get("users", []) if isinstance(payload, dict) else []
    indexed = {}
    for user in users:
        username = str(user.get("username", "")).strip().lower()
        role = str(user.get("role", "operator")).strip().lower()
        if not username or role not in VALID_ROLES:
            continue
        indexed[username] = {
            "username": username,
            "password": str(user.get("password", "")),
            "role": role,
            "vehicle_ids": [str(v).strip() for v in user.get("vehicle_ids", []) if str(v).strip()],
        }

    USER_STORE = indexed


def save_user_store() -> None:
    users = [
        {
            "username": user["username"],
            "password": user["password"],
            "role": user["role"],
            "vehicle_ids": user.get("vehicle_ids", []),
        }
        for user in USER_STORE.values()
    ]
    users.sort(key=lambda x: x["username"].lower())
    USERS_FILE.write_text(json.dumps({"users": users}, indent=2), encoding="utf-8")


def issue_jwt(user: dict) -> str:
    if jwt is None:
        raise RuntimeError("PyJWT is not installed")
    now = utc_now()
    payload = {
        "sub": str(user["username"]).lower(),
        "role": user["role"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def parse_jwt_from_request() -> Optional[dict]:
    auth = str(request.headers.get("Authorization", "")).strip()
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
    if not token:
        token = str(request.cookies.get("tharani_token", "")).strip()
    if not token:
        return None
    if jwt is None:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None

    username = str(payload.get("sub", "")).strip()
    user = USER_STORE.get(username)
    if not user:
        return None
    return user


def safe_user(user: Optional[dict]) -> dict:
    if not user:
        return {"username": "anonymous", "role": "anonymous", "vehicle_ids": []}
    return {
        "username": user["username"],
        "role": user["role"],
        "vehicle_ids": list(user.get("vehicle_ids", [])),
    }


def current_user() -> Optional[dict]:
    user = getattr(g, "current_user", None)
    if user is not None:
        return user
    user = parse_jwt_from_request()
    if user is None:
        user = DEFAULT_GUEST_USER
    g.current_user = user
    return user


def is_admin(user: Optional[dict]) -> bool:
    return bool(user and user.get("role") == "admin")


def has_role(user: Optional[dict], *roles: str) -> bool:
    if not user:
        return False
    return user.get("role") in set(roles)


def scoped_vehicle_ids_for_user(user: Optional[dict]) -> Optional[set[str]]:
    if not user:
        return set()
    if user.get("role") in {"admin", "officer", "operator", "guest"}:
        return None
    return set(user.get("vehicle_ids", []))


def user_can_access_vehicle(user: Optional[dict], vehicle_id: str) -> bool:
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is None:
        return True
    return vehicle_id in allowed


def scope_rows_by_user(rows: list[dict], user: Optional[dict]) -> list[dict]:
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is None:
        return rows
    return [row for row in rows if str(row.get("vehicle_id", "")) in allowed]


def role_api_access(path: str, role: str, method: str) -> bool:
    if path in {"/api/auth/login", "/api/auth/logout"}:
        return True
    if role not in VALID_ROLES:
        return False

    if path.startswith("/api/admin"):
        return role == "admin"
    if path.startswith("/export/"):
        return role in {"admin", "officer", "owner", "operator", "guest"}
    if path in {"/gps", "/camera"}:
        return True
    if path.startswith("/api/control-state") or path.startswith("/api/permits"):
        return True
    if path.startswith("/api/camera/events"):
        return True
    if path.startswith("/api/users"):
        return role == "admin"

    if path.startswith("/api/heatmap"):
        return True
    if path.startswith("/api/module-predictions"):
        return True
    if path.startswith("/api/digital-twin"):
        return True
    if path.startswith("/api/ai-overview"):
        return True
    if path.startswith("/api/predictions"):
        return True

    if path.startswith("/api/lorries") or path.startswith("/api/vehicle/"):
        return True
    if path.startswith("/api/alerts") or path.startswith("/api/history/") or path.startswith("/api/trips"):
        return True

    if path.startswith("/api/"):
        return True

    return True


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = sin(d_lat / 2.0) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2.0) ** 2
    c = 2.0 * atan2(sqrt(a), sqrt(1.0 - a))
    return radius * c


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lon = radians(lon2 - lon1)
    y = sin(d_lon) * cos(radians(lat2))
    x = cos(radians(lat1)) * sin(radians(lat2)) - sin(radians(lat1)) * cos(radians(lat2)) * cos(d_lon)
    angle = atan2(y, x)
    return (angle * 180.0 / 3.141592653589793 + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def table_columns(table_name: str) -> set[str]:
    rows = db_query(f"PRAGMA table_info({table_name})")
    return {row["name"] for row in rows}


def ensure_column(table_name: str, column_name: str, column_definition: str) -> None:
    if column_name not in table_columns(table_name):
        db_execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def load_weight_model():
    global WEIGHT_MODEL
    if joblib is None or not WEIGHT_MODEL_PATH.exists():
        WEIGHT_MODEL = None
        return None

    try:
        WEIGHT_MODEL = joblib.load(WEIGHT_MODEL_PATH)
    except Exception:
        WEIGHT_MODEL = None
    return WEIGHT_MODEL


def predict_weight_from_features(features: dict, use_heuristic: bool = False) -> tuple[float, float, str]:
    row = [float(features[name]) for name in WEIGHT_FEATURE_ORDER]

    predicted = None
    confidence = 0.72
    source = "heuristic"

    if not use_heuristic and WEIGHT_MODEL is not None:
        try:
            row_df = pd.DataFrame([row], columns=WEIGHT_FEATURE_ORDER)
            predicted = float(WEIGHT_MODEL.predict(row_df)[0])
            source = "model"
            if hasattr(WEIGHT_MODEL, "estimators_"):
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    tree_predictions = [float(estimator.predict(row_df.values)[0]) for estimator in WEIGHT_MODEL.estimators_]
                spread = statistics.pstdev(tree_predictions) if len(tree_predictions) > 1 else 0.0
                confidence = clamp(1.0 - min(spread / 18.0, 0.45), 0.55, 0.97)
            else:
                confidence = 0.84
        except Exception:
            predicted = None

    if predicted is None:
        predicted = (
            3.75
            + (0.18 * float(features["trip_time"]))
            + (0.22 * float(features["route_distance"]))
            + (0.11 * float(features["stops_count"]))
            + (0.07 * float(features["acceleration_variation"]))
            + (0.03 * float(features["trip_number"]))
            + (0.015 * float(features["max_speed"]))
            - (0.12 * float(features["avg_speed"]))
            + (0.05 * max(0.0, 18.0 - float(features["avg_speed"])))
            + (0.02 * abs(float(features["time_of_day"]) - 13.0))
        )
        confidence = 0.68

    predicted = clamp(float(predicted), 2.0, 42.0)
    return round(predicted, 2), round(confidence, 3), source


def compute_shap_like_explanation(features: dict, predicted_weight: float) -> dict:
    explanation = {"method": "fallback", "items": []}
    if not features:
        return explanation

    items = [
        ("trip_time", 0.18 * float(features.get("trip_time", 0.0))),
        ("route_distance", 0.22 * float(features.get("route_distance", 0.0))),
        ("stops_count", 0.11 * float(features.get("stops_count", 0.0))),
        ("acceleration_variation", 0.07 * float(features.get("acceleration_variation", 0.0))),
        ("avg_speed", -0.12 * float(features.get("avg_speed", 0.0))),
    ]
    items.sort(key=lambda x: abs(x[1]), reverse=True)
    explanation["items"] = [{"feature": key, "impact": round(value, 3)} for key, value in items[:3]]

    if shap is not None and WEIGHT_MODEL is not None and hasattr(WEIGHT_MODEL, "estimators_"):
        try:
            explainer = shap.TreeExplainer(WEIGHT_MODEL)
            row = [[float(features[name]) for name in WEIGHT_FEATURE_ORDER]]
            shap_values = explainer.shap_values(row)
            values = shap_values[0] if isinstance(shap_values, list) else shap_values[0]
            ranked = sorted(zip(WEIGHT_FEATURE_ORDER, values), key=lambda x: abs(float(x[1])), reverse=True)[:3]
            explanation["method"] = "shap"
            explanation["items"] = [{"feature": f, "impact": round(float(v), 3)} for f, v in ranked]
        except Exception:
            pass

    explanation["predicted_weight"] = round(float(predicted_weight), 2)
    return explanation


LAST_ANOMALY_FIT_TIME = 0.0

def refit_anomaly_model_async(buffer_copy):
    global ANOMALY_MODEL
    try:
        model = IsolationForest(n_estimators=120, contamination=0.07, random_state=42)
        model.fit(buffer_copy)
        ANOMALY_MODEL = model
    except Exception:
        pass


def update_anomaly_score(state: dict, features: dict) -> float:
    global ANOMALY_MODEL, ANOMALY_EVENT_COUNT, LAST_ANOMALY_FIT_TIME

    vector = [
        float(features.get("trip_time", 0.0)),
        float(features.get("avg_speed", 0.0)),
        float(features.get("max_speed", 0.0)),
        float(features.get("stops_count", 0.0)),
        float(features.get("acceleration_variation", 0.0)),
        float(features.get("route_distance", 0.0)),
        float(state.get("risk", 0.0)),
        float(state.get("prediction", {}).get("probability", 0.0)),
    ]

    ANOMALY_BUFFER.append(vector)
    if len(ANOMALY_BUFFER) > 5000:
        del ANOMALY_BUFFER[:-5000]

    ANOMALY_EVENT_COUNT += 1
    if IsolationForest is not None and len(ANOMALY_BUFFER) >= ANOMALY_MIN_BUFFER:
        curr_time = time.time()
        if ANOMALY_MODEL is None:
            try:
                ANOMALY_MODEL = IsolationForest(n_estimators=120, contamination=0.07, random_state=42)
                ANOMALY_MODEL.fit(ANOMALY_BUFFER)
                LAST_ANOMALY_FIT_TIME = curr_time
            except Exception:
                ANOMALY_MODEL = None
        elif ANOMALY_EVENT_COUNT % ANOMALY_REFIT_INTERVAL == 0 and curr_time - LAST_ANOMALY_FIT_TIME >= 60.0:
            LAST_ANOMALY_FIT_TIME = curr_time
            buffer_copy = list(ANOMALY_BUFFER)
            Thread(target=refit_anomaly_model_async, args=(buffer_copy,), daemon=True, name="tharani-anomaly-fit").start()

    if ANOMALY_MODEL is None:
        # Heuristic fallback anomaly scoring when IsolationForest is unavailable.
        risk_value = float(state.get("risk", 0.0)) / 100.0
        speed_ratio = clamp(float(features.get("max_speed", 0.0)) / 130.0, 0.0, 1.0)
        fluctuation_ratio = clamp(float(features.get("acceleration_variation", 0.0)) / 22.0, 0.0, 1.0)
        stop_ratio = clamp(float(features.get("stops_count", 0.0)) / 25.0, 0.0, 1.0)
        predicted_prob = float(state.get("prediction", {}).get("probability", 0.0))
        anomaly_score = clamp((0.35 * risk_value) + (0.20 * speed_ratio) + (0.20 * fluctuation_ratio) + (0.10 * stop_ratio) + (0.15 * predicted_prob), 0.0, 1.0)
    else:
        try:
            raw = float(ANOMALY_MODEL.score_samples([vector])[0])
            anomaly_score = clamp(((-raw) - 0.25) * 3.2, 0.0, 1.0)
        except Exception:
            anomaly_score = 0.0

    state["anomaly_score"] = round(anomaly_score, 3)
    state["anomaly_flag"] = anomaly_score >= 0.72
    return float(state["anomaly_score"])


def update_driver_behavior(state: dict) -> dict:
    deltas = [float(x) for x in state.get("speed_deltas", [])[-30:] if x is not None]
    speeds = [float(x) for x in state.get("speed_samples", [])[-30:] if x is not None]
    harsh_braking = sum(1 for x in deltas if x >= 18.0)
    fluctuation = statistics.pstdev(speeds) if len(speeds) >= 2 else 0.0
    profile = str(state.get("profile", "normal"))
    risk_value = float(state.get("risk", 0.0))
    anomaly_value = float(state.get("anomaly_score", 0.0))

    harsh_threshold = 3
    fluctuation_threshold = 11.0
    if profile == "high_risk":
        harsh_threshold = 2
        fluctuation_threshold = 8.5
    elif profile == "safe":
        harsh_threshold = 4
        fluctuation_threshold = 13.0

    risky = harsh_braking >= harsh_threshold or fluctuation >= fluctuation_threshold

    # Align behavior outcome with risk profile expectations, especially for high-risk vehicles.
    if profile == "high_risk" and (risk_value >= 45.0 or anomaly_value >= 0.45 or float(state.get("recent_speed_kmh", 0.0)) >= 80.0):
        risky = True
    if profile == "safe" and risk_value < 35.0 and anomaly_value < 0.35 and harsh_braking <= 1 and fluctuation < 8.5:
        risky = False

    expected_risky = profile == "high_risk"
    profile_alignment = (risky and expected_risky) or ((not risky) and (not expected_risky))

    state["driver_behavior"] = {
        "harsh_braking": int(harsh_braking),
        "speed_fluctuation": round(float(fluctuation), 2),
        "risky": bool(risky),
        "expected_risky": bool(expected_risky),
        "profile_alignment": bool(profile_alignment),
        "profile": profile,
    }
    return state["driver_behavior"]


def compute_lstm_style_forecast(state: dict) -> dict:
    next_zone = "dump" if state.get("stage") == "to_dump" else "mine" if state.get("stage") == "to_mine" else "mine"
    base_weight = state.get("predicted_weight") or state.get("average_weight") or 0.0
    trend = 0.08 * (float(state.get("risk", 0.0)) / 100.0)
    future_load = clamp(float(base_weight) * (1.0 + trend), 0.0, 45.0)
    state["time_series_forecast"] = {
        "model": "lstm-lite",
        "future_route": next_zone,
        "future_load_tons": round(float(future_load), 2),
    }
    return state["time_series_forecast"]


def compute_fusion_threat_score(state: dict) -> float:
    risk = float(state.get("risk", 0.0))
    probability = float(state.get("prediction", {}).get("probability", 0.0)) * 100.0
    overload_boost = 14.0 if state.get("overload_flag") else 0.0
    anomaly_boost = float(state.get("anomaly_score", 0.0)) * 24.0
    driver_boost = 8.0 if state.get("driver_behavior", {}).get("risky") else 0.0

    fusion = clamp((0.45 * risk) + (0.35 * probability) + overload_boost + anomaly_boost + driver_boost, 0.0, 100.0)
    state["final_threat_score"] = round(float(fusion), 2)
    return state["final_threat_score"]


def compute_digital_twin_summary() -> dict:
    with STATE_LOCK:
        states = list(vehicle_state.values())
    active = len(states)
    overloads = sum(1 for s in states if s.get("overload_flag"))
    avg_risk = round(sum(float(s.get("risk", 0.0)) for s in states) / active, 2) if active else 0.0
    avg_threat = round(sum(float(s.get("final_threat_score", 0.0)) for s in states) / active, 2) if active else 0.0
    return {
        "active_trucks": active,
        "configured_routes": len(route_definitions),
        "configured_mines": len(route_definitions),
        "configured_dumps": len(route_definitions),
        "overloads": overloads,
        "avg_risk": avg_risk,
        "avg_final_threat": avg_threat,
    }


def build_lorry_rows() -> list[dict]:
    rows = []
    with STATE_LOCK:
        items = list(vehicle_state.items())
    for vehicle_id, state in items:
        gps = gps_store.get(vehicle_id, {})
        weight_prediction = state.get("weight_prediction", {})
        rows.append(
            {
                "vehicle_id": vehicle_id,
                "district": state.get("district") or gps.get("district") or "Unknown",
                "route_id": state.get("route_id"),
                "route_name": state.get("route_name"),
                "lat": gps.get("lat"),
                "lon": gps.get("lon"),
                "zone_name": gps.get("zone_name") or state.get("current_zone_name") or "Outside",
                "trips": int(state.get("trips", 0)),
                "trips_24h": int(state.get("trips_24h", 0)),
                "risk": round(float(state.get("risk", 0.0)), 2),
                "risk_level": classify_risk(float(state.get("risk", 0.0))),
                "prediction_label": state.get("prediction", {}).get("label", "LOW"),
                "prediction_probability": float(state.get("prediction", {}).get("probability", 0.0)),
                "predicted_weight": float(state.get("predicted_weight", 0.0) or 0.0),
                "average_weight": float(state.get("average_weight", 0.0) or 0.0),
                "weight_locked": bool(weight_prediction.get("is_locked", False)),
                "overload_flag": bool(state.get("overload_flag", False)),
                "anomaly_score": float(state.get("anomaly_score", 0.0)),
                "final_threat_score": float(state.get("final_threat_score", 0.0)),
                "driver_behavior": state.get("driver_behavior", {}),
                "time_series_forecast": state.get("time_series_forecast", {}),
                "profile": state.get("profile", "normal"),
                "last_event": state.get("last_event", ""),
                "updated_at": state.get("updated_at") or gps.get("timestamp"),
                "weight_history": state.get("weight_history", [])[-30:],
            }
        )
    rows.sort(key=lambda item: (item["final_threat_score"], item["risk"], item["vehicle_id"]), reverse=True)
    return rows


def filter_lorry_rows(rows: list[dict], query: str = "", district: str = "") -> list[dict]:
    normalized_query = query.strip().lower()
    normalized_district = district.strip().lower()

    filtered = []
    for row in rows:
        if normalized_district and row.get("district", "").lower() != normalized_district:
            continue

        if normalized_query:
            haystack = " ".join(
                [
                    str(row.get("vehicle_id", "")),
                    str(row.get("district", "")),
                    str(row.get("route_id", "")),
                    str(row.get("route_name", "")),
                    str(row.get("profile", "")),
                    str(row.get("last_event", "")),
                    str(row.get("driver_behavior", {})),
                    str(row.get("time_series_forecast", {})),
                ]
            ).lower()
            if normalized_query not in haystack:
                continue

        filtered.append(row)

    return filtered


def paginate_rows(rows: list[dict], page: int, page_size: int) -> dict:
    safe_page_size = max(1, min(page_size, 50))
    total = len(rows)
    total_pages = max(1, (total + safe_page_size - 1) // safe_page_size)
    safe_page = max(1, min(page, total_pages))
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return {
        "items": rows[start:end],
        "page": safe_page,
        "page_size": safe_page_size,
        "total": total,
        "total_pages": total_pages,
    }


def build_chat_knowledge() -> list[dict]:
    rows = build_lorry_rows()
    districts = {}
    for row in rows:
        district = row.get("district", "Unknown")
        district_rows = districts.setdefault(district, [])
        district_rows.append(row)

    docs = []
    twin = compute_digital_twin_summary()
    docs.append(
        {
            "id": "overview",
            "type": "overview",
            "text": (
                f"Tharani Sengol monitors {twin['active_trucks']} active trucks across {twin['configured_routes']} routes and {twin['configured_mines']} mines in Tamil Nadu. "
                f"Average risk is {twin['avg_risk']}, average final threat score is {twin['avg_final_threat']}, and overload count is {twin['overloads']}."
            ),
            "answer": (
                f"Overall Tamil Nadu summary: {twin['active_trucks']} active trucks, {twin['configured_routes']} routes, {twin['configured_mines']} mine zones, {twin['overloads']} overloads, avg risk {twin['avg_risk']}, avg final threat {twin['avg_final_threat']}."
            ),
        }
    )

    for district_name, district_rows in districts.items():
        overloads = sum(1 for item in district_rows if item.get("overload_flag"))
        avg_risk = round(sum(float(item.get("risk", 0.0)) for item in district_rows) / max(1, len(district_rows)), 2)
        avg_threat = round(sum(float(item.get("final_threat_score", 0.0)) for item in district_rows) / max(1, len(district_rows)), 2)
        docs.append(
            {
                "id": f"district:{district_name}",
                "type": "district",
                "text": (
                    f"District {district_name} has {len(district_rows)} active trucks, {overloads} overloads, average risk {avg_risk}, and average final threat {avg_threat}."
                ),
                "answer": (
                    f"District {district_name}: {len(district_rows)} active trucks, {overloads} overloads, avg risk {avg_risk}, avg final threat {avg_threat}."
                ),
            }
        )

    for route_id, route in route_definitions.items():
        docs.append(
            {
                "id": f"route:{route_id}",
                "type": "route",
                "text": (
                    f"Route {route_id} is {route.get('name')} in {route.get('district', 'Tamil Nadu')} with mine zone {route['mine_zone']['name']} and dump zone {route['dump_zone']['name']}."
                ),
                "answer": (
                    f"Route {route_id} ({route.get('name')}), district {route.get('district', 'Tamil Nadu')}. Mine zone: {route['mine_zone']['name']}. Dump zone: {route['dump_zone']['name']}."
                ),
            }
        )

    top_rows = sorted(rows, key=lambda item: item.get("final_threat_score", 0.0), reverse=True)[:60]
    for row in top_rows:
        docs.append(
            {
                "id": f"vehicle:{row['vehicle_id']}",
                "type": "vehicle",
                "text": (
                    f"Vehicle {row['vehicle_id']} in {row['district']} route {row['route_id']} has risk {row['risk']}, prediction {row['prediction_label']} at {round(row['prediction_probability'] * 100)} percent, weight {row['predicted_weight']:.1f} tons, overload {row['overload_flag']}, anomaly score {row['anomaly_score']}, final threat {row['final_threat_score']}. Driver behavior harsh braking {row['driver_behavior'].get('harsh_braking', 0)} and speed fluctuation {row['driver_behavior'].get('speed_fluctuation', 0)}."
                ),
                "answer": (
                    f"{row['vehicle_id']} is in {row['district']} on {row['route_id']} with risk {row['risk']} ({row['risk_level']}), prediction {row['prediction_label']} ({round(row['prediction_probability'] * 100)}%), weight {row['predicted_weight']:.1f} tons, overload {'YES' if row['overload_flag'] else 'NO'}, anomaly {row['anomaly_score']}, final threat {row['final_threat_score']}."
                ),
            }
        )

    return docs


def answer_chat_query(query: str) -> dict:
    normalized = query.strip().lower()
    rows = build_lorry_rows()
    docs = build_chat_knowledge()

    vehicle_match = re.search(r"\b(?:vehicle|truck|lorry)\s*[_-]?(\d{1,4})\b", normalized)
    vehicle_key = f"truck_{int(vehicle_match.group(1))}" if vehicle_match else None
    route_match = re.search(r"\broute\s*[_-]?(\d{1,4})\b", normalized)
    route_key = f"route_{int(route_match.group(1))}" if route_match else None

    vehicle_hit = None
    if vehicle_key:
        vehicle_hit = next((row for row in rows if row["vehicle_id"].lower() == vehicle_key), None)
    if vehicle_hit is None:
        vehicle_hit = next((row for row in rows if row["vehicle_id"].lower() in normalized), None)
    route_hit = None
    if route_key and route_key in route_definitions:
        route_hit = route_definitions[route_key]
    if route_hit is None:
        route_hit = next((route for route_id, route in route_definitions.items() if route_id.lower() in normalized or route["name"].lower() in normalized), None)
    district_hit = next((doc for doc in docs if doc["type"] == "district" and doc["id"].split(":", 1)[1].lower() in normalized), None)

    if vehicle_hit:
        behavior = vehicle_hit.get("driver_behavior", {})
        forecast = vehicle_hit.get("time_series_forecast", {})
        explanation = vehicle_hit.get("final_threat_score", 0.0)
        return {
            "answer": (
                f"{vehicle_hit['vehicle_id']} is in {vehicle_hit['district']} on {vehicle_hit['route_id']}. Risk is {vehicle_hit['risk']} ({vehicle_hit['risk_level']}). "
                f"Prediction is {vehicle_hit['prediction_label']} ({round(vehicle_hit['prediction_probability'] * 100)}%). Weight is {'locked at ' + str(round(vehicle_hit['predicted_weight'], 1)) + ' tons' if vehicle_hit['weight_locked'] else 'pending lock'}. "
                f"Driver behavior shows {behavior.get('harsh_braking', 0)} harsh braking events and speed fluctuation {behavior.get('speed_fluctuation', 0)}. "
                f"Future route forecast: {forecast.get('future_route', 'n/a')}, future load {forecast.get('future_load_tons', 0)} tons. Final threat score {explanation}."
            ),
            "source": vehicle_hit,
        }

    if route_hit:
        return {
            "answer": (
                f"{route_hit['name']} is in {route_hit.get('district', 'Tamil Nadu')}. Mine zone is {route_hit['mine_zone']['name']} and dump zone is {route_hit['dump_zone']['name']}."
            ),
            "source": route_hit,
        }

    if district_hit:
        return {"answer": district_hit["answer"], "source": district_hit}

    tokens = [token for token in normalized.replace("_", " ").split() if token]
    ignored_tokens = {"vehicle", "truck", "lorry", "route", "mine", "dump", "zone", "details", "detail", "show", "tell", "about"}
    filtered_tokens = [token for token in tokens if token not in ignored_tokens and not token.isdigit()]
    if not filtered_tokens:
        return {
            "answer": (
                "Please specify a full identifier like truck_120 or route_38, or include a district name like Salem."
            ),
            "source": {"type": "help"},
        }

    best = None
    best_score = 0
    for doc in docs:
        text = doc.get("text", "").lower()
        score = 0
        for token in filtered_tokens:
            if token in text:
                score += 1
        if score > best_score:
            best = doc
            best_score = score

    if not best or best_score <= 0:
        return {
            "answer": (
                "I can answer about Tamil Nadu district statistics, route details, mine zones, driver behavior, weight prediction, anomaly detection, overloads, and final threat scores. Ask about a truck ID like truck_52, a district like Salem, or a route like route_14."
            ),
            "source": {"type": "help"},
        }

    return {"answer": best.get("answer", "I found related information, but the response is limited."), "source": best}


def compute_heatmap_clusters(limit: int = 1200, clusters: int = KMEANS_DEFAULT_CLUSTERS) -> list[dict]:
    points = violation_heatmap[-max(50, min(limit, MAX_HEATMAP_POINTS)) :]
    if len(points) < 5:
        return []

    output = []
    dataset = [[float(p["lat"]), float(p["lon"])] for p in points]

    if KMeans is not None:
        k = max(2, min(clusters, len(dataset) // 10))
        try:
            model = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = model.fit_predict(dataset)

            grouped = {idx: {"count": 0, "weight": 0.0} for idx in range(k)}
            for label, point in zip(labels, points):
                grouped[int(label)]["count"] += 1
                grouped[int(label)]["weight"] += float(point.get("weight", 1.0))

            for idx, centroid in enumerate(model.cluster_centers_):
                output.append(
                    {
                        "cluster_id": idx,
                        "lat": round(float(centroid[0]), 6),
                        "lon": round(float(centroid[1]), 6),
                        "points": grouped[idx]["count"],
                        "intensity": round(float(grouped[idx]["weight"]), 2),
                        "zone_type": "Potential illegal mining zone" if grouped[idx]["count"] >= 6 else "Watch zone",
                    }
                )
        except Exception:
            output = []

    # Fallback clustering when sklearn is unavailable.
    if not output:
        bins = {}
        for point in points:
            lat = float(point.get("lat", 0.0))
            lon = float(point.get("lon", 0.0))
            key = (round(lat, 2), round(lon, 2))
            item = bins.setdefault(
                key,
                {
                    "sum_lat": 0.0,
                    "sum_lon": 0.0,
                    "count": 0,
                    "weight": 0.0,
                },
            )
            item["sum_lat"] += lat
            item["sum_lon"] += lon
            item["count"] += 1
            item["weight"] += float(point.get("weight", 1.0))

        ranked = sorted(bins.values(), key=lambda x: (x["weight"], x["count"]), reverse=True)[: max(2, min(clusters, 20))]
        for idx, item in enumerate(ranked):
            count = max(1, int(item["count"]))
            output.append(
                {
                    "cluster_id": idx,
                    "lat": round(item["sum_lat"] / count, 6),
                    "lon": round(item["sum_lon"] / count, 6),
                    "points": count,
                    "intensity": round(float(item["weight"]), 2),
                    "zone_type": "Potential illegal mining zone" if count >= 6 else "Watch zone",
                }
            )

    output.sort(key=lambda x: x["intensity"], reverse=True)
    return output


def build_weight_features(state: dict, now: datetime) -> dict:
    trip_started_raw = state.get("trip_started_at")
    if trip_started_raw:
        trip_started = to_aware(datetime.fromisoformat(trip_started_raw))
    else:
        trip_started = now

    trip_time = max((now - trip_started).total_seconds() / 60.0, 1.0)
    route_distance_km = max(float(state.get("trip_distance_m", 0.0)) / 1000.0, 0.01)
    avg_speed = route_distance_km / max(trip_time / 60.0, 1e-3)
    max_speed = max(float(state.get("max_speed", 0.0)), float(state.get("recent_speed_kmh", 0.0)))

    speed_samples = [float(value) for value in state.get("speed_samples", []) if value is not None]
    if not speed_samples and max_speed:
        speed_samples = [max_speed]

    stops_count = int(state.get("stops_count", 0))
    if not stops_count and speed_samples:
        stops_count = sum(1 for value in speed_samples if value < 6.0)

    speed_deltas = [float(value) for value in state.get("speed_deltas", []) if value is not None]
    if len(speed_deltas) >= 2:
        acceleration_variation = statistics.pstdev(speed_deltas)
    elif speed_deltas:
        acceleration_variation = float(speed_deltas[-1])
    else:
        acceleration_variation = 0.0

    features = {
        "trip_time": round(float(trip_time), 2),
        "avg_speed": round(float(avg_speed), 2),
        "max_speed": round(float(max_speed), 2),
        "stops_count": int(stops_count),
        "acceleration_variation": round(float(acceleration_variation), 3),
        "route_distance": round(float(route_distance_km), 3),
        "trip_number": int(state.get("trips", 0)) + 1,
        "time_of_day": int(now.hour),
    }
    return features


def reset_weight_trip(state: dict, now: datetime, lat: Optional[float] = None, lon: Optional[float] = None) -> None:
    state["trip_started_at"] = now.isoformat() if lat is not None and lon is not None else None
    state["trip_distance_m"] = 0.0
    state["max_speed"] = 0.0
    state["stops_count"] = 0
    state["speed_samples"] = []
    state["speed_deltas"] = []
    state["last_weight_prediction_at"] = None
    state["weight_locked_for_trip"] = False
    state["weight_locked_at"] = None
    state["last_weight_lock_key"] = None
    state["predicted_weight"] = None
    state["overload_flag"] = False
    state["overload_alerted"] = False
    if lat is not None:
        state["trip_start_lat"] = lat
    if lon is not None:
        state["trip_start_lon"] = lon


def finalize_weight_trip(vehicle_id: str, state: dict, now: datetime) -> None:
    state["last_trip_completed_at"] = now.isoformat()
    
    predicted_weight = float(state.get("predicted_weight") or 0.0)
    
    # Retrieve permit details
    permit_rows = db_query("SELECT permit_id FROM permits WHERE vehicle_number = ? AND status = 'active'", (vehicle_id,))
    permit_id = permit_rows[0]["permit_id"] if permit_rows else None
    
    # Save completed trip record
    trip_count = int(state.get("trips", 0))
    trip_id = f"TRIP-{vehicle_id}-{trip_count}-{int(now.timestamp())}"
    db_execute(
        """
        INSERT OR IGNORE INTO trip_records (trip_id, vehicle_id, permit_id, predicted_load, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (trip_id, vehicle_id, permit_id, predicted_weight, now.isoformat())
    )
    
    # Update permit tallies
    if permit_id:
        db_execute(
            """
            UPDATE permits
            SET completed_trips = completed_trips + 1,
                used_quantity = used_quantity + ?
            WHERE permit_id = ?
            """,
            (predicted_weight, permit_id)
        )
        
        # Immediate limit check alerts
        updated_permit_rows = db_query("SELECT completed_trips, max_trips, used_quantity, max_quantity FROM permits WHERE permit_id = ?", (permit_id,))
        if updated_permit_rows:
            up = updated_permit_rows[0]
            if up["completed_trips"] > up["max_trips"]:
                append_alert(vehicle_id, f"Permit trip limit exceeded: {up['completed_trips']}/{up['max_trips']} trips completed", severity="warning")
            if up["used_quantity"] > up["max_quantity"]:
                append_alert(vehicle_id, f"Permit quantity limit exceeded: {up['used_quantity']:.1f}/{up['max_quantity']:.1f} Tons", severity="critical")
                
    reset_weight_trip(state, now)


def update_weight_prediction(vehicle_id: str, state: dict, now: datetime, previous_record: Optional[dict], current_lat: float, current_lon: float) -> dict:
    if not state.get("trip_started_at"):
        reset_weight_trip(state, now, current_lat, current_lon)

    last_update_raw = state.get("last_update")
    if previous_record is not None and last_update_raw:
        try:
            last_update = to_aware(datetime.fromisoformat(last_update_raw))
            elapsed_seconds = max((now - last_update).total_seconds(), 1.0)
        except ValueError:
            elapsed_seconds = 1.0

        moved_meters = haversine_meters(previous_record["lat"], previous_record["lon"], current_lat, current_lon)
        state["trip_distance_m"] = float(state.get("trip_distance_m", 0.0)) + moved_meters

        speed_kmh = (moved_meters / elapsed_seconds) * 3.6
        recent_speeds = state.setdefault("speed_samples", [])
        if recent_speeds:
            state.setdefault("speed_deltas", []).append(abs(speed_kmh - float(recent_speeds[-1])))
        recent_speeds.append(speed_kmh)
        if len(recent_speeds) > 160:
            state["speed_samples"] = recent_speeds[-160:]

        if speed_kmh < 6.0 or moved_meters < 18.0:
            state["stops_count"] = int(state.get("stops_count", 0)) + 1

        state["max_speed"] = max(float(state.get("max_speed", 0.0)), speed_kmh)
        state["recent_speed_kmh"] = round(speed_kmh, 2)

    features = build_weight_features(state, now)
    trip_distance_km = float(features["route_distance"])
    trip_time_minutes = float(features["trip_time"])
    eligible_for_lock = (
        state.get("stage") == "to_dump"
        and trip_distance_km >= WEIGHT_LOCK_MIN_DISTANCE_KM
        and trip_time_minutes >= WEIGHT_LOCK_MIN_TRIP_MINUTES
    )

    if state.get("weight_locked_for_trip") and state.get("predicted_weight") is not None:
        predicted_weight = float(state["predicted_weight"])
        confidence = float(state.get("weight_prediction", {}).get("confidence", 0.0) or 0.0)
        source = str(state.get("weight_prediction", {}).get("source", "model"))
    else:
        if eligible_for_lock:
            # Lock the weight using the Random Forest model
            predicted_weight, confidence, source = predict_weight_from_features(features, use_heuristic=False)
            state["predicted_weight"] = predicted_weight
            state["weight_locked_for_trip"] = True
            state["weight_locked_at"] = now.isoformat()
        else:
            # Calculate real-time predicted weight on every tick using fast heuristic
            predicted_weight, confidence, source = predict_weight_from_features(features, use_heuristic=True)
            state["predicted_weight"] = predicted_weight

    if state.get("weight_locked_for_trip") and state.get("predicted_weight") is not None:
        history = state.setdefault("weight_history", [])
        lock_key = f"trip_{int(state.get('trips', 0))}_{state.get('weight_locked_at', '')}"
        if state.get("last_weight_lock_key") != lock_key:
            history.append(
                {
                    "ts": now.isoformat(),
                    "weight": float(state["predicted_weight"]),
                    "overload": float(state["predicted_weight"]) > WEIGHT_LIMIT_TONS,
                    "trip": int(state.get("trips", 0)),
                }
            )
            state["last_weight_lock_key"] = lock_key
            if len(history) > 120:
                state["weight_history"] = history[-120:]

    weights = [float(item.get("weight", 0.0)) for item in state.get("weight_history", []) if item.get("weight") is not None]
    state["average_weight"] = round(sum(weights) / len(weights), 2) if weights else round(predicted_weight, 2)
    state["overload_flag"] = bool(predicted_weight > WEIGHT_LIMIT_TONS)
    state["weight_prediction"] = {
        "predicted_weight": round(float(predicted_weight), 2),
        "average_weight": state["average_weight"],
        "confidence": round(float(confidence), 3),
        "source": source,
        "limit": WEIGHT_LIMIT_TONS,
        "overload_flag": state["overload_flag"],
        "is_locked": bool(state.get("weight_locked_for_trip")),
        "lock_distance_km": round(WEIGHT_LOCK_MIN_DISTANCE_KM, 2),
        "lock_trip_minutes": round(WEIGHT_LOCK_MIN_TRIP_MINUTES, 1),
        "distance_km": round(trip_distance_km, 3),
        "trip_time_min": round(trip_time_minutes, 2),
        "features": features,
    }
    if state.get("weight_locked_for_trip") and state.get("predicted_weight") is not None:
        state["weight_prediction"]["explain"] = compute_shap_like_explanation(features, state["predicted_weight"])

    if state["overload_flag"] and not state.get("overload_alerted"):
        if not reason_throttled(state, "overload", now, 180):
            update_risk(vehicle_id, "Overload detected", 18, severity="critical", lat=current_lat, lon=current_lon)
            state["last_event"] = f"Overload detected ({predicted_weight:.1f} tons)"
        state["overload_alerted"] = True
    elif not state["overload_flag"]:
        state["overload_alerted"] = False

    state["last_weight_prediction_at"] = now.isoformat()
    return state["weight_prediction"]


class GPSPayload:
    def __init__(self, payload: dict):
        self.vehicle_id = str(payload.get("vehicle_id", "")).strip()
        self.lat = float(payload.get("lat"))
        self.lon = float(payload.get("lon"))
        self.timestamp = to_aware(datetime.fromisoformat(payload.get("timestamp")))
        self.route_id = payload.get("route_id")
        self.weight = payload.get("weight")


class CameraPayload:
    def __init__(self, payload: dict):
        self.camera_id = str(payload.get("camera_id", "")).strip()
        self.lat = float(payload.get("lat"))
        self.lon = float(payload.get("lon"))
        self.truck_count = int(payload.get("truck_count", 0))
        self.timestamp = to_aware(datetime.fromisoformat(payload.get("timestamp")))
        self.route_id = payload.get("route_id")


def build_route(route_id, name, color, mine_center, dump_center, path_points=None, mine_size=0.00125, dump_size=0.00125, district_name="Tiruchirappalli"):
    mine_lat, mine_lon = mine_center
    dump_lat, dump_lon = dump_center

    mine_polygon = [
        [mine_lat - mine_size, mine_lon - mine_size],
        [mine_lat - mine_size, mine_lon + mine_size],
        [mine_lat + mine_size, mine_lon + mine_size],
        [mine_lat + mine_size, mine_lon - mine_size],
    ]

    dump_polygon = [
        [dump_lat - dump_size, dump_lon - dump_size],
        [dump_lat - dump_size, dump_lon + dump_size],
        [dump_lat + dump_size, dump_lon + dump_size],
        [dump_lat + dump_size, dump_lon - dump_size],
    ]

    route_path = path_points if path_points else [
        [mine_lat, mine_lon],
        [mine_lat + 0.0012, mine_lon + 0.0010],
        [mine_lat + 0.0026, mine_lon + 0.0022],
        [mine_lat + 0.0038, mine_lon + 0.0038],
        [dump_lat - 0.0010, dump_lon - 0.0012],
        [dump_lat, dump_lon],
        [dump_lat - 0.0010, dump_lon - 0.0012],
        [mine_lat + 0.0038, mine_lon + 0.0038],
        [mine_lat + 0.0026, mine_lon + 0.0022],
        [mine_lat + 0.0012, mine_lon + 0.0010],
        [mine_lat, mine_lon],
    ]

    return {
        "id": route_id,
        "name": name,
        "color": color,
        "state": "Tamil Nadu",
        "district": district_name,
        "mine_zone": {
            "id": f"{route_id}_mine",
            "name": f"Mine Zone {name}",
            "type": "mine",
            "route_id": route_id,
            "polygon": mine_polygon,
            "color": color,
        },
        "dump_zone": {
            "id": f"{route_id}_dump",
            "name": f"Dump Zone {name}",
            "type": "dump",
            "route_id": route_id,
            "polygon": dump_polygon,
            "color": color,
        },
        "path": route_path,
    }


def generate_tamilnadu_routes(existing_routes: dict, target_count: int) -> dict:
    if len(existing_routes) >= target_count:
        return existing_routes

    generated = dict(existing_routes)
    palette = ["#0f9d58", "#4285f4", "#f4b400", "#00acc1", "#db4437", "#7c3aed", "#f97316", "#14b8a6"]
    rng = random.Random(42)

    next_index = len(generated) + 1
    district_cycle = list(TAMIL_NADU_DISTRICTS)
    while len(generated) < target_count:
        route_id = f"route_{next_index}"
        district_name, d_lat, d_lon = district_cycle[(next_index - 1) % len(district_cycle)]
        mine_lat = clamp(d_lat + rng.uniform(-0.16, 0.16), TN_BOUNDS["lat_min"] + 0.2, TN_BOUNDS["lat_max"] - 0.2)
        mine_lon = clamp(d_lon + rng.uniform(-0.16, 0.16), TN_BOUNDS["lon_min"] + 0.2, TN_BOUNDS["lon_max"] - 0.2)

        lat_shift = rng.uniform(-0.45, 0.45)
        lon_shift = rng.uniform(-0.45, 0.45)
        dump_lat = clamp(mine_lat + lat_shift, TN_BOUNDS["lat_min"] + 0.18, TN_BOUNDS["lat_max"] - 0.18)
        dump_lon = clamp(mine_lon + lon_shift, TN_BOUNDS["lon_min"] + 0.18, TN_BOUNDS["lon_max"] - 0.18)

        generated[route_id] = build_route(
            route_id,
            f"TN Route {next_index}",
            palette[next_index % len(palette)],
            (mine_lat, mine_lon),
            (dump_lat, dump_lon),
            district_name=district_name,
        )
        next_index += 1

    return generated


def build_vehicle_profiles_and_permits(fleet_size: int) -> tuple[dict, dict]:
    profiles = {}
    permits = {}
    for idx in range(1, fleet_size + 1):
        vehicle_id = f"truck_{idx}"
        phase = idx % 10
        if phase in (0, 1, 2):
            profile = "safe"
        elif phase in (3, 4, 5, 6, 7):
            profile = "normal"
        else:
            profile = "high_risk"

        profiles[vehicle_id] = profile
        permits[vehicle_id] = {
            "allowed_24h_trips": 14 + (idx % 8),
            "rolling_window_hours": 24,
            "start_hour": 0,
            "end_hour": 24,
        }

    return profiles, permits


def interpolate_route(points: list[list[float]], steps_per_segment: int = 8) -> list[tuple[float, float]]:
    smooth_route = []
    for index in range(len(points) - 1):
        start_lat, start_lon = points[index]
        end_lat, end_lon = points[index + 1]
        for step in range(steps_per_segment):
            ratio = step / float(steps_per_segment)
            smooth_route.append((start_lat + (end_lat - start_lat) * ratio, start_lon + (end_lon - start_lon) * ratio))
    smooth_route.append(tuple(points[-1]))
    return smooth_route


def profile_for_truck(index: int) -> str:
    phase = index % 10
    if phase in (0, 1, 2):
        return "safe"
    if phase in (3, 4, 5, 6, 7):
        return "normal"
    return "high_risk"


def start_internal_simulator() -> None:
    global INTERNAL_SIMULATOR_STARTED
    if INTERNAL_SIMULATOR_STARTED:
        return
    if str(os.getenv("THARANI_DISABLE_INTERNAL_SIMULATOR", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return

    INTERNAL_SIMULATOR_STARTED = True

    def worker() -> None:
        time.sleep(float(os.getenv("THARANI_INTERNAL_SIMULATOR_GRACE_SECONDS", "6")))
        if gps_store or camera_events:
            return

        rng = random.Random(17)
        fleet_size = max(10, min(int(os.getenv("THARANI_INTERNAL_SIM_FLEET_SIZE", "60")), DEFAULT_FLEET_SIZE))
        route_ids = sorted(route_definitions.keys())
        if not route_ids:
            return

        fleet = []
        for idx in range(1, fleet_size + 1):
            route_id = route_ids[(idx - 1) % len(route_ids)]
            route_path = route_definitions[route_id].get("path", [])
            if len(route_path) < 2:
                continue
            fleet.append(
                {
                    "vehicle_id": f"truck_{idx}",
                    "route_id": route_id,
                    "points": interpolate_route(route_path, steps_per_segment=rng.randint(6, 12)),
                    "index": rng.randint(0, max(0, len(route_path) - 1)),
                    "stride": rng.randint(1, 4),
                    "tick": 0,
                    "profile": profile_for_truck(idx),
                }
            )

        if not fleet:
            return

        while True:
            active_shift = get_active_shift()
            shift_factor = {"morning_peak": 1.25, "noon_low": 0.70, "evening_peak": 1.20, "night_low": 0.80}.get(active_shift, 1.0)
            traffic_factor = float(CONTROL_STATE.get("traffic_factor", 1.0)) * shift_factor
            anomaly_factor = float(CONTROL_STATE.get("anomaly_factor", 1.0))
            gps_noise = float(CONTROL_STATE.get("gps_noise", 0.1))

            for vehicle in fleet:
                route_points = vehicle["points"]
                if not route_points:
                    continue

                vehicle["tick"] += 1
                if vehicle["tick"] < max(1, int(round(vehicle["stride"] / max(0.55, traffic_factor)))):
                    continue
                vehicle["tick"] = 0
                vehicle["index"] = (vehicle["index"] + 1) % len(route_points)
                lat, lon = route_points[vehicle["index"]]

                jitter = 0.0005 + (gps_noise * 0.0012)
                if vehicle["profile"] == "safe":
                    lat += rng.uniform(-jitter, jitter)
                    lon += rng.uniform(-jitter, jitter)
                elif vehicle["profile"] == "normal":
                    lat += rng.uniform(-jitter * 2.0, jitter * 2.0)
                    lon += rng.uniform(-jitter * 2.0, jitter * 2.0)
                    if rng.random() < (0.004 * anomaly_factor):
                        lat += 0.0014
                        lon += 0.0009
                else:
                    lat += rng.uniform(-jitter * 3.0, jitter * 3.0)
                    lon += rng.uniform(-jitter * 3.0, jitter * 3.0)
                    if rng.random() < (0.010 * anomaly_factor):
                        lat += 0.0022
                        lon += 0.0015

                process_gps(GPSPayload({"vehicle_id": vehicle["vehicle_id"], "lat": lat, "lon": lon, "timestamp": datetime.now(timezone.utc).isoformat(), "route_id": vehicle["route_id"]}))

            time.sleep(max(0.25, float(os.getenv("THARANI_INTERNAL_SIM_SLEEP_SECONDS", "0.5"))))

    Thread(target=worker, daemon=True, name="tharani-internal-simulator").start()


route_definitions = {
    "route_1": build_route(
        "route_1", "Route 1", "#0f9d58", (10.7350, 78.6000), (10.7480, 78.6400),
        path_points=[
            [10.7350, 78.6000], [10.7390, 78.6070], [10.7420, 78.6160], [10.7460, 78.6240],
            [10.7470, 78.6330], [10.7480, 78.6400], [10.7450, 78.6350], [10.7410, 78.6260],
            [10.7380, 78.6170], [10.7360, 78.6080], [10.7350, 78.6000],
        ],
        district_name="Tiruchirappalli",
    ),
    "route_2": build_route(
        "route_2", "Route 2", "#4285f4", (10.7720, 78.7200), (10.8110, 78.7140),
        path_points=[
            [10.7720, 78.7200], [10.7790, 78.7210], [10.7870, 78.7190], [10.7950, 78.7180],
            [10.8040, 78.7160], [10.8110, 78.7140], [10.8050, 78.7120], [10.7970, 78.7130],
            [10.7890, 78.7150], [10.7800, 78.7170], [10.7720, 78.7200],
        ],
        district_name="Tiruchirappalli",
    ),
    "route_3": build_route(
        "route_3", "Route 3", "#f4b400", (10.8360, 78.6600), (10.8210, 78.6120),
        path_points=[
            [10.8360, 78.6600], [10.8340, 78.6500], [10.8320, 78.6400], [10.8290, 78.6310],
            [10.8260, 78.6210], [10.8210, 78.6120], [10.8240, 78.6180], [10.8270, 78.6280],
            [10.8300, 78.6380], [10.8330, 78.6490], [10.8360, 78.6600],
        ],
        district_name="Salem",
    ),
    "route_4": build_route(
        "route_4", "Route 4", "#00acc1", (10.8700, 78.7600), (10.8410, 78.8000),
        path_points=[
            [10.8700, 78.7600], [10.8660, 78.7680], [10.8620, 78.7760], [10.8570, 78.7840],
            [10.8500, 78.7920], [10.8410, 78.8000], [10.8470, 78.7930], [10.8540, 78.7850],
            [10.8600, 78.7770], [10.8650, 78.7690], [10.8700, 78.7600],
        ],
        district_name="Villupuram",
    ),
    "route_5": build_route(
        "route_5", "Route 5", "#db4437", (10.7900, 78.8400), (10.7600, 78.7900),
        path_points=[
            [10.7900, 78.8400], [10.7840, 78.8320], [10.7780, 78.8240], [10.7730, 78.8150],
            [10.7670, 78.8040], [10.7600, 78.7900], [10.7650, 78.7980], [10.7710, 78.8080],
            [10.7770, 78.8180], [10.7830, 78.8290], [10.7900, 78.8400],
        ],
        district_name="Madurai",
    ),
}

route_definitions = generate_tamilnadu_routes(route_definitions, DEFAULT_ROUTE_COUNT)

zone_definitions = {}
for route in route_definitions.values():
    zone_definitions[route["mine_zone"]["id"]] = route["mine_zone"]
    zone_definitions[route["dump_zone"]["id"]] = route["dump_zone"]

zone_polygons = {
    zone_id: Polygon([(lon, lat) for lat, lon in zone_info["polygon"]])
    for zone_id, zone_info in zone_definitions.items()
}

route_lines = {
    route_id: LineString([(lon, lat) for lat, lon in route_info["path"]])
    for route_id, route_info in route_definitions.items()
}

route_zone_ids = {
    route_id: [route["mine_zone"]["id"], route["dump_zone"]["id"]]
    for route_id, route in route_definitions.items()
}

GPS_STALE_SECONDS = 7
SPOOF_SPEED_KMH = 180.0
CONVOY_DISTANCE_METERS = 85.0
CONVOY_HEADING_DELTA_DEG = 18.0
BASE_DEVIATION_THRESHOLD_METERS = 180.0
MAX_ALERTS = 300
MAX_HEATMAP_POINTS = 900

WEATHER_PROFILES = {
    "clear": {"gps_penalty": 0.00, "camera_penalty": 0.00},
    "rain": {"gps_penalty": 0.08, "camera_penalty": 0.12},
    "dust": {"gps_penalty": 0.12, "camera_penalty": 0.16},
    "storm": {"gps_penalty": 0.18, "camera_penalty": 0.24},
}

SCENARIO_PRESETS = {
    "calm_day": {
        "scenario": "calm_day",
        "weather": "clear",
        "gps_noise": 0.04,
        "camera_noise": 0.05,
        "anomaly_factor": 0.60,
        "traffic_factor": 0.90,
    },
    "suspicious_day": {
        "scenario": "suspicious_day",
        "weather": "rain",
        "gps_noise": 0.10,
        "camera_noise": 0.12,
        "anomaly_factor": 1.00,
        "traffic_factor": 1.00,
    },
    "raid_day": {
        "scenario": "raid_day",
        "weather": "dust",
        "gps_noise": 0.18,
        "camera_noise": 0.20,
        "anomaly_factor": 1.45,
        "traffic_factor": 1.20,
    },
}

CONTROL_STATE = {
    **SCENARIO_PRESETS["suspicious_day"],
    "shift_mode": "auto",
}

PROFILE_CONFIG = {
    "safe": {
        "risk_multiplier": 0.70,
        "prediction_bias": -0.60,
        "decay_multiplier": 1.35,
        "deviation_threshold": 230.0,
        "permit_adjust": 2,
        "risk_cap": 72.0,
    },
    "normal": {
        "risk_multiplier": 1.00,
        "prediction_bias": 0.0,
        "decay_multiplier": 1.00,
        "deviation_threshold": BASE_DEVIATION_THRESHOLD_METERS,
        "permit_adjust": 0,
        "risk_cap": 88.0,
    },
    "high_risk": {
        "risk_multiplier": 1.25,
        "prediction_bias": 0.45,
        "decay_multiplier": 0.75,
        "deviation_threshold": 150.0,
        "permit_adjust": -2,
        "risk_cap": 100.0,
    },
}

VEHICLE_PROFILES, vehicle_permits = build_vehicle_profiles_and_permits(DEFAULT_FLEET_SIZE)

BASE_PERMIT = {
    "allowed_24h_trips": 18,
    "rolling_window_hours": 24,
    "start_hour": 0,
    "end_hour": 24,
}


gps_store = {}
vehicle_state = {}
alerts = []
violation_heatmap = []
camera_events = []
INTERNAL_SIMULATOR_STARTED = False


def get_shift_bucket(now: Optional[datetime] = None) -> str:
    clock = now or utc_now()
    hour = clock.hour
    if 6 <= hour <= 10:
        return "morning_peak"
    if 11 <= hour <= 15:
        return "noon_low"
    if 16 <= hour <= 20:
        return "evening_peak"
    return "night_low"


def get_active_shift() -> str:
    if CONTROL_STATE.get("shift_mode", "auto") == "auto":
        return get_shift_bucket(utc_now())
    return CONTROL_STATE.get("shift_mode", "noon_low")


def get_confidence(vehicle_profile: str, signal: str, state: Optional[dict] = None) -> float:
    weather = CONTROL_STATE.get("weather", "clear")
    weather_cfg = WEATHER_PROFILES.get(weather, WEATHER_PROFILES["clear"])
    base = 0.94 if signal == "gps" else 0.90
    penalty = weather_cfg["gps_penalty"] if signal == "gps" else weather_cfg["camera_penalty"]
    penalty += CONTROL_STATE.get("gps_noise", 0.0) if signal == "gps" else CONTROL_STATE.get("camera_noise", 0.0)

    if vehicle_profile == "high_risk":
        penalty += 0.03

    if state and signal == "gps":
        if state.get("stale_alerted"):
            penalty += 0.18
        if state.get("recent_speed_kmh", 0.0) > 120:
            penalty += 0.12

    return clamp(base - penalty, 0.20, 0.99)


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def init_db() -> None:
    with DB_LOCK:
        conn = get_db_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS gps_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                route_id TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                zone_type TEXT,
                zone_name TEXT,
                risk REAL,
                prediction_label TEXT,
                prediction_probability REAL,
                predicted_weight REAL,
                overload_flag INTEGER
            );

            CREATE TABLE IF NOT EXISTS vehicle_snapshots (
                vehicle_id TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                route_id TEXT,
                route_name TEXT,
                zone_type TEXT,
                zone_name TEXT,
                trips_total INTEGER,
                trips_24h INTEGER,
                risk REAL,
                risk_level TEXT,
                prediction_label TEXT,
                prediction_probability REAL,
                predicted_weight REAL,
                average_weight REAL,
                overload_flag INTEGER,
                weight_history_json TEXT,
                weight_prediction_json TEXT,
                profile TEXT,
                last_event TEXT
            );

            CREATE TABLE IF NOT EXISTS violations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                points REAL NOT NULL,
                severity TEXT,
                lat REAL,
                lon REAL,
                risk_after REAL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_time TEXT NOT NULL,
                vehicle_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                meta_json TEXT
            );

            CREATE TABLE IF NOT EXISTS camera_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_time TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                route_id TEXT,
                lat REAL,
                lon REAL,
                truck_count INTEGER,
                nearby_active INTEGER,
                mismatch INTEGER
            );

            CREATE TABLE IF NOT EXISTS vehicle_config (
                vehicle_id TEXT PRIMARY KEY,
                profile TEXT NOT NULL,
                allowed_24h_trips INTEGER NOT NULL,
                rolling_window_hours INTEGER NOT NULL,
                start_hour INTEGER NOT NULL,
                end_hour INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS system_config (
                config_key TEXT PRIMARY KEY,
                config_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS permits (
                permit_id TEXT PRIMARY KEY,
                vehicle_number TEXT UNIQUE,
                approved_route TEXT,
                max_quantity REAL,
                used_quantity REAL,
                max_trips INTEGER,
                completed_trips INTEGER,
                valid_from TEXT,
                valid_to TEXT,
                status TEXT
            );

            CREATE TABLE IF NOT EXISTS trip_records (
                trip_id TEXT PRIMARY KEY,
                vehicle_id TEXT NOT NULL,
                permit_id TEXT,
                predicted_load REAL NOT NULL,
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id TEXT NOT NULL,
                gps_event_id INTEGER,
                timestamp TEXT NOT NULL,
                trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rag_documents (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                source TEXT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rag_chunks (
                id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding_json TEXT,
                FOREIGN KEY(doc_id) REFERENCES rag_documents(id)
            );
            """
        )
        conn.commit()
        conn.close()

    ensure_column("gps_events", "predicted_weight", "REAL")
    ensure_column("gps_events", "overload_flag", "INTEGER")
    ensure_column("vehicle_snapshots", "predicted_weight", "REAL")
    ensure_column("vehicle_snapshots", "average_weight", "REAL")
    ensure_column("vehicle_snapshots", "overload_flag", "INTEGER")
    ensure_column("vehicle_snapshots", "weight_history_json", "TEXT")
    ensure_column("vehicle_snapshots", "weight_prediction_json", "TEXT")


def db_execute(sql: str, params: tuple = ()) -> None:
    with DB_LOCK:
        conn = get_db_connection()
        conn.execute(sql, params)
        conn.commit()
        conn.close()


def db_execute_insert(sql: str, params: tuple = ()) -> int:
    with DB_LOCK:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        last_id = cursor.lastrowid
        conn.close()
        return last_id


def db_query(sql: str, params: tuple = ()) -> list[dict]:
    with DB_LOCK:
        conn = get_db_connection()
        rows = conn.execute(sql, params).fetchall()
        conn.close()
    return [dict(row) for row in rows]


def classify_risk(value: float) -> str:
    if value >= 80:
        return "DANGEROUS"
    if value >= 50:
        return "SUSPICIOUS"
    return "SAFE"


def init_permits() -> None:
    existing = {
        row["vehicle_number"]: row
        for row in db_query("SELECT * FROM permits")
    }

    route_ids = sorted(route_definitions.keys())
    if not route_ids:
        return

    for idx in range(1, DEFAULT_FLEET_SIZE + 1):
        vehicle_id = f"truck_{idx}"
        if vehicle_id not in existing:
            permit_id = f"PRM-TN2026-TRK-{idx:04d}"
            approved_route = route_ids[(idx - 1) % len(route_ids)]
            max_quantity = float(300.0 + (idx % 6) * 100.0)
            used_quantity = 0.0
            max_trips = int(12 + (idx % 8) * 3)
            completed_trips = 0
            status = "active"
            valid_from = "2026-01-01"
            valid_to = "2026-12-31"

            # Setup violation scenarios to test compliance
            if idx % 20 == 3:
                valid_from = "2026-05-01"
                valid_to = "2026-06-05" # Expired (Relative to June 7, 2026)
            elif idx % 20 == 7:
                status = "inactive"
            elif idx % 20 == 11:
                approved_route = route_ids[(idx) % len(route_ids)] # Mismatched route
            elif idx % 20 == 15:
                max_trips = 2
                completed_trips = 3
                max_quantity = 50.0
                used_quantity = 65.0 # Exceeded trips/quantity

            db_execute(
                """
                INSERT OR IGNORE INTO permits (
                    permit_id, vehicle_number, approved_route, max_quantity, used_quantity,
                    max_trips, completed_trips, valid_from, valid_to, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    permit_id,
                    vehicle_id,
                    approved_route,
                    max_quantity,
                    used_quantity,
                    max_trips,
                    completed_trips,
                    valid_from,
                    valid_to,
                    status
                )
            )


def init_runtime_config() -> None:
    existing = {
        row["vehicle_id"]: row
        for row in db_query("SELECT * FROM vehicle_config")
    }

    for idx in range(1, DEFAULT_FLEET_SIZE + 1):
        vehicle_id = f"truck_{idx}"
        if vehicle_id not in existing:
            base = vehicle_permits.get(vehicle_id, BASE_PERMIT)
            profile = VEHICLE_PROFILES.get(vehicle_id, "normal")
            db_execute(
                "INSERT INTO vehicle_config(vehicle_id, profile, allowed_24h_trips, rolling_window_hours, start_hour, end_hour, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    vehicle_id,
                    profile,
                    int(base["allowed_24h_trips"]),
                    int(base["rolling_window_hours"]),
                    int(base["start_hour"]),
                    int(base["end_hour"]),
                    utc_now().isoformat(),
                ),
            )

    configs = db_query("SELECT * FROM vehicle_config")
    for row in configs:
        VEHICLE_PROFILES[row["vehicle_id"]] = row["profile"]
        vehicle_permits[row["vehicle_id"]] = {
            "allowed_24h_trips": int(row["allowed_24h_trips"]),
            "rolling_window_hours": int(row["rolling_window_hours"]),
            "start_hour": int(row["start_hour"]),
            "end_hour": int(row["end_hour"]),
        }

    init_permits()


def save_control_state() -> None:
    db_execute(
        """
        INSERT INTO system_config(config_key, config_value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(config_key) DO UPDATE SET
            config_value=excluded.config_value,
            updated_at=excluded.updated_at
        """,
        ("global_control", json.dumps(CONTROL_STATE), utc_now().isoformat()),
    )


def init_system_config() -> None:
    rows = db_query("SELECT config_value FROM system_config WHERE config_key=?", ("global_control",))
    if rows:
        try:
            loaded = json.loads(rows[0]["config_value"])
            for key, value in loaded.items():
                CONTROL_STATE[key] = value
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
    else:
        save_control_state()


def get_permit(vehicle_id: str, profile: str) -> dict:
    permit = dict(vehicle_permits.get(vehicle_id, BASE_PERMIT))
    permit["allowed_24h_trips"] = max(1, permit["allowed_24h_trips"] + PROFILE_CONFIG[profile]["permit_adjust"])
    return permit


def compute_classifier_shap(state: dict, now: datetime) -> dict:
    if CLASSIFIER_MODEL is None or shap is None:
        speed = float(state.get("recent_speed_kmh", 0.0))
        trip_count = float(state.get("trips", 0))
        route_deviation = float(1 if state.get("route_deviation_flag") else 0)
        gps_signal_loss = float(1 if (state.get("gps_confidence", 0.9) < 0.45 or state.get("stale_alerted")) else 0)
        time_of_day = float(now.hour)
        day_of_week = float(now.weekday())
        risk_score = float(state.get("risk", 0.0))
        
        contributions = [
            {"feature": "speed", "impact": round(0.01 * speed if speed > 60 else 0.0, 3)},
            {"feature": "trip_count", "impact": round(0.02 * trip_count if trip_count > 5 else 0.0, 3)},
            {"feature": "route_deviation", "impact": round(0.4 if route_deviation else 0.0, 3)},
            {"feature": "gps_signal_loss", "impact": round(0.3 if gps_signal_loss else 0.0, 3)},
            {"feature": "time_of_day", "impact": round(0.1 if (time_of_day < 6 or time_of_day > 20) else -0.05, 3)},
            {"feature": "day_of_week", "impact": round(0.0, 3)},
            {"feature": "risk_score", "impact": round(0.005 * risk_score, 3)}
        ]
        contributions.sort(key=lambda x: abs(x["impact"]), reverse=True)
        return {"method": "fallback", "items": contributions}
        
    try:
        speed = float(state.get("recent_speed_kmh", 0.0))
        trip_count = float(state.get("trips", 0))
        route_deviation = float(1 if state.get("route_deviation_flag") else 0)
        gps_signal_loss = float(1 if (state.get("gps_confidence", 0.9) < 0.45 or state.get("stale_alerted")) else 0)
        time_of_day = float(now.hour)
        day_of_week = float(now.weekday())
        risk_score = float(state.get("risk", 0.0))
        
        row_df = pd.DataFrame([{
            "speed": speed,
            "trip_count": trip_count,
            "route_deviation": route_deviation,
            "gps_signal_loss": gps_signal_loss,
            "time_of_day": time_of_day,
            "day_of_week": day_of_week,
            "risk_score": risk_score
        }])
        explainer = shap.TreeExplainer(CLASSIFIER_MODEL)
        shap_values = explainer.shap_values(row_df)
        
        if isinstance(shap_values, list):
            values = shap_values[1][0]
        else:
            if len(shap_values.shape) == 3:
                values = shap_values[0, :, 1]
            elif len(shap_values.shape) == 2:
                if shap_values.shape[1] == 7:
                    values = shap_values[0]
                else:
                    values = shap_values[0]
            else:
                values = shap_values[0]
                
        feature_names = ['speed', 'trip_count', 'route_deviation', 'gps_signal_loss', 'time_of_day', 'day_of_week', 'risk_score']
        contributions = [{"feature": name, "impact": round(float(val), 4)} for name, val in zip(feature_names, values)]
        contributions.sort(key=lambda x: abs(x["impact"]), reverse=True)
        return {"method": "shap", "items": contributions}
    except Exception as e:
        return {"method": "error", "error": str(e), "items": []}


def compute_regressor_shap(features: dict) -> dict:
    if WEIGHT_MODEL is None or shap is None:
        return compute_shap_like_explanation(features, 0.0)
    try:
        row_df = pd.DataFrame([{name: float(features[name]) for name in WEIGHT_FEATURE_ORDER}])
        explainer = shap.TreeExplainer(WEIGHT_MODEL)
        shap_values = explainer.shap_values(row_df)
        values = shap_values[0] if hasattr(shap_values, "shape") and len(shap_values.shape) == 2 else shap_values
        if len(values.shape) > 1:
            values = values[0]
        ranked = sorted(zip(WEIGHT_FEATURE_ORDER, values), key=lambda x: abs(float(x[1])), reverse=True)
        return {"method": "shap", "items": [{"feature": f, "impact": round(float(v), 3)} for f, v in ranked]}
    except Exception as e:
        return {"method": "error", "error": str(e), "items": []}


def explain_vehicle_risk(vehicle_id: str) -> dict:
    state = vehicle_state.get(vehicle_id)
    if not state:
        return {
            "vehicle_id": vehicle_id,
            "risk": 0.0,
            "risk_level": "SAFE",
            "prediction": {"label": "LOW", "probability": 0.0, "reason": "no data"},
            "weight_prediction": {"predicted_weight": 0.0, "average_weight": 0.0, "confidence": 0.0, "source": "pending", "limit": WEIGHT_LIMIT_TONS, "overload_flag": False, "is_locked": False, "features": {}},
            "risk_reasons": [],
            "safe_reasons": ["No telemetry received yet"],
            "how_heatmap_works": "Heatmap points represent where violations occurred. Brighter zones mean repeated violations or higher risk weight.",
        }

    risk_reasons = []
    for event in reversed(state.get("history", [])[-8:]):
        risk_reasons.append(
            {
                "time": event.get("time"),
                "reason": event.get("reason"),
                "points": event.get("points"),
                "severity": event.get("severity", "warning"),
            }
        )

    safe_reasons = []
    if state.get("recent_speed_kmh", 0.0) < 80:
        safe_reasons.append("Speed pattern is within expected limits")
    if not state.get("stale_alerted"):
        safe_reasons.append("GPS telemetry is active")
    if state.get("trips_24h", 0) <= get_permit(vehicle_id, state.get("profile", "normal"))["allowed_24h_trips"]:
        safe_reasons.append("Trip count remains within 24h permit")
    if len(risk_reasons) <= 2:
        safe_reasons.append("Low recent violation frequency")
    if not safe_reasons:
        safe_reasons.append("No strong safe signal currently")

    now = utc_now()
    clf_shap = compute_classifier_shap(state, now)
    weight_feats = state.get("weight_prediction", {}).get("features", {})
    reg_shap = compute_regressor_shap(weight_feats) if weight_feats else {"method": "no_features", "items": []}

    return {
        "vehicle_id": vehicle_id,
        "risk": round(float(state.get("risk", 0.0)), 2),
        "risk_level": classify_risk(float(state.get("risk", 0.0))),
        "prediction": state.get("prediction", {"label": "LOW", "probability": 0.0, "reason": "n/a"}),
        "weight_prediction": state.get("weight_prediction", {"predicted_weight": 0.0, "average_weight": 0.0, "confidence": 0.0, "source": "pending", "limit": WEIGHT_LIMIT_TONS, "overload_flag": False, "is_locked": False, "features": {}}),
        "environment": {
            "scenario": CONTROL_STATE.get("scenario"),
            "weather": CONTROL_STATE.get("weather"),
            "active_shift": get_active_shift(),
            "gps_confidence": round(float(state.get("gps_confidence", 0.9)), 3),
        },
        "risk_reasons": risk_reasons,
        "safe_reasons": safe_reasons,
        "how_heatmap_works": "Heatmap intensity uses violation weight: repeated and severe violations at the same area produce hotter colors.",
        "explain": {
            "risk_contributions": clf_shap,
            "weight_contributions": reg_shap
        }
    }


def get_zone(lat: float, lon: float, route_id: Optional[str] = None):
    point = Point(lon, lat)
    if route_id and route_id in route_zone_ids:
        candidate_zone_ids = route_zone_ids[route_id]
    else:
        candidate_zone_ids = zone_definitions.keys()

    for zone_id in candidate_zone_ids:
        zone_info = zone_definitions[zone_id]
        if zone_polygons[zone_id].contains(point):
            return zone_info
    return None


def ensure_vehicle_state(vehicle_id: str, route_id=None, route_name=None):
    with STATE_LOCK:
        if vehicle_id not in vehicle_state:
            profile = VEHICLE_PROFILES.get(vehicle_id, "normal")
            vehicle_state[vehicle_id] = {
                "stage": "to_dump",
                "trips": 0,
                "trip_timestamps": [],
                "trips_24h": 0,
                "route_id": route_id,
                "route_name": route_name,
                "profile": profile,
                "last_zone": "outside",
                "last_event": "Waiting for route",
                "risk": 0.0,
                "history": [],
                "risk_timeline": [{"ts": utc_now().isoformat(), "risk": 0.0, "reason": "init"}],
                "prediction": {"probability": 0.0, "label": "LOW", "reason": "insufficient data"},
                "last_risk_decay_at": None,
                "last_update": None,
                "last_lat": None,
                "last_lon": None,
                "stale_alerted": False,
                "recent_speed_kmh": 0.0,
                "heading": None,
                "cooldowns": {},
                "convoy_hits": 0,
                "trip_started_at": None,
                "trip_distance_m": 0.0,
                "speed_samples": [],
                "speed_deltas": [],
                "stops_count": 0,
                "max_speed": 0.0,
                "predicted_weight": None,
                "average_weight": 0.0,
                "weight_history": [],
                "weight_prediction": {"predicted_weight": 0.0, "average_weight": 0.0, "confidence": 0.0, "source": "pending", "limit": WEIGHT_LIMIT_TONS, "overload_flag": False, "is_locked": False, "features": {}},
                "weight_locked_for_trip": False,
                "weight_locked_at": None,
                "last_weight_lock_key": None,
                "overload_flag": False,
                "overload_alerted": False,
            }

        state = vehicle_state[vehicle_id]
        if route_id is not None:
            state["route_id"] = route_id
        if route_name is not None:
            state["route_name"] = route_name
        return state


def reason_throttled(state: dict, reason: str, now: datetime, seconds: int = 20) -> bool:
    previous = state["cooldowns"].get(reason)
    if previous:
        prev_dt = to_aware(datetime.fromisoformat(previous))
        if (now - prev_dt).total_seconds() < seconds:
            return True
    state["cooldowns"][reason] = now.isoformat()
    return False


def append_alert(vehicle_id: str, message: str, severity: str = "warning", meta: Optional[dict] = None):
    entry = {
        "vehicle_id": vehicle_id,
        "message": message,
        "severity": severity,
        "time": utc_now().isoformat(),
        "meta": meta or {},
    }
    alerts.append(entry)
    if len(alerts) > MAX_ALERTS:
        del alerts[:-MAX_ALERTS]

    db_execute(
        "INSERT INTO alerts(alert_time, vehicle_id, severity, message, meta_json) VALUES (?, ?, ?, ?, ?)",
        (entry["time"], vehicle_id, severity, message, json.dumps(entry["meta"])),
    )


def append_heatmap_point(vehicle_id: str, lat: float, lon: float, reason: str, weight: float):
    violation_heatmap.append(
        {
            "vehicle_id": vehicle_id,
            "lat": lat,
            "lon": lon,
            "reason": reason,
            "weight": weight,
            "time": utc_now().isoformat(),
        }
    )
    if len(violation_heatmap) > MAX_HEATMAP_POINTS:
        del violation_heatmap[:-MAX_HEATMAP_POINTS]


def refresh_trip_window(state: dict, now: datetime):
    cutoff = now - timedelta(hours=24)
    kept = []
    for raw in state.get("trip_timestamps", []):
        try:
            ts = to_aware(datetime.fromisoformat(raw))
        except ValueError:
            continue
        if ts >= cutoff:
            kept.append(ts.isoformat())
    state["trip_timestamps"] = kept
    state["trips_24h"] = len(kept)


def push_risk_timeline(state: dict, reason: str):
    state["risk_timeline"].append({"ts": utc_now().isoformat(), "risk": round(state["risk"], 2), "reason": reason})
    if len(state["risk_timeline"]) > 160:
        state["risk_timeline"] = state["risk_timeline"][-160:]


def update_risk(vehicle_id: str, reason: str, points: float, severity: str = "warning", lat: Optional[float] = None, lon: Optional[float] = None):
    state = ensure_vehicle_state(vehicle_id)
    profile_cfg = PROFILE_CONFIG[state["profile"]]
    scaled_points = float(points) * profile_cfg["risk_multiplier"]
    hard_cap = float(profile_cfg.get("risk_cap", 100.0))
    if severity == "critical":
        hard_cap = min(100.0, hard_cap + 8.0)
    state["risk"] = clamp(state["risk"] + scaled_points, 0.0, hard_cap)
    now = utc_now()

    violation = {
        "reason": reason,
        "points": round(scaled_points, 2),
        "severity": severity,
        "time": now.isoformat(),
    }
    if lat is not None and lon is not None:
        violation["lat"] = lat
        violation["lon"] = lon
        append_heatmap_point(vehicle_id, lat, lon, reason, weight=max(1.0, scaled_points / 10.0))

    state["history"].append(violation)
    if len(state["history"]) > 280:
        state["history"] = state["history"][-280:]

    push_risk_timeline(state, reason)
    append_alert(vehicle_id, f"{reason} (+{int(scaled_points)} risk)", severity=severity)

    db_execute(
        "INSERT INTO violations(event_time, vehicle_id, reason, points, severity, lat, lon, risk_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            violation["time"],
            vehicle_id,
            reason,
            float(scaled_points),
            severity,
            lat,
            lon,
            float(state["risk"]),
        ),
    )


def apply_smart_decay(state: dict, now: datetime):
    last_decay_raw = state.get("last_risk_decay_at")
    if not last_decay_raw:
        state["last_risk_decay_at"] = now.isoformat()
        return

    last_decay = to_aware(datetime.fromisoformat(last_decay_raw))
    elapsed = (now - last_decay).total_seconds()
    if elapsed < 12:
        return

    recent_violations = 0
    window = now - timedelta(minutes=30)
    for event in reversed(state["history"]):
        event_time = to_aware(datetime.fromisoformat(event["time"]))
        if event_time < window:
            break
        recent_violations += 1

    base = 1.2 if recent_violations == 0 else 0.45
    decay_multiplier = PROFILE_CONFIG[state["profile"]]["decay_multiplier"]
    decay = base * decay_multiplier * (elapsed / 60.0)
    old = state["risk"]
    state["risk"] = clamp(state["risk"] - decay, 0.0, 100.0)
    if int(old) != int(state["risk"]):
        push_risk_timeline(state, "smart_decay")

    state["last_risk_decay_at"] = now.isoformat()


def compute_prediction(state: dict):
    now = utc_now()
    
    # Check cache first
    cached = state.get("prediction")
    last_pred_time_str = state.get("last_pred_time")
    if last_pred_time_str:
        try:
            last_pred_time = to_aware(datetime.fromisoformat(last_pred_time_str))
            time_elapsed = (now - last_pred_time).total_seconds()
        except Exception:
            time_elapsed = 999.0
    else:
        time_elapsed = 999.0

    if cached:
        if (state.get("last_pred_update") == state.get("last_update") and 
            state.get("last_pred_risk") == state.get("risk") and 
            state.get("last_pred_stale") == state.get("stale_alerted")):
            return cached
        if time_elapsed < 10.0:
            return cached

    risk = state["risk"]
    recent_critical = 0
    recent_warning = 0
    window = now - timedelta(minutes=10)

    for event in reversed(state["history"]):
        event_time = to_aware(datetime.fromisoformat(event["time"]))
        if event_time < window:
            break
        if event.get("severity") == "critical":
            recent_critical += 1
        else:
            recent_warning += 1

    trend_component = 0.0
    delta = 0.0
    timeline = state["risk_timeline"]
    if len(timeline) >= 2:
        latest = timeline[-1]["risk"]
        prior = timeline[max(0, len(timeline) - 6)]["risk"]
        delta = float(latest - prior)
        trend_component = clamp(delta / 40.0, -0.4, 0.8)

    speed_flag = 1.0 if state.get("recent_speed_kmh", 0.0) > 120 else 0.0
    stale_flag = 1.0 if state.get("stale_alerted") else 0.0
    bias = PROFILE_CONFIG[state["profile"]]["prediction_bias"]
    anomaly_factor = float(CONTROL_STATE.get("anomaly_factor", 1.0))
    gps_confidence = float(state.get("gps_confidence", 0.9))

    linear = (
        -2.25
        + bias
        + ((anomaly_factor - 1.0) * 0.70)
        + (0.030 * risk)
        + (0.75 * recent_critical)
        + (0.30 * recent_warning)
        + (0.50 * speed_flag)
        + (0.40 * stale_flag)
        + (0.45 * trend_component)
        + ((0.9 - gps_confidence) * 0.35)
    )
    probability = 1.0 / (1.0 + exp(-linear))

    # Fuse with the loaded RandomForest Classifier model prediction.
    # Fusing the RandomForest Classifier model prediction with the heuristic formula is a robust engineering decision
    # because the classifier is trained on synthetic statistical distributions (which might be clean/idealized),
    # whereas the heuristic linear formula integrates real-time control state modifiers (like anomaly_factor, bias profiles, and delta trends)
    # that adapt dynamically to simulator changes. Fusing them 60/40 preserves the ML model's pattern recognition while keeping the responsive real-time control logic of the heuristic.
    if CLASSIFIER_MODEL is not None:
        try:
            speed = float(state.get("recent_speed_kmh", 0.0))
            trip_count = float(state.get("trips", 0))
            route_deviation = float(1 if state.get("route_deviation_flag") else 0)
            gps_signal_loss = float(1 if (state.get("gps_confidence", 0.9) < 0.45 or state.get("stale_alerted")) else 0)
            time_of_day = float(now.hour)
            day_of_week = float(now.weekday())
            risk_score = float(risk)
            
            row_df = pd.DataFrame([{
                "speed": speed,
                "trip_count": trip_count,
                "route_deviation": route_deviation,
                "gps_signal_loss": gps_signal_loss,
                "time_of_day": time_of_day,
                "day_of_week": day_of_week,
                "risk_score": risk_score
            }])
            rf_prob = float(CLASSIFIER_MODEL.predict_proba(row_df)[0][1])
            probability = 0.6 * rf_prob + 0.4 * probability
        except Exception:
            pass

    label = "LOW"
    if probability >= 0.78:
        label = "HIGH"
    elif probability >= 0.48:
        label = "MEDIUM"

    reason = "stable"
    if recent_critical >= 1:
        reason = "critical anomaly observed"
    elif recent_warning >= 3:
        reason = "frequent warning events"
    elif delta > 8:
        reason = "risk rising quickly"
    elif risk >= 70:
        reason = "high current risk"

    state["prediction"] = {
        "probability": round(float(probability), 3),
        "label": label,
        "reason": reason,
        "gps_confidence": round(gps_confidence, 3),
    }
    state["last_pred_time"] = now.isoformat()
    state["last_pred_update"] = state.get("last_update")
    state["last_pred_risk"] = state.get("risk")
    state["last_pred_stale"] = state.get("stale_alerted")
    return state["prediction"]


FORBIDDEN_MINING_ZONES = {
    "forbidden_zone_1": {
        "name": "Cauvery River Protected Basin (Illegal Mining Zone A)",
        "polygon": Polygon([
            (78.50, 10.85),
            (78.55, 10.85),
            (78.55, 10.90),
            (78.50, 10.90)
        ])
    },
    "forbidden_zone_2": {
        "name": "Pachaimalai Forest Reserve (Illegal Mining Zone B)",
        "polygon": Polygon([
            (78.65, 11.10),
            (78.75, 11.10),
            (78.75, 11.20),
            (78.65, 11.20)
        ])
    }
}


def check_geofence(vehicle_id: str, route_id: str, lat: float, lon: float, state: dict, now: datetime):
    truck_point = Point(lon, lat)

    # 1. Check if vehicle is inside forbidden zones
    for f_id, f_zone in FORBIDDEN_MINING_ZONES.items():
        if f_zone["polygon"].contains(truck_point):
            if not reason_throttled(state, f"forbidden_zone_{f_id}", now, 120):
                update_risk(vehicle_id, f"Entry into unauthorized zone: {f_zone['name']}", 25, severity="critical", lat=lat, lon=lon)
                state["last_event"] = "Unauthorized zone entry!"
                append_alert(vehicle_id, f"Geofence breach: entered {f_zone['name']}", severity="critical", meta={"lat": lat, "lon": lon, "zone_name": f_zone['name']})
                return True

    # 2. Check if vehicle entered a mine zone that does not match its approved route's mine zone
    current_zone = get_zone(lat, lon, route_id)
    if current_zone and current_zone.get("type") == "mine":
        permit_rows = state.get("permit_cache")
        last_permit_fetch_str = state.get("last_permit_fetch")
        if last_permit_fetch_str:
            try:
                time_elapsed = (now - to_aware(datetime.fromisoformat(last_permit_fetch_str))).total_seconds()
            except Exception:
                time_elapsed = 999.0
        else:
            time_elapsed = 999.0

        if permit_rows is None or time_elapsed >= 15.0:
            permit_rows = db_query("SELECT * FROM permits WHERE vehicle_number = ?", (vehicle_id,))
            state["permit_cache"] = permit_rows
            state["last_permit_fetch"] = now.isoformat()

        if permit_rows:
            approved_route = permit_rows[0]["approved_route"]
            approved_mine_zone_id = f"{approved_route}_mine"
            if current_zone["id"] != approved_mine_zone_id:
                if not reason_throttled(state, "unauthorized_mine_entry", now, 120):
                    update_risk(vehicle_id, f"Entered unauthorized mine zone ({current_zone['name']})", 20, severity="critical", lat=lat, lon=lon)
                    state["last_event"] = "Unauthorized mine zone entry"
                    append_alert(vehicle_id, f"Geofence breach: entered unauthorized mine zone {current_zone['name']} (Permitted Route: {approved_route})", severity="critical")
                    return True
    return False


def check_route_deviation(vehicle_id: str, route_id: str, lat: float, lon: float, state: dict, now: datetime):
    state["route_deviation_flag"] = False
    if route_id not in route_lines:
        return
    # Ignore deviation checks while vehicle is in mine/dump zones; this prevents false positives near zone polygons.
    if state.get("current_zone") in ("mine", "dump"):
        return
    threshold = PROFILE_CONFIG[state["profile"]]["deviation_threshold"]
    point = Point(lon, lat)
    distance_deg = point.distance(route_lines[route_id])
    distance_m = distance_deg * 111139.0
    if distance_m > threshold:
        state["route_deviation_flag"] = True
        if not reason_throttled(state, "route_deviation", now, 26):
            update_risk(vehicle_id, "Route deviation detected", 13, lat=lat, lon=lon)
            state["last_event"] = "Deviation from legal route"


def check_spoof(vehicle_id: str, state: dict, lat: float, lon: float, event_time: datetime, now: datetime):
    if state.get("last_lat") is None or state.get("last_lon") is None or not state.get("last_update"):
        return

    prev_time = to_aware(datetime.fromisoformat(state["last_update"]))
    dt = (event_time - prev_time).total_seconds()
    if dt <= 0:
        return

    moved = haversine_meters(state["last_lat"], state["last_lon"], lat, lon)
    speed_kmh = (moved / dt) * 3.6
    state["recent_speed_kmh"] = round(speed_kmh, 2)
    state["heading"] = bearing_degrees(state["last_lat"], state["last_lon"], lat, lon)

    if speed_kmh > SPOOF_SPEED_KMH and not reason_throttled(state, "gps_spoof", now, 40):
        update_risk(vehicle_id, "GPS spoofing / impossible jump", 28, severity="critical", lat=lat, lon=lon)
        state["last_event"] = f"Impossible jump detected ({int(speed_kmh)} km/h)"


def check_convoy(vehicle_id: str, route_id: str, lat: float, lon: float, state: dict, now: datetime):
    if state.get("heading") is None:
        return

    if reason_throttled(state, "convoy_check_run", now, 10):
        return

    close = 0
    with STATE_LOCK:
        items = list(vehicle_state.items())
    for other_id, other in items:
        if other_id == vehicle_id:
            continue
        if other.get("route_id") != route_id:
            continue
        if other.get("last_lat") is None or other.get("last_lon") is None:
            continue
        if other.get("heading") is None or not other.get("last_update"):
            continue

        if (now - to_aware(datetime.fromisoformat(other["last_update"]))).total_seconds() > 8:
            continue

        dist = haversine_meters(lat, lon, other["last_lat"], other["last_lon"])
        if dist > CONVOY_DISTANCE_METERS:
            continue

        if angle_diff_deg(state["heading"], other["heading"]) <= CONVOY_HEADING_DELTA_DEG:
            close += 1

    if close >= 1:
        state["convoy_hits"] += 1
    else:
        state["convoy_hits"] = max(0, state["convoy_hits"] - 1)

    if state["convoy_hits"] >= 5 and not reason_throttled(state, "convoy", now, 55):
        update_risk(vehicle_id, "Convoy behavior detected", 10, lat=lat, lon=lon)
        state["last_event"] = "Possible convoy behavior"
        state["convoy_hits"] = 0


def check_permit(vehicle_id: str, state: dict, now: datetime):
    permit_rows = state.get("permit_cache")
    last_permit_fetch_str = state.get("last_permit_fetch")
    if last_permit_fetch_str:
        try:
            time_elapsed = (now - to_aware(datetime.fromisoformat(last_permit_fetch_str))).total_seconds()
        except Exception:
            time_elapsed = 999.0
    else:
        time_elapsed = 999.0

    if permit_rows is None or time_elapsed >= 15.0:
        permit_rows = db_query("SELECT * FROM permits WHERE vehicle_number = ?", (vehicle_id,))
        state["permit_cache"] = permit_rows
        state["last_permit_fetch"] = now.isoformat()
    if not permit_rows:
        if not reason_throttled(state, "no_permit", now, 180):
            update_risk(vehicle_id, "No valid mining permit found", 25, severity="critical")
            state["last_event"] = "Unregistered vehicle alert"
            append_alert(vehicle_id, "Compliance Violation: Vehicle is active without registered government permit!", severity="critical")
        return

    p = permit_rows[0]
    now_date = now.date().isoformat()

    # 1. Check status
    if p["status"] != "active":
        if not reason_throttled(state, "permit_inactive", now, 180):
            update_risk(vehicle_id, f"Inactive permit used (status: {p['status']})", 20, severity="critical")
            state["last_event"] = "Inactive permit violation"
            append_alert(vehicle_id, f"Compliance Violation: Inactive/Revoked permit {p['permit_id']} detected!", severity="critical")

    # 2. Check date validity
    if not (p["valid_from"] <= now_date <= p["valid_to"]):
        if not reason_throttled(state, "permit_expired", now, 180):
            update_risk(vehicle_id, "Permit is expired or not yet valid", 18, severity="critical")
            state["last_event"] = "Expired permit violation"
            append_alert(vehicle_id, f"Compliance Violation: Permit {p['permit_id']} is outside valid date range ({p['valid_from']} to {p['valid_to']})!", severity="critical")

    # 3. Check completed trips vs max trips
    if p["completed_trips"] > p["max_trips"]:
        if not reason_throttled(state, "permit_trips_exceeded", now, 180):
            update_risk(vehicle_id, "Permit trip limit exceeded", 15, severity="warning")
            state["last_event"] = "Trip limit exceeded"
            append_alert(vehicle_id, f"Compliance Violation: Permit {p['permit_id']} trip limit exceeded ({p['completed_trips']}/{p['max_trips']})", severity="warning")

    # 4. Check used quantity vs max quantity
    if p["used_quantity"] > p["max_quantity"]:
        if not reason_throttled(state, "permit_quantity_exceeded", now, 180):
            update_risk(vehicle_id, "Excavation limit exceeded", 22, severity="critical")
            state["last_event"] = "Excavation limit exceeded"
            append_alert(vehicle_id, f"Compliance Violation: Permit {p['permit_id']} quantity cap exceeded ({p['used_quantity']:.1f}/{p['max_quantity']:.1f} Tons)!", severity="critical")


LAST_BG_CHECK_RUN = 0.0


def run_background_checks(now: Optional[datetime] = None, force: bool = False):
    if not force:
        return

    global LAST_BG_CHECK_RUN
    curr_time = time.time()
    if curr_time - LAST_BG_CHECK_RUN < 4.0:
        return
    LAST_BG_CHECK_RUN = curr_time

    check_time = now or utc_now()
    with STATE_LOCK:
        items = list(vehicle_state.items())
    for vehicle_id, state in items:
        apply_smart_decay(state, check_time)

        last_update = state.get("last_update")
        if last_update:
            last_dt = to_aware(datetime.fromisoformat(last_update))
            stale = (check_time - last_dt).total_seconds()
            if stale > GPS_STALE_SECONDS:
                if not state.get("stale_alerted"):
                    update_risk(vehicle_id, "GPS OFF / no telemetry", 22, severity="critical")
                    state["stale_alerted"] = True
                    state["last_event"] = "GPS signal missing"
            else:
                state["stale_alerted"] = False

        prediction = compute_prediction(state)
        if prediction["label"] == "HIGH" and prediction["probability"] >= 0.88:
            if not reason_throttled(state, "prediction_high", check_time, 60):
                append_alert(
                    vehicle_id,
                    "Predicted high violation probability in next 10 minutes",
                    severity="warning",
                    meta=prediction,
                )


def persist_snapshot(vehicle_id: str, state: dict):
    weight_prediction = state.get("weight_prediction", {})
    db_execute(
        """
        INSERT INTO vehicle_snapshots(
            vehicle_id, updated_at, route_id, route_name, zone_type, zone_name,
            trips_total, trips_24h, risk, risk_level, prediction_label,
            prediction_probability, predicted_weight, average_weight, overload_flag,
            weight_history_json, weight_prediction_json, profile, last_event
        )
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vehicle_id) DO UPDATE SET
            updated_at=excluded.updated_at,
            route_id=excluded.route_id,
            route_name=excluded.route_name,
            zone_type=excluded.zone_type,
            zone_name=excluded.zone_name,
            trips_total=excluded.trips_total,
            trips_24h=excluded.trips_24h,
            risk=excluded.risk,
            risk_level=excluded.risk_level,
            prediction_label=excluded.prediction_label,
            prediction_probability=excluded.prediction_probability,
            predicted_weight=excluded.predicted_weight,
            average_weight=excluded.average_weight,
            overload_flag=excluded.overload_flag,
            weight_history_json=excluded.weight_history_json,
            weight_prediction_json=excluded.weight_prediction_json,
            profile=excluded.profile,
            last_event=excluded.last_event
        """,
        (
            vehicle_id,
            state.get("updated_at") or utc_now().isoformat(),
            state.get("route_id"),
            state.get("route_name"),
            state.get("current_zone"),
            state.get("current_zone_name"),
            int(state.get("trips", 0)),
            int(state.get("trips_24h", 0)),
            float(state.get("risk", 0.0)),
            classify_risk(float(state.get("risk", 0.0))),
            state.get("prediction", {}).get("label", "LOW"),
            float(state.get("prediction", {}).get("probability", 0.0)),
            float(state.get("predicted_weight", 0.0) or 0.0),
            float(state.get("average_weight", 0.0) or 0.0),
            1 if state.get("overload_flag") else 0,
            json.dumps(state.get("weight_history", [])[-20:]),
            json.dumps(weight_prediction),
            state.get("profile", "normal"),
            state.get("last_event", ""),
        ),
    )


class AgentOrchestrator:
    def __init__(self, vehicle_id: str, state: dict, data: GPSPayload, previous_record: Optional[dict], now: datetime):
        self.vehicle_id = vehicle_id
        self.state = state
        self.data = data
        self.previous_record = previous_record
        self.now = now
        self.trace = []
        self.decisions = {}

    def log_agent(self, agent: str, ran: bool, input_summary: str, output_summary: str, reason: str):
        self.trace.append({
            "agent": agent,
            "ran": ran,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "reason": reason
        })

    def run(self):
        # 1. Orchestrator Manager Node evaluates state and plans dynamic execution flow (conditional routing)
        self.orchestrate_flow()
        
        # Run nodes in order
        self.run_node("GeofenceAgent", self.node_geofence)
        self.run_node("RouteDeviationAgent", self.node_route_deviation)
        self.run_node("SpoofAgent", self.node_spoof)
        self.run_node("ConvoyAgent", self.node_convoy)
        self.run_node("PermitAgent", self.node_permit)
        self.run_node("CameraAgent", self.node_camera)
        self.run_node("WeightAgent", self.node_weight)
        self.run_node("WeightLockAgent", self.node_weight_lock)
        self.run_node("DriverBehaviorAgent", self.node_driver_behavior)
        self.run_node("PredictionAgent", self.node_prediction)
        self.run_node("AnomalyAgent", self.node_anomaly)
        self.run_node("ForecastAgent", self.node_forecast)
        self.run_node("FusionAgent", self.node_fusion)

    def orchestrate_flow(self):
        route_id = self.data.route_id or self.state.get("route_id")
        in_zone = self.state.get("current_zone") in ("mine", "dump")
        
        # 1. Geofence Check (always run)
        self.decisions["GeofenceAgent"] = {"run": True, "reason": "Mandatory compliance check for forbidden areas and unapproved mines."}
        
        # 2. Route Deviation Check
        if in_zone:
            self.decisions["RouteDeviationAgent"] = {"run": True, "reason": "Runs baseline route validation within mine/dump boundaries."}
        else:
            self.decisions["RouteDeviationAgent"] = {"run": True, "reason": "Evaluates distance deviation from the assigned route line."}
            
        # 3. Spoof Check
        no_prev = self.state.get("last_lat") is None or self.state.get("last_lon") is None or not self.state.get("last_update")
        if no_prev:
            self.decisions["SpoofAgent"] = {"run": True, "reason": "Initial tick: establishing baseline position context."}
        else:
            self.decisions["SpoofAgent"] = {"run": True, "reason": "Verifies speed sanity to detect GPS jumps."}
            
        # 4. Convoy Check
        active_on_route = sum(1 for v_id, s in vehicle_state.items() if s.get("route_id") == route_id)
        if active_on_route < 2:
            self.decisions["ConvoyAgent"] = {"run": True, "reason": "Evaluates surrounding vehicle patterns to detect proximity behavior."}
        else:
            self.decisions["ConvoyAgent"] = {"run": True, "reason": "Detects close-following patterns between vehicles."}
            
        # 5. Permit Check
        self.decisions["PermitAgent"] = {"run": True, "reason": "Validates permit existence and trip limits."}
            
        # 6. Camera Check
        recent_events = [
            e for e in camera_events 
            if (self.now - to_aware(datetime.fromisoformat(e["time"]))).total_seconds() <= 60
        ]
        nearby_camera_event = None
        for ev in recent_events:
            if haversine_meters(self.data.lat, self.data.lon, ev["lat"], ev["lon"]) <= 250:
                nearby_camera_event = ev
                break
        
        if nearby_camera_event is None:
            self.decisions["CameraAgent"] = {"run": True, "reason": "Performs route checkpoint scan for visual verification."}
        else:
            self.decisions["CameraAgent"] = {"run": True, "reason": "Evaluates vehicle presence visual mismatch from nearby camera."}
            self.state["_last_camera_event"] = nearby_camera_event
            
        # 7. Weight Predictive Model (Kinematics)
        self.decisions["WeightAgent"] = {"run": True, "reason": "Runs kinematics regression to predict payload."}
        
        # 8. Weight Lock Agent
        features = build_weight_features(self.state, self.now)
        trip_distance_km = float(features["route_distance"])
        trip_time_minutes = float(features["trip_time"])
        eligible_for_lock = (
            self.state.get("stage") == "to_dump"
            and trip_distance_km >= WEIGHT_LOCK_MIN_DISTANCE_KM
            and trip_time_minutes >= WEIGHT_LOCK_MIN_TRIP_MINUTES
        )
        if not eligible_for_lock:
            self.decisions["WeightLockAgent"] = {"run": True, "reason": "Monitors trip metrics for lock eligibility."}
        else:
            self.decisions["WeightLockAgent"] = {"run": True, "reason": "Locks the predicted payload when stable trip thresholds are met."}
            
        # Other standard agents always run
        self.decisions["DriverBehaviorAgent"] = {"run": True, "reason": "Analyzes speed variances for harsh braking and profiling."}
        self.decisions["PredictionAgent"] = {"run": True, "reason": "Fuses RF classifier predictions with hand-tuned sigmoids."}
        self.decisions["AnomalyAgent"] = {"run": True, "reason": "Isolation Forest checks for multivariate outliers."}
        self.decisions["ForecastAgent"] = {"run": True, "reason": "Predicts future trip targets and payloads."}
        self.decisions["FusionAgent"] = {"run": True, "reason": "Combines heuristics, classifier ML, anomalies, and driver behaviors into a unified score."}

    def run_node(self, name, node_func):
        decision = self.decisions[name]
        if decision["run"]:
            node_func()
        else:
            self.log_agent(
                agent=name,
                ran=False,
                input_summary="n/a",
                output_summary="n/a",
                reason=decision["reason"]
            )

    def node_geofence(self):
        route_id = self.data.route_id or self.state.get("route_id")
        risk_before = float(self.state.get("risk", 0.0))
        geofence_triggered = check_geofence(self.vehicle_id, route_id, self.data.lat, self.data.lon, self.state, self.now)
        risk_after = float(self.state.get("risk", 0.0))
        self.log_agent(
            agent="GeofenceAgent",
            ran=True,
            input_summary=f"lat={self.data.lat}, lon={self.data.lon}, route={route_id}",
            output_summary=f"triggered={geofence_triggered}, risk={risk_before}->{risk_after}, event='{self.state.get('last_event', '')}'",
            reason=self.decisions["GeofenceAgent"]["reason"]
        )

    def node_route_deviation(self):
        route_id = self.data.route_id or self.state.get("route_id")
        risk_before = float(self.state.get("risk", 0.0))
        check_route_deviation(self.vehicle_id, route_id, self.data.lat, self.data.lon, self.state, self.now)
        risk_after = float(self.state.get("risk", 0.0))
        self.log_agent(
            agent="RouteDeviationAgent",
            ran=True,
            input_summary=f"lat={self.data.lat}, lon={self.data.lon}",
            output_summary=f"risk={risk_before}->{risk_after}, event='{self.state.get('last_event', '')}'",
            reason=self.decisions["RouteDeviationAgent"]["reason"]
        )

    def node_spoof(self):
        risk_before = float(self.state.get("risk", 0.0))
        check_spoof(self.vehicle_id, self.state, self.data.lat, self.data.lon, self.data.timestamp, self.now)
        risk_after = float(self.state.get("risk", 0.0))
        self.log_agent(
            agent="SpoofAgent",
            ran=True,
            input_summary=f"lat={self.data.lat}, lon={self.data.lon}, prev_lat={self.state.get('last_lat')}, prev_lon={self.state.get('last_lon')}",
            output_summary=f"speed={self.state.get('recent_speed_kmh')} km/h, risk={risk_before}->{risk_after}, event='{self.state.get('last_event', '')}'",
            reason=self.decisions["SpoofAgent"]["reason"]
        )

    def node_convoy(self):
        route_id = self.data.route_id or self.state.get("route_id")
        risk_before = float(self.state.get("risk", 0.0))
        check_convoy(self.vehicle_id, route_id, self.data.lat, self.data.lon, self.state, self.now)
        risk_after = float(self.state.get("risk", 0.0))
        self.log_agent(
            agent="ConvoyAgent",
            ran=True,
            input_summary=f"route={route_id}",
            output_summary=f"convoy_hits={self.state.get('convoy_hits')}, risk={risk_before}->{risk_after}",
            reason=self.decisions["ConvoyAgent"]["reason"]
        )

    def node_permit(self):
        risk_before = float(self.state.get("risk", 0.0))
        check_permit(self.vehicle_id, self.state, self.now)
        risk_after = float(self.state.get("risk", 0.0))
        self.log_agent(
            agent="PermitAgent",
            ran=True,
            input_summary=f"vehicle_id={self.vehicle_id}",
            output_summary=f"risk={risk_before}->{risk_after}, event='{self.state.get('last_event', '')}'",
            reason=self.decisions["PermitAgent"]["reason"]
        )

    def node_camera(self):
        ev = self.state.pop("_last_camera_event", None)
        if ev:
            mismatch = ev["mismatch"]
            # Expose camera risk triggers dynamically
            if mismatch >= (2 if ev["camera_confidence"] >= 0.55 else 3):
                update_risk(self.vehicle_id, f"Camera mismatch visual anomaly ({ev['camera_id']})", 12, "warning", self.data.lat, self.data.lon)
            self.log_agent(
                agent="CameraAgent",
                ran=True,
                input_summary=f"camera_id={ev['camera_id']}, count={ev['truck_count']}, active_gps={ev['nearby_active']}",
                output_summary=f"mismatch={mismatch}, risk={self.state.get('risk')}",
                reason=self.decisions["CameraAgent"]["reason"]
            )
        else:
            self.log_agent(
                agent="CameraAgent",
                ran=True,
                input_summary="camera_id=none_nearby",
                output_summary="mismatch=0, status=clear_by_route_sweep",
                reason=self.decisions["CameraAgent"]["reason"]
            )

    def node_weight(self):
        self.state["gps_confidence"] = get_confidence(self.state.get("profile", "normal"), "gps", self.state)
        weight_before = self.state.get("predicted_weight")
        update_weight_prediction(self.vehicle_id, self.state, self.data.timestamp, self.previous_record, self.data.lat, self.data.lon)
        weight_after = self.state.get("predicted_weight")
        self.log_agent(
            agent="WeightAgent",
            ran=True,
            input_summary=f"stage={self.state.get('stage')}",
            output_summary=f"predicted_weight={weight_after} tons (was={weight_before})",
            reason=self.decisions["WeightAgent"]["reason"]
        )

    def node_weight_lock(self):
        self.log_agent(
            agent="WeightLockAgent",
            ran=True,
            input_summary=f"stage={self.state.get('stage')}",
            output_summary=f"weight_locked_for_trip={self.state.get('weight_locked_for_trip')}, locked_weight={self.state.get('predicted_weight')}",
            reason=self.decisions["WeightLockAgent"]["reason"]
        )

    def node_driver_behavior(self):
        update_driver_behavior(self.state)
        behavior = self.state.get("driver_behavior", {})
        self.log_agent(
            agent="DriverBehaviorAgent",
            ran=True,
            input_summary=f"speed_samples={len(self.state.get('speed_samples', []))}",
            output_summary=f"harsh_braking={behavior.get('harsh_braking')}, fluctuation={behavior.get('speed_fluctuation')}, risky={behavior.get('risky')}",
            reason=self.decisions["DriverBehaviorAgent"]["reason"]
        )
        if self.state.pop("trip_completed_this_event", False):
            finalize_weight_trip(self.vehicle_id, self.state, self.data.timestamp)
        if self.state["gps_confidence"] < 0.45 and not reason_throttled(self.state, "low_gps_conf", self.now, 180):
            append_alert(self.vehicle_id, "Low GPS confidence due to weather/noise", severity="warning")

    def node_prediction(self):
        compute_prediction(self.state)
        pred = self.state.get("prediction", {})
        self.log_agent(
            agent="PredictionAgent",
            ran=True,
            input_summary=f"risk={self.state.get('risk')}, recent_speed={self.state.get('recent_speed_kmh')}",
            output_summary=f"prob={pred.get('probability')}, label={pred.get('label')}",
            reason=self.decisions["PredictionAgent"]["reason"]
        )

    def node_anomaly(self):
        update_anomaly_score(self.state, self.state.get("weight_prediction", {}).get("features", {}))
        if self.state.get("anomaly_flag") and not reason_throttled(self.state, "anomaly_alert", self.now, 180):
            append_alert(self.vehicle_id, "Anomaly detected by Isolation Forest", severity="warning", meta={"anomaly_score": self.state.get("anomaly_score")})
        self.log_agent(
            agent="AnomalyAgent",
            ran=True,
            input_summary="features_dict",
            output_summary=f"score={self.state.get('anomaly_score')}, flagged={self.state.get('anomaly_flag')}",
            reason=self.decisions["AnomalyAgent"]["reason"]
        )

    def node_forecast(self):
        compute_lstm_style_forecast(self.state)
        forecast = self.state.get("time_series_forecast", {})
        self.log_agent(
            agent="ForecastAgent",
            ran=True,
            input_summary=f"predicted_weight={self.state.get('predicted_weight')}",
            output_summary=f"future_route={forecast.get('future_route')}, load={forecast.get('future_load_tons')} tons",
            reason=self.decisions["ForecastAgent"]["reason"]
        )

    def node_fusion(self):
        compute_fusion_threat_score(self.state)
        self.log_agent(
            agent="FusionAgent",
            ran=True,
            input_summary=f"risk={self.state.get('risk')}, anomaly={self.state.get('anomaly_score')}",
            output_summary=f"final_threat_score={self.state.get('final_threat_score')}",
            reason=self.decisions["FusionAgent"]["reason"]
        )


def process_gps(data: GPSPayload):
    run_background_checks(utc_now())

    vehicle_id = data.vehicle_id
    previous_record = gps_store.get(vehicle_id)
    previous_zone = vehicle_state.get(vehicle_id, {}).get("last_zone", "outside")

    route_id = data.route_id or vehicle_state.get(vehicle_id, {}).get("route_id")
    route_name = vehicle_state.get(vehicle_id, {}).get("route_name")

    current_zone = get_zone(data.lat, data.lon, route_id)
    if route_id is None and current_zone is not None:
        route_id = current_zone["route_id"]
        current_zone = get_zone(data.lat, data.lon, route_id)

    if route_id in route_definitions:
        route_name = route_definitions[route_id]["name"]
    route_info = route_definitions.get(route_id, {})
    district_name = route_info.get("district", "Unknown")

    gps_store[vehicle_id] = {
        "lat": data.lat,
        "lon": data.lon,
        "timestamp": data.timestamp.isoformat(),
        "route_id": route_id,
        "route_name": route_name,
        "zone_id": current_zone["id"] if current_zone else "outside",
        "zone_name": current_zone["name"] if current_zone else "Outside",
        "zone_type": current_zone["type"] if current_zone else "outside",
        "district": district_name,
    }

    state = ensure_vehicle_state(vehicle_id, route_id, route_name)
    current_zone_type = current_zone["type"] if current_zone else "outside"
    current_zone_name = current_zone["name"] if current_zone else "Outside"

    if previous_record is not None and previous_zone != current_zone_type:
        if previous_zone != "outside" and current_zone_type == "outside":
            state["last_event"] = f"Exited {previous_record['zone_name']}"
        elif previous_zone == "outside" and current_zone_type != "outside":
            state["last_event"] = f"Entered {current_zone_name}"
        elif previous_zone != "outside" and current_zone_type != "outside":
            state["last_event"] = f"Moved {previous_record['zone_name']} -> {current_zone_name}"

    if state["stage"] == "start" and current_zone_type == "mine":
        state["stage"] = "to_dump"
    elif state["stage"] == "to_dump" and current_zone_type == "dump":
        state["stage"] = "to_mine"
    elif state["stage"] == "to_mine" and current_zone_type == "mine":
        state["stage"] = "to_dump"
        state["trips"] += 1
        state["trip_timestamps"].append(data.timestamp.isoformat())
        refresh_trip_window(state, data.timestamp)
        state["last_event"] = f"Completed trip #{state['trips']}"
        state["trip_completed_this_event"] = True

    state["last_zone"] = current_zone_type
    state["current_zone"] = current_zone_type
    state["current_zone_name"] = current_zone_name
    state["district"] = district_name

    now = utc_now()
    orchestrator = AgentOrchestrator(vehicle_id, state, data, previous_record, now)
    orchestrator.run()

    state["updated_at"] = data.timestamp.isoformat()
    state["last_update"] = data.timestamp.isoformat()
    state["last_lat"] = data.lat
    state["last_lon"] = data.lon

    state_copy = {
        "updated_at": state.get("updated_at"),
        "route_id": state.get("route_id"),
        "route_name": state.get("route_name"),
        "current_zone": state.get("last_zone"),
        "current_zone_name": state.get("current_zone_name"),
        "trips": state.get("trips"),
        "trips_24h": state.get("trips_24h"),
        "risk": state.get("risk"),
        "prediction": dict(state.get("prediction", {})),
        "predicted_weight": state.get("predicted_weight"),
        "average_weight": state.get("average_weight"),
        "overload_flag": state.get("overload_flag"),
        "weight_history": list(state.get("weight_history", [])),
        "weight_prediction": dict(state.get("weight_prediction", {})),
        "profile": state.get("profile"),
        "last_event": state.get("last_event")
    }

    DB_QUEUE.put({
        "vehicle_id": vehicle_id,
        "timestamp": data.timestamp.isoformat(),
        "route_id": route_id,
        "lat": data.lat,
        "lon": data.lon,
        "zone_type": current_zone_type,
        "zone_name": current_zone_name,
        "risk": float(state["risk"]),
        "prediction_label": state["prediction"]["label"],
        "prediction_probability": float(state["prediction"]["probability"]),
        "predicted_weight": float(state.get("predicted_weight", 0.0) or 0.0),
        "overload_flag": 1 if state.get("overload_flag") else 0,
        "trace": orchestrator.trace,
        "state_copy": state_copy
    })

    return {
        "vehicle_id": vehicle_id,
        "route_id": route_id,
        "route_name": route_name,
        "zone_name": current_zone_name,
        "zone_type": current_zone_type,
        "event": state.get("last_event", ""),
        "trips": state["trips"],
        "trips_24h": state["trips_24h"],
        "risk": round(state["risk"], 2),
        "risk_level": classify_risk(state["risk"]),
        "prediction": state.get("prediction", {}),
        "weight_prediction": state.get("weight_prediction", {}),
        "predicted_weight": round(float(state.get("predicted_weight", 0.0) or 0.0), 2),
        "average_weight": round(float(state.get("average_weight", 0.0) or 0.0), 2),
        "overload_flag": bool(state.get("overload_flag", False)),
        "driver_behavior": state.get("driver_behavior", {}),
        "anomaly_score": state.get("anomaly_score", 0.0),
        "anomaly_flag": state.get("anomaly_flag", False),
        "time_series_forecast": state.get("time_series_forecast", {}),
        "final_threat_score": state.get("final_threat_score", 0.0),
        "district": district_name,
        "profile": state.get("profile"),
        "gps_confidence": round(float(state.get("gps_confidence", 0.9)), 3),
    }


@app.before_request
def enforce_auth_and_rbac():
    if app.testing:
        g.current_user = {"username": "admin", "role": "admin", "vehicle_ids": []}
        return None
    path = request.path or "/"
    if path.startswith("/static/"):
        return None

    if path in {"/login", "/api/auth/login", "/health"}:
        return None

    user = current_user()

    protected_api = path.startswith("/api/") or path in {"/gps", "/camera"} or path.startswith("/export/")
    if protected_api:
        if not user:
            return jsonify({"error": "unauthorized", "message": "Login required"}), 401
        if not role_api_access(path, user.get("role", ""), request.method):
            return jsonify({"error": "forbidden", "message": "Role does not have access"}), 403
        return None

    if user:
        role = user.get("role")
        if path == "/admin" and role != "admin":
            return redirect(url_for("dashboard_page"))
        if path in {"/module-predictions"} and role not in {"admin", "officer"}:
            return redirect(url_for("dashboard_page"))

    return None


@app.get("/login")
def login_page():
    return render_template("login.html", web_name="Tharani Sengol")


@app.post("/api/auth/login")
def api_auth_login():
    # Reload user file so changes in user_accounts.json are effective without restart.
    load_user_store()
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", "")).strip()

    user = USER_STORE.get(username)
    if (not user or user.get("password") != password) and username:
        # Resilient fallback so baseline credentials remain valid even if runtime store is out of sync.
        defaults = default_users_index()
        fallback_user = defaults.get(username)
        if fallback_user and fallback_user.get("password") == password:
            USER_STORE[username] = fallback_user
            save_user_store()
            user = fallback_user

    if not user or user.get("password") != password:
        return jsonify({"error": "invalid_credentials", "message": "Invalid username or password"}), 401

    if jwt is None:
        return jsonify({"error": "jwt_missing", "message": "PyJWT is not installed in environment"}), 500

    token = issue_jwt(user)
    response = make_response(jsonify({"token": token, "user": safe_user(user), "expires_hours": JWT_EXPIRE_HOURS}))
    response.set_cookie(
        "tharani_token",
        token,
        max_age=JWT_EXPIRE_HOURS * 3600,
        httponly=True,
        samesite="Lax",
        secure=False,
        path="/",
    )
    return response


@app.post("/api/auth/logout")
def api_auth_logout():
    response = make_response(jsonify({"ok": True}))
    response.delete_cookie("tharani_token", path="/")
    return response


@app.get("/api/auth/me")
def api_auth_me():
    user = current_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401
    return jsonify({"user": safe_user(user)})


@app.get("/api/users")
def api_users_list():
    users = [safe_user(item) for item in USER_STORE.values()]
    users.sort(key=lambda x: x["username"].lower())
    return jsonify(users)


@app.post("/api/users")
def api_users_create_or_update():
    payload = request.get_json(force=True, silent=True) or {}
    username = str(payload.get("username", "")).strip().lower()
    password = str(payload.get("password", "")).strip()
    role = str(payload.get("role", "operator")).strip().lower()
    vehicle_ids = [str(v).strip() for v in payload.get("vehicle_ids", []) if str(v).strip()]

    if not username or not password:
        return jsonify({"error": "invalid_input", "message": "username and password are required"}), 400
    if role not in VALID_ROLES:
        return jsonify({"error": "invalid_role", "message": "role must be admin/officer/owner/operator"}), 400

    USER_STORE[username] = {
        "username": username,
        "password": password,
        "role": role,
        "vehicle_ids": vehicle_ids,
    }
    save_user_store()
    return jsonify({"ok": True, "user": safe_user(USER_STORE[username])})


@app.delete("/api/users/<username>")
def api_users_delete(username: str):
    target = str(username).strip()
    if not target or target not in USER_STORE:
        return jsonify({"error": "not_found", "message": "user not found"}), 404
    if target == "admin":
        return jsonify({"error": "blocked", "message": "default admin cannot be deleted"}), 400

    del USER_STORE[target]
    save_user_store()
    return jsonify({"ok": True})


@app.post("/gps")
def receive_gps():
    payload = request.get_json(force=True, silent=False)
    try:
        if isinstance(payload, list):
            for item in payload:
                GPS_QUEUE.put(GPSPayload(item))
            return jsonify({"ok": True})
        else:
            GPS_QUEUE.put(GPSPayload(payload))
            return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": "bad_request", "message": str(e)}), 400


@app.get("/api/routes")
def api_routes():
    district = str(request.args.get("district", "")).strip().lower()
    if not district:
        return jsonify(route_definitions)
    filtered = {route_id: route for route_id, route in route_definitions.items() if route.get("district", "").lower() == district}
    return jsonify(filtered)


@app.get("/api/vehicles")
def api_vehicles():
    run_background_checks(utc_now())
    user = current_user()
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is None:
        return jsonify(gps_store)
    return jsonify({k: v for k, v in gps_store.items() if k in allowed})


@app.get("/api/lorries")
def api_lorries():
    run_background_checks(utc_now())
    user = current_user()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    query = str(request.args.get("query", ""))
    district = str(request.args.get("district", ""))
    rows = filter_lorry_rows(build_lorry_rows(), query=query, district=district)
    rows = scope_rows_by_user(rows, user)
    payload = paginate_rows(rows, page=page, page_size=page_size)
    payload["district"] = district or "all"
    payload["query"] = query
    return jsonify(payload)


@app.get("/api/trips")
def api_trips():
    run_background_checks(utc_now())
    user = current_user()
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is None:
        return jsonify(vehicle_state)
    return jsonify({k: v for k, v in vehicle_state.items() if k in allowed})


@app.get("/api/alerts")
def api_alerts():
    run_background_checks(utc_now())
    user = current_user()
    limit = int(request.args.get("limit", 50))
    district = str(request.args.get("district", "")).strip().lower()
    query = str(request.args.get("query", "")).strip().lower()
    subset = list(reversed(alerts[-max(1, min(limit, 400)):]))
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is not None:
        subset = [item for item in subset if item.get("vehicle_id") in allowed]
    if district:
        subset = [item for item in subset if vehicle_state.get(item.get("vehicle_id"), {}).get("district", "").lower() == district]
    if query:
        subset = [item for item in subset if query in f"{item.get('vehicle_id', '')} {item.get('message', '')}".lower()]
    return jsonify(subset[: max(1, min(limit, 200))])


@app.get("/api/heatmap")
def api_heatmap():
    run_background_checks(utc_now())
    user = current_user()
    if user and user.get("role") not in {"admin", "officer"}:
        return jsonify([])
    limit = int(request.args.get("limit", 500))
    district = str(request.args.get("district", "")).strip().lower()
    points = violation_heatmap[-max(1, min(limit, MAX_HEATMAP_POINTS)):]
    if district:
        points = [point for point in points if vehicle_state.get(point.get("vehicle_id"), {}).get("district", "").lower() == district]
    return jsonify(points)


@app.get("/api/risk-timeline")
def api_risk_timeline():
    run_background_checks(utc_now())
    limit = int(request.args.get("limit", 50))
    capped = max(5, min(limit, 160))
    with STATE_LOCK:
        items = list(vehicle_state.items())
    timeline = {vehicle_id: state.get("risk_timeline", [])[-capped:] for vehicle_id, state in items}
    return jsonify(timeline)


@app.get("/api/map-context")
def api_map_context():
    run_background_checks(utc_now())
    user = current_user()
    district = str(request.args.get("district", "")).strip().lower()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    lorries = filter_lorry_rows(build_lorry_rows(), query=str(request.args.get("query", "")), district=district)
    lorries = scope_rows_by_user(lorries, user)
    lorry_page = paginate_rows(lorries, page=page, page_size=page_size)

    include_all_routes = str(request.args.get("include_all_routes", "0")).strip() == "1"
    routes = {}
    if user and user.get("role") in {"admin", "officer"} and district:
        routes = {route_id: route for route_id, route in route_definitions.items() if route.get("district", "").lower() == district}
    elif user and user.get("role") in {"admin", "officer"} and include_all_routes:
        routes = route_definitions

    heat = []
    if user and user.get("role") in {"admin", "officer"}:
        heat = violation_heatmap[-max(1, min(int(request.args.get("heat_limit", 400)), MAX_HEATMAP_POINTS)):]
        if district:
            heat = [point for point in heat if vehicle_state.get(point.get("vehicle_id"), {}).get("district", "").lower() == district]

    return jsonify({"routes": routes, "lorries": lorry_page, "heatmap": heat, "district": district or None})


@app.get("/api/predictions")
def api_predictions():
    run_background_checks(utc_now())
    user = current_user()
    allowed = scoped_vehicle_ids_for_user(user)
    with STATE_LOCK:
        items = list(vehicle_state.items())
    predictions = {
        vehicle_id: state.get("prediction", {"probability": 0.0, "label": "LOW", "reason": "n/a"})
        for vehicle_id, state in items
        if allowed is None or vehicle_id in allowed
    }
    return jsonify(predictions)


@app.post("/api/chat")
def api_chat():
    payload = request.get_json(force=True, silent=True) or {}
    query = str(payload.get("query", "")).strip()
    if not query:
        return jsonify({"answer": "Please ask a question about a district, truck, route, mine zone, driver behavior, anomaly, weight, or threat score.", "source": {"type": "help"}})
    response = answer_chat_query(query)
    return jsonify(response)


@app.get("/api/ai-overview")
def api_ai_overview():
    run_background_checks(utc_now())
    user = current_user()
    scoped_rows = scope_rows_by_user(build_lorry_rows(), user)
    scoped_ids = {item.get("vehicle_id") for item in scoped_rows}
    states = [state for vehicle_id, state in vehicle_state.items() if vehicle_id in scoped_ids]

    total = len(states)
    high_pred = 0
    medium_pred = 0
    locked_weights = 0
    overloads = 0
    avg_prob = 0.0
    avg_weight = 0.0
    prob_count = 0
    weight_count = 0

    for state in states:
        prediction = state.get("prediction", {})
        label = str(prediction.get("label", "LOW"))
        if label == "HIGH":
            high_pred += 1
        elif label == "MEDIUM":
            medium_pred += 1

        probability = prediction.get("probability")
        if probability is not None:
            avg_prob += float(probability)
            prob_count += 1

        weight_pred = state.get("weight_prediction", {})
        if weight_pred.get("is_locked"):
            locked_weights += 1
        if weight_pred.get("overload_flag"):
            overloads += 1

        weight_value = state.get("predicted_weight")
        if weight_value is not None:
            avg_weight += float(weight_value)
            weight_count += 1

    twin = compute_digital_twin_summary()
    return jsonify(
        {
            "system": {
                "configured_routes": len(route_definitions),
                "configured_vehicles": len(VEHICLE_PROFILES),
                "configured_mine_zones": len(route_definitions),
                "configured_dump_zones": len(route_definitions),
            },
            "classification": {
                "vehicles": total,
                "high_predictions": high_pred,
                "medium_predictions": medium_pred,
                "avg_probability": round((avg_prob / prob_count) if prob_count else 0.0, 3),
            },
            "regression": {
                "locked_weight_predictions": locked_weights,
                "overloads": overloads,
                "weight_limit_tons": WEIGHT_LIMIT_TONS,
                "avg_predicted_weight": round((avg_weight / weight_count) if weight_count else 0.0, 2),
                "lock_distance_km": WEIGHT_LOCK_MIN_DISTANCE_KM,
                "lock_trip_minutes": WEIGHT_LOCK_MIN_TRIP_MINUTES,
            },
            "modules": {
                "anomaly_enabled": True,
                "time_series_enabled": True,
                "driver_behavior_enabled": True,
                "clustering_enabled": True,
                "fusion_enabled": True,
                "explainability_enabled": True,
            },
            "digital_twin": twin,
        }
    )


@app.get("/api/module-predictions")
def api_module_predictions():
    run_background_checks(utc_now())
    rows = build_lorry_rows()
    total = len(rows)

    anomaly_rows = sorted(rows, key=lambda item: float(item.get("anomaly_score", 0.0)), reverse=True)[:30]
    anomaly_bins = {"0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for item in rows:
        value = float(item.get("anomaly_score", 0.0))
        if value < 0.2:
            anomaly_bins["0-0.2"] += 1
        elif value < 0.4:
            anomaly_bins["0.2-0.4"] += 1
        elif value < 0.6:
            anomaly_bins["0.4-0.6"] += 1
        elif value < 0.8:
            anomaly_bins["0.6-0.8"] += 1
        else:
            anomaly_bins["0.8-1.0"] += 1

    forecast_rows = []
    forecast_zone_counts = {"mine": 0, "dump": 0, "unknown": 0}
    for item in rows:
        forecast = item.get("time_series_forecast", {}) or {}
        future_route = str(forecast.get("future_route", "unknown")).lower()
        if future_route not in forecast_zone_counts:
            future_route = "unknown"
        forecast_zone_counts[future_route] += 1
        forecast_rows.append(
            {
                "vehicle_id": item.get("vehicle_id"),
                "future_route": future_route,
                "future_load_tons": round(float(forecast.get("future_load_tons", 0.0)), 2),
            }
        )

    behavior_summary = {
        "safe": {"count": 0, "risky": 0, "aligned": 0},
        "normal": {"count": 0, "risky": 0, "aligned": 0},
        "high_risk": {"count": 0, "risky": 0, "aligned": 0},
    }
    for item in rows:
        profile = str(item.get("profile", "normal"))
        profile = profile if profile in behavior_summary else "normal"
        behavior = item.get("driver_behavior", {}) or {}
        behavior_summary[profile]["count"] += 1
        if behavior.get("risky"):
            behavior_summary[profile]["risky"] += 1
        if behavior.get("profile_alignment"):
            behavior_summary[profile]["aligned"] += 1

    clusters = compute_heatmap_clusters(limit=1200, clusters=KMEANS_DEFAULT_CLUSTERS)

    fusion_rows = sorted(rows, key=lambda item: float(item.get("final_threat_score", 0.0)), reverse=True)[:30]
    twin = compute_digital_twin_summary()

    shap_feature_impact = {}
    shap_sources = 0
    for state in vehicle_state.values():
        explain = (state.get("weight_prediction", {}) or {}).get("explain", {}) or {}
        for entry in explain.get("items", [])[:4]:
            feature = str(entry.get("feature", "unknown"))
            impact = abs(float(entry.get("impact", 0.0)))
            shap_feature_impact[feature] = shap_feature_impact.get(feature, 0.0) + impact
        if explain.get("items"):
            shap_sources += 1

    shap_ranked = [
        {"feature": key, "impact": round(value, 3)}
        for key, value in sorted(shap_feature_impact.items(), key=lambda x: x[1], reverse=True)[:8]
    ]

    return jsonify(
        {
            "summary": {
                "vehicles": total,
                "anomaly_flagged": sum(1 for item in rows if bool(item.get("anomaly_score", 0.0) >= 0.72)),
                "risky_drivers": sum(1 for item in rows if bool((item.get("driver_behavior", {}) or {}).get("risky"))),
                "high_threat": sum(1 for item in rows if float(item.get("final_threat_score", 0.0)) >= 70.0),
                "cluster_count": len(clusters),
                "shap_sources": shap_sources,
            },
            "anomaly": {
                "top": [
                    {
                        "vehicle_id": item.get("vehicle_id"),
                        "profile": item.get("profile"),
                        "risk": item.get("risk"),
                        "anomaly_score": round(float(item.get("anomaly_score", 0.0)), 3),
                    }
                    for item in anomaly_rows
                ],
                "distribution": anomaly_bins,
            },
            "forecast": {
                "zone_counts": forecast_zone_counts,
                "top_loads": sorted(forecast_rows, key=lambda x: x["future_load_tons"], reverse=True)[:20],
            },
            "driver_behavior": behavior_summary,
            "clusters": clusters,
            "fusion": {
                "top": [
                    {
                        "vehicle_id": item.get("vehicle_id"),
                        "profile": item.get("profile"),
                        "risk": round(float(item.get("risk", 0.0)), 2),
                        "anomaly_score": round(float(item.get("anomaly_score", 0.0)), 3),
                        "final_threat_score": round(float(item.get("final_threat_score", 0.0)), 2),
                    }
                    for item in fusion_rows
                ]
            },
            "digital_twin": twin,
            "shap": {
                "top_features": shap_ranked,
                "enabled": True,
            },
        }
    )


@app.get("/api/driver-behavior")
def api_driver_behavior():
    run_background_checks(utc_now())
    rows = build_lorry_rows()

    items = []
    for item in rows:
        behavior = item.get("driver_behavior", {}) or {}
        items.append(
            {
                "vehicle_id": item.get("vehicle_id"),
                "profile": item.get("profile", "normal"),
                "risk": round(float(item.get("risk", 0.0)), 2),
                "trips_24h": int(item.get("trips_24h", 0)),
                "harsh_braking": int(behavior.get("harsh_braking", 0)),
                "speed_fluctuation": round(float(behavior.get("speed_fluctuation", 0.0)), 2),
                "risky": bool(behavior.get("risky", False)),
                "expected_risky": bool(behavior.get("expected_risky", False)),
                "profile_alignment": bool(behavior.get("profile_alignment", False)),
                "final_threat_score": round(float(item.get("final_threat_score", 0.0)), 2),
            }
        )

    items.sort(key=lambda x: (x["profile_alignment"], x["risky"], x["final_threat_score"]), reverse=False)

    profile_summary = {
        "safe": {"count": 0, "risky": 0, "aligned": 0},
        "normal": {"count": 0, "risky": 0, "aligned": 0},
        "high_risk": {"count": 0, "risky": 0, "aligned": 0},
    }
    for row in items:
        profile = row["profile"] if row["profile"] in profile_summary else "normal"
        profile_summary[profile]["count"] += 1
        if row["risky"]:
            profile_summary[profile]["risky"] += 1
        if row["profile_alignment"]:
            profile_summary[profile]["aligned"] += 1

    return jsonify({
        "summary": profile_summary,
        "rows": items,
        "misaligned": [row for row in items if not row["profile_alignment"]][:120],
    })


@app.get("/api/tn-dashboard-stats")
def api_tn_dashboard_stats():
    run_background_checks(utc_now())
    user = current_user()
    district_filter = str(request.args.get("district", "")).strip().lower()
    query = str(request.args.get("query", "")).strip()
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))

    states = list(vehicle_state.items())
    allowed = scoped_vehicle_ids_for_user(user)
    if allowed is not None:
        states = [(vehicle_id, state) for vehicle_id, state in states if vehicle_id in allowed]
    if district_filter:
        states = [(vehicle_id, state) for vehicle_id, state in states if state.get("district", "").lower() == district_filter]
    active = len(states)

    overall = {
        "state": "Tamil Nadu",
        "configured_trucks": len(VEHICLE_PROFILES),
        "configured_routes": len(route_definitions),
        "configured_mines": len(route_definitions),
        "active_trucks": active,
        "overloads": sum(1 for _, s in states if s.get("overload_flag")),
        "avg_risk": round(sum(float(s.get("risk", 0.0)) for _, s in states) / active, 2) if active else 0.0,
        "avg_final_threat": round(sum(float(s.get("final_threat_score", 0.0)) for _, s in states) / active, 2) if active else 0.0,
    }

    by_district = {}
    for vehicle_id, state in states:
        district = state.get("district", "Unknown")
        row = by_district.setdefault(
            district,
            {
                "district": district,
                "trucks": 0,
                "overloads": 0,
                "avg_risk": 0.0,
                "avg_threat": 0.0,
            },
        )
        row["trucks"] += 1
        row["avg_risk"] += float(state.get("risk", 0.0))
        row["avg_threat"] += float(state.get("final_threat_score", 0.0))
        if state.get("overload_flag"):
            row["overloads"] += 1

    district_rows = []
    for district, row in by_district.items():
        trucks = max(1, int(row["trucks"]))
        district_rows.append(
            {
                "district": district,
                "trucks": row["trucks"],
                "overloads": row["overloads"],
                "avg_risk": round(float(row["avg_risk"]) / trucks, 2),
                "avg_threat": round(float(row["avg_threat"]) / trucks, 2),
            }
        )
    district_rows.sort(key=lambda x: (x["avg_threat"], x["overloads"]), reverse=True)

    lorries = filter_lorry_rows(build_lorry_rows(), query=query, district=district_filter)
    lorries = scope_rows_by_user(lorries, user)
    paged = paginate_rows(lorries, page=page, page_size=page_size)

    return jsonify({"overall": overall, "districts": district_rows[:40], "lorries": paged, "selected_district": district_filter or "", "query": query})


@app.get("/api/heatmap/clusters")
def api_heatmap_clusters():
    limit = int(request.args.get("limit", 1200))
    clusters = int(request.args.get("clusters", KMEANS_DEFAULT_CLUSTERS))
    return jsonify(compute_heatmap_clusters(limit=limit, clusters=clusters))


@app.get("/api/digital-twin")
def api_digital_twin():
    run_background_checks(utc_now())
    return jsonify(compute_digital_twin_summary())


@app.get("/government-dashboard")
def government_dashboard_page():
    return render_template("government_dashboard.html", web_name="Tharani Sengol")


@app.get("/api/high-risk-vehicles")
def api_high_risk_vehicles():
    run_background_checks(utc_now())
    high_risk = []
    for vehicle_id, state in vehicle_state.items():
        if state.get("risk", 0.0) >= 50.0:
            high_risk.append({
                "vehicle_id": vehicle_id,
                "risk": round(state["risk"], 2),
                "risk_level": classify_risk(state["risk"]),
                "route_name": state.get("route_name"),
                "profile": state.get("profile"),
                "last_event": state.get("last_event"),
                "predicted_weight": round(float(state.get("predicted_weight", 0.0) or 0.0), 2),
                "overload_flag": bool(state.get("overload_flag", False))
            })
    
    if not high_risk:
        rows = db_query("SELECT vehicle_id, risk, risk_level, route_name, profile, last_event, predicted_weight, overload_flag FROM vehicle_snapshots WHERE risk >= 50 ORDER BY risk DESC LIMIT 30")
        high_risk = [dict(row) for row in rows]
    else:
        high_risk.sort(key=lambda x: x["risk"], reverse=True)
    return jsonify(high_risk[:30])


@app.get("/api/illegal-trips")
def api_illegal_trips():
    rows = db_query("""
        SELECT v.id, v.event_time, v.vehicle_id, v.reason, v.severity, v.lat, v.lon, v.risk_after,
               s.route_name
        FROM violations v
        LEFT JOIN vehicle_snapshots s ON v.vehicle_id = s.vehicle_id
        WHERE v.reason LIKE '%unauthorized%' 
           OR v.reason LIKE '%deviation%' 
           OR v.reason LIKE '%Overload%' 
           OR v.reason LIKE '%Permit%' 
           OR v.reason LIKE '%spoof%'
        ORDER BY v.id DESC LIMIT 40
    """)
    return jsonify(rows)


@app.get("/api/permit-violations")
def api_permit_violations():
    permits = db_query("SELECT * FROM permits")
    now_date = utc_now().date().isoformat()
    violations = []
    
    for p in permits:
        issues = []
        if p["status"] != "active":
            issues.append(f"Permit status is '{p['status']}'")
        if p["valid_from"] > now_date or p["valid_to"] < now_date:
            issues.append(f"Outside validity dates (Valid: {p['valid_from']} to {p['valid_to']})")
        if p["completed_trips"] > p["max_trips"]:
            issues.append(f"Trips exceeded ({p['completed_trips']}/{p['max_trips']})")
        if p["used_quantity"] > p["max_quantity"]:
            issues.append(f"Quantity exceeded ({p['used_quantity']:.1f}/{p['max_quantity']:.1f} Tons)")
            
        if issues:
            violations.append({
                "permit_id": p["permit_id"],
                "vehicle_number": p["vehicle_number"],
                "approved_route": p["approved_route"],
                "max_quantity": p["max_quantity"],
                "used_quantity": round(p["used_quantity"], 2),
                "max_trips": p["max_trips"],
                "completed_trips": p["completed_trips"],
                "valid_from": p["valid_from"],
                "valid_to": p["valid_to"],
                "status": p["status"],
                "violations": issues
            })
            
    return jsonify(violations)


@app.get("/api/heatmap-data")
def api_heatmap_data():
    points = []
    for p in violation_heatmap:
        points.append({
            "lat": p["lat"],
            "lon": p["lon"],
            "weight": p["weight"],
            "reason": p["reason"],
            "vehicle_id": p["vehicle_id"],
            "time": p["time"]
        })
    if not points:
        rows = db_query("SELECT lat, lon, reason, vehicle_id, event_time, points FROM violations WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY id DESC LIMIT 500")
        for r in rows:
            points.append({
                "lat": r["lat"],
                "lon": r["lon"],
                "weight": max(1.0, float(r["points"]) / 10.0),
                "reason": r["reason"],
                "vehicle_id": r["vehicle_id"],
                "time": r["event_time"]
            })
    return jsonify(points)


@app.get("/api/permit/<permit_id>/qr")
def api_permit_qr(permit_id: str):
    import qrcode
    from io import BytesIO
    import base64
    
    rows = db_query("SELECT * FROM permits WHERE permit_id = ?", (permit_id,))
    if not rows:
        return jsonify({"error": "not_found", "message": "Permit not registered"}), 404
        
    p = rows[0]
    payload = {
        "permit_id": p["permit_id"],
        "vehicle_number": p["vehicle_number"],
        "approved_route": p["approved_route"],
        "max_quantity": p["max_quantity"],
        "max_trips": p["max_trips"],
        "valid_from": p["valid_from"],
        "valid_to": p["valid_to"],
        "status": p["status"]
    }
    
    try:
        qr = qrcode.QRCode(version=1, box_size=8, border=3)
        qr.add_data(json.dumps(payload))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return jsonify({
            "permit_id": permit_id,
            "qr_image_base64": f"data:image/png;base64,{img_str}",
            "payload": payload
        })
    except Exception as e:
        return jsonify({"error": "generation_failed", "message": str(e)}), 500


@app.post("/api/permit/verify")
def api_permit_verify():
    payload = request.get_json(force=True, silent=True) or {}
    permit_id = payload.get("permit_id")
    vehicle_number = payload.get("vehicle_number")
    
    if not permit_id and not vehicle_number:
        return jsonify({"error": "missing_parameters", "message": "permit_id or vehicle_number is required"}), 400
        
    query_str = "SELECT * FROM permits WHERE "
    params = []
    if permit_id:
        query_str += "permit_id = ?"
        params.append(permit_id)
    else:
        query_str += "vehicle_number = ?"
        params.append(vehicle_number)
        
    rows = db_query(query_str, tuple(params))
    if not rows:
        return jsonify({
            "valid": False,
            "message": "Fraudulent permit! No registered permit record found in government database.",
            "checks": {
                "registered": False,
                "active": False,
                "date_valid": False,
                "route_valid": False,
                "trips_valid": False,
                "quantity_valid": False
            }
        }), 200
        
    p = rows[0]
    now_date = utc_now().date().isoformat()
    
    registered = True
    active = p["status"] == "active"
    date_valid = p["valid_from"] <= now_date <= p["valid_to"]
    
    current_route_id = payload.get("route_id")
    route_valid = True
    if current_route_id:
        route_valid = p["approved_route"] == current_route_id
        
    trips_valid = p["completed_trips"] <= p["max_trips"]
    quantity_valid = p["used_quantity"] <= p["max_quantity"]
    
    valid = active and date_valid and route_valid and trips_valid and quantity_valid
    
    errors = []
    if not active:
        errors.append(f"Permit status is '{p['status']}' (not active)")
    if not date_valid:
        errors.append(f"Current date outside range ({p['valid_from']} to {p['valid_to']})")
    if not route_valid:
        errors.append(f"Route mismatch: approved route is {p['approved_route']}, but checked on {current_route_id}")
    if not trips_valid:
        errors.append(f"Trip limit exceeded: {p['completed_trips']}/{p['max_trips']} trips completed")
    if not quantity_valid:
        errors.append(f"Tonnage exceeded: {p['used_quantity']:.1f}/{p['max_quantity']:.1f} Tons")
        
    return jsonify({
        "valid": valid,
        "message": "Permit is fully compliant." if valid else "Permit compliance violation detected!",
        "permit": {
            "permit_id": p["permit_id"],
            "vehicle_number": p["vehicle_number"],
            "approved_route": p["approved_route"],
            "max_quantity": p["max_quantity"],
            "used_quantity": round(p["used_quantity"], 2),
            "max_trips": p["max_trips"],
            "completed_trips": p["completed_trips"],
            "valid_from": p["valid_from"],
            "valid_to": p["valid_to"],
            "status": p["status"]
        },
        "checks": {
            "registered": registered,
            "active": active,
            "date_valid": date_valid,
            "route_valid": route_valid,
            "trips_valid": trips_valid,
            "quantity_valid": quantity_valid
        },
        "errors": errors
    })


@app.post("/api/permit/revoke")
def api_permit_revoke():
    payload = request.get_json(force=True, silent=True) or {}
    permit_id = payload.get("permit_id")
    if not permit_id:
        return jsonify({"error": "missing_permit_id", "message": "permit_id is required"}), 400
        
    db_execute("UPDATE permits SET status = 'revoked' WHERE permit_id = ?", (permit_id,))
    
    rows = db_query("SELECT vehicle_number FROM permits WHERE permit_id = ?", (permit_id,))
    if rows:
        vehicle_id = rows[0]["vehicle_number"]
        state = ensure_vehicle_state(vehicle_id)
        update_risk(vehicle_id, "Permit revoked by Government authority", 20, severity="critical")
        append_alert(vehicle_id, f"Permit {permit_id} was revoked by government authority!", severity="critical")
        
    return jsonify({"ok": True})


@app.get("/api/permits")
def api_permits():
    rows = db_query("SELECT * FROM permits ORDER BY vehicle_number ASC")
    return jsonify(rows)


@app.get("/api/control-state")
def api_control_state():
    payload = dict(CONTROL_STATE)
    payload["active_shift"] = get_active_shift()
    payload["weather_profiles"] = list(WEATHER_PROFILES.keys())
    payload["scenario_presets"] = list(SCENARIO_PRESETS.keys())
    return jsonify(payload)


@app.get("/api/admin/config")
def api_admin_config():
    rows = db_query("SELECT * FROM vehicle_config ORDER BY vehicle_id ASC")
    return jsonify(rows)


@app.post("/api/admin/config")
def api_admin_config_update():
    payload = request.get_json(force=True, silent=False)
    vehicle_id = str(payload.get("vehicle_id", "")).strip()
    profile = str(payload.get("profile", "normal")).strip()
    if profile not in PROFILE_CONFIG:
        profile = "normal"

    allowed_24h_trips = int(payload.get("allowed_24h_trips", 18))
    rolling_window_hours = int(payload.get("rolling_window_hours", 24))
    start_hour = int(payload.get("start_hour", 0))
    end_hour = int(payload.get("end_hour", 24))

    db_execute(
        """
        INSERT INTO vehicle_config(vehicle_id, profile, allowed_24h_trips, rolling_window_hours, start_hour, end_hour, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(vehicle_id) DO UPDATE SET
            profile=excluded.profile,
            allowed_24h_trips=excluded.allowed_24h_trips,
            rolling_window_hours=excluded.rolling_window_hours,
            start_hour=excluded.start_hour,
            end_hour=excluded.end_hour,
            updated_at=excluded.updated_at
        """,
        (
            vehicle_id,
            profile,
            allowed_24h_trips,
            rolling_window_hours,
            start_hour,
            end_hour,
            utc_now().isoformat(),
        ),
    )

    init_runtime_config()
    if vehicle_id in vehicle_state:
        vehicle_state[vehicle_id]["profile"] = profile
    return jsonify({"ok": True})


@app.post("/api/admin/control")
def api_admin_control_update():
    payload = request.get_json(force=True, silent=False)
    weather = str(payload.get("weather", CONTROL_STATE.get("weather", "clear"))).strip()
    shift_mode = str(payload.get("shift_mode", CONTROL_STATE.get("shift_mode", "auto"))).strip()

    if weather not in WEATHER_PROFILES:
        weather = "clear"
    valid_shift_modes = {"auto", "morning_peak", "noon_low", "evening_peak", "night_low"}
    if shift_mode not in valid_shift_modes:
        shift_mode = "auto"

    CONTROL_STATE["weather"] = weather
    CONTROL_STATE["shift_mode"] = shift_mode
    CONTROL_STATE["gps_noise"] = clamp(float(payload.get("gps_noise", CONTROL_STATE.get("gps_noise", 0.1))), 0.0, 0.40)
    CONTROL_STATE["camera_noise"] = clamp(float(payload.get("camera_noise", CONTROL_STATE.get("camera_noise", 0.1))), 0.0, 0.40)
    CONTROL_STATE["anomaly_factor"] = clamp(float(payload.get("anomaly_factor", CONTROL_STATE.get("anomaly_factor", 1.0))), 0.40, 2.50)
    CONTROL_STATE["traffic_factor"] = clamp(float(payload.get("traffic_factor", CONTROL_STATE.get("traffic_factor", 1.0))), 0.50, 2.00)
    save_control_state()
    return jsonify({"ok": True, "control_state": CONTROL_STATE, "active_shift": get_active_shift()})


@app.post("/api/admin/scenario")
def api_admin_scenario():
    payload = request.get_json(force=True, silent=False)
    preset_name = str(payload.get("preset", "suspicious_day")).strip()
    if preset_name not in SCENARIO_PRESETS:
        preset_name = "suspicious_day"

    preset = SCENARIO_PRESETS[preset_name]
    for key, value in preset.items():
        CONTROL_STATE[key] = value
    if "shift_mode" in payload:
        CONTROL_STATE["shift_mode"] = str(payload.get("shift_mode", "auto"))
    save_control_state()
    return jsonify({"ok": True, "preset": preset_name, "control_state": CONTROL_STATE, "active_shift": get_active_shift()})


@app.post("/api/admin/reset-runtime")
def api_admin_reset_runtime():
    vehicle_state.clear()
    gps_store.clear()
    alerts.clear()
    violation_heatmap.clear()
    camera_events.clear()

    db_execute("DELETE FROM vehicle_snapshots")
    db_execute("DELETE FROM alerts")
    db_execute("DELETE FROM violations")
    db_execute("DELETE FROM gps_events")
    db_execute("DELETE FROM camera_events")
    return jsonify({"ok": True, "message": "Runtime and event tables reset"})


@app.get("/api/history/risk")
def api_history_risk():
    user = current_user()
    minutes = int(request.args.get("minutes", 240))
    district = str(request.args.get("district", "")).strip().lower()
    cutoff = (utc_now() - timedelta(minutes=max(10, min(minutes, 24 * 60)))).isoformat()
    rows = db_query(
        "SELECT event_time, vehicle_id, risk FROM gps_events WHERE event_time >= ? ORDER BY event_time ASC",
        (cutoff,),
    )
    grouped = {}
    allowed = scoped_vehicle_ids_for_user(user)
    for row in rows:
        if allowed is not None and row["vehicle_id"] not in allowed:
            continue
        if district:
            state = vehicle_state.get(row["vehicle_id"], {})
            if state.get("district", "").lower() != district:
                continue
        grouped.setdefault(row["vehicle_id"], []).append({"ts": row["event_time"], "risk": row["risk"]})
    return jsonify(grouped)


@app.get("/api/history/violation-rate")
def api_history_violation_rate():
    user = current_user()
    minutes = int(request.args.get("minutes", 240))
    bucket_minutes = int(request.args.get("bucket_minutes", 5))
    window = max(10, min(minutes, 24 * 60))
    bucket = max(1, min(bucket_minutes, 60))
    cutoff = (utc_now() - timedelta(minutes=window)).isoformat()

    rows = db_query(
        "SELECT event_time, severity, vehicle_id FROM violations WHERE event_time >= ? ORDER BY event_time ASC",
        (cutoff,),
    )

    buckets = {}
    allowed = scoped_vehicle_ids_for_user(user)
    for row in rows:
        if allowed is not None and row.get("vehicle_id") not in allowed:
            continue
        event_dt = to_aware(datetime.fromisoformat(row["event_time"]))
        rounded_minute = (event_dt.minute // bucket) * bucket
        bucket_key = event_dt.replace(minute=rounded_minute, second=0, microsecond=0).isoformat()
        if bucket_key not in buckets:
            buckets[bucket_key] = {"ts": bucket_key, "critical": 0, "warning": 0, "total": 0}
        sev = row.get("severity") or "warning"
        if sev == "critical":
            buckets[bucket_key]["critical"] += 1
        else:
            buckets[bucket_key]["warning"] += 1
        buckets[bucket_key]["total"] += 1

    return jsonify([buckets[key] for key in sorted(buckets.keys())])


@app.get("/api/vehicle/<vehicle_id>/agent-trace")
def api_vehicle_agent_trace(vehicle_id: str):
    run_background_checks(utc_now())
    if not user_can_access_vehicle(current_user(), vehicle_id):
        return jsonify({"error": "forbidden"}), 403
    limit = request.args.get("limit", default=10, type=int)
    rows = db_query(
        """
        SELECT id, gps_event_id, timestamp, trace_json
        FROM agent_traces
        WHERE vehicle_id = ?
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
        """,
        (vehicle_id, limit)
    )
    result = []
    for r in rows:
        result.append({
            "id": r["id"],
            "gps_event_id": r["gps_event_id"],
            "timestamp": r["timestamp"],
            "trace": json.loads(r["trace_json"])
        })
    return jsonify(result)


@app.get("/api/vehicle/<vehicle_id>/explain")
def api_vehicle_explain(vehicle_id: str):
    run_background_checks(utc_now())
    if not user_can_access_vehicle(current_user(), vehicle_id):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(explain_vehicle_risk(vehicle_id))


@app.get("/api/vehicle/<vehicle_id>/detail")
def api_vehicle_detail(vehicle_id: str):
    run_background_checks(utc_now())
    if not user_can_access_vehicle(current_user(), vehicle_id):
        return jsonify({"error": "forbidden"}), 403

    row = next((item for item in build_lorry_rows() if item.get("vehicle_id") == vehicle_id), None)
    snapshot = None
    if not row:
        rows = db_query("SELECT * FROM vehicle_snapshots WHERE vehicle_id=? ORDER BY updated_at DESC LIMIT 1", (vehicle_id,))
        snapshot = rows[0] if rows else None
        if snapshot:
            row = {
                "vehicle_id": snapshot["vehicle_id"],
                "district": "Unknown",
                "route_id": snapshot["route_id"],
                "route_name": snapshot["route_name"],
                "lat": None,
                "lon": None,
                "zone_name": snapshot["zone_name"] or "Outside",
                "trips": int(snapshot["trips_total"] or 0),
                "trips_24h": int(snapshot["trips_24h"] or 0),
                "risk": float(snapshot["risk"] or 0.0),
                "risk_level": snapshot["risk_level"] or classify_risk(float(snapshot["risk"] or 0.0)),
                "prediction_label": snapshot["prediction_label"] or "LOW",
                "prediction_probability": float(snapshot["prediction_probability"] or 0.0),
                "predicted_weight": float(snapshot["predicted_weight"] or 0.0),
                "average_weight": float(snapshot["average_weight"] or 0.0),
                "weight_locked": bool(float(snapshot["predicted_weight"] or 0.0) > 0.0),
                "overload_flag": bool(snapshot["overload_flag"]),
                "anomaly_score": 0.0,
                "final_threat_score": 0.0,
                "driver_behavior": {},
                "time_series_forecast": {},
                "profile": snapshot["profile"] or "normal",
                "last_event": snapshot["last_event"] or "n/a",
                "updated_at": snapshot["updated_at"],
                "weight_history": [],
            }

    if not row:
        return jsonify({"error": "vehicle not found", "vehicle_id": vehicle_id}), 404

    explain = explain_vehicle_risk(vehicle_id)

    recent_path = db_query(
        """
        SELECT event_time, lat, lon, zone_name, zone_type, risk, prediction_label, predicted_weight
        FROM gps_events
        WHERE vehicle_id=?
        ORDER BY event_time DESC
        LIMIT 80
        """,
        (vehicle_id,),
    )
    recent_path = list(reversed(recent_path))

    recent_alerts = db_query(
        "SELECT alert_time, severity, message FROM alerts WHERE vehicle_id=? ORDER BY id DESC LIMIT 30",
        (vehicle_id,),
    )
    recent_violations = db_query(
        "SELECT event_time, reason, points, severity, risk_after FROM violations WHERE vehicle_id=? ORDER BY id DESC LIMIT 30",
        (vehicle_id,),
    )

    return jsonify(
        {
            "vehicle": row,
            "explain": explain,
            "path": recent_path,
            "alerts": recent_alerts,
            "violations": recent_violations,
        }
    )


def csv_response(filename: str, rows: list[list]):
    buffer = StringIO()
    csv_writer = writer(buffer)
    for row in rows:
        csv_writer.writerow(row)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/export/alerts.csv")
def export_alerts_csv():
    rows = db_query("SELECT alert_time, vehicle_id, severity, message FROM alerts ORDER BY id DESC")
    data = [["alert_time", "vehicle_id", "severity", "message"]]
    for row in rows:
        data.append([row["alert_time"], row["vehicle_id"], row["severity"], row["message"]])
    return csv_response("alerts.csv", data)


@app.get("/export/violations.csv")
def export_violations_csv():
    rows = db_query("SELECT event_time, vehicle_id, reason, points, severity, lat, lon, risk_after FROM violations ORDER BY id DESC")
    data = [["event_time", "vehicle_id", "reason", "points", "severity", "lat", "lon", "risk_after"]]
    for row in rows:
        data.append([
            row["event_time"],
            row["vehicle_id"],
            row["reason"],
            row["points"],
            row["severity"],
            row["lat"],
            row["lon"],
            row["risk_after"],
        ])
    return csv_response("violations.csv", data)


@app.get("/export/trips.csv")
def export_trips_csv():
    rows = db_query("SELECT updated_at, vehicle_id, route_id, route_name, trips_total, trips_24h, risk, prediction_label, predicted_weight, average_weight, overload_flag FROM vehicle_snapshots ORDER BY vehicle_id ASC")
    data = [["updated_at", "vehicle_id", "route_id", "route_name", "trips_total", "trips_24h", "risk", "prediction_label", "predicted_weight", "average_weight", "overload_flag"]]
    for row in rows:
        data.append([
            row["updated_at"],
            row["vehicle_id"],
            row["route_id"],
            row["route_name"],
            row["trips_total"],
            row["trips_24h"],
            row["risk"],
            row["prediction_label"],
            row.get("predicted_weight"),
            row.get("average_weight"),
            row.get("overload_flag"),
        ])
    return csv_response("trips.csv", data)


@app.get("/api/stats")
def api_stats():
    run_background_checks(utc_now())
    rows = scope_rows_by_user(build_lorry_rows(), current_user())
    data = {
        "vehicles": len(rows),
        "trips": int(sum(int(item.get("trips", 0)) for item in rows)),
        "dangerous": int(sum(1 for item in rows if float(item.get("risk", 0.0)) >= 80.0)),
        "suspicious": int(sum(1 for item in rows if 50.0 <= float(item.get("risk", 0.0)) < 80.0)),
    }
    return jsonify(data)


@app.post("/camera")
def receive_camera_event():
    payload = request.get_json(force=True, silent=False)
    data = CameraPayload(payload)
    route_id = data.route_id or "route_1"

    nearby_active = 0
    now = utc_now()
    for state in vehicle_state.values():
        if state.get("route_id") != route_id:
            continue
        if state.get("last_lat") is None or state.get("last_lon") is None or not state.get("last_update"):
            continue
        if (now - to_aware(datetime.fromisoformat(state["last_update"]))).total_seconds() > 8:
            continue
        if haversine_meters(data.lat, data.lon, state["last_lat"], state["last_lon"]) <= 250:
            nearby_active += 1

    mismatch = abs(nearby_active - data.truck_count)
    event = {
        "camera_id": data.camera_id,
        "route_id": route_id,
        "lat": data.lat,
        "lon": data.lon,
        "truck_count": data.truck_count,
        "nearby_active": nearby_active,
        "mismatch": mismatch,
        "camera_confidence": round(get_confidence("normal", "camera"), 3),
        "weather": CONTROL_STATE.get("weather", "clear"),
        "time": data.timestamp.isoformat(),
    }
    camera_events.append(event)

    db_execute(
        "INSERT INTO camera_events(event_time, camera_id, route_id, lat, lon, truck_count, nearby_active, mismatch) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event["time"],
            event["camera_id"],
            event["route_id"],
            event["lat"],
            event["lon"],
            event["truck_count"],
            event["nearby_active"],
            event["mismatch"],
        ),
    )

    mismatch_threshold = 2 if event["camera_confidence"] >= 0.55 else 3
    if mismatch >= mismatch_threshold:
        append_alert(
            "camera",
            f"Camera {data.camera_id} mismatch: seen={data.truck_count} gps={nearby_active}",
            severity="warning",
            meta=event,
        )

    return jsonify(event)


@app.get("/api/camera/events")
def api_camera_events():
    limit = int(request.args.get("limit", 40))
    return jsonify(list(reversed(camera_events[-max(1, min(limit, 200)):])))


@app.get("/")
def home():
    return render_template("index.html", web_name="Tharani Sengol")

@app.get("/dashboard")
def dashboard_page():
    return render_template("dashboard.html", web_name="Tharani Sengol")


@app.get("/vehicles")
def vehicles_page():
    return render_template("vehicles.html", web_name="Tharani Sengol")


@app.get("/vehicles/<vehicle_id>")
def vehicle_detail_page(vehicle_id: str):
    return render_template("vehicle_detail.html", vehicle_id=vehicle_id, web_name="Tharani Sengol")


@app.get("/alerts")
def alerts_page():
    rows = db_query("SELECT * FROM alerts ORDER BY id DESC LIMIT 200")
    return render_template("alerts.html", rows=rows, web_name="Tharani Sengol")


REGULATION_DOCS = [
    {
        "id": "tn_minor_mineral_rule_36_1",
        "title": "Tamil Nadu Minor Mineral Concession Rules, 1959 - Rule 36(1) (Permit Requirement)",
        "source": "Tamil Nadu Minor Mineral Concession Rules, 1959",
        "text": "No person shall undertake any mining operations in any area, except under and in accordance with the terms and conditions of a quarrying permit or a quarrying lease granted under these rules. Any mining without a lease/permit is illegal and subject to heavy penal actions."
    },
    {
        "id": "tn_minor_mineral_rule_36_5",
        "title": "Tamil Nadu Minor Mineral Concession Rules, 1959 - Rule 36(5) (Seizure of Vehicles)",
        "source": "Tamil Nadu Minor Mineral Concession Rules, 1959",
        "text": "Seizure of vehicles. Any officer authorized by the State Government may seize any vehicle, equipment, tool, or animal found engaged in quarrying or transporting any mineral without a valid permit."
    },
    {
        "id": "tn_minor_mineral_rule_36a",
        "title": "Tamil Nadu Minor Mineral Concession Rules, 1959 - Rule 36A (Transport Permit)",
        "source": "Tamil Nadu Minor Mineral Concession Rules, 1959",
        "text": "Transport Permit Requirement. All minor minerals transported from any quarrying area must be accompanied by a valid Transit Pass (Permit) issued by the Assistant Director of Geology and Mining of the concerned district."
    },
    {
        "id": "mmdr_act_section_21_1",
        "title": "Mines and Minerals Act, 1957 - Section 21(1) (Illegal Mining Penalties)",
        "source": "Mines and Minerals (Development and Regulation) Act, 1957",
        "text": "Whoever knowingly contravenes the provisions of sub-section (1) or sub-section (1A) of section 4 shall be punishable with imprisonment for a term which may extend to five years and with fine which may extend to five lakh rupees per hectare."
    },
    {
        "id": "mmdr_act_section_21_4",
        "title": "Mines and Minerals Act, 1957 - Section 21(4) (Power of Confiscation)",
        "source": "Mines and Minerals (Development and Regulation) Act, 1957",
        "text": "Power of court to confiscate. Any tool, device, vehicle, or vessel used in illegal mining operations may be confiscated by the order of the competent court."
    },
    {
        "id": "tn_transit_pass_validity",
        "title": "Tamil Nadu Transit Pass - Expiry and Validity",
        "source": "Tamil Nadu Transit Pass Rules",
        "text": "Every transit pass is issued with a specific start time and end time. Typically, a transit pass is valid only for 12 hours or as stamped on the pass. Transporting minerals with an expired pass is considered illegal transportation of minor minerals."
    },
    {
        "id": "tn_transit_pass_route",
        "title": "Tamil Nadu Transit Pass - Route Specifications",
        "source": "Tamil Nadu Transit Pass Rules",
        "text": "The transit pass specifies the approved route from the quarry/mine to the destination (e.g., crushing unit or construction site). Drivers must strictly follow the approved route. Deviation from this route without prior authorization constitutes a compliance violation."
    },
    {
        "id": "mv_act_section_113",
        "title": "Motor Vehicles Act, 1988 - Section 113 (Overloading Limits)",
        "source": "Motor Vehicles Act, 1988",
        "text": "No person shall drive any motor vehicle in any public place unless it complies with the registered gross vehicle weight (GVW) and axle weight limit. Carrying weight above the registered payload is an offense."
    },
    {
        "id": "mv_act_section_194",
        "title": "Motor Vehicles Act, 1988 - Section 194 (Overloading Penalties)",
        "source": "Motor Vehicles Act, 1988",
        "text": "Driving an overloaded vehicle is subject to a minimum fine of Rs. 20,000, plus an additional fine of Rs. 2,000 per extra ton. The vehicle may also be detained and offloaded at the owner's expense."
    },
    {
        "id": "tn_night_mining_prohibitions",
        "title": "Night Mining Prohibitions in Tamil Nadu",
        "source": "Tamil Nadu Environmental Clearance Conditions",
        "text": "Under environmental clearance conditions and local district administration orders, quarrying operations and transport of minor minerals are generally prohibited during night hours (typically between 6:00 PM and 6:00 AM) in sensitive ecological zones or residential areas."
    },
    {
        "id": "tn_sand_mining_gps_mandate",
        "title": "Tamil Nadu Sand Mining Policy - GPS Tracker Mandate",
        "source": "Tamil Nadu Sand Mining Policy",
        "text": "All trucks engaged in transporting river sand or quarry sand must be fitted with an approved GPS/AIS-140 tracking device. The device must remain active and transmit location data in real time to the state monitoring center."
    },
    {
        "id": "tn_gps_tampering_penalty",
        "title": "Penalty for GPS Telemetry Tampering",
        "source": "Tamil Nadu Mining Transport Rules",
        "text": "Tampering, disconnecting, or shielding the GPS tracker on mineral transport vehicles is a serious violation. It leads to immediate suspension of the vehicle's transport permit and a fine of up to Rs. 10,000 for the first offense."
    },
    {
        "id": "tn_transit_pass_qr_verification",
        "title": "Tamil Nadu Mineral Transit Pass QR Code Verification",
        "source": "Tamil Nadu Geology and Mining Inspection Guidelines",
        "text": "Checking officers utilize a mobile app to scan the QR code printed on the transit pass. If the QR code is invalid, missing, or does not match the database record, the vehicle is detained under suspicion of transporting illegal minerals."
    },
    {
        "id": "tn_quarry_boundary_restrictions",
        "title": "Quarry Boundary Restrictions (Geofencing)",
        "source": "Tamil Nadu Land Revenue and Mining Rules",
        "text": "Quarry operators must establish boundary pillars with GPS coordinates marked. Extracting minerals or loading vehicles outside the demarcated quarry lease boundary is treated as theft under the Indian Penal Code and illegal mining."
    },
    {
        "id": "tn_mineral_permit_quantity_limits",
        "title": "Tamil Nadu Mineral Permit Quantity Limits",
        "source": "Tamil Nadu Geology and Mining Permit Rules",
        "text": "A quarry permit specifies the maximum volume or tonnage of mineral that can be excavated and transported. Exceeding this permitted quantity is a violation, and the excess mineral will be confiscated, accompanied by a penalty equal to 100% of the mineral value."
    },
    {
        "id": "tn_ec_trip_limits",
        "title": "Environmental Clearance (EC) Trip Limits",
        "source": "Tamil Nadu Environmental Compliance Rules",
        "text": "Environmental clearances set annual and daily limits on quarry production and the number of trips allowed. Operators must not exceed these limits, and the transit pass system will automatically lock/deactivate if the daily trip limit is exceeded."
    },
    {
        "id": "tn_river_sand_transport_rules",
        "title": "Tamil Nadu River Sand Transport Rules",
        "source": "Tamil Nadu sand transport rules",
        "text": "Transporting river sand requires a special pink-colored transit pass issued online by the Public Works Department (PWD). Sand transport is restricted to designated routes and is strictly banned during night hours."
    },
    {
        "id": "tn_vehicle_fitness_certificate",
        "title": "Vehicle Fitness Certificate (FC) for Mineral Transport",
        "source": "Tamil Nadu Commercial Transport Regulations",
        "text": "All commercial vehicles transporting minerals must possess a valid Fitness Certificate. Transporting heavy minerals like stone or sand in an unfit vehicle poses public safety hazards and is subject to immediate seizure."
    },
    {
        "id": "tn_transit_pass_mismatch_penalties",
        "title": "Transit Pass Mismatch Penalties",
        "source": "Tamil Nadu Mining Transport Rules",
        "text": "If the registration number of the vehicle transporting minerals does not match the vehicle number printed on the transit pass, it is treated as a major violation (permit misuse) and subject to vehicle detention and a fine of Rs. 15,000."
    },
    {
        "id": "tn_mining_check_posts",
        "title": "Tamil Nadu Geology and Mining Check Posts",
        "source": "Tamil Nadu Mining Enforcement Guidelines",
        "text": "Check posts are established at key transit points and district borders. All mineral-carrying trucks must stop for inspection and permit verification. Evading a check post is a punishable offense."
    },
    {
        "id": "tn_mining_permit_renewal",
        "title": "Mining Permit Renewal Grace Period",
        "source": "Tamil Nadu Minor Mineral Rules",
        "text": "There is no grace period for expired quarrying leases or permits. Mining or transporting minerals even one day after expiry is illegal and subject to the same penalties as unauthorized mining."
    },
    {
        "id": "tn_bulk_transport_permits",
        "title": "Bulk Transport Permits (Tamil Nadu)",
        "source": "Tamil Nadu Mining Administration Rules",
        "text": "Large-scale construction projects may obtain bulk transport permits. However, each individual truck must still carry a separate transit pass generated against the bulk permit for each trip."
    },
    {
        "id": "tn_safety_equipment_for_mineral_trucks",
        "title": "Safety Equipment for Mineral Trucks",
        "source": "Tamil Nadu Pollution Control Board Directives",
        "text": "Trucks carrying minor minerals must cover the payload with a tarpaulin sheet to prevent dust emission and spillage during transit. Failure to cover the cargo results in a fine of Rs. 2,000 under pollution control norms."
    },
    {
        "id": "tn_dmf_trust_contributions",
        "title": "District Mineral Foundation (DMF) Trust",
        "source": "Tamil Nadu Minor Mineral Concession Rules",
        "text": "A percentage of the seigniorage fee paid by quarry operators goes to the DMF. Failure to contribute to the DMF is a breach of lease terms and may lead to lease termination."
    },
    {
        "id": "tn_stockyard_permit_requirements",
        "title": "Stockyard Permit Requirements",
        "source": "Tamil Nadu Mineral Storage Rules",
        "text": "Storing minerals at any location outside the leasehold area requires a stockyard license. Storing minerals without a license is treated as illegal storage and the mineral is subject to seizure."
    },
    {
        "id": "tn_geological_survey_inspections",
        "title": "Geological Survey Inspections",
        "source": "Tamil Nadu Mining Plan Regulations",
        "text": "Officers of the Geology and Mining Department carry out periodic physical inspections of quarries to verify depth, slope, and boundary pillars. Violations of mining plan parameters lead to suspension of operations."
    },
    {
        "id": "tn_district_collector_powers",
        "title": "Tamil Nadu District Collector Powers",
        "source": "Tamil Nadu Minor Mineral Concession Rules",
        "text": "The District Collector has the authority to suspend quarrying leases, seal illegal mines, and impose compounding penalties for minor mineral violations within the district."
    },
    {
        "id": "tn_compounding_mining_offenses",
        "title": "Compounding of Mining Offenses",
        "source": "Tamil Nadu Minor Mineral Concession Rules",
        "text": "The Department of Geology and Mining may allow compounding of minor offenses on payment of seigniorage fee, cost of mineral, and a compounding fee. Repeat offenses are not compoundable and must be prosecuted in court."
    },
    {
        "id": "tn_illegal_sand_storage_penalties",
        "title": "Illegal Sand Storage Penalties",
        "source": "Tamil Nadu Minor Mineral Concession Rules",
        "text": "Storing sand or gravel near riverbeds without a valid stockyard license is a cognizable offense. The offender faces imprisonment up to two years under Section 21 of the MMDR Act."
    },
    {
        "id": "tn_water_spraying_mandate",
        "title": "Water Spraying Mandate in Quarries",
        "source": "Tamil Nadu environmental compliance",
        "text": "To control dust, quarry operators must spray water on haul roads and loading points. Non-compliance results in warnings and eventual suspension of mining by the Pollution Control Board."
    },
    {
        "id": "tn_blasting_permit_regulations",
        "title": "Blasting Permit Regulations",
        "source": "Tamil Nadu Explosives Control Rules",
        "text": "Using explosives in quarries requires a blasting license from the Controller of Explosives. Blasting is strictly prohibited during night hours (6:00 PM to 6:00 AM) and within 100 meters of public roads or residential structures."
    },
    {
        "id": "tn_revenue_recovery_act_mining",
        "title": "Revenue Recovery Act in Mining",
        "source": "Tamil Nadu Revenue Recovery Act",
        "text": "Unpaid seigniorage fees, royalties, or penalties imposed for illegal mining are recovered as arrears of land revenue under the Revenue Recovery Act, which includes attachment of property."
    },
    {
        "id": "tn_etransit_pass_lockouts",
        "title": "Tamil Nadu e-Transit Pass Lockouts",
        "source": "Tamil Nadu Geology and Mining System Rules",
        "text": "The online system automatically locks transit pass generation for vehicles associated with unpaid fines, repeated route deviations, or blacklisted drivers."
    },
    {
        "id": "tn_private_land_quarry_permits",
        "title": "Private Land Quarry Permits",
        "source": "Tamil Nadu Revenue Land Quarry Rules",
        "text": "Quarrying minor minerals on patta (private) land still requires permission from the District Collector and payment of seigniorage fee. Excavation without permit is illegal."
    },
    {
        "id": "tn_transit_pass_cancellations",
        "title": "Tamil Nadu Mineral Transit Pass Cancellations",
        "source": "Tamil Nadu Transit Pass Rules",
        "text": "A transit pass once generated cannot be cancelled after the vehicle has exited the quarry gate. Any attempt to reuse a cancelled pass is treated as transport without permit."
    }
]

RAG_MODEL = None
RAG_INDEX = None
RAG_CHUNKS = []
RAG_TFIDF_VECTORIZER = None
RAG_TFIDF_MATRIX = None


def populate_rag_corpus_db():
    for doc in REGULATION_DOCS:
        db_execute(
            """
            INSERT OR IGNORE INTO rag_documents (id, title, source, text, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (doc["id"], doc["title"], doc["source"], doc["text"], utc_now().isoformat())
        )


def generate_rag_chunks_db():
    docs = db_query("SELECT id, text FROM rag_documents")
    for doc in docs:
        db_execute(
            """
            INSERT OR IGNORE INTO rag_chunks (id, doc_id, chunk_index, text, embedding_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (f"{doc['id']}_c0", doc["id"], 0, doc["text"], None)
        )


def init_rag_system():
    global RAG_MODEL, RAG_INDEX, RAG_CHUNKS, RAG_TFIDF_VECTORIZER, RAG_TFIDF_MATRIX
    print("Initializing RAG System...")
    try:
        conn = get_db_connection()
        count = conn.execute("SELECT COUNT(*) FROM rag_documents").fetchone()[0]
        conn.close()

        if count == 0:
            print("Populating RAG corpus to DB...")
            populate_rag_corpus_db()

        chunks_count = db_query("SELECT COUNT(*) AS cnt FROM rag_chunks")[0]["cnt"]
        if chunks_count == 0:
            print("Generating RAG chunks in DB...")
            generate_rag_chunks_db()

        chunks_rows = db_query("SELECT doc_id, chunk_index, text FROM rag_chunks")
        RAG_CHUNKS = []
        for row in chunks_rows:
            doc_rows = db_query("SELECT title FROM rag_documents WHERE id = ?", (row["doc_id"],))
            title = doc_rows[0]["title"] if doc_rows else "Regulation"
            RAG_CHUNKS.append({
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "text": row["text"],
                "title": title
            })

        print(f"Loaded {len(RAG_CHUNKS)} chunks for RAG.")

        # Try loading SentenceTransformer + FAISS first
        try:
            import ssl
            ssl._create_default_https_context = ssl._create_unverified_context
            from sentence_transformers import SentenceTransformer
            import faiss
            import numpy as np

            RAG_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
            texts = [c["text"] for c in RAG_CHUNKS]
            if texts:
                embedded = RAG_MODEL.encode(texts)
                embeddings_np = np.array(embedded).astype('float32')
                dimension = embeddings_np.shape[1]
                RAG_INDEX = faiss.IndexFlatL2(dimension)
                RAG_INDEX.add(embeddings_np)
                print("FAISS Index initialized and loaded successfully.")
        except Exception:
            # Fallback to scikit-learn TF-IDF Vectorizer
            from sklearn.feature_extraction.text import TfidfVectorizer
            texts = [c["text"] for c in RAG_CHUNKS]
            if texts:
                RAG_TFIDF_VECTORIZER = TfidfVectorizer(stop_words='english')
                RAG_TFIDF_MATRIX = RAG_TFIDF_VECTORIZER.fit_transform(texts)
                print("TF-IDF RAG Vectorizer initialized successfully (scikit-learn fallback).")

    except Exception as e:
        print(f"RAG system initialization failed: {e}")


def classify_rag_intent(question: str) -> str:
    normalized = question.strip().lower()
    mining_keywords = [
        "truck", "lorry", "vehicle", "route", "permit", "rule", "law", "penalty", "fine", 
        "seize", "seizure", "convoy", "spoof", "overload", "weight", "mine", "quarry", 
        "sand", "mineral", "deviation", "alert", "threat", "risk", "trichy", "salem", 
        "coimbatore", "chennai", "tamil nadu", "tn", "concession", "act", "transpor", "compliance",
        "violation", "alert"
    ]
    if not any(kw in normalized for kw in mining_keywords):
        return "out_of_scope"

    live_keywords = [
        "high risk", "dangerous", "suspicious", "active", "where is", "current", "live",
        "right now", "status of", "telemetry", "latest", "at risk", "threat score of", "top risk",
        "which vehicles", "which trucks", "are overloaded", "is overloaded", "are deviating", "is deviating",
        "recent alert", "latest alert", "recent violation", "latest violation", "active alert", "check permit", "permit details", "permit of"
    ]
    if any(kw in normalized for kw in live_keywords) or re.search(r"\b(?:vehicle|truck|lorry)\s*[_-]?\d+\b", normalized):
        return "live_data"

    return "documents"


def answer_rag_question(question: str) -> dict:
    intent = classify_rag_intent(question)
    
    if intent == "out_of_scope":
        return {
            "answer": "This question is outside the scope of GeoGuard's monitoring. I can help you with questions about vehicle alerts, route compliance, permit status, and Tamil Nadu mining regulations.",
            "sources": [],
            "grounded_in": "documents"
        }
        
    if intent == "live_data":
        normalized = question.lower()
        
        # 1. Recent Alerts query tool
        if "recent alert" in normalized or "latest alert" in normalized or "active alert" in normalized:
            recent_alerts = db_query("SELECT alert_time, vehicle_id, severity, message FROM alerts ORDER BY alert_time DESC, id DESC LIMIT 5")
            if recent_alerts:
                answer = "Here are the latest 5 alerts registered in the system:\n"
                for idx, a in enumerate(recent_alerts, 1):
                    answer += f"{idx}. {a['alert_time']} - Lorry {a['vehicle_id']}: {a['message']} ({a['severity'].upper()})\n"
                return {
                    "answer": answer,
                    "sources": recent_alerts,
                    "grounded_in": "live_data"
                }
            else:
                return {
                    "answer": "No recent alerts have been recorded in the database.",
                    "sources": [],
                    "grounded_in": "live_data"
                }

        # 2. Recent Violations query tool
        if "recent violation" in normalized or "latest violation" in normalized or "compliance violation" in normalized:
            recent_viols = db_query("SELECT event_time, vehicle_id, reason, points, severity FROM violations ORDER BY event_time DESC, id DESC LIMIT 5")
            if recent_viols:
                answer = "Here are the latest 5 compliance violations recorded:\n"
                for idx, v in enumerate(recent_viols, 1):
                    answer += f"{idx}. {v['event_time']} - Lorry {v['vehicle_id']} violated due to: {v['reason']} (Points: {v['points']}, Severity: {v.get('severity', 'warning')})\n"
                return {
                    "answer": answer,
                    "sources": recent_viols,
                    "grounded_in": "live_data"
                }
            else:
                return {
                    "answer": "No violations have been recorded in the database.",
                    "sources": [],
                    "grounded_in": "live_data"
                }

        # 3. Permits details check tool
        if "permit" in normalized:
            vehicle_match = re.search(r"\b(?:vehicle|truck|lorry)\s*[_-]?(\d+)\b", normalized)
            vehicle_key = f"truck_{int(vehicle_match.group(1))}" if vehicle_match else None
            if vehicle_key:
                permit_rows = db_query("SELECT permit_id, vehicle_number, approved_route, max_quantity, used_quantity, max_trips, completed_trips, status FROM permits WHERE vehicle_number = ? OR permit_id = ? OR vehicle_number LIKE ?", (vehicle_key, vehicle_key, f"%{vehicle_key}%"))
                if permit_rows:
                    p = permit_rows[0]
                    answer = f"Permit Details for {vehicle_key}:\nPermit ID: {p['permit_id']}\nApproved Route: {p['approved_route']}\nQuantity: {p['used_quantity']}/{p['max_quantity']} tons used\nTrips: {p['completed_trips']}/{p['max_trips']} completed\nStatus: {p['status']}"
                    return {
                        "answer": answer,
                        "sources": permit_rows,
                        "grounded_in": "live_data"
                    }
            active_permits = db_query("SELECT permit_id, vehicle_number, approved_route, max_trips, completed_trips, status FROM permits LIMIT 5")
            if active_permits:
                answer = "Here are some of the active permits registered in the system:\n"
                for idx, p in enumerate(active_permits, 1):
                    answer += f"{idx}. Vehicle: {p['vehicle_number']} | Route: {p['approved_route']} | Trips: {p['completed_trips']}/{p['max_trips']} | Status: {p['status']}\n"
                return {
                    "answer": answer,
                    "sources": active_permits,
                    "grounded_in": "live_data"
                }
            else:
                return {
                    "answer": "No permits are currently configured in the system.",
                    "sources": [],
                    "grounded_in": "live_data"
                }

        # 4. Fallback live vehicle lookup
        rows = build_lorry_rows()
        vehicle_match = re.search(r"\b(?:vehicle|truck|lorry)\s*[_-]?(\d+)\b", normalized)
        vehicle_key = f"truck_{int(vehicle_match.group(1))}" if vehicle_match else None
        
        vehicle_hit = None
        if vehicle_key:
            vehicle_hit = next((row for row in rows if row["vehicle_id"].lower() == vehicle_key), None)
            
        if vehicle_hit:
            behavior = vehicle_hit.get("driver_behavior", {})
            forecast = vehicle_hit.get("time_series_forecast", {})
            answer = (
                f"Live Update for {vehicle_hit['vehicle_id']}: Currently in {vehicle_hit['district']} on route {vehicle_hit['route_id']}. "
                f"Risk is {vehicle_hit['risk']} ({vehicle_hit['risk_level']}) with a final threat score of {vehicle_hit['final_threat_score']}. "
                f"Predicted weight is {vehicle_hit['predicted_weight']:.1f} tons (overload: {'YES' if vehicle_hit['overload_flag'] else 'NO'}). "
                f"Telemetry is active. Anomaly score: {vehicle_hit['anomaly_score']}. "
                f"Driver Behavior: harsh braking={behavior.get('harsh_braking', 0)}, fluctuation={behavior.get('speed_fluctuation', 0)}. "
                f"Forecast: future route {forecast.get('future_route', 'n/a')}, load {forecast.get('future_load_tons', 0)} tons."
            )
            return {
                "answer": answer,
                "sources": [vehicle_hit],
                "grounded_in": "live_data"
            }
            
        if any(kw in normalized for kw in ["high risk", "dangerous", "threat", "suspicious", "overload"]):
            high_threat_trucks = [r for r in rows if r["final_threat_score"] >= 45 or r["risk"] >= 45][:5]
            if high_threat_trucks:
                answer = "The following active trucks are classified as high risk or suspicious right now:\n"
                for idx, t in enumerate(high_threat_trucks, 1):
                    answer += f"{idx}. {t['vehicle_id']} in {t['district']} (threat: {t['final_threat_score']}, risk: {t['risk']}, weight: {t['predicted_weight']:.1f}t, overload: {'YES' if t['overload_flag'] else 'NO'})\n"
                return {
                    "answer": answer,
                    "sources": high_threat_trucks,
                    "grounded_in": "live_data"
                }
            else:
                return {
                    "answer": "All monitored vehicles are currently safe and within normal compliance parameters.",
                    "sources": [],
                    "grounded_in": "live_data"
                }
                
        return {
            "answer": f"Fleet Summary: There are currently {len(rows)} active trucks. Average final threat score is {compute_digital_twin_summary().get('avg_final_threat', 0.0)}.",
            "sources": rows[:5],
            "grounded_in": "live_data"
        }
        
    if (RAG_INDEX is None or RAG_MODEL is None) and (RAG_TFIDF_VECTORIZER is None or RAG_TFIDF_MATRIX is None):
        return {
            "answer": "The RAG assistant is currently loading or unavailable. General Rules: Transporting minerals without a permit violates Rule 36 of the TN Minor Mineral Concession Rules.",
            "sources": [],
            "grounded_in": "documents"
        }
        
    try:
        matched_sources = []
        if RAG_INDEX is not None and RAG_MODEL is not None:
            import numpy as np
            query_emb = RAG_MODEL.encode([question])
            query_np = np.array(query_emb).astype('float32')
            
            distances, indices = RAG_INDEX.search(query_np, k=3)
            for dist, idx in zip(distances[0], indices[0]):
                if idx >= 0 and idx < len(RAG_CHUNKS):
                    chunk = RAG_CHUNKS[idx]
                    matched_sources.append({
                        "title": chunk["title"],
                        "text": chunk["text"],
                        "similarity": round(float(1.0 / (1.0 + dist)), 3)
                    })
        elif RAG_TFIDF_VECTORIZER is not None and RAG_TFIDF_MATRIX is not None:
            from sklearn.metrics.pairwise import cosine_similarity
            query_vec = RAG_TFIDF_VECTORIZER.transform([question])
            sims = cosine_similarity(query_vec, RAG_TFIDF_MATRIX)[0]
            top_indices = sims.argsort()[::-1][:3]
            for idx in top_indices:
                if sims[idx] > 0.0:
                    chunk = RAG_CHUNKS[idx]
                    matched_sources.append({
                        "title": chunk["title"],
                        "text": chunk["text"],
                        "similarity": round(float(sims[idx]), 3)
                    })

        if matched_sources:
            best_match = matched_sources[0]
            answer = f"According to {best_match['title']}: \"{best_match['text']}\""
            if len(matched_sources) > 1:
                second = matched_sources[1]
                answer += f"\n\nIn addition, referring to {second['title']}: \"{second['text']}\""
            return {
                "answer": answer,
                "sources": matched_sources,
                "grounded_in": "documents"
            }
    except Exception as e:
        return {
            "answer": f"Error during RAG search: {e}",
            "sources": [],
            "grounded_in": "documents"
        }
        
    return {
        "answer": "No relevant regulation document was found for your query. Please ask a question about permits, overloading limits, route deviation penalties, or night mining rules.",
        "sources": [],
        "grounded_in": "documents"
    }


@app.post("/api/rag/chat")
def api_rag_chat():
    payload = request.get_json(force=True, silent=True) or {}
    question = str(payload.get("question", payload.get("query", ""))).strip()
    if not question:
        return jsonify({
            "answer": "Please ask a question about Tamil Nadu mining regulations, overloading fines, permit trip limits, or active vehicles.",
            "sources": [],
            "grounded_in": "documents"
        })
    response = answer_rag_question(question)
    return jsonify(response)


@app.get("/rag-assistant")
def rag_assistant_page():
    return render_template("rag_assistant.html", web_name="Tharani Sengol")


@app.get("/agentic-ai")
def agentic_ai_page():
    return render_template("agentic_ai.html", web_name="Tharani Sengol")


@app.get("/analytics")
def analytics_page():
    top_hotspots = db_query(
        """
        SELECT reason, ROUND(AVG(lat), 5) AS avg_lat, ROUND(AVG(lon), 5) AS avg_lon, COUNT(*) AS hits
        FROM violations
        WHERE lat IS NOT NULL AND lon IS NOT NULL
        GROUP BY reason
        ORDER BY hits DESC
        LIMIT 10
        """
    )
    return render_template("analytics.html", hotspots=top_hotspots, web_name="Tharani Sengol")


@app.get("/ai-prediction")
def ai_prediction_page():
    return render_template("ai_prediction.html", web_name="Tharani Sengol")


@app.get("/module-predictions")
def module_predictions_page():
    return render_template("module_predictions.html", web_name="Tharani Sengol")


@app.get("/driver-behavior")
def driver_behavior_page():
    return render_template("driver_behavior.html", web_name="Tharani Sengol")


@app.get("/admin")
def admin_page():
    rows = db_query("SELECT * FROM vehicle_config ORDER BY vehicle_id ASC")
    return render_template("admin.html", rows=rows, web_name="Tharani Sengol")


@app.get("/health")
def health():
    return jsonify({"ok": True, "db": str(DB_PATH)})


@app.context_processor
def inject_auth_user_context():
    return {"auth_user": safe_user(current_user())}


CLASSIFIER_MODEL_PATH = BASE_DIR / "illegal_mining_rf.pkl"
CLASSIFIER_MODEL = None


def load_classifier_model():
    global CLASSIFIER_MODEL
    if joblib is None or not CLASSIFIER_MODEL_PATH.exists():
        CLASSIFIER_MODEL = None
        return None
    try:
        CLASSIFIER_MODEL = joblib.load(CLASSIFIER_MODEL_PATH)
    except Exception:
        CLASSIFIER_MODEL = None
    return CLASSIFIER_MODEL


init_db()
load_user_store()
init_runtime_config()
init_system_config()
load_weight_model()
load_classifier_model()
init_rag_system()


if __name__ == "__main__":
    start_internal_simulator()
    app.run(host="127.0.0.1", port=8000, debug=False)
