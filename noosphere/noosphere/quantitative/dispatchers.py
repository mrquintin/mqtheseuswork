"""Data-source and statistical-test dispatchers for the quantitative runner.

Two seams are formalised here so the runner stays a thin orchestrator:

* :func:`resolve_data_source` turns a ``DataSourceSpec`` into a
  pandas-like rows iterable. Supported sources in v1: internal
  Postgres tables (read-only via the noosphere ``Store``), CSV/Parquet
  files under ``noosphere/data/quantitative/``, and a thin yfinance
  fetcher. Unknown sources raise :class:`UnknownDataSourceError`.

* :func:`run_test` dispatches a ``StatisticalTestSpec`` against the
  resolved dataframe and returns a ``QuantitativeTestOutput``. Each
  branch documents the library it leans on so the formalisation
  drafter and the runner stay in sync.

Both seams are sync; the runner runs them inside a thread executor so
the scheduler does not block on a blocking SciPy call.
"""

from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

from noosphere.models import (
    DataSourceSpec,
    QuantitativeTestOutput,
    StatisticalTestKind,
    StatisticalTestSpec,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pandas as pd


DATA_DIR = Path(__file__).parents[2] / "data" / "quantitative"

# Internal Postgres-style sources are addressed as "postgres://<table>"
# or "internal://<table>"; the runner reads them through the noosphere
# Store engine (read-only by convention — the runner never writes back).
_INTERNAL_PROVENANCE_PATTERN = re.compile(r"^(postgres|internal)://([A-Za-z0-9_\".]+)$")

# yfinance fetches are addressed as "yfinance://<TICKER>?period=...".
_YFINANCE_PATTERN = re.compile(r"^yfinance://([A-Za-z0-9\.\-]+)(?:\?(.+))?$")

# File sources resolve under ``DATA_DIR``. Absolute paths are denied so
# a misbehaving formalisation cannot point the runner at /etc/shadow.
_FILE_PATTERN = re.compile(r"^file://(.+)$")


class UnknownDataSourceError(ValueError):
    """Raised when a ``DataSourceSpec`` provenance is not supported.

    The runner converts this into a ``FAILED`` per-source result row
    with ``error="UNKNOWN_DATA_SOURCE"`` rather than crashing.
    """


@dataclass(frozen=True)
class ResolvedDataset:
    name: str
    dataframe: "pd.DataFrame"
    provenance: str
    row_count: int


def _require_pandas() -> Any:
    try:
        import pandas as pd  # noqa: WPS433 — lazy import.

        return pd
    except ImportError as exc:  # pragma: no cover
        raise UnknownDataSourceError(
            "pandas is required for the quantitative runner"
        ) from exc


def _resolve_file_path(rel_or_path: str) -> Path:
    candidate = Path(rel_or_path)
    if candidate.is_absolute():
        raise UnknownDataSourceError(
            "absolute file paths are not permitted in quantitative data sources"
        )
    # Allow either "fixtures/foo.csv" or "foo.csv" — both resolve under
    # DATA_DIR. Tests inject a fixture path via the runner kwarg.
    resolved = (DATA_DIR / candidate).resolve()
    if not str(resolved).startswith(str(DATA_DIR.resolve())):
        raise UnknownDataSourceError(
            f"file path escapes data root: {rel_or_path}"
        )
    return resolved


def _load_file(path: Path) -> "pd.DataFrame":
    pd = _require_pandas()
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise UnknownDataSourceError(
        f"unsupported file extension: {path.suffix} (csv/parquet only)"
    )


def _yfinance_fetcher() -> Any:
    """Lazy yfinance import wrapped so tests can monkeypatch it.

    The runner never imports ``yfinance`` at module-load time; tests
    monkeypatch this function to inject a stub frame and assert that no
    real network call is attempted.
    """
    import yfinance as yf  # noqa: WPS433 — lazy import.

    return yf


def _load_yfinance(ticker: str, query: str | None) -> "pd.DataFrame":
    pd = _require_pandas()
    yf = _yfinance_fetcher()
    period = "1y"
    interval = "1d"
    if query:
        for chunk in query.split("&"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            if key == "period":
                period = value
            elif key == "interval":
                interval = value
    df = yf.download(
        ticker, period=period, interval=interval, progress=False, auto_adjust=False
    )
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return df.reset_index()


def resolve_data_source(
    spec: DataSourceSpec,
    *,
    data_dir: Path | None = None,
    store: Any | None = None,
) -> ResolvedDataset:
    """Resolve a ``DataSourceSpec.provenance`` to a pandas DataFrame.

    ``data_dir`` overrides the module-level default; the test fixture
    formalisation points at ``noosphere/tests/fixtures`` so the runner
    can be exercised without seeding the gitignored ``data/`` tree.
    """

    global DATA_DIR
    pd = _require_pandas()
    provenance = (spec.provenance or "").strip()
    if not provenance:
        raise UnknownDataSourceError("empty provenance")

    file_match = _FILE_PATTERN.match(provenance)
    if file_match:
        previous = DATA_DIR
        if data_dir is not None:
            DATA_DIR = data_dir
        try:
            path = _resolve_file_path(file_match.group(1))
        finally:
            DATA_DIR = previous
        df = _load_file(path)
        return ResolvedDataset(
            name=spec.name,
            dataframe=df,
            provenance=provenance,
            row_count=int(len(df)),
        )

    yf_match = _YFINANCE_PATTERN.match(provenance)
    if yf_match:
        ticker = yf_match.group(1)
        query = yf_match.group(2)
        df = _load_yfinance(ticker, query)
        return ResolvedDataset(
            name=spec.name,
            dataframe=df,
            provenance=provenance,
            row_count=int(len(df)),
        )

    internal_match = _INTERNAL_PROVENANCE_PATTERN.match(provenance)
    if internal_match:
        if store is None:
            raise UnknownDataSourceError(
                "internal data sources require a Store instance"
            )
        table = internal_match.group(2)
        # Read-only: explicitly use SELECT *. Quoting is deliberate —
        # the table name is constrained by the regex above.
        from sqlalchemy import text as sa_text

        with store.engine.connect() as conn:
            rows = conn.execute(sa_text(f'SELECT * FROM {table}')).fetchall()
            cols = list(conn.execute(sa_text(f'SELECT * FROM {table} LIMIT 0')).keys())
        df = pd.DataFrame(rows, columns=cols)
        return ResolvedDataset(
            name=spec.name,
            dataframe=df,
            provenance=provenance,
            row_count=int(len(df)),
        )

    raise UnknownDataSourceError(provenance)


# ── Test dispatch ───────────────────────────────────────────────────────────


def _enum(kind: Any) -> str:
    return kind.value if hasattr(kind, "value") else str(kind)


def _filter_frame(df: "pd.DataFrame", dataset_filter: str) -> "pd.DataFrame":
    """Apply a ``DataFrame.query`` filter, guarding against bad expressions.

    Empty filter → no-op. Failing filter → raise so the runner reports
    the test as FAILED with a useful error.
    """

    text = (dataset_filter or "").strip()
    if not text:
        return df
    return df.query(text)


def _regression_test(
    df: "pd.DataFrame", spec: StatisticalTestSpec
) -> tuple[QuantitativeTestOutput, dict[str, Any]]:
    """OLS regression via statsmodels.

    Returns the ``QuantitativeTestOutput`` plus a side-channel
    ``{"fitted": ..., "resid": ...}`` payload the runner uses to draw
    the residual plot.
    """

    pd = _require_pandas()
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing dependency: {exc}",
                passed_threshold=False,
            ),
            {},
        )

    cols = [spec.dependent, *spec.independents, *spec.controls]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing columns: {missing}",
                passed_threshold=False,
            ),
            {},
        )

    frame = df[cols].dropna()
    if len(frame) < 3:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                sample_size=int(len(frame)),
                notes="insufficient rows for OLS (<3)",
                passed_threshold=False,
            ),
            {},
        )

    y = frame[spec.dependent].astype(float).to_numpy()
    x_cols = [*spec.independents, *spec.controls]
    X_df = frame[x_cols].astype(float)
    focal = spec.independents[0] if spec.independents else x_cols[0]

    # Prefer statsmodels for proper p-values + CIs; fall back to a
    # numpy/scipy OLS so the runner does not depend on statsmodels.
    try:
        import statsmodels.api as sm

        X_with_const = sm.add_constant(X_df, has_constant="add")
        model = sm.OLS(y, X_with_const).fit()
        coef = float(model.params.get(focal, float("nan")))
        pval = float(model.pvalues.get(focal, float("nan")))
        ci_df = model.conf_int()
        ci = ci_df.loc[focal].tolist() if focal in ci_df.index else None
        fitted = np.asarray(model.fittedvalues, dtype=float).tolist()
        resid = np.asarray(model.resid, dtype=float).tolist()
        r2 = float(model.rsquared)
    except ImportError:
        # numpy OLS with scipy-derived t/p values.
        from scipy import stats as _stats

        X = np.column_stack(
            [np.ones(len(frame)), X_df.to_numpy()]
        )
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        fitted_arr = X @ beta
        resid_arr = y - fitted_arr
        n = X.shape[0]
        k = X.shape[1]
        dof = max(1, n - k)
        sigma2 = float((resid_arr @ resid_arr) / dof)
        cov = sigma2 * np.linalg.pinv(X.T @ X)
        se = np.sqrt(np.diag(cov))
        # Coefficient indices: column 0 is intercept, then x_cols.
        focal_index = x_cols.index(focal) + 1
        coef = float(beta[focal_index])
        t_stat = coef / float(se[focal_index]) if se[focal_index] > 0 else float("nan")
        pval = (
            float(2.0 * (1.0 - _stats.t.cdf(abs(t_stat), dof)))
            if t_stat == t_stat
            else float("nan")
        )
        t_crit = float(_stats.t.ppf(0.975, dof))
        ci = [
            coef - t_crit * float(se[focal_index]),
            coef + t_crit * float(se[focal_index]),
        ]
        ss_res = float((resid_arr @ resid_arr))
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        fitted = fitted_arr.tolist()
        resid = resid_arr.tolist()

    passed = bool(pval == pval and pval < float(spec.expected_p_threshold))
    output = QuantitativeTestOutput(
        test_kind=_enum(spec.kind),
        statistic=coef,
        p_value=pval if pval == pval else None,
        effect_size=coef,
        sample_size=int(len(frame)),
        confidence_interval=[float(v) for v in ci] if ci is not None else None,
        passed_threshold=passed,
        notes=f"focal={focal}; r2={r2:.4f}",
    )
    sidecar = {"fitted": fitted, "resid": resid}
    return output, sidecar


def _ks_test(
    df: "pd.DataFrame", spec: StatisticalTestSpec
) -> tuple[QuantitativeTestOutput, dict[str, Any]]:
    """Two-sample Kolmogorov–Smirnov via scipy.

    ``dependent`` is the column; ``independents[0]`` names a boolean /
    binary partition column. Missing partition column → FAILED.
    """

    try:
        from scipy import stats
    except ImportError as exc:  # pragma: no cover
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing dependency: {exc}",
                passed_threshold=False,
            ),
            {},
        )
    if not spec.independents:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes="ks_test requires one independent (partition column)",
                passed_threshold=False,
            ),
            {},
        )
    partition = spec.independents[0]
    if spec.dependent not in df.columns or partition not in df.columns:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing columns: {[spec.dependent, partition]}",
                passed_threshold=False,
            ),
            {},
        )
    frame = df[[spec.dependent, partition]].dropna()
    groups = list(frame.groupby(partition))
    if len(groups) < 2:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                sample_size=int(len(frame)),
                notes="ks_test requires two groups",
                passed_threshold=False,
            ),
            {},
        )
    a = groups[0][1][spec.dependent].astype(float).values
    b = groups[1][1][spec.dependent].astype(float).values
    statistic, p_value = stats.ks_2samp(a, b)
    passed = bool(p_value < float(spec.expected_p_threshold))
    return (
        QuantitativeTestOutput(
            test_kind=_enum(spec.kind),
            statistic=float(statistic),
            p_value=float(p_value),
            sample_size=int(len(frame)),
            passed_threshold=passed,
            notes=f"groups={[str(g[0]) for g in groups[:2]]}",
        ),
        {"a": list(map(float, a)), "b": list(map(float, b))},
    )


def _correlation_test(
    df: "pd.DataFrame", spec: StatisticalTestSpec
) -> tuple[QuantitativeTestOutput, dict[str, Any]]:
    try:
        from scipy import stats
    except ImportError as exc:  # pragma: no cover
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing dependency: {exc}",
                passed_threshold=False,
            ),
            {},
        )
    if not spec.independents:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes="correlation requires one independent",
                passed_threshold=False,
            ),
            {},
        )
    other = spec.independents[0]
    if spec.dependent not in df.columns or other not in df.columns:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing columns: {[spec.dependent, other]}",
                passed_threshold=False,
            ),
            {},
        )
    frame = df[[spec.dependent, other]].dropna()
    if len(frame) < 3:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                sample_size=int(len(frame)),
                notes="insufficient rows (<3)",
                passed_threshold=False,
            ),
            {},
        )
    r, p = stats.pearsonr(frame[spec.dependent], frame[other])
    return (
        QuantitativeTestOutput(
            test_kind=_enum(spec.kind),
            statistic=float(r),
            p_value=float(p),
            effect_size=float(r),
            sample_size=int(len(frame)),
            passed_threshold=bool(p < float(spec.expected_p_threshold)),
        ),
        {},
    )


def _classification_test(
    df: "pd.DataFrame", spec: StatisticalTestSpec
) -> tuple[QuantitativeTestOutput, dict[str, Any]]:
    """Binary classification AUC via scikit-learn.

    ``dependent`` is the 0/1 label, ``independents`` are the features.
    Returns AUC as statistic and ships predicted/actual to the runner
    for the calibration plot.
    """

    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
    except ImportError as exc:  # pragma: no cover
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing dependency: {exc}",
                passed_threshold=False,
            ),
            {},
        )
    cols = [spec.dependent, *spec.independents]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                notes=f"missing columns: {missing}",
                passed_threshold=False,
            ),
            {},
        )
    frame = df[cols].dropna()
    if len(frame) < 8:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                sample_size=int(len(frame)),
                notes="insufficient rows (<8)",
                passed_threshold=False,
            ),
            {},
        )
    y = frame[spec.dependent].astype(int).values
    X = frame[spec.independents].astype(float).values
    if len(set(y.tolist())) < 2:
        return (
            QuantitativeTestOutput(
                test_kind=_enum(spec.kind),
                sample_size=int(len(frame)),
                notes="dependent has a single class",
                passed_threshold=False,
            ),
            {},
        )
    model = LogisticRegression(max_iter=200)
    model.fit(X, y)
    predicted = model.predict_proba(X)[:, 1]
    auc = float(roc_auc_score(y, predicted))
    return (
        QuantitativeTestOutput(
            test_kind=_enum(spec.kind),
            statistic=auc,
            effect_size=auc,
            sample_size=int(len(frame)),
            passed_threshold=bool(auc >= 0.6),
            notes=f"auc={auc:.4f}",
        ),
        {"predicted": predicted.tolist(), "actual": y.tolist()},
    )


def run_test(
    df: "pd.DataFrame", spec: StatisticalTestSpec
) -> tuple[QuantitativeTestOutput, dict[str, Any]]:
    """Dispatch a test spec to the right library and return its output.

    The second element of the tuple is sidecar data the runner uses to
    draw a plot. Empty dict means "no plot for this test."
    """

    kind = _enum(spec.kind)
    try:
        frame = _filter_frame(df, spec.dataset_filter)
    except Exception as exc:
        return (
            QuantitativeTestOutput(
                test_kind=kind,
                notes=f"filter failed: {exc}",
                passed_threshold=False,
            ),
            {},
        )

    if kind == StatisticalTestKind.REGRESSION.value:
        return _regression_test(frame, spec)
    if kind == StatisticalTestKind.KS_TEST.value:
        return _ks_test(frame, spec)
    if kind == StatisticalTestKind.CORRELATION.value:
        return _correlation_test(frame, spec)
    if kind == StatisticalTestKind.CLASSIFICATION.value:
        return _classification_test(frame, spec)
    # Event study, hazard, AB — not implemented in v1.
    return (
        QuantitativeTestOutput(
            test_kind=kind,
            notes=f"test kind not implemented in v1: {kind}",
            passed_threshold=False,
        ),
        {},
    )
