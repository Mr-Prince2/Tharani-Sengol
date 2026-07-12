import argparse
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def parse_args():
    parser = argparse.ArgumentParser(description="Start Tharani Sengol services")
    parser.add_argument("--camera", action="store_true", help="Also start camera_ingest.py")
    parser.add_argument("--camera-script", default="camera_ingest.py", help="Camera ingestion script path")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open dashboard")
    parser.add_argument("--fleet-size", type=int, default=1000, help="Configured fleet size for backend")
    parser.add_argument("--route-count", type=int, default=120, help="Configured route count for backend")
    parser.add_argument("--sim-fleet-size", type=int, default=1000, help="Simulator active fleet size (defaults to 1000)")
    parser.add_argument("--weight-lock-km", type=float, default=0.15, help="Distance before locking weight prediction")
    parser.add_argument("--weight-lock-min", type=float, default=0.3, help="Trip minutes before locking weight prediction")
    return parser.parse_args()


def resolve_python_executable():
    venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def cleanup_orphans():
    if os.name != "nt":
        return
    try:
        import os as local_os
        my_pid = local_os.getpid()
        cmd = 'wmic process where "name=\'python.exe\'" get ProcessID, CommandLine /format:csv'
        output = subprocess.check_output(cmd, shell=True, text=True)
        for line in output.splitlines():
            if not line.strip() or "Node," in line:
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            cmdline = parts[1]
            try:
                pid = int(parts[2].strip())
            except ValueError:
                continue
            if pid == my_pid:
                continue
            if "app.py" in cmdline or "simulator.py" in cmdline or "camera_ingest.py" in cmdline:
                try:
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                except Exception:
                    pass
    except Exception:
        pass


def main():
    cleanup_orphans()
    args = parse_args()
    py_exec = resolve_python_executable()
    child_env = os.environ.copy()
    child_env["THARANI_FLEET_SIZE"] = str(max(1000, int(args.fleet_size)))
    child_env["THARANI_ROUTE_COUNT"] = str(max(100, int(args.route_count)))
    child_env["THARANI_SIM_FLEET_SIZE"] = str(max(1, int(args.sim_fleet_size)))
    child_env["THARANI_WEIGHT_LOCK_MIN_DISTANCE_KM"] = str(max(0.10, float(args.weight_lock_km)))
    child_env["THARANI_WEIGHT_LOCK_MIN_TRIP_MINUTES"] = str(max(0.5, float(args.weight_lock_min)))
    child_env["THARANI_DISABLE_INTERNAL_SIMULATOR"] = "1"
    child_env["THARANI_SIM_SLEEP_SECONDS"] = "0.5"

    backend_cmd = [py_exec, "-u", "app.py"]
    simulator_cmd = [py_exec, "-u", "simulator.py"]
    camera_cmd = [py_exec, "-u", args.camera_script]

    backend = subprocess.Popen(backend_cmd, cwd=BASE_DIR, env=child_env)
    simulator = None
    camera = None

    try:
        # Give the API a short startup window before starting the simulator.
        time.sleep(2)
        simulator = subprocess.Popen(simulator_cmd, cwd=BASE_DIR, env=child_env)

        if args.camera:
            camera = subprocess.Popen(camera_cmd, cwd=BASE_DIR, env=child_env)

        if not args.no_browser:
            webbrowser.open("http://127.0.0.1:8000/")

        if args.camera:
            print("Started backend + simulator + camera ingest.")
        else:
            print("Started backend + simulator.")
        print(f"Python interpreter: {py_exec}")
        print(
            f"Configured scale: trucks={child_env['THARANI_FLEET_SIZE']}, routes={child_env['THARANI_ROUTE_COUNT']}, "
            f"simulator={child_env['THARANI_SIM_FLEET_SIZE']}, weight_lock={child_env['THARANI_WEIGHT_LOCK_MIN_DISTANCE_KM']}km/{child_env['THARANI_WEIGHT_LOCK_MIN_TRIP_MINUTES']}min"
        )
        print("Dashboard: http://127.0.0.1:8000/")
        print("AI Prediction: http://127.0.0.1:8000/ai-prediction")
        print("Press Ctrl+C to stop everything.")

        while True:
            if backend.poll() is not None:
                print("Backend stopped unexpectedly.")
                break
            if simulator.poll() is not None:
                print("Simulator stopped unexpectedly.")
                break
            if camera and camera.poll() is not None:
                print("Camera ingest stopped unexpectedly.")
                break
            time.sleep(1)

    except KeyboardInterrupt:
        print("Stopping services...")
    finally:
        if camera and camera.poll() is None:
            camera.terminate()
            try:
                camera.wait(timeout=5)
            except subprocess.TimeoutExpired:
                camera.kill()

        if simulator and simulator.poll() is None:
            simulator.terminate()
            try:
                simulator.wait(timeout=5)
            except subprocess.TimeoutExpired:
                simulator.kill()

        if backend.poll() is None:
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend.kill()


if __name__ == "__main__":
    main()
