"""Calibrate the severity rubric against realized objection outcomes.

The severity rubric in :mod:`noosphere.peer_review.severity` is
*stipulated*: it maps the five structural inputs to a score by a
formula the firm asserts. That is the honest shape at cold start — but
a stipulated formula is a hypothesis, not a measurement. Once enough
objections have run all the way to a resolution, we can ask the
question the score is *supposed* to answer and check the formula
against the answer:

    of the objections that scored "high", how many — if true — actually
    moved the conclusion?

This module does three things:

A. **Outcome labelling.** :func:`label_objections` joins every recorded
   objection to its realized outcome via the revision ledger (prompt
   16): ``material_change`` (a committed, non-reverted revision moved
   the conclusion), ``addendum`` (an addendum was attached without
   revising the conclusion), or ``dismissed`` (neither).

B. **A fitted scorer.** :func:`train_severity_calibration_model` fits an
   L2-regularised logistic regression predicting *material change* from
   the severity inputs. :func:`fit_severity_calibration` is the
   orchestrator: it splits, fits, evaluates held-out, and refits the
   production model on all the data. The fitted
   :class:`SeverityCalibrationModel` plugs into
   :func:`noosphere.peer_review.severity.score_objection_with_model` as
   the new severity scorer; the stipulated formula stays as the
   cold-start fallback and the ablation alternative.

C. **A re-score + a reliability diagram.**
   :func:`rescore_live_objections` recomputes severity for every live
   objection under the fitted model and flags conclusions whose MQS
   Severity objection-penalty moves by more than δ for the founder
   queue. :func:`reliability_diagram` bins predicted severity against
   the realized material-change rate — a calibration plot, surfaced on
   the methods page.

Cold-start discipline
---------------------
:func:`fit_severity_calibration` will **not** fit on tiny data. Below
:data:`COLD_START_MIN_N` labeled objections — or with only one outcome
class present — it returns a ``cold_start`` result and the caller
(``scripts/fit_severity_model.sh``) writes a deliberate-deferral note
to ``docs/methods/Severity_Calibration_Status.md`` and exits. Shipping
a noisy model fit on forty examples would be worse than keeping the
honest stipulated formula; the gate makes that refusal explicit.

The fitted model is recomputed nightly, on the same cadence as drift
detection — see ``scripts/fit_severity_model.sh``.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

import numpy as np

from noosphere.peer_review.severity import (
    SeverityInputs,
    aggregate,
    label_for,
    mqs_severity_penalty,
    score_objection,
    score_objection_with_model,
)

# ── Schemas / constants ──────────────────────────────────────────────

MODEL_SCHEMA = "theseus.severity_calibration_model.v1"
ARTIFACT_SCHEMA = "theseus.severity_calibration.artifact.v1"

# Outcome labels. A recorded objection lands in exactly one of these.
OUTCOME_MATERIAL = "material_change"
OUTCOME_ADDENDUM = "addendum"
OUTCOME_DISMISSED = "dismissed"
OUTCOME_LABELS = (OUTCOME_MATERIAL, OUTCOME_ADDENDUM, OUTCOME_DISMISSED)

# Cold-start gate. Below this many labeled objections the firm does NOT
# replace the stipulated formula — see the module docstring.
COLD_START_MIN_N = 50

# Default L2 penalty on the logistic-regression slopes (never the bias).
DEFAULT_L2 = 1.0

# Re-score gate. A conclusion whose objection-driven MQS Severity
# penalty multiplier moves by more than this under the fitted model
# goes to the founder queue.
DEFAULT_RESCORE_DELTA = 0.05

# The feature vector the model is fit over. Source credibility and the
# judge estimate are optional on `SeverityInputs`; each gets a value
# column (0.0 when absent) plus a "present" indicator so a missing
# input is a learnable signal rather than a silent zero.
FEATURE_NAMES: tuple[str, ...] = (
    "cascade_weight",
    "claim_centrality",
    "failure_mode_severity",
    "source_credibility",
    "source_present",
    "judge_severity",
    "judge_present",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    return max(0.0, min(1.0, float(x)))


def feature_vector(inp: SeverityInputs) -> list[float]:
    """Project a :class:`SeverityInputs` into the model's feature space."""

    cred = inp.source_credibility
    judge = inp.judge_severity
    return [
        _clamp01(inp.cascade_weight),
        _clamp01(inp.claim_centrality),
        _clamp01(inp.failure_mode_severity),
        _clamp01(cred) if cred is not None else 0.0,
        1.0 if cred is not None else 0.0,
        _clamp01(judge) if judge is not None else 0.0,
        1.0 if judge is not None else 0.0,
    ]


def feature_dict(inp: SeverityInputs) -> dict[str, float]:
    return dict(zip(FEATURE_NAMES, feature_vector(inp)))


# ══════════════════════════════════════════════════════════════════════
# A. Outcome labelling
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RawObjection:
    """A recorded objection awaiting an outcome label.

    ``inputs`` is the :class:`SeverityInputs` snapshot the objection was
    scored with — the features the calibration model learns over.
    ``conclusion_id`` is the conclusion the objection attacks.
    ``addendum_issued`` is True when an addendum was attached to the
    conclusion citing this objection *without* the conclusion being
    revised — the (ii) outcome.
    """

    objection_id: str
    conclusion_id: str
    inputs: SeverityInputs
    raised_at: datetime
    addendum_issued: bool = False


@dataclass(frozen=True)
class LabeledObjection:
    """A :class:`RawObjection` joined to its realized outcome."""

    objection_id: str
    conclusion_id: str
    inputs: SeverityInputs
    outcome: str  # one of OUTCOME_LABELS
    raised_at: datetime
    revision_event_id: Optional[str] = None  # set iff outcome == material

    @property
    def material_change(self) -> bool:
        return self.outcome == OUTCOME_MATERIAL

    @property
    def label(self) -> int:
        """Binary target the calibration model is fit against."""

        return 1 if self.outcome == OUTCOME_MATERIAL else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "objection_id": self.objection_id,
            "conclusion_id": self.conclusion_id,
            "inputs": {
                "cascade_weight": self.inputs.cascade_weight,
                "claim_centrality": self.inputs.claim_centrality,
                "failure_mode_severity": self.inputs.failure_mode_severity,
                "source_credibility": self.inputs.source_credibility,
                "judge_severity": self.inputs.judge_severity,
            },
            "outcome": self.outcome,
            "raised_at": self.raised_at.isoformat(),
            "revision_event_id": self.revision_event_id,
        }

    @classmethod
    def from_dict(cls, blob: dict[str, Any]) -> "LabeledObjection":
        raw = blob.get("inputs", {})
        return cls(
            objection_id=str(blob["objection_id"]),
            conclusion_id=str(blob["conclusion_id"]),
            inputs=SeverityInputs(
                cascade_weight=float(raw.get("cascade_weight", 0.0)),
                claim_centrality=float(raw.get("claim_centrality", 0.0)),
                failure_mode_severity=float(raw.get("failure_mode_severity", 0.0)),
                source_credibility=(
                    None
                    if raw.get("source_credibility") is None
                    else float(raw["source_credibility"])
                ),
                judge_severity=(
                    None
                    if raw.get("judge_severity") is None
                    else float(raw["judge_severity"])
                ),
            ),
            outcome=str(blob["outcome"]),
            raised_at=_parse_dt(blob["raised_at"]),
            revision_event_id=blob.get("revision_event_id"),
        )


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    dt = datetime.fromisoformat(str(value))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def classify_outcome(*, materially_revised: bool, addendum_issued: bool) -> str:
    """Reduce two booleans to the realized-outcome label.

    Material change dominates: an objection that triggered a revision is
    labelled ``material_change`` even if an addendum was also attached.
    """

    if materially_revised:
        return OUTCOME_MATERIAL
    if addendum_issued:
        return OUTCOME_ADDENDUM
    return OUTCOME_DISMISSED


def _revision_touched_conclusion(event: Any, conclusion_id: str) -> bool:
    """True when a (non-reverted) RevisionEvent moved ``conclusion_id``.

    "Moved" means the conclusion appears in the revision plan's
    ``changed`` / ``newly_contradicted`` / ``newly_supported`` buckets —
    a confidence shift larger than the plan's δ. ``stable`` conclusions
    are not counted: the revision engine itself does not consider them
    materially changed.

    Duck-typed against :class:`noosphere.cascade.revision.RevisionEvent`
    so this module needs no import of the cascade package.
    """

    if getattr(event, "reverted", False):
        return False
    plan = getattr(event, "plan", None)
    if plan is None:
        return False
    buckets = (
        getattr(plan, "changed", ()) or (),
        getattr(plan, "newly_contradicted", ()) or (),
        getattr(plan, "newly_supported", ()) or (),
    )
    for bucket in buckets:
        for shift in bucket:
            if getattr(shift, "conclusion_id", None) == conclusion_id:
                return True
    return False


def label_objections(
    objections: Iterable[RawObjection],
    revision_events: Iterable[Any],
) -> list[LabeledObjection]:
    """Join each objection to its realized outcome (part A).

    An objection counts as having triggered a **material change** when a
    non-reverted :class:`~noosphere.cascade.revision.RevisionEvent`
    committed *at or after* the objection was raised moved the
    objection's conclusion. The earliest such revision wins (it is the
    one the objection most plausibly drove). With no such revision the
    outcome is **addendum** if an addendum was attached, else
    **dismissed**.

    The temporal guard — only revisions committed at/after ``raised_at``
    — keeps an objection from being credited with a conclusion change
    that predated it.
    """

    events = sorted(
        revision_events, key=lambda e: getattr(e, "committed_at")
    )
    labeled: list[LabeledObjection] = []
    for obj in objections:
        revision_id: Optional[str] = None
        for ev in events:
            if getattr(ev, "committed_at") < obj.raised_at:
                continue
            if _revision_touched_conclusion(ev, obj.conclusion_id):
                revision_id = getattr(ev, "event_id")
                break
        outcome = classify_outcome(
            materially_revised=revision_id is not None,
            addendum_issued=obj.addendum_issued,
        )
        labeled.append(
            LabeledObjection(
                objection_id=obj.objection_id,
                conclusion_id=obj.conclusion_id,
                inputs=obj.inputs,
                outcome=outcome,
                raised_at=obj.raised_at,
                revision_event_id=revision_id,
            )
        )
    return labeled


def outcome_counts(labeled: Iterable[LabeledObjection]) -> dict[str, int]:
    """Tally labeled objections by outcome — always all three keys."""

    counts = Counter(r.outcome for r in labeled)
    return {label: int(counts.get(label, 0)) for label in OUTCOME_LABELS}


# ══════════════════════════════════════════════════════════════════════
# B. The fitted scorer — L2-regularised logistic regression
# ══════════════════════════════════════════════════════════════════════


def _sigmoid(z: float) -> float:
    # Numerically stable scalar sigmoid.
    if z >= 0.0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _sigmoid_arr(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0.0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


@dataclass
class SeverityCalibrationModel:
    """A logistic model: P(objection materially changes the conclusion).

    Serialisable to plain JSON so the nightly script can archive it and
    the methods page can read it without a Python round-trip. The
    predicted probability *is* the calibrated severity value —
    :func:`noosphere.peer_review.severity.score_objection_with_model`
    consumes :meth:`predict_inputs` directly.
    """

    feature_names: list[str]
    weights: list[float]
    bias: float
    l2: float
    n_train: int
    n_material: int
    base_rate: float  # train-set material-change rate — the baseline predictor
    trained_at: str = field(default_factory=_utc_now_iso)
    notes: str = ""

    # ── prediction ───────────────────────────────────────────────────

    def predict_vector(self, vector: Sequence[float]) -> float:
        if len(vector) != len(self.feature_names):
            raise ValueError(
                f"expected {len(self.feature_names)} features, "
                f"got {len(vector)}"
            )
        z = self.bias + float(
            np.dot(
                np.asarray(vector, dtype=float),
                np.asarray(self.weights, dtype=float),
            )
        )
        return _sigmoid(z)

    def predict_features(self, features: dict[str, float]) -> float:
        try:
            vector = [features[name] for name in self.feature_names]
        except KeyError as exc:  # pragma: no cover - defensive
            raise ValueError(f"feature dict missing {exc}") from exc
        return self.predict_vector(vector)

    def predict_inputs(self, inputs: SeverityInputs) -> float:
        """Predicted P(material change) — the calibrated severity value."""

        return self.predict_vector(feature_vector(inputs))

    def baseline_prediction(self) -> float:
        """The predict-the-base-rate fallback — what 'no skill' looks like."""

        return _clamp01(self.base_rate)

    def top_drivers(
        self, inputs: SeverityInputs, *, k: int = 4
    ) -> list[dict[str, Any]]:
        """The ``k`` features moving this objection's score furthest.

        Signed contribution = ``weight * feature_value`` (log-odds
        units). This is what makes a calibrated severity explainable on
        the review page: "scored high mainly because cascade weight is
        0.9 and the claim is load-bearing".
        """

        features = feature_dict(inputs)
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
            "n_material": int(self.n_material),
            "base_rate": round(float(self.base_rate), 8),
            "trained_at": self.trained_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, blob: dict[str, Any]) -> "SeverityCalibrationModel":
        return cls(
            feature_names=list(blob["feature_names"]),
            weights=[float(w) for w in blob["weights"]],
            bias=float(blob["bias"]),
            l2=float(blob.get("l2", DEFAULT_L2)),
            n_train=int(blob.get("n_train", 0)),
            n_material=int(blob.get("n_material", 0)),
            base_rate=float(blob.get("base_rate", 0.5)),
            trained_at=str(blob.get("trained_at", "")),
            notes=str(blob.get("notes", "")),
        )


def _fit_logistic(
    X: np.ndarray,
    y: np.ndarray,
    l2: float,
    *,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> tuple[np.ndarray, float]:
    """Newton–Raphson (IRLS) fit of an L2-penalised logistic regression.

    The bias column is appended to ``X`` and its diagonal entry in the
    penalty matrix is zeroed — we regularise the slopes, never the
    intercept, so a strongly-penalised model collapses to the *base
    rate*, not to 50/50. The L2 term also keeps the Hessian well-posed
    when the labelled set is (near-)separable, which a stipulated rubric
    with a clean structural signal often is.
    """

    n, d = X.shape
    Xb = np.hstack([X, np.ones((n, 1))])
    penalty = np.eye(d + 1) * float(l2)
    penalty[d, d] = 0.0
    w = np.zeros(d + 1, dtype=float)

    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        for _ in range(max_iter):
            p = _sigmoid_arr(Xb @ w)
            grad = Xb.T @ (p - y) + penalty @ w
            # IRLS weights, floored so a saturated probability cannot
            # make the Hessian singular.
            s = np.clip(p * (1.0 - p), 1e-9, None)
            hess = (Xb * s[:, None]).T @ Xb + penalty
            try:
                step = np.linalg.solve(hess, grad)
            except np.linalg.LinAlgError:  # pragma: no cover - defensive
                break
            w_new = w - step
            if not np.all(np.isfinite(w_new)):  # pragma: no cover - defensive
                break
            if float(np.max(np.abs(w_new - w))) < tol:
                w = w_new
                break
            w = w_new

    return w[:d].astype(float), float(w[d])


def train_severity_calibration_model(
    labeled: Sequence[LabeledObjection],
    *,
    l2: float = DEFAULT_L2,
    notes: str = "",
) -> SeverityCalibrationModel:
    """Fit a :class:`SeverityCalibrationModel` on labeled objections.

    Raises on an empty corpus or a single-class corpus — logistic
    regression needs both material-change and non-material examples to
    have anything to separate. :func:`fit_severity_calibration` guards
    these cases up front and routes them to cold-start instead; this
    function is the bare fit.
    """

    rows = list(labeled)
    if not rows:
        raise ValueError("no labeled objections to fit on")
    y = np.array([float(r.label) for r in rows], dtype=float)
    n_material = int(y.sum())
    if n_material == 0 or n_material == len(rows):
        raise ValueError(
            "labeled set has a single outcome class — logistic "
            "regression needs both material-change and non-material "
            "examples"
        )

    X = np.array([feature_vector(r.inputs) for r in rows], dtype=float)
    weights, bias = _fit_logistic(X, y, l2)
    if not np.all(np.isfinite(weights)):  # pragma: no cover - defensive
        raise ValueError("logistic fit produced non-finite coefficients")

    return SeverityCalibrationModel(
        feature_names=list(FEATURE_NAMES),
        weights=[float(w) for w in weights],
        bias=bias,
        l2=float(l2),
        n_train=len(rows),
        n_material=n_material,
        base_rate=float(y.mean()),
        notes=notes,
    )


# ══════════════════════════════════════════════════════════════════════
# Held-out evaluation
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CalibrationEvaluation:
    """How the fitted model did on a held-out shard.

    ``skill`` is the headline honesty number: ``1 - log_loss /
    baseline_log_loss``, where the baseline predicts the train-set base
    rate for every objection. Positive means the model beats "everyone
    gets the base rate"; ``<= 0`` means it is, at best, noise — and the
    methods page is built to say exactly that.
    """

    n_eval: int
    n_material: int
    log_loss: float
    baseline_log_loss: float
    skill: float
    brier: float
    auc: float
    accuracy: float
    predicted_material_rate: float
    actual_material_rate: float

    @property
    def beats_baseline(self) -> bool:
        return self.skill > 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_eval": self.n_eval,
            "n_material": self.n_material,
            "log_loss": round(self.log_loss, 6),
            "baseline_log_loss": round(self.baseline_log_loss, 6),
            "skill": round(self.skill, 6),
            "beats_baseline": self.beats_baseline,
            "brier": round(self.brier, 6),
            "auc": round(self.auc, 6),
            "accuracy": round(self.accuracy, 6),
            "predicted_material_rate": round(self.predicted_material_rate, 6),
            "actual_material_rate": round(self.actual_material_rate, 6),
        }


def _log_loss(pred: np.ndarray, actual: np.ndarray) -> float:
    eps = 1e-12
    p = np.clip(pred, eps, 1.0 - eps)
    return float(-np.mean(actual * np.log(p) + (1.0 - actual) * np.log(1.0 - p)))


def _auc(pred: np.ndarray, actual: np.ndarray) -> float:
    """ROC AUC via the Mann–Whitney U statistic, ties counted as 0.5.

    Returns 0.5 (chance) when one class is absent — there is nothing to
    rank against.
    """

    pos = pred[actual == 1.0]
    neg = pred[actual == 0.0]
    if len(pos) == 0 or len(neg) == 0:
        return 0.5
    order = np.argsort(pred, kind="mergesort")
    ranks = np.empty(len(pred), dtype=float)
    sorted_pred = pred[order]
    i = 0
    while i < len(sorted_pred):
        j = i
        while j + 1 < len(sorted_pred) and sorted_pred[j + 1] == sorted_pred[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # ranks are 1-based
        ranks[order[i : j + 1]] = avg_rank
        i = j + 1
    rank_sum_pos = float(np.sum(ranks[actual == 1.0]))
    n_pos = len(pos)
    n_neg = len(neg)
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def evaluate_calibration(
    model: SeverityCalibrationModel,
    labeled: Sequence[LabeledObjection],
) -> CalibrationEvaluation:
    """Score ``model`` on a held-out set, baseline-relative."""

    rows = list(labeled)
    if not rows:
        raise ValueError("no labeled objections to evaluate on")

    pred = np.array([model.predict_inputs(r.inputs) for r in rows], dtype=float)
    actual = np.array([float(r.label) for r in rows], dtype=float)
    baseline = np.full_like(actual, model.baseline_prediction())

    log_loss = _log_loss(pred, actual)
    baseline_log_loss = _log_loss(baseline, actual)
    skill = (
        1.0 - (log_loss / baseline_log_loss)
        if baseline_log_loss > 1e-12
        else 0.0
    )
    brier = float(np.mean((pred - actual) ** 2))
    accuracy = float(np.mean((pred >= 0.5).astype(float) == actual))

    return CalibrationEvaluation(
        n_eval=len(rows),
        n_material=int(actual.sum()),
        log_loss=log_loss,
        baseline_log_loss=baseline_log_loss,
        skill=skill,
        brier=brier,
        auc=_auc(pred, actual),
        accuracy=accuracy,
        predicted_material_rate=float(pred.mean()),
        actual_material_rate=float(actual.mean()),
    )


# ══════════════════════════════════════════════════════════════════════
# D. Reliability diagram — predicted severity vs realized change rate
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ReliabilityBin:
    """One predicted-severity bucket: mean predicted vs realized rate.

    ``realized_change_rate`` is the fraction of objections in the bin
    whose realized outcome was ``material_change``. On a well-calibrated
    model it tracks ``mean_predicted`` — that is the diagonal the
    methods-page plot draws against.
    """

    lo: float
    hi: float
    n: int
    mean_predicted: Optional[float]
    realized_change_rate: Optional[float]
    sparse: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "lo": round(self.lo, 4),
            "hi": round(self.hi, 4),
            "n": self.n,
            "mean_predicted": (
                None if self.mean_predicted is None
                else round(self.mean_predicted, 6)
            ),
            "realized_change_rate": (
                None if self.realized_change_rate is None
                else round(self.realized_change_rate, 6)
            ),
            "sparse": self.sparse,
        }


# Bins thinner than this are drawn greyed / without weight on the plot —
# a 2-objection bin must not look like a confident calibration point.
RELIABILITY_SPARSE_THRESHOLD = 5


def reliability_diagram(
    model: SeverityCalibrationModel,
    labeled: Sequence[LabeledObjection],
    *,
    n_bins: int = 10,
    sparse_threshold: int = RELIABILITY_SPARSE_THRESHOLD,
) -> list[ReliabilityBin]:
    """Bin predicted severity against the realized material-change rate.

    Empty bins are still returned (with ``n=0`` and null stats) so the
    plot has a stable x-axis; bins below ``sparse_threshold`` are marked
    ``sparse`` so the renderer can grey them.
    """

    preds = [model.predict_inputs(r.inputs) for r in labeled]
    labels = [r.label for r in labeled]
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[ReliabilityBin] = []
    for i in range(n_bins):
        lo, hi = float(edges[i]), float(edges[i + 1])
        if i == n_bins - 1:
            idx = [j for j, p in enumerate(preds) if lo <= p <= hi]
        else:
            idx = [j for j, p in enumerate(preds) if lo <= p < hi]
        n = len(idx)
        if n == 0:
            bins.append(ReliabilityBin(lo, hi, 0, None, None, sparse=True))
            continue
        mean_predicted = sum(preds[j] for j in idx) / n
        realized = sum(labels[j] for j in idx) / n
        bins.append(
            ReliabilityBin(
                lo=lo,
                hi=hi,
                n=n,
                mean_predicted=mean_predicted,
                realized_change_rate=realized,
                sparse=n < sparse_threshold,
            )
        )
    return bins


# ══════════════════════════════════════════════════════════════════════
# E. Cold-start handling + fit orchestration
# ══════════════════════════════════════════════════════════════════════

STATUS_FITTED = "fitted"
STATUS_COLD_START = "cold_start"


@dataclass(frozen=True)
class CalibrationFitResult:
    """The output of :func:`fit_severity_calibration`.

    ``status`` is ``fitted`` or ``cold_start``. On cold start ``model``,
    ``evaluation`` and ``reliability`` are absent/empty and
    ``cold_start_reason`` explains the refusal; the caller writes the
    deferral note and leaves the stipulated formula in place.
    """

    status: str
    n_labeled: int
    n_material: int
    n_addendum: int
    n_dismissed: int
    model: Optional[SeverityCalibrationModel]
    evaluation: Optional[CalibrationEvaluation]
    reliability: list[ReliabilityBin]
    min_n: int = COLD_START_MIN_N
    cold_start_reason: str = ""
    generated_at: str = field(default_factory=_utc_now_iso)

    @property
    def is_cold_start(self) -> bool:
        return self.status == STATUS_COLD_START

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "n_labeled": self.n_labeled,
            "n_material": self.n_material,
            "n_addendum": self.n_addendum,
            "n_dismissed": self.n_dismissed,
            "min_n": self.min_n,
            "cold_start_reason": self.cold_start_reason,
            "generated_at": self.generated_at,
            "model": None if self.model is None else self.model.to_dict(),
            "evaluation": (
                None if self.evaluation is None else self.evaluation.to_dict()
            ),
            "reliability": [b.to_dict() for b in self.reliability],
        }


def _deterministic_split(
    rows: Sequence[LabeledObjection],
    holdout_fraction: float,
) -> tuple[list[LabeledObjection], list[LabeledObjection]]:
    """Stable hash-based train/holdout split keyed on objection id.

    Deterministic so a re-run on the same corpus gives the same model —
    no global RNG, no shuffle seed to thread through the script.
    """

    import hashlib

    train: list[LabeledObjection] = []
    holdout: list[LabeledObjection] = []
    for r in rows:
        h = hashlib.sha256(r.objection_id.encode("utf-8")).digest()
        u = int.from_bytes(h[:8], "big") / 2 ** 64
        (holdout if u < holdout_fraction else train).append(r)
    return train, holdout


def fit_severity_calibration(
    labeled: Iterable[LabeledObjection],
    *,
    l2: float = DEFAULT_L2,
    min_n: int = COLD_START_MIN_N,
    holdout_fraction: float = 0.2,
    n_bins: int = 10,
    notes: str = "",
) -> CalibrationFitResult:
    """Fit the calibration model — or refuse, on cold-start grounds.

    The orchestrator for parts B + D + E:

    1. **Cold-start gate.** Below ``min_n`` labeled objections, or with
       only one outcome class present, return a ``cold_start`` result
       and fit nothing. The caller writes the deferral note.
    2. **Held-out evaluation.** Split deterministically, fit on the
       train shard, score the holdout — that is the honest
       generalisation number (``skill``, ``auc``).
    3. **Production refit.** Refit on *all* the labeled data for the
       model that ships; the holdout was spent buying the evaluation,
       not withheld from production. Standard practice, made explicit.
    4. **Reliability diagram** over the full labeled set under the
       production model.
    """

    rows = list(labeled)
    counts = outcome_counts(rows)
    n = len(rows)
    n_material = counts[OUTCOME_MATERIAL]

    def _cold(reason: str) -> CalibrationFitResult:
        return CalibrationFitResult(
            status=STATUS_COLD_START,
            n_labeled=n,
            n_material=n_material,
            n_addendum=counts[OUTCOME_ADDENDUM],
            n_dismissed=counts[OUTCOME_DISMISSED],
            model=None,
            evaluation=None,
            reliability=[],
            min_n=min_n,
            cold_start_reason=reason,
        )

    if n < min_n:
        return _cold(
            f"only {n} labeled objection(s) — below the cold-start "
            f"threshold of {min_n}. Fitting a logistic model on data "
            f"this thin would ship a noisy scorer; the stipulated "
            f"rubric is the honest fallback until the corpus grows."
        )
    if n_material == 0 or n_material == n:
        only = "material-change" if n_material == n else "non-material"
        return _cold(
            f"all {n} labeled objections share one outcome class "
            f"({only}) — logistic regression has nothing to separate. "
            f"Deferring until both classes are observed."
        )

    train, holdout = _deterministic_split(rows, holdout_fraction)
    # Guard a split that stranded a class entirely on one side, or left
    # a holdout too thin to mean anything — same refusal, different
    # cause.
    train_material = sum(r.label for r in train)
    if not train or train_material == 0 or train_material == len(train):
        return _cold(
            f"the deterministic train/holdout split left the train "
            f"shard single-class (n_train={len(train)}). Corpus is too "
            f"small or too imbalanced to fit honestly."
        )

    eval_model = train_severity_calibration_model(
        train,
        l2=l2,
        notes=f"held-out eval model — train shard ({len(train)} rows)",
    )
    evaluation: Optional[CalibrationEvaluation] = None
    if holdout:
        evaluation = evaluate_calibration(eval_model, holdout)

    # Production refit on all the data.
    model = train_severity_calibration_model(
        rows,
        l2=l2,
        notes=notes
        or (
            f"severity calibration — logistic regression on {n} labeled "
            f"objections ({n_material} material-change)"
        ),
    )
    reliability = reliability_diagram(model, rows, n_bins=n_bins)

    return CalibrationFitResult(
        status=STATUS_FITTED,
        n_labeled=n,
        n_material=n_material,
        n_addendum=counts[OUTCOME_ADDENDUM],
        n_dismissed=counts[OUTCOME_DISMISSED],
        model=model,
        evaluation=evaluation,
        reliability=reliability,
        min_n=min_n,
    )


# ══════════════════════════════════════════════════════════════════════
# C. Re-score live objections
# ══════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ConclusionRescore:
    """One conclusion's severity re-score: stipulated vs calibrated.

    The number that matters is ``penalty_delta`` — the change in the MQS
    Severity objection-penalty multiplier when the conclusion's live
    objections are re-scored under the fitted model. ``score_severity``
    multiplies the Severity sub-score by that penalty, so a swing in the
    penalty is a swing in the sub-score; conclusions whose penalty moves
    by more than δ go to the founder queue.
    """

    conclusion_id: str
    n_objections: int
    old_severity_penalty: float
    new_severity_penalty: float
    penalty_delta: float
    old_max_label: str
    new_max_label: str
    founder_queue: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "conclusion_id": self.conclusion_id,
            "n_objections": self.n_objections,
            "old_severity_penalty": round(self.old_severity_penalty, 6),
            "new_severity_penalty": round(self.new_severity_penalty, 6),
            "penalty_delta": round(self.penalty_delta, 6),
            "old_max_label": self.old_max_label,
            "new_max_label": self.new_max_label,
            "founder_queue": self.founder_queue,
        }


def rescore_live_objections(
    objections_by_conclusion: dict[str, Sequence[SeverityInputs]],
    model: SeverityCalibrationModel,
    *,
    delta: float = DEFAULT_RESCORE_DELTA,
) -> list[ConclusionRescore]:
    """Recompute severity for all live objections under the fitted model.

    ``objections_by_conclusion`` maps a conclusion id to the
    :class:`SeverityInputs` of its live (non-stale) objections. For each
    conclusion this computes the MQS Severity objection-penalty
    multiplier under (a) the stipulated rubric and (b) the fitted model,
    and flags the conclusion for the founder queue when the multiplier
    moves by more than ``delta``.

    Results are returned sorted by conclusion id (deterministic), so a
    nightly diff of two runs is stable.
    """

    results: list[ConclusionRescore] = []
    for cid in sorted(objections_by_conclusion):
        inputs_list = list(objections_by_conclusion[cid])
        old_sevs = [score_objection(inp) for inp in inputs_list]
        new_sevs = [
            score_objection_with_model(inp, model) for inp in inputs_list
        ]
        old_agg = aggregate(old_sevs)
        new_agg = aggregate(new_sevs)
        old_penalty = mqs_severity_penalty(old_agg)
        new_penalty = mqs_severity_penalty(new_agg)
        penalty_delta = new_penalty - old_penalty
        results.append(
            ConclusionRescore(
                conclusion_id=cid,
                n_objections=len(inputs_list),
                old_severity_penalty=old_penalty,
                new_severity_penalty=new_penalty,
                penalty_delta=penalty_delta,
                old_max_label=old_agg.max_label,
                new_max_label=new_agg.max_label,
                founder_queue=abs(penalty_delta) > delta,
            )
        )
    return results


def founder_queue(rescores: Iterable[ConclusionRescore]) -> list[ConclusionRescore]:
    """The subset of a re-score that crossed δ — ordered by swing size."""

    flagged = [r for r in rescores if r.founder_queue]
    flagged.sort(key=lambda r: abs(r.penalty_delta), reverse=True)
    return flagged


# ══════════════════════════════════════════════════════════════════════
# Artifact + status doc
# ══════════════════════════════════════════════════════════════════════


def calibration_artifact(
    result: CalibrationFitResult,
    *,
    rescores: Optional[Sequence[ConclusionRescore]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Assemble the on-disk ``model.json`` the methods page reads.

    One self-describing blob: the fit result (model, held-out
    evaluation, reliability diagram, cold-start state) plus, when a
    re-score ran, the founder queue it produced.
    """

    blob: dict[str, Any] = {"schema": ARTIFACT_SCHEMA}
    blob.update(result.to_dict())
    if rescores is not None:
        flagged = founder_queue(rescores)
        blob["rescore"] = {
            "n_conclusions": len(list(rescores)),
            "n_founder_queue": len(flagged),
            "delta": DEFAULT_RESCORE_DELTA,
            "founder_queue": [r.to_dict() for r in flagged],
        }
    if extra:
        blob.update(extra)
    return blob


def load_labeled_corpus(path: str) -> list[LabeledObjection]:
    """Read a ``labeled_objections.jsonl`` corpus (missing file → empty)."""

    out: list[LabeledObjection] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                out.append(LabeledObjection.from_dict(json.loads(line)))
    except FileNotFoundError:
        return []
    return out


def status_markdown(
    result: CalibrationFitResult,
    *,
    corpus_path: str = "",
) -> str:
    """Render ``docs/methods/Severity_Calibration_Status.md``.

    The status doc is the deliberate-deferral note on cold start and the
    "model is live" record once fitted. Either way it is regenerated
    every nightly run, so the doc never drifts from the artifact.
    """

    lines: list[str] = []
    lines.append("# Severity Calibration — Status")
    lines.append("")
    lines.append(
        "_Generated by `noosphere/scripts/fit_severity_model.sh` — "
        "do not edit by hand. Regenerated on every nightly run._"
    )
    lines.append("")
    lines.append(f"- **Generated at:** {result.generated_at}")
    lines.append(f"- **Status:** `{result.status}`")
    lines.append(
        f"- **Labeled objections:** {result.n_labeled} "
        f"(threshold to fit: {result.min_n})"
    )
    lines.append(
        f"- **Outcome mix:** {result.n_material} material-change · "
        f"{result.n_addendum} addendum · {result.n_dismissed} dismissed"
    )
    if corpus_path:
        lines.append(f"- **Corpus:** `{corpus_path}`")
    lines.append("")

    if result.is_cold_start:
        lines.append("## Deliberate deferral")
        lines.append("")
        lines.append(result.cold_start_reason)
        lines.append("")
        lines.append(
            "The stipulated severity rubric "
            "(`noosphere.peer_review.severity.score_objection`) remains "
            "the active scorer. This is a deliberate choice, not a gap: "
            "fitting a logistic model on a corpus this thin would ship a "
            "noisy scorer dressed up as a measurement. The firm would "
            "rather run the honest stipulated formula and say so than "
            "swap in a model it cannot defend."
        )
        lines.append("")
        lines.append(
            f"The replacement is gated on sample size: it engages "
            f"automatically once the labeled corpus reaches "
            f"**{result.min_n}** objections with both outcome classes "
            f"present. Until then, no action is required — the nightly "
            f"job re-checks the corpus and this note is its output."
        )
        lines.append("")
        return "\n".join(lines) + "\n"

    # Fitted.
    model = result.model
    assert model is not None  # status == fitted guarantees this
    lines.append("## Fitted model is active")
    lines.append("")
    lines.append(
        "The stipulated rubric has been replaced as the active severity "
        "scorer by a fitted logistic regression "
        "(`score_objection_with_model`). The stipulated formula "
        "(`score_objection`) is retained in code as the cold-start "
        "fallback and the ablation alternative — it is not deleted."
    )
    lines.append("")
    lines.append(f"- **Trained at:** {model.trained_at}")
    lines.append(f"- **Train rows (production refit):** {model.n_train}")
    lines.append(f"- **L2 penalty:** {model.l2}")
    lines.append(f"- **Base rate (material change):** {model.base_rate:.4f}")
    lines.append("")
    lines.append("### Held-out evaluation")
    lines.append("")
    ev = result.evaluation
    if ev is None:
        lines.append(
            "_No held-out shard was available for this run — the "
            "deterministic split left the holdout empty. The production "
            "model is fit on all labeled data; treat its skill as "
            "unmeasured until the corpus grows._"
        )
    else:
        verdict = (
            "beats the predict-the-base-rate baseline"
            if ev.beats_baseline
            else "**does NOT beat the baseline — treat as noise**"
        )
        lines.append(f"- **Held-out n:** {ev.n_eval}")
        lines.append(
            f"- **Skill (vs base-rate predictor):** {ev.skill:+.4f} "
            f"— {verdict}"
        )
        lines.append(f"- **Log loss:** {ev.log_loss:.4f} "
                     f"(baseline {ev.baseline_log_loss:.4f})")
        lines.append(f"- **AUC:** {ev.auc:.4f}")
        lines.append(f"- **Brier:** {ev.brier:.4f}")
        lines.append(f"- **Accuracy @0.5:** {ev.accuracy:.4f}")
    lines.append("")
    lines.append("### Feature weights (log-odds)")
    lines.append("")
    lines.append("| Feature | Weight |")
    lines.append("| --- | --- |")
    for name, w in zip(model.feature_names, model.weights):
        lines.append(f"| `{name}` | {w:+.4f} |")
    lines.append(f"| _bias_ | {model.bias:+.4f} |")
    lines.append("")
    lines.append(
        "The reliability diagram (predicted severity vs realized "
        "material-change rate) is surfaced on the methods page."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


__all__ = [
    "ARTIFACT_SCHEMA",
    "COLD_START_MIN_N",
    "DEFAULT_L2",
    "DEFAULT_RESCORE_DELTA",
    "FEATURE_NAMES",
    "MODEL_SCHEMA",
    "OUTCOME_ADDENDUM",
    "OUTCOME_DISMISSED",
    "OUTCOME_LABELS",
    "OUTCOME_MATERIAL",
    "RELIABILITY_SPARSE_THRESHOLD",
    "STATUS_COLD_START",
    "STATUS_FITTED",
    "CalibrationEvaluation",
    "CalibrationFitResult",
    "ConclusionRescore",
    "LabeledObjection",
    "RawObjection",
    "ReliabilityBin",
    "SeverityCalibrationModel",
    "calibration_artifact",
    "classify_outcome",
    "evaluate_calibration",
    "feature_dict",
    "feature_vector",
    "fit_severity_calibration",
    "founder_queue",
    "label_objections",
    "load_labeled_corpus",
    "outcome_counts",
    "reliability_diagram",
    "rescore_live_objections",
    "status_markdown",
    "train_severity_calibration_model",
]
