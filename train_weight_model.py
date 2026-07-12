from __future__ import annotations

import argparse
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from weight_dataset_gen import generate_weight_dataset

FEATURES = [
    "trip_time",
    "avg_speed",
    "max_speed",
    "stops_count",
    "acceleration_variation",
    "route_distance",
    "trip_number",
    "time_of_day",
]
TARGET = "weight"


def train_weight_model(dataset_path: str = "weight_dataset.csv", model_path: str = "weight_model.pkl") -> dict:
    source = Path(dataset_path)
    if not source.exists():
        generate_weight_dataset(num_rows=50000, output_file=str(source))

    frame = pd.read_csv(source)
    missing = [column for column in FEATURES + [TARGET] if column not in frame.columns]
    if missing:
        raise ValueError(f"Dataset missing required columns: {', '.join(missing)}")

    x_train, x_test, y_train, y_test = train_test_split(
        frame[FEATURES],
        frame[TARGET],
        test_size=0.2,
        random_state=42,
    )

    model = RandomForestRegressor(
        n_estimators=180,
        max_depth=18,
        min_samples_split=4,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    r2 = r2_score(y_test, predictions)
    mae = mean_absolute_error(y_test, predictions)

    joblib.dump(model, model_path)
    return {
        "rows": len(frame),
        "r2": r2,
        "mae": mae,
        "model_path": model_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the truck weight regression model")
    parser.add_argument("--dataset", default="weight_dataset.csv", help="Input dataset CSV")
    parser.add_argument("--model", default="weight_model.pkl", help="Output model path")
    args = parser.parse_args()

    result = train_weight_model(args.dataset, args.model)
    print(f"Loaded {result['rows']:,} rows")
    print(f"R2 score: {result['r2']:.4f}")
    print(f"MAE: {result['mae']:.3f} tons")
    print(f"Saved model to {result['model_path']}")


if __name__ == "__main__":
    main()
