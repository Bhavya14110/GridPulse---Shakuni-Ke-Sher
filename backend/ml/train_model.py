"""Train the generation forecasting models.

One gradient-boosted regressor per technology (solar, wind), trained on the
physics-derived history from `build_historical_dataset.py`. The target is
capacity factor rather than raw kW, so a single model serves every site of that
type regardless of nameplate, and the headline error metric reads directly as a
percentage of capacity.

Two things worth calling out, because they're the difference between a number
you can defend to a judge and one you can't:

  * the train/validation split is chronological, not random. Shuffling hourly
    time-series data lets the model see 13:00 and 15:00 while predicting 14:00,
    which inflates the score enormously and means nothing operationally. We hold
    out the most recent ~20% of the record and never touch it during training.
  * we score against a persistence baseline -- assume the next hour looks like
    this one, which is what a control room does without a model. "Beats
    persistence by X%" is the claim that actually matters.

Usage:
    python ml/train_model.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import DATA_DIR, MODEL_DIR  # noqa: E402
from app.services.feature_builder import (  # noqa: E402
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    build_features,
    feature_matrix,
)

DATASET_PATH = DATA_DIR / "historical_generation.csv"
METRICS_PATH = MODEL_DIR / "metrics.json"

WEATHER_COLUMNS = [
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "temperature_2m",
    "windspeed_10m",
    "windspeed_100m",
    "cloudcover",
]

# Confidence bands come from held-out residuals, bucketed by how much the model
# is predicting. A model sitting near zero or near rated output is far more
# certain than one predicting the middle of a ramp, and a flat band hides that.
CF_BUCKET_EDGES = [0.0, 0.05, 0.15, 0.30, 0.50, 0.70, 1.01]

XGB_PARAMS = dict(
    n_estimators=600,
    max_depth=7,
    learning_rate=0.05,
    subsample=0.85,
    colsample_bytree=0.85,
    min_child_weight=5,
    reg_lambda=1.5,
    objective="reg:squarederror",
    tree_method="hist",
    n_jobs=-1,
    random_state=42,
)


def prepare(dataset: pd.DataFrame, site_type: str) -> pd.DataFrame:
    """Feature-build each site separately, then stack.

    Per-site is not optional: lag and rolling features must never reach across a
    site boundary, or one farm's midnight ends up predicting another's noon.
    """
    frames = []
    for site_id, group in dataset[dataset["site_type"] == site_type].groupby("site_id"):
        group = group.sort_values("timestamp").set_index("timestamp")
        featured = build_features(
            group[WEATHER_COLUMNS],
            capacity_kw=float(group["capacity_kw"].iloc[0]),
            latitude=float(group["latitude"].iloc[0]),
            longitude=float(group["longitude"].iloc[0]),
            generation_kw=group["generation_kw"],
        )
        featured["site_id"] = site_id
        frames.append(featured)

    combined = pd.concat(frames).sort_index()
    return combined.dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])


def chronological_split(frame: pd.DataFrame, holdout: float = 0.2):
    stamps = frame.index.unique().sort_values()
    cutoff = stamps[int(len(stamps) * (1 - holdout))]
    return frame[frame.index < cutoff], frame[frame.index >= cutoff]


def residual_buckets(y_true: np.ndarray, y_pred: np.ndarray) -> list[dict]:
    """Held-out residual spread, sliced by predicted capacity factor."""
    buckets = []
    for low, high in zip(CF_BUCKET_EDGES[:-1], CF_BUCKET_EDGES[1:]):
        mask = (y_pred >= low) & (y_pred < high)
        # Fall back to the global spread if a bucket is too thin to trust.
        residuals = (y_true - y_pred)[mask] if mask.sum() >= 50 else (y_true - y_pred)
        buckets.append(
            {
                "cf_low": round(float(low), 3),
                "cf_high": round(float(high), 3),
                "residual_std": round(float(np.std(residuals)), 5),
                "n": int(mask.sum()),
            }
        )
    return buckets


def evaluate(site_type: str, valid: pd.DataFrame, predicted: np.ndarray) -> dict:
    actual = valid[TARGET_COLUMN].to_numpy()
    capacity = valid["capacity_kw"].to_numpy()
    persistence = valid["lag_cf_1h"].to_numpy()

    mae_cf = float(mean_absolute_error(actual, predicted))
    rmse_cf = float(np.sqrt(mean_squared_error(actual, predicted)))
    mae_persistence = float(mean_absolute_error(actual, persistence))

    return {
        "site_type": site_type,
        "validation_rows": int(len(valid)),
        "validation_span": [str(valid.index.min()), str(valid.index.max())],
        "mae_pct_capacity": round(mae_cf * 100, 3),
        "rmse_pct_capacity": round(rmse_cf * 100, 3),
        "r2": round(float(r2_score(actual, predicted)), 4),
        "mae_kw": round(float(np.mean(np.abs(actual - predicted) * capacity)), 1),
        "baseline_persistence_mae_pct_capacity": round(mae_persistence * 100, 3),
        "improvement_over_persistence_pct": round(
            (1 - mae_cf / mae_persistence) * 100 if mae_persistence else 0.0, 1
        ),
        "residual_buckets": residual_buckets(actual, predicted),
    }


def train_one(dataset: pd.DataFrame, site_type: str) -> dict:
    print("")
    print("=== " + site_type.upper() + " ===")
    frame = prepare(dataset, site_type)
    train, valid = chronological_split(frame)
    print("  train {:,} rows  |  holdout {:,} rows (most recent 20%)".format(len(train), len(valid)))

    model = xgb.XGBRegressor(**XGB_PARAMS)
    model.fit(
        feature_matrix(train),
        train[TARGET_COLUMN],
        eval_set=[(feature_matrix(valid), valid[TARGET_COLUMN])],
        verbose=False,
    )

    predicted = np.clip(model.predict(feature_matrix(valid)), 0.0, 1.0)
    metrics = evaluate(site_type, valid, predicted)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_model(str(MODEL_DIR / (site_type + "_model.json")))

    importance = sorted(zip(FEATURE_COLUMNS, model.feature_importances_), key=lambda kv: -kv[1])[:8]
    metrics["top_features"] = [
        {"feature": name, "importance": round(float(value), 4)} for name, value in importance
    ]

    print("  MAE   {:.2f}% of capacity  ({:,.0f} kW)".format(metrics["mae_pct_capacity"], metrics["mae_kw"]))
    print("  RMSE  {:.2f}% of capacity".format(metrics["rmse_pct_capacity"]))
    print("  R^2   {:.4f}".format(metrics["r2"]))
    print(
        "  vs persistence baseline ({:.2f}%): {:.1f}% better".format(
            metrics["baseline_persistence_mae_pct_capacity"],
            metrics["improvement_over_persistence_pct"],
        )
    )
    print("  top features: " + ", ".join(name for name, _ in importance[:5]))
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train GridPulse generation models")
    parser.add_argument("--dataset", type=Path, default=DATASET_PATH)
    args = parser.parse_args()

    if not args.dataset.exists():
        raise SystemExit(
            "No dataset at {}. Run `python ml/build_historical_dataset.py` first.".format(args.dataset)
        )

    dataset = pd.read_csv(args.dataset, parse_dates=["timestamp"])
    print("Loaded {:,} rows covering {} sites".format(len(dataset), dataset["site_name"].nunique()))

    report = {
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_rows": int(len(dataset)),
        "dataset_span": [
            str(dataset["timestamp"].min().date()),
            str(dataset["timestamp"].max().date()),
        ],
        "feature_columns": FEATURE_COLUMNS,
        "models": {},
    }
    for site_type in ("solar", "wind"):
        report["models"][site_type] = train_one(dataset, site_type)

    METRICS_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("")
    print("Saved models + metrics to {}".format(MODEL_DIR))


if __name__ == "__main__":
    main()
