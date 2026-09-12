"""Score a trained XGBoost ensemble using only numpy.

XGBoost is a superb training library and a very heavy runtime dependency: the
Linux wheel is ~154 MB compressed and pulls scipy with it, which is most of why
a deployment bundle blows past a 500 MB function limit. But *scoring* a
gradient-boosted tree ensemble is not complicated — it is walking a few hundred
small binary trees and adding up the leaves they land on.

So training still uses XGBoost (see `ml/train_model.py`), and serving reads the
same saved JSON model through this module. Nothing about the model changes; this
is the identical arithmetic XGBoost would do, and `ml/verify_tree_model.py`
asserts the two agree to floating-point noise.

The implementation is vectorised across trees rather than looping over them: all
600 trees are walked in lockstep, one depth level per iteration, using numpy
gathers. That keeps a single-row prediction at tens of microseconds, which
matters because the forecast horizon is evaluated recursively, one hour at a
time.

Supported: `gbtree` boosters with a scalar, identity-link objective
(`reg:squarederror`), which is what GridPulse trains. Anything else raises
rather than silently returning wrong numbers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Objectives whose raw margin is already the prediction. Adding, say, logistic
# would mean applying its link function to the summed leaves.
_IDENTITY_OBJECTIVES = {"reg:squarederror", "reg:linear", "reg:pseudohubererror"}

# Trees are shallow; this only exists so a malformed model can't spin forever.
_MAX_DEPTH_GUARD = 128


class UnsupportedModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class TreeEnsemble:
    """Every tree flattened into one set of arrays, plus per-tree offsets."""

    left: np.ndarray          # tree-local index of the left child, -1 at a leaf
    right: np.ndarray         # tree-local index of the right child
    feature: np.ndarray       # feature index tested at this node
    condition: np.ndarray     # float32 split threshold, or the leaf value at a leaf
    default_left: np.ndarray  # where a missing value goes
    tree_start: np.ndarray    # global offset of each tree's first node
    base_score: float
    n_features: int

    @property
    def n_trees(self) -> int:
        return int(self.tree_start.shape[0])

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict for a (n_rows, n_features) matrix. Returns (n_rows,).

        Splits are compared in float32 deliberately. XGBoost stores thresholds
        as float32 and the JSON holds their decimal rendering, so comparing in
        float64 puts a feature value that sits between the two on the wrong side
        of the split. On real data that flips a handful of branches and shifts
        the prediction by ~2.5e-3 -- small, but a real disagreement rather than
        rounding. Matching the reference precision brings it to ~5e-7.
        """
        rows = np.atleast_2d(np.asarray(X, dtype=np.float32))
        if rows.shape[1] != self.n_features:
            raise ValueError(
                f"expected {self.n_features} features, got {rows.shape[1]}"
            )

        n_rows = rows.shape[0]
        # Current node for every (row, tree) pair, as a global index.
        node = np.repeat(self.tree_start[None, :], n_rows, axis=0)

        for _ in range(_MAX_DEPTH_GUARD):
            left_child = self.left[node]
            internal = left_child >= 0
            if not internal.any():
                break

            feature = self.feature[node]
            value = np.take_along_axis(rows, feature, axis=1)
            threshold = self.condition[node]  # float32, see the note above

            # XGBoost sends anything that isn't strictly less than the threshold
            # down the right branch, and missing values down `default_left`.
            go_left = value < threshold
            missing = np.isnan(value)
            if missing.any():
                go_left = np.where(missing, self.default_left[node] == 1, go_left)

            child = np.where(go_left, left_child, self.right[node])
            # Children are numbered within their own tree, so re-base them.
            tree_base = np.repeat(self.tree_start[None, :], n_rows, axis=0)
            node = np.where(internal, tree_base + child, node)

        # At a leaf, XGBoost stores the output value in `split_conditions`.
        # Accumulate the leaves in float64: the branch decisions are already
        # settled by this point, so the extra precision costs nothing.
        leaves = self.condition[node].astype(np.float64)
        return self.base_score + leaves.sum(axis=1)


def load_ensemble(path: str | Path) -> TreeEnsemble:
    """Read a model saved by `Booster.save_model(...)` / `XGBRegressor.save_model(...)`."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    try:
        learner = raw["learner"]
        booster = learner["gradient_booster"]
        params = learner["learner_model_param"]
    except KeyError as exc:  # pragma: no cover - malformed file
        raise UnsupportedModelError(f"not an XGBoost JSON model: missing {exc}") from exc

    if booster.get("name") != "gbtree":
        raise UnsupportedModelError(f"only gbtree is supported, got {booster.get('name')!r}")

    objective = learner.get("objective", {}).get("name", "")
    if objective not in _IDENTITY_OBJECTIVES:
        raise UnsupportedModelError(
            f"objective {objective!r} needs a link function this scorer doesn't apply"
        )

    trees = booster["model"]["trees"]
    if any(tree.get("categories") for tree in trees):
        raise UnsupportedModelError("categorical splits are not supported")

    left, right, feature, condition, default_left, starts = [], [], [], [], [], []
    offset = 0
    for tree in trees:
        starts.append(offset)
        left.append(np.asarray(tree["left_children"], dtype=np.int32))
        right.append(np.asarray(tree["right_children"], dtype=np.int32))
        feature.append(np.asarray(tree["split_indices"], dtype=np.int64))
        # float32 to match the precision XGBoost splits at -- see predict().
        condition.append(np.asarray(tree["split_conditions"], dtype=np.float32))
        default_left.append(np.asarray(tree["default_left"], dtype=np.int8))
        offset += len(tree["left_children"])

    return TreeEnsemble(
        left=np.concatenate(left),
        right=np.concatenate(right),
        feature=np.concatenate(feature),
        condition=np.concatenate(condition),
        default_left=np.concatenate(default_left),
        tree_start=np.asarray(starts, dtype=np.int64),
        base_score=_scalar(params["base_score"]),
        n_features=int(_scalar(params["num_feature"])),
    )


def _scalar(value) -> float:
    """Pull a number out of `learner_model_param`.

    XGBoost serialises these as strings, and vector-valued ones keep their
    brackets -- base_score arrives as the string "[1.7959732E-1]", not a float.
    """
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)):
        return float(value[0])
    return float(str(value).strip().lstrip("[").rstrip("]").split(",")[0])
