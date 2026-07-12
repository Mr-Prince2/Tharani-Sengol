from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone

import requests

BASE_URL = os.getenv("THARANI_BASE_URL", "http://127.0.0.1:8000")
LOGIN_API_URL = f"{BASE_URL}/api/auth/login"
CONTROL_API_URL = f"{BASE_URL}/api/control-state"
ROUTES_API_URL = f"{BASE_URL}/api/routes"
GPS_API_URL = f"{BASE_URL}/gps"
SIM_USERNAME = os.getenv("THARANI_SIM_USERNAME", "admin")
SIM_PASSWORD = os.getenv("THARANI_SIM_PASSWORD", "admin123")

SIM_FLEET_SIZE = max(5, int(os.getenv("THARANI_SIM_FLEET_SIZE", os.getenv("THARANI_FLEET_SIZE", "5"))))
# Lowered floor + lowered default so the sim ticks noticeably faster out of the box.
SIM_SLEEP_SECONDS = max(0.05, float(os.getenv("THARANI_SIM_SLEEP_SECONDS", "0.05")))

SHIFT_TRAFFIC_FACTOR = {
    "morning_peak": 1.25,
    "noon_low": 0.70,
    "evening_peak": 1.20,
    "night_low": 0.80,
}

# Weather now actually drives behaviour instead of being fetched and ignored.
WEATHER_EFFECTS = {
    "clear": {"traffic": 1.00, "noise": 0.05},
    "hot": {"traffic": 1.05, "noise": 0.08},
    "rain": {"traffic": 1.35, "noise": 0.22},
    "storm": {"traffic": 1.60, "noise": 0.35},
    "fog": {"traffic": 1.30, "noise": 0.28},
}


def derive_shift_from_time(now: datetime) -> str:
    """Pick the active shift from the real wall-clock hour instead of a fixed default."""
    hour = now.hour
    if 6 <= hour < 10:
        return "morning_peak"
    if 10 <= hour < 16:
        return "noon_low"
    if 16 <= hour < 20:
        return "evening_peak"
    return "night_low"


def derive_weather_from_date(now: datetime) -> str:
    """Seasonal default for Tamil Nadu (India) so weather adapts to the current date
    when the control API doesn't override it."""
    month = now.month
    if month in (6, 7, 8, 9):
        return "rain"          # SW monsoon
    if month in (10, 11):
        return "storm"         # NE monsoon / cyclone season
    if month in (3, 4, 5):
        return "hot"
    return "clear"


def current_dynamic_defaults() -> dict:
    now = datetime.now()
    return {
        "active_shift": derive_shift_from_time(now),
        "anomaly_factor": 1.0,
        "traffic_factor": 1.0,
        "gps_noise": 0.1,
        "weather": derive_weather_from_date(now),
        "scenario": "suspicious_day",
    }


def fetch_control_state(session, fallback):
    try:
        response = session.get(CONTROL_API_URL, timeout=2)
        if response.status_code >= 400:
            return fallback
        data = response.json()
        return {
            "active_shift": data.get("active_shift", fallback.get("active_shift")),
            "anomaly_factor": float(data.get("anomaly_factor", fallback.get("anomaly_factor", 1.0))),
            "traffic_factor": float(data.get("traffic_factor", fallback.get("traffic_factor", 1.0))),
            "gps_noise": float(data.get("gps_noise", fallback.get("gps_noise", 0.1))),
            "weather": data.get("weather", fallback.get("weather")),
            "scenario": data.get("scenario", fallback.get("scenario", "suspicious_day")),
        }
    except requests.RequestException:
        return fallback


def fetch_routes(session):
    try:
        response = session.get(ROUTES_API_URL, timeout=3)
        if response.status_code >= 400:
            return {}
        data = response.json()
        if not isinstance(data, dict):
            return {}

        sanitized = {}
        for route_id, route in data.items():
            if isinstance(route, dict) and isinstance(route.get("path"), list):
                sanitized[route_id] = route
        return sanitized
    except requests.RequestException:
        return {}


def ensure_auth(session, username: str, password: str) -> bool:
    try:
        response = session.post(
            LOGIN_API_URL,
            json={"username": username, "password": password},
            timeout=3,
        )
        if response.status_code != 200:
            return False
        payload = response.json()
        token = str(payload.get("token", "")).strip()
        if not token:
            return False
        session.headers.update({"Authorization": f"Bearer {token}"})
        return True
    except requests.RequestException:
        return False


def interpolate_route(points, steps_per_segment=8):
    smooth_route = []
    for index in range(len(points) - 1):
        start_lat, start_lon = points[index]
        end_lat, end_lon = points[index + 1]

        for step in range(steps_per_segment):
            ratio = step / float(steps_per_segment)
            smooth_route.append((
                start_lat + (end_lat - start_lat) * ratio,
                start_lon + (end_lon - start_lon) * ratio,
            ))

    smooth_route.append(points[-1])
    return smooth_route


def profile_for_truck(index: int, rng: random.Random) -> str:
    """Deterministically assign profile based on vehicle index to match backend alignment."""
    phase = index % 10
    if phase in (0, 1, 2):
        return "safe"
    if phase in (3, 4, 5, 6, 7):
        return "normal"
    return "high_risk"


def build_sim_fleet(route_defs: dict, fleet_size: int, rng: random.Random):
    route_ids = sorted(route_defs.keys())
    if not route_ids:
        return {}

    fleet = {}
    for idx in range(1, fleet_size + 1):
        vehicle_id = f"truck_{idx}"
        route_id = route_ids[(idx - 1) % len(route_ids)]
        route_path = route_defs[route_id].get("path", [])
        if len(route_path) < 2:
            continue

        # Fewer interpolation steps + tighter tick stride range => faster movement along the route.
        steps = rng.randint(3, 6)
        points = interpolate_route(route_path, steps_per_segment=steps)
        fleet[vehicle_id] = {
            "vehicle_id": vehicle_id,
            "route_id": route_id,
            "points": points,
            "index": rng.randint(0, max(0, len(points) - 1)),
            "base_tick_stride": rng.randint(1, 2),
            "tick_stride": 1,
            "tick_counter": 0,
            "wait_ticks": 0,
            "base_load_wait": (rng.randint(0, 1), rng.randint(1, 3)),
            "load_wait": (0, 2),
            "silence_ticks": 0,
            "profile": profile_for_truck(idx, rng),
            "base_weight": rng.randint(18_000, 25_000),
            "current_weight": 0,
        }
    return fleet


rng = random.Random(42)
http = requests.Session()
auth_ok = ensure_auth(http, SIM_USERNAME, SIM_PASSWORD)
control_state = current_dynamic_defaults()

routes_payload = {}
fleet = {}
last_control_fetch = 0.0
last_routes_fetch = 0.0
last_log = 0.0

while True:
    now_epoch = time.time()

    if not auth_ok:
        auth_ok = ensure_auth(http, SIM_USERNAME, SIM_PASSWORD)
        if not auth_ok:
            print("Simulator auth failed; retrying...")
            time.sleep(max(1.0, SIM_SLEEP_SECONDS))
            continue

    if now_epoch - last_control_fetch > 6:
        # Refresh the date-derived defaults each cycle so a restarted/long-running
        # sim keeps tracking the real clock even if the control API never responds.
        control_state = fetch_control_state(http, {**current_dynamic_defaults(), **control_state})
        last_control_fetch = now_epoch

    if not fleet:
        new_routes = fetch_routes(http)
        if new_routes:
            routes_payload = new_routes
            fleet = build_sim_fleet(routes_payload, SIM_FLEET_SIZE, rng)
            print(f"Built simulator fleet: {len(fleet)} vehicles over {len(routes_payload)} routes")
        last_routes_fetch = now_epoch

    active_shift = control_state.get("active_shift") or derive_shift_from_time(datetime.now())
    shift_factor = SHIFT_TRAFFIC_FACTOR.get(active_shift, 1.0)

    weather = control_state.get("weather") or derive_weather_from_date(datetime.now())
    weather_effect = WEATHER_EFFECTS.get(weather, WEATHER_EFFECTS["clear"])

    traffic_factor = float(control_state.get("traffic_factor", 1.0)) * shift_factor * weather_effect["traffic"]
    anomaly_factor = float(control_state.get("anomaly_factor", 1.0))
    weather_noise = float(control_state.get("gps_noise", 0.1)) + weather_effect["noise"]

    batch_payload = []
    for vehicle in fleet.values():
        route_id = vehicle["route_id"]
        route_points = vehicle["points"]
        if not route_points:
            continue

        idx = vehicle["index"]
        lat, lon = route_points[idx]

        dynamic_stride = max(1, int(round(vehicle["base_tick_stride"] / max(0.55, traffic_factor))))
        vehicle["tick_stride"] = dynamic_stride

        wait_min_base, wait_max_base = vehicle["base_load_wait"]
        wait_scale = 1.35 if traffic_factor < 0.9 else 0.85 if traffic_factor > 1.1 else 1.0
        vehicle["load_wait"] = (
            max(0, int(round(wait_min_base * wait_scale))),
            max(1, int(round(wait_max_base * wait_scale))),
        )

        if vehicle["silence_ticks"] > 0:
            vehicle["silence_ticks"] -= 1
            continue

        profile = vehicle["profile"]
        
        # Determine current weight based on profile
        weight_penalty = 0
        if profile == "high_risk":
            weight_penalty = rng.randint(2000, 8000) if rng.random() < 0.4 else 0
        elif profile == "normal":
            weight_penalty = rng.randint(1000, 4000) if rng.random() < 0.2 else 0
        
        vehicle["current_weight"] = vehicle["base_weight"] + weight_penalty

        if profile == "safe":
            if rng.random() < (0.002 * anomaly_factor):
                lat += 0.0005
                lon += 0.0003
            if rng.random() < (0.001 + weather_noise * 0.008):
                vehicle["silence_ticks"] = rng.randint(1, 2)
                continue
        elif profile == "normal":
            if rng.random() < (0.004 * anomaly_factor + weather_noise * 0.015):
                vehicle["silence_ticks"] = rng.randint(1, 4)
                continue
            if rng.random() < (0.007 * anomaly_factor):
                lat += 0.0023
                lon += 0.0011
        else:
            if rng.random() < (0.010 * anomaly_factor + weather_noise * 0.02):
                vehicle["silence_ticks"] = rng.randint(2, 8)
                continue
            if rng.random() < (0.014 * anomaly_factor):
                lat += 0.0034
                lon += 0.0018

        if vehicle["wait_ticks"] > 0:
            vehicle["wait_ticks"] -= 1
        else:
            vehicle["tick_counter"] += 1
            if vehicle["tick_counter"] >= vehicle["tick_stride"]:
                vehicle["tick_counter"] = 0
                vehicle["index"] = (idx + 1) % len(route_points)

                dump_index = len(route_points) // 2
                if vehicle["index"] in (0, dump_index):
                    wait_min, wait_max = vehicle["load_wait"]
                    vehicle["wait_ticks"] = rng.randint(wait_min, wait_max)

        batch_payload.append({
            "vehicle_id": vehicle["vehicle_id"],
            "lat": lat,
            "lon": lon,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "route_id": route_id,
            "weight": vehicle["current_weight"],
        })

    if batch_payload:
        try:
            print(f"Sending GPS batch of {len(batch_payload)} vehicles to {GPS_API_URL}")
            response = http.post(
                GPS_API_URL,
                json=batch_payload,
                timeout=15,
            )
            print(f"GPS batch response status: {response.status_code}")
            if response.status_code == 401:
                auth_ok = False
        except requests.RequestException as e:
            print(f"GPS batch post failed: {e}")

    if time.time() - last_log > 5:
        print(
            f"{len(fleet)} trucks active over {len(routes_payload)} routes | shift={active_shift} | "
            f"weather={weather} | scenario={control_state.get('scenario')} | "
            f"traffic_factor={traffic_factor:.2f} | anomaly_factor={anomaly_factor:.2f}"
        )
        last_log = time.time()

    time.sleep(SIM_SLEEP_SECONDS)