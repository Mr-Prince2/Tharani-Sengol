# GeoGuard — Vehicle Monitoring & Weight Estimation

This repository contains a vehicle monitoring and weight-estimation project with data ingestion, dataset generation, training, and a web dashboard for visualization and alerts.

## Key Features

- Camera ingestion and capture utilities for collecting vehicle images and sensor data.
- Dataset generation scripts and example CSV datasets for vehicle/weight modeling.
- Training scripts for classification and weight-estimation models.
- A Flask-based web UI (templates + static assets) for predictions, analytics, and admin.

## Quick Start

1. Create a Python virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
```

2. Run the application (development):

```bash
python run_all.py
# or run the web app directly if applicable:
python app.py
```

3. Train models (examples):

```bash
python train_model.py
python train_weight_model.py
```

## Important Scripts & Files

- `run_all.py` — Orchestrates the project's main flow.
- `app.py` — Web application entrypoint (Flask).
- `camera_ingest.py`, `capture.py` — Camera capture and ingestion utilities.
- `dataset_gen.py`, `weight_dataset_gen.py` — Dataset creation helpers.
- `train_model.py`, `train_weight_model.py` — Training scripts for models.
- `trichy_vehicle_dataset.csv`, `weight_dataset.csv` — Example datasets.
- `static/` and `templates/` — Frontend assets and HTML templates.
- `geoguard-phase4/` — Additional frontend/backend components.

## Dataset Notes

Example CSV files are included to help reproduce training runs. If you add or replace datasets, ensure the scripts that consume them (dataset generation and training) are updated accordingly.

## Development Tips

- Keep a separate virtual environment per project.
- Use small test subsets of CSVs when iterating on training.
- Screenshots and sample outputs are in the `screenshots/` directory.

## Contributing

Contributions are welcome. Open an issue or send a pull request describing the change.

## License

Add your preferred license (e.g., MIT) or contact the project owner for details.

## Contact

For questions, see `user_accounts.json` or contact the repository owner.
