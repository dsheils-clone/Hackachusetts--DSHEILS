"""Train one habitat model per target species for Shifting Grounds (task 3).

One ``HistGradientBoostingClassifier`` is trained per species on bottom temperature
(BOTTEMP) and depth (AVGDEPTH) only. The label is presence (0/1) from the zero-filled
presence table. Latitude, longitude and year are NEVER features: letting the model see
location or time would let it memorize places instead of learning a temperature/depth
response (design.md, Model table; .kiro/steering/workflow.md guardrails). This module
asserts that invariant and fails loudly if it is ever violated.

Data (design.md, Model table):
- Join data/processed/presence.csv (long form: ID, species, SVSPP, present) to
  data/processed/tows.csv on ID to get BOTTEMP and AVGDEPTH per (tow, species).
- Split on EST_YEAR from tows.csv: train on 2009-2018, test on 2019 onward.
  There is no 2020 data (COVID survey gap) and 2017 is partial; we simply use whatever
  years fall in each window (decision logged in docs/DECISIONS.md).

Outputs (design.md, Project structure):
- models/<species>.joblib  : one trained classifier per species
- models/metrics.json      : per-species test AUC and class balance (positive rate in
                             train and test, plus row counts)
"""

from __future__ import annotations

import json
import os

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

from prepare_data import (
    PRESENCE_PATH,
    REPO_ROOT,
    TARGET_SPECIES,
    TOWS_PATH,
)

# --- Paths ------------------------------------------------------------------

MODELS_DIR = os.path.join(REPO_ROOT, "models")
METRICS_PATH = os.path.join(MODELS_DIR, "metrics.json")

# --- Model config (design.md, Model table) ---------------------------------

# The ONLY two features. Latitude, longitude and year must never appear here.
FEATURES = ["BOTTEMP", "AVGDEPTH"]
LABEL = "present"

# Columns that must never be used as features (fail loudly if they leak in).
FORBIDDEN_FEATURES = {
    "DECDEG_BEGLAT",  # latitude
    "DECDEG_BEGLON",  # longitude
    "EST_YEAR",       # year
    "lat",
    "lon",
    "latitude",
    "longitude",
    "year",
}

# Split windows (design.md: train 2009-2018, test 2019 onward).
TRAIN_YEARS = (2009, 2018)  # inclusive range
TEST_MIN_YEAR = 2019

RANDOM_STATE = 42

# --- Regularization (task 3.1; human-approved option 2: mild regularization) -----------
#
# The default HistGradientBoostingClassifier overfits where training data is sparse. The
# SHAP temperature-response plot showed a jagged oscillation at the cold end (~6-8 C) where
# few tows exist: a gradient-boosted-tree artifact, not biology. The human (who knows fish
# behavior) chose REGULARIZATION rather than a monotonic temperature constraint, precisely
# to AVOID baking in "colder is always better". A monotonic constraint would erase a
# possible cold optimum for cold-water species such as Atlantic cod. So we smooth with
# regularization ONLY and add NO monotonic constraint (D-0xx).
#
# Two knobs, both pushing the trees toward simpler, better-supported splits:
#   - min_samples_leaf: require more tows in each leaf so a handful of cold tows can no
#     longer carve out their own sharp leaf (default is 20; we raise it).
#   - l2_regularization: shrink leaf values toward zero, damping spiky over-confident leaves.
# These are named constants so the choice is auditable (.kiro/steering/workflow.md). They
# visibly damp the sparse cold-end jaggedness while keeping the ecologically real sharp
# warm-edge decline; any small AUC cost is reported honestly in models/metrics.json.
MIN_SAMPLES_LEAF = 30      # approved range 20-40; raised from the sklearn default of 20
L2_REGULARIZATION = 1.0    # small positive value; default is 0.0 (no shrinkage)


def _assert_features_allowed(features: list[str]) -> None:
    """Fail loudly if latitude, longitude or year is among the model features."""
    leaked = sorted(set(features) & FORBIDDEN_FEATURES)
    assert not leaked, (
        "Forbidden feature(s) in the model inputs: "
        f"{leaked}. Latitude, longitude and year must NEVER be features "
        "(see .kiro/steering/workflow.md and design.md Model table)."
    )
    assert set(features) == set(FEATURES), (
        f"Model features {features} differ from the allowed set {FEATURES}."
    )


# --- Data -------------------------------------------------------------------


def load_training_frame(
    tows_path: str = TOWS_PATH, presence_path: str = PRESENCE_PATH
) -> pd.DataFrame:
    """Join presence to tows on ID so each (tow, species) row carries BOTTEMP,
    AVGDEPTH and EST_YEAR. Returns one tidy frame with the feature columns, the label
    and EST_YEAR (kept only for splitting, never used as a feature)."""
    tows = pd.read_csv(tows_path, dtype={"ID": str})
    presence = pd.read_csv(presence_path, dtype={"ID": str})

    merged = presence.merge(
        tows[["ID", "EST_YEAR", *FEATURES]], on="ID", how="left", validate="many_to_one"
    )
    # Every presence row should match a tow; a NaN feature means a broken join.
    missing = merged[FEATURES].isna().any(axis=1).sum()
    assert missing == 0, (
        f"{missing} (tow, species) rows did not match a tow with valid "
        f"{FEATURES}; the presence/tows join is broken."
    )
    return merged


def split_species(frame: pd.DataFrame, species: str):
    """Return (X_train, y_train, X_test, y_test) for one species using the year split.

    X frames contain ONLY the allowed features. EST_YEAR is used to split and then
    dropped, so it can never reach the model.
    """
    sp = frame.loc[frame["species"] == species].copy()

    year = pd.to_numeric(sp["EST_YEAR"], errors="coerce")
    is_train = (year >= TRAIN_YEARS[0]) & (year <= TRAIN_YEARS[1])
    is_test = year >= TEST_MIN_YEAR

    train = sp.loc[is_train]
    test = sp.loc[is_test]

    _assert_features_allowed(FEATURES)

    X_train = train[FEATURES].copy()
    y_train = train[LABEL].astype(int)
    X_test = test[FEATURES].copy()
    y_test = test[LABEL].astype(int)

    # Belt and braces: the feature matrices must not carry lat/lon/year.
    _assert_features_allowed(list(X_train.columns))
    _assert_features_allowed(list(X_test.columns))

    return X_train, y_train, X_test, y_test


# --- Training ---------------------------------------------------------------


def train_species(frame: pd.DataFrame, species: str):
    """Train one HistGradientBoostingClassifier for `species`. Returns (model, metrics)."""
    X_train, y_train, X_test, y_test = split_species(frame, species)

    model = HistGradientBoostingClassifier(
        random_state=RANDOM_STATE,
        min_samples_leaf=MIN_SAMPLES_LEAF,     # task 3.1: smooth sparse-data leaves
        l2_regularization=L2_REGULARIZATION,   # task 3.1: shrink spiky leaf values
    )
    model.fit(X_train, y_train)

    # Test AUC. roc_auc_score needs both classes present in y_test.
    if y_test.nunique() < 2:
        test_auc = None
    else:
        proba = model.predict_proba(X_test)[:, 1]
        test_auc = float(roc_auc_score(y_test, proba))

    metrics = {
        "species": species,
        "svspp": TARGET_SPECIES[species],
        "features": list(FEATURES),
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
        "train_positive_rate": float(y_train.mean()) if len(y_train) else None,
        "test_positive_rate": float(y_test.mean()) if len(y_test) else None,
        "test_auc": test_auc,
        "train_years": list(range(TRAIN_YEARS[0], TRAIN_YEARS[1] + 1)),
        "test_min_year": TEST_MIN_YEAR,
        "min_samples_leaf": MIN_SAMPLES_LEAF,
        "l2_regularization": L2_REGULARIZATION,
    }
    return model, metrics


def save_model(model, species: str, models_dir: str = MODELS_DIR) -> str:
    """Persist a trained model to models/<species>.joblib. Returns the path."""
    os.makedirs(models_dir, exist_ok=True)
    path = os.path.join(models_dir, f"{species}.joblib")
    joblib.dump(model, path)
    return path


def train_all(frame: pd.DataFrame) -> dict:
    """Train every target species, save each model, and return the metrics dict."""
    all_metrics: dict[str, dict] = {}
    for species in TARGET_SPECIES:
        model, metrics = train_species(frame, species)
        path = save_model(model, species)
        metrics["model_path"] = os.path.relpath(path, REPO_ROOT)
        all_metrics[species] = metrics

        auc_str = "n/a" if metrics["test_auc"] is None else f"{metrics['test_auc']:.3f}"
        print(
            f"[train] {species:>16}: "
            f"train n={metrics['n_train']} pos={metrics['train_positive_rate']:.1%} | "
            f"test n={metrics['n_test']} pos={metrics['test_positive_rate']:.1%} | "
            f"test AUC={auc_str} -> {metrics['model_path']}"
        )
    return all_metrics


def save_metrics(metrics: dict, path: str = METRICS_PATH) -> None:
    """Write the per-species metrics to models/metrics.json."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)


# --- Script entry point -----------------------------------------------------


def main() -> None:
    print("=== Shifting Grounds: train habitat models (task 3) ===")
    print(f"[train] features (and ONLY these): {FEATURES}")
    # Guard before touching any data: lat/lon/year must not be features.
    _assert_features_allowed(FEATURES)

    frame = load_training_frame()
    print(
        f"[train] joined frame: {len(frame)} (tow, species) rows across "
        f"{frame['species'].nunique()} species"
    )

    metrics = train_all(frame)
    save_metrics(metrics)
    print(f"[train] saved metrics for {len(metrics)} species to {METRICS_PATH}")


if __name__ == "__main__":
    main()
