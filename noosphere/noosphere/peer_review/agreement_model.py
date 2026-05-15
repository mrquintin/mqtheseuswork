"""A predictive model of reviewer agreement.

Given a conclusion's pre-review features (see
:mod:`noosphere.peer_review.agreement_features`), this model predicts
the **inter-reviewer agreement** the swarm will reach — a continuous
score in ``[0, 1]`` where 1.0 means "every reviewer will land on the
same objection severity" and low values mean "expect contention".

The model is deliberately simple: an L2-regularised linear regression
(ridge) fit by the normal equations. Three reasons:

* The tournament corpus is small (tens of configurations × ten bench
  items). A high-capacity model would memorise it.
* A linear model is *inspectable* — :meth:`AgreementModel.top_drivers`
  reads the weights straight off, so the founder can see *why* a
  conclusion is predicted contentious.
* The prompt's constraint is explicit: the model is a *predictive aid,
  not a gate*. A simple, auditable model is the honest shape for that.

Honesty discipline baked in:

* Evaluation is always against a held-out shard and always reports the
  **predict-the-mean baseline** alongside the model's error. ``skill``
  is ``1 - mae/baseline_mae``; a model that does not beat the baseline
  has ``skill <= 0`` and the dashboard says so rather than dressing up
  noise.
* The model is subject to drift. :func:`calibration_snapshot` produces
  a time-stamped calibration record, and :func:`agreement_drift_rows`
  adapts a snapshot's predictions into
  :class:`noosphere.evaluation.method_drift.DriftResolution` rows so the
  *existing* drift detector — not a bespoke one — watches the agreement
  model the same way it watches every other method.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import numpy as np

from noosphere.peer_review.agreement_features import (
    FEATURE_NAMES,
    AgreementExample,
    FeatureInputs,
    feature_dict,
)

MODEL_SCHEMA = "theseus.reviewer_agreement_model.v1"
DEFAULT_L2 = 1.0

# The continuous agreement label is binarised at this threshold when we
# hand predictions to the (binary-outcome) method-drift detector: a
# review that lands at >= this score "converged". Documented here so the
# dashboard and the drift rows agree on the cut.
CONVERGENCE_THRESHOLD = 0.70


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(x)))


# ── The model ────────────────────────────────────────────────────────


@dataclass
class AgreementModel:
    """A trained ridge model over :data:`FEATURE_NAMES`.

    Serialisable to plain JSON (:meth:`to_dict` / :meth:`from_dict`) so
    the training script can archive it and the web app can read it
    without a Python round-trip.
    """

    feature_names: list[str]
    weights: list[float]
    bias: float
    l2: float
    n_train: int
    target_mean: float  # train-set mean agreement — the baseline predictor
    trained_at: str = field(default_factory=_utc_now_iso)
    notes: str = ""

    # ── prediction ───────────────────────────────────────────────────

    def predict_vector(self, vector: Sequence[float]) -> float:
        if len(vector) != len(self.feature_names):
            raise ValueError(
                f"expected {len(self.feature_names)} features, "
                f"got {len(vector)}"
            )
        raw = self.bias + float(np.dot(np.asarray(vector, dtype=float),
                                       np.asarray(self.weights, dtype=float)))
        return _clamp01(raw)

    def predict_features(self, features: dict[str, float]) -> float:
        """Predict from a feature dict (order-independent)."""

        try:
            vector = [features[name] for name in self.feature_names]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"feature dict missing {exc}") from exc
        return self.predict_vector(vector)

    def predict_inputs(self, fi: FeatureInputs) -> float:
        """Predict directly from :class:`FeatureInputs` (the pre-review path)."""

        return self.predict_features(feature_dict(fi))

    def predict_example(self, example: AgreementExample) -> float:
        return self.predict_vector(example.vector())

    def baseline_prediction(self) -> float:
        """The predict-the-mean fallback — what 'no skill' looks like."""

        return _clamp01(self.target_mean)

    def top_drivers(self, features: dict[str, float], *, k: int = 4) -> list[dict[str, Any]]:
        """The ``k`` features moving this prediction furthest from the mean.

        Signed contribution = ``weight * feature_value``. This is what
        makes the prediction explainable on the review page: "predicted
        contentious mainly because claim type is normative and
        temperature is high".
        """

        contribs = [
            {
                "feature": name,
                "value": float(features.get(name, 0.0)),
                "weight": float(w),
                "contribution": float(w) * float(features.get(name, 0.0)),
            }
            for name, w in zip(self.feature_names, self.weights)
        ]
        contribs.sort(key=lambda c: abs(c["contribution"]), reverse=True)
        return contribs[:k]

    # ── serialisation ────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MODEL_SCHEMA,
            "feature_names": list(self.feature_names),
            "weights": [round(float(w), 8) for w in self.weights],
            "bias": round(float(self.bias), 8),
            "l2": float(self.l2),
            "n_train": int(self.n_train),
            "target_mean": round(float(self.target_mean), 8),
            "trained_at": self.trained_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, blob: dict[str, Any]) -> "AgreementModel":
        return cls(
            feature_names=list(blob["feature_names"]),
            weights=[float(w) for w in blob["weights"]],
            bias=float(blob["bias"]),
            l2=float(blob.get("l2", DEFAULT_L2)),
            n_train=int(blob.get("n_train", 0)),
            target_mean=float(blob.get("target_mean", 0.5)),
            trained_at=str(blob.get("trained_at", "")),
            notes=str(blob.get("notes", "")),
        )


# ── Training ─────────────────────────────────────────────────────────


def train_agreement_model(
    examples: Sequence[AgreementExample],
    *,
    l2: float = DEFAULT_L2,
    notes: str = "",
) -> AgreementModel:
    """Fit a ridge regression predicting agreement from pre-review features.

    Closed-form normal equations: ``w = (XᵀX + λI)⁻¹ Xᵀy``. The bias
    column is appended to ``X`` and its diagonal entry in the penalty
    matrix is zeroed — we regularise the slopes, never the intercept,
    so a strongly-penalised model still collapses to the *mean*, not to
    *zero*.

    Only examples with ``trainable`` set (≥2 reviewers) should be passed
    in — inter-reviewer agreement is undefined for a monoculture. The
    function raises if it is handed an empty corpus.
    """

    rows = [e for e in examples if e.trainable]
    if not rows:
        raise ValueError(
            "no trainable examples — agreement is undefined for "
            "single-reviewer configurations; pass multi-provider rows"
        )

    X = np.array([e.vector() for e in rows], dtype=float)
    y = np.array([e.agreement for e in rows], dtype=float)
    n, d = X.shape

    # Augment with a bias column.
    Xb = np.hstack([X, np.ones((n, 1))])
    penalty = np.eye(d + 1) * float(l2)
    penalty[d, d] = 0.0  # do not regularise the intercept

    # ``np.errstate`` here silences a *spurious* divide/overflow warning
    # some BLAS backends (notably OpenBLAS on Apple Silicon) emit for a
    # plain ``A.T @ A`` even on finite, well-conditioned input. The
    # solve below is verified well-posed by the L2 ridge term; the
    # warning is a known false positive, not a numerical problem.
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        gram = Xb.T @ Xb + penalty
        coef = np.linalg.solve(gram, Xb.T @ y)
    weights = coef[:d]
    bias = float(coef[d])

    if not np.all(np.isfinite(coef)):  # pragma: no cover - defensive
        raise ValueError(
            "ridge solve produced non-finite coefficients — check the "
            "feature matrix for degenerate columns"
        )

    return AgreementModel(
        feature_names=list(FEATURE_NAMES),
        weights=[float(w) for w in weights],
        bias=bias,
        l2=float(l2),
        n_train=n,
        target_mean=float(np.mean(y)),
        notes=notes,
    )


# ── Evaluation ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class CalibrationBin:
    """One predicted-agreement bucket: mean predicted vs mean actual."""

    lo: float
    hi: float
    count: int
    mean_predicted: float
    mean_actual: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "lo": round(self.lo, 4),
            "hi": round(self.hi, 4),
            "count": self.count,
            "mean_predicted": round(self.mean_predicted, 4),
            "mean_actual": round(self.mean_actual, 4),
        }


@dataclass(frozen=True)
class EvaluationReport:
    """How the model did on a held-out shard.

    ``skill`` is the headline honesty number: ``1 - mae/baseline_mae``.
    Positive means the model beats predicting the training mean;
    ``<= 0`` means it is, at best, noise — and the founder dashboard is
    built to say exactly that rather than hide it.
    """

    n_eval: int
    mae: float
    rmse: float
    pearson_r: float
    baseline_mae: float
    skill: float
    predicted_mean: float
    actual_mean: float
    calibration_bins: list[CalibrationBin]

    @property
    def beats_baseline(self) -> bool:
        return self.skill > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_eval": self.n_eval,
            "mae": round(self.mae, 6),
            "rmse": round(self.rmse, 6),
            "pearson_r": round(self.pearson_r, 6),
            "baseline_mae": round(self.baseline_mae, 6),
            "skill": round(self.skill, 6),
            "beats_baseline": self.beats_baseline,
            "predicted_mean": round(self.predicted_mean, 6),
            "actual_mean": round(self.actual_mean, 6),
            "calibration_bins": [b.to_dict() for b in self.calibration_bins],
        }


def _pearson(pred: np.ndarray, actual: np.ndarray) -> float:
    if len(pred) < 2:
        return 0.0
    sp = float(np.std(pred))
    sa = float(np.std(actual))
    if sp <= 1e-12 or sa <= 1e-12:
        # One of the series is constant — correlation is undefined.
        # Report 0.0 rather than NaN; "no linear relationship measured".
        return 0.0
    return float(np.corrcoef(pred, actual)[0, 1])


def _calibration_bins(
    pred: np.ndarray, actual: np.ndarray, *, n_bins: int = 4
) -> list[CalibrationBin]:
    bins: list[CalibrationBin] = []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        # Last bin is closed on the right so a prediction of exactly 1.0
        # lands somewhere.
        if i == n_bins - 1:
            mask = (pred >= lo) & (pred <= hi)
        else:
            mask = (pred >= lo) & (pred < hi)
        count = int(mask.sum())
        if count == 0:
            bins.append(CalibrationBin(lo, hi, 0, (lo + hi) / 2, (lo + hi) / 2))
            continue
        bins.append(
            CalibrationBin(
                lo=lo,
                hi=hi,
                count=count,
                mean_predicted=float(pred[mask].mean()),
                mean_actual=float(actual[mask].mean()),
            )
        )
    return bins


def evaluate(
    model: AgreementModel, examples: Sequence[AgreementExample]
) -> EvaluationReport:
    """Score ``model`` on a held-out set, baseline-relative."""

    rows = [e for e in examples if e.trainable]
    if not rows:
        raise ValueError("no trainable examples to evaluate on")

    pred = np.array([model.predict_example(e) for e in rows], dtype=float)
    actual = np.array([e.agreement for e in rows], dtype=float)
    baseline = np.full_like(actual, model.baseline_prediction())

    mae = float(np.mean(np.abs(pred - actual)))
    rmse = float(np.sqrt(np.mean((pred - actual) ** 2)))
    baseline_mae = float(np.mean(np.abs(baseline - actual)))
    # Skill: how much of the baseline error the model removes. Guard the
    # degenerate baseline (every holdout label identical) — then there
    # is nothing to have skill *over*.
    skill = 1.0 - (mae / baseline_mae) if baseline_mae > 1e-9 else 0.0

    return EvaluationReport(
        n_eval=len(rows),
        mae=mae,
        rmse=rmse,
        pearson_r=_pearson(pred, actual),
        baseline_mae=baseline_mae,
        skill=skill,
        predicted_mean=float(pred.mean()),
        actual_mean=float(actual.mean()),
        calibration_bins=_calibration_bins(pred, actual),
    )


# ── Calibration tracking + drift ─────────────────────────────────────


@dataclass(frozen=True)
class CalibrationSnapshot:
    """One time-stamped calibration record for the trends widget.

    Appended to ``calibration_history.jsonl`` on every training run. The
    founder dashboard plots these to answer the question the prompt
    poses directly: *does the model actually predict agreement, or is it
    just adding noise?*
    """

    observed_at: str
    n_eval: int
    mae: float
    rmse: float
    skill: float
    pearson_r: float
    predicted_mean: float
    actual_mean: float
    model_trained_at: str
    n_train: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "theseus.reviewer_agreement_calibration.v1",
            "observed_at": self.observed_at,
            "n_eval": self.n_eval,
            "mae": round(self.mae, 6),
            "rmse": round(self.rmse, 6),
            "skill": round(self.skill, 6),
            "pearson_r": round(self.pearson_r, 6),
            "predicted_mean": round(self.predicted_mean, 6),
            "actual_mean": round(self.actual_mean, 6),
            "model_trained_at": self.model_trained_at,
            "n_train": self.n_train,
        }

    @classmethod
    def from_dict(cls, blob: dict[str, Any]) -> "CalibrationSnapshot":
        return cls(
            observed_at=str(blob["observed_at"]),
            n_eval=int(blob.get("n_eval", 0)),
            mae=float(blob.get("mae", 0.0)),
            rmse=float(blob.get("rmse", 0.0)),
            skill=float(blob.get("skill", 0.0)),
            pearson_r=float(blob.get("pearson_r", 0.0)),
            predicted_mean=float(blob.get("predicted_mean", 0.0)),
            actual_mean=float(blob.get("actual_mean", 0.0)),
            model_trained_at=str(blob.get("model_trained_at", "")),
            n_train=int(blob.get("n_train", 0)),
        )


def calibration_snapshot(
    model: AgreementModel,
    report: EvaluationReport,
    *,
    observed_at: Optional[str] = None,
) -> CalibrationSnapshot:
    """Build a :class:`CalibrationSnapshot` from a held-out evaluation."""

    return CalibrationSnapshot(
        observed_at=observed_at or _utc_now_iso(),
        n_eval=report.n_eval,
        mae=report.mae,
        rmse=report.rmse,
        skill=report.skill,
        pearson_r=report.pearson_r,
        predicted_mean=report.predicted_mean,
        actual_mean=report.actual_mean,
        model_trained_at=model.trained_at,
        n_train=model.n_train,
    )


def agreement_drift_rows(
    model: AgreementModel,
    examples: Sequence[AgreementExample],
    *,
    observed_at: datetime,
    convergence_threshold: float = CONVERGENCE_THRESHOLD,
) -> list[Any]:
    """Adapt held-out predictions into ``method_drift.DriftResolution`` rows.

    The agreement model is "subject to drift" like any other method, and
    the prompt says to surface that drift *via the existing drift
    detector*. That detector
    (:mod:`noosphere.evaluation.method_drift`) works on binary-outcome
    resolutions: a ``probability`` and an ``outcome`` in ``{0, 1}``.

    We map each held-out example onto one resolution:

    * ``probability`` = the model's predicted agreement,
    * ``outcome`` = ``1.0`` if the *actual* agreement reached
      ``convergence_threshold``, else ``0.0``,
    * ``observed_at`` = the training-run timestamp,
    * ``domain`` = the conclusion's domain.

    A scheduler can accumulate these across training runs and feed them
    straight into ``method_drift.evaluate_method`` under
    ``method_name="reviewer_agreement_model"``. No bespoke drift code.
    """

    from noosphere.evaluation.method_drift import DriftResolution

    rows: list[Any] = []
    for ex in examples:
        if not ex.trainable:
            continue
        prob = model.predict_example(ex)
        outcome = 1.0 if ex.agreement >= convergence_threshold else 0.0
        rows.append(
            DriftResolution(
                prediction_id=f"{ex.conclusion_id}:{ex.config_id}",
                probability=prob,
                outcome=outcome,
                observed_at=observed_at,
                brier=(prob - outcome) ** 2,
                domain=ex.domain,
            )
        )
    return rows


# ── JSON artifact I/O ────────────────────────────────────────────────


def model_artifact(
    model: AgreementModel,
    report: EvaluationReport,
    history: Sequence[CalibrationSnapshot],
    *,
    routing_policy: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the on-disk ``model.json`` the web app reads.

    Everything the dashboard widget and the review page need in one
    self-describing blob: the model, its latest held-out evaluation, the
    full calibration history, and (optionally) the routing policy in
    effect.
    """

    blob: dict[str, Any] = {
        "schema": MODEL_SCHEMA,
        "model": model.to_dict(),
        "evaluation": report.to_dict(),
        "calibration_history": [s.to_dict() for s in history],
        "convergence_threshold": CONVERGENCE_THRESHOLD,
    }
    if routing_policy is not None:
        blob["routing_policy"] = routing_policy
    if extra:
        blob.update(extra)
    return blob


def load_model_artifact(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_calibration_history(path: str) -> list[CalibrationSnapshot]:
    """Read a ``calibration_history.jsonl`` file (missing file → empty)."""

    out: list[CalibrationSnapshot] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                out.append(CalibrationSnapshot.from_dict(json.loads(line)))
    except FileNotFoundError:
        return []
    return out


def append_calibration_snapshot(path: str, snapshot: CalibrationSnapshot) -> None:
    """Append one snapshot to the JSONL history (creates the file)."""

    import os

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")


__all__ = [
    "AgreementModel",
    "CONVERGENCE_THRESHOLD",
    "CalibrationBin",
    "CalibrationSnapshot",
    "DEFAULT_L2",
    "EvaluationReport",
    "MODEL_SCHEMA",
    "agreement_drift_rows",
    "append_calibration_snapshot",
    "calibration_snapshot",
    "evaluate",
    "load_calibration_history",
    "load_model_artifact",
    "model_artifact",
    "train_agreement_model",
]
