import time
import random
from datetime import datetime, timezone

import cv2
import requests

API_URL = "http://127.0.0.1:8000/camera"
CAMERA_ID = "cam_gate_1"
ROUTE_ID = "route_1"
CAMERA_LAT = 10.7350
CAMERA_LON = 78.6000
POST_INTERVAL_SECONDS = 2.0
VEHICLE_API_URL = "http://127.0.0.1:8000/api/vehicles"
CONTROL_API_URL = "http://127.0.0.1:8000/api/control-state"


def estimate_truck_count(frame, subtractor):
    # Lightweight motion-based estimate to simulate camera vehicle counting.
    fg = subtractor.apply(frame)
    _, mask = cv2.threshold(fg, 210, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    large_motions = 0
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > 1300:
            large_motions += 1
    return min(6, large_motions)


def ensure_auth(session, username: str = "admin", password: str = "admin123") -> bool:
    try:
        response = session.post(
            "http://127.0.0.1:8000/api/auth/login",
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
    except Exception:
        return False


def fetch_control_state(session):
    try:
        response = session.get(CONTROL_API_URL, timeout=2)
        return response.json()
    except requests.RequestException:
        return {"camera_noise": 0.10, "weather": "clear", "scenario": "suspicious_day"}


def estimate_simulated_truck_count(session, rng):
    # Virtual camera mode: infer approximate nearby load from live vehicle telemetry and add small noise.
    nearby = 0
    try:
        response = session.get(VEHICLE_API_URL, timeout=2)
        if response.status_code == 401:
            if ensure_auth(session):
                response = session.get(VEHICLE_API_URL, timeout=2)
            else:
                return 0
        
        vehicles = response.json()
        if isinstance(vehicles, dict) and "error" not in vehicles:
            for _, item in vehicles.items():
                if not isinstance(item, dict):
                    continue
                if item.get("route_id") != ROUTE_ID:
                    continue
                lat = float(item.get("lat", 0.0))
                lon = float(item.get("lon", 0.0))
                if abs(lat - CAMERA_LAT) <= 0.0038 and abs(lon - CAMERA_LON) <= 0.0038:
                    nearby += 1
    except Exception:
        pass

    control = fetch_control_state(session)
    noise = float(control.get("camera_noise", 0.1))
    weather = str(control.get("weather", "clear"))
    weather_penalty = {"clear": 0.0, "rain": 0.4, "dust": 0.6, "storm": 0.9}.get(weather, 0.0)
    noise_band = max(1, int(round((noise * 6.0) + weather_penalty)))
    noisy = nearby + rng.randint(-noise_band, noise_band)
    return max(0, min(6, noisy))


def post_count(session, count):
    payload = {
        "camera_id": CAMERA_ID,
        "lat": CAMERA_LAT,
        "lon": CAMERA_LON,
        "truck_count": int(count),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "route_id": ROUTE_ID,
    }
    try:
        session.post(API_URL, json=payload, timeout=2)
    except requests.RequestException:
        pass


def main():
    session = requests.Session()
    rng = random.Random(17)
    ensure_auth(session)

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("No physical camera found, starting virtual camera mode.")
        while True:
            count = estimate_simulated_truck_count(session, rng)
            post_count(session, count)
            print(f"Virtual camera posted count={count}")
            time.sleep(POST_INTERVAL_SECONDS)

    subtractor = cv2.createBackgroundSubtractorMOG2(history=400, varThreshold=42, detectShadows=False)
    last_post = 0.0

    print("Camera ingest started. Press q in the preview window to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        estimated_count = estimate_truck_count(frame, subtractor)
        now = time.time()
        if now - last_post >= POST_INTERVAL_SECONDS:
            post_count(session, estimated_count)
            last_post = now

        cv2.putText(
            frame,
            f"Estimated trucks: {estimated_count}",
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (30, 220, 30),
            2,
        )
        cv2.imshow("GeoGuard Camera Ingest", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
