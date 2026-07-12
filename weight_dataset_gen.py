from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def generate_weight_dataset(num_rows: int = 50000, output_file: str = "weight_dataset.csv", seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    trip_number = rng.integers(1, 220, size=num_rows)
    time_of_day = rng.integers(0, 24, size=num_rows)
    route_distance = rng.uniform(6.5, 58.0, size=num_rows)

    rush_hour = np.isin(time_of_day, [7, 8, 9, 17, 18, 19]).astype(float)
    night_shift = np.isin(time_of_day, [0, 1, 2, 3, 4, 22, 23]).astype(float)

    stops_count = rng.poisson(lam=1.2 + (route_distance / 18.0) + (trip_number / 120.0) + night_shift * 0.35).astype(int)
    stops_count = np.clip(stops_count, 0, 14)

    weight = (
        8.5
        + (route_distance * 0.24)
        + (stops_count * 0.55)
        + (trip_number * 0.015)
        + (night_shift * 0.9)
        - (rush_hour * 0.45)
        + rng.normal(0.0, 2.6, size=num_rows)
    )
    weight = np.clip(weight, 3.0, 40.0)

    avg_speed = (
        70.0
        - (weight * 0.95)
        - (stops_count * 0.42)
        - (route_distance * 0.08)
        + (rush_hour * 1.8)
        + rng.normal(0.0, 2.8, size=num_rows)
    )
    avg_speed = np.clip(avg_speed, 18.0, 88.0)

    max_speed = np.clip(avg_speed + rng.uniform(7.0, 18.0, size=num_rows), avg_speed + 2.0, 100.0)

    acceleration_variation = np.clip(
        0.35 + (stops_count * 0.08) + (weight * 0.02) + rng.normal(0.0, 0.12, size=num_rows),
        0.05,
        4.5,
    )

    trip_time = (
        (route_distance / np.maximum(avg_speed, 1.0)) * 60.0
        * (1.05 + (weight / 44.0) + (stops_count * 0.018) + rng.normal(0.0, 0.04, size=num_rows))
    )
    trip_time = np.clip(trip_time, 10.0, 900.0)

    data = pd.DataFrame(
        {
            "trip_time": np.round(trip_time, 2),
            "avg_speed": np.round(avg_speed, 2),
            "max_speed": np.round(max_speed, 2),
            "stops_count": stops_count.astype(int),
            "acceleration_variation": np.round(acceleration_variation, 3),
            "route_distance": np.round(route_distance, 3),
            "trip_number": trip_number.astype(int),
            "time_of_day": time_of_day.astype(int),
            "weight": np.round(weight, 2),
        }
    )

    output_path = Path(output_file)
    data.to_csv(output_path, index=False)
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic truck weight dataset")
    parser.add_argument("--rows", type=int, default=50000, help="Number of rows to generate")
    parser.add_argument("--output", default="weight_dataset.csv", help="Output CSV path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    frame = generate_weight_dataset(args.rows, args.output, args.seed)
    print(f"Generated {len(frame):,} rows at {args.output}")


if __name__ == "__main__":
    main()
