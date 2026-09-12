"""Prove the numpy scorer agrees with XGBoost, on the real models and real data.

Serving does not import XGBoost -- that library is ~154 MB on Linux and drags
scipy along, which is most of a deployment's bundle budget. Instead
`app/services/tree_model.py` walks the saved JSON model directly. That is only
safe if the two genuinely produce the same numbers, so this script checks:

    python ml/verify_tree_model.py

It needs XGBoost installed (it is in requirements-train.txt), so run it after
training, not in production. Exits non-zero if the two ever disagree by more
than floating-point noise.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import MODEL_DIR  # noqa: E402
from app.services.feature_builder import FEATURE_COLUMNS  # noqa: E402
from app.services.tree_model import load_ensemble  # noqa: E402

# Anything above this is a real disagreement, not float32/float64 drift.
TOLERANCE = 1e-5


def check(site_type: str, n_rows: int = 4000, seed: int = 7) -> bool:
    import xgboost as xgb

    path = MODEL_DIR / f"{site_type}_model.json"
    if not path.exists():
        print(f"  {site_type}: no model at {path} -- run ml/train_model.py first")
        return False

    booster = xgb.XGBRegressor()
    booster.load_model(str(path))
    ours = load_ensemble(path)

    rng = np.random.default_rng(seed)
    # Cover the ordinary range and the edges: exact threshold hits, zeros and
    # NaNs are where a hand-written scorer usually diverges.
    X = rng.normal(0.0, 40.0, size=(n_rows, len(FEATURE_COLUMNS)))
    X[rng.random(X.shape) < 0.05] = 0.0
    X[rng.random(X.shape) < 0.02] = np.nan

    started = time.time()
    expected = booster.predict(X.astype("float32"))
    xgb_ms = (time.time() - started) * 1000

    started = time.time()
    actual = ours.predict(X)
    ours_ms = (time.time() - started) * 1000

    diff = np.abs(expected - actual)
    worst = float(diff.max())
    ok = worst <= TOLERANCE

    print(
        f"  {site_type:<6} rows={n_rows}  max|diff|={worst:.2e}  "
        f"{'MATCH' if ok else 'MISMATCH'}   "
        f"(xgboost {xgb_ms:.0f} ms, numpy {ours_ms:.0f} ms)"
    )
    if not ok:
        i = int(diff.argmax())
        print(f"    worst row {i}: xgboost={expected[i]:.8f} numpy={actual[i]:.8f}")
    return ok


def check_real_features(site_type: str) -> bool:
    """The case that actually matters: the live feature matrix for a real site.

    Random inputs are not enough. Real features land exactly on split
    thresholds -- irradiance and cloud cover arrive as whole numbers, and the
    thresholds were chosen from data -- so tie-breaking and threshold precision
    get exercised here in a way uniform noise never reaches. A float64/float32
    mismatch that random data hid showed up immediately on this matrix.
    """
    import xgboost as xgb

    from app.core.database import SessionLocal
    from app.models import Site
    from app.services import weather_service
    from app.services.feature_builder import build_features, feature_matrix

    session = SessionLocal()
    try:
        site = session.query(Site).filter(Site.site_type == site_type).first()
        if site is None:
            print(f"  {site_type}: no seeded site to test against")
            return True
        weather = weather_service.fetch_forecast(
            site.latitude, site.longitude, forecast_days=4, past_days=2
        )
        features = build_features(
            weather,
            capacity_kw=site.capacity_kw,
            latitude=site.latitude,
            longitude=site.longitude,
            generation_kw=None,
        )
    finally:
        session.close()

    # The lag columns are NaN until the recursive loop fills them in.
    X = np.nan_to_num(feature_matrix(features).to_numpy(), nan=0.2)

    booster = xgb.XGBRegressor()
    booster.load_model(str(MODEL_DIR / f"{site_type}_model.json"))
    ours = load_ensemble(MODEL_DIR / f"{site_type}_model.json")

    diff = np.abs(booster.predict(X.astype("float32")) - ours.predict(X))
    worst = float(diff.max())
    ok = worst <= TOLERANCE
    print(
        f"  {site_type:<6} live features for {site.name:<22} rows={len(X)}  "
        f"max|diff|={worst:.2e}  {'MATCH' if ok else 'MISMATCH'}"
    )
    return ok


def main() -> None:
    print(f"Comparing numpy scorer against XGBoost (tolerance {TOLERANCE:g})")
    print("\nSynthetic inputs, wide range including zeros and missing values:")
    results = [check(t) for t in ("solar", "wind")]
    print("\nLive feature matrices, where values sit exactly on split thresholds:")
    results += [check_real_features(t) for t in ("solar", "wind")]
    if all(results):
        print("\nAll models agree. Serving can drop the XGBoost dependency.")
    else:
        print("\nMismatch -- do NOT ship the numpy scorer.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
