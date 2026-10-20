"""
pipeline/analytics/forecast.py
Phase 7 — EV registration forecasting per district and vehicle class.

Strategy:
- Uses statsmodels ExponentialSmoothing (Holt-Winters) — no Stan/cmdstan dependency.
- Districts with ≥ 12 months: direct model. Otherwise uses state-level share.
- Three scenarios: baseline, accelerated (1.5×), conservative (0.7×).
- 95% confidence interval approximated as ± 1.96 * residual std.
- Backtests by training to 12 months ago, comparing forecast to actuals.
"""
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    logger.warning("statsmodels not available — using linear trend fallback.")

ROOT = Path(os.environ.get("PROJECT_ROOT", str(Path(__file__).resolve().parents[3])))
with open(ROOT / "config" / "project.yaml") as f:
    CONFIG = yaml.safe_load(f)

DB_URL = (
    f"postgresql+psycopg2://{os.environ.get('DB_USER','evuser')}:"
    f"{os.environ.get('DB_PASSWORD','password')}@"
    f"{os.environ.get('DB_HOST','db')}:"
    f"{os.environ.get('DB_PORT','5432')}/"
    f"{os.environ.get('DB_NAME','ev_infra')}"
)

MODEL_VERSION = "2.0"   # bumped: Holt-Winters replaces Prophet
HORIZON_MONTHS = 36
MIN_MONTHS = 12
SCENARIOS = {
    "baseline":     1.0,
    "accelerated":  1.5,
    "conservative": 0.7,
}
VEHICLE_CLASSES = ["2W", "3W", "4W", "bus", "other"]


def load_series(engine) -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(text("""
            SELECT admin_unit_id, year, month, vehicle_class, SUM(count) AS count
            FROM clean.ev_registrations
            GROUP BY admin_unit_id, year, month, vehicle_class
        """), conn)
    df["ds"] = pd.to_datetime(df[["year", "month"]].assign(day=1))
    df["y"] = df["count"].astype(float)
    return df


def fit_and_forecast(series_y: np.ndarray, horizon: int):
    """
    Fit Holt-Winters (additive trend, no seasonality for short series)
    and return (forecast_mean, forecast_lower, forecast_upper).
    """
    n = len(series_y)
    if HAS_STATSMODELS and n >= MIN_MONTHS:
        try:
            seasonal = "add" if n >= 24 else None
            sp = 12 if seasonal else None
            model = ExponentialSmoothing(
                series_y, trend="add", seasonal=seasonal, seasonal_periods=sp,
                initialization_method="estimated"
            )
            fit = model.fit(optimized=True, remove_bias=True)
            fc = fit.forecast(horizon)
            fc = np.clip(fc, 0, None)
            # Approx 95% CI: ±1.96 * residual std
            resid_std = np.std(fit.resid) if len(fit.resid) > 1 else max(np.mean(series_y) * 0.2, 1)
            lo = np.clip(fc - 1.96 * resid_std, 0, None)
            hi = fc + 1.96 * resid_std
            return fc, lo, hi
        except Exception as e:
            logger.debug("ETS failed (%s), using linear trend.", e)

    # Fallback: simple linear trend extrapolation
    x = np.arange(n, dtype=float)
    coeffs = np.polyfit(x, series_y, 1) if n >= 2 else [0.0, series_y[-1]]
    x_future = np.arange(n, n + horizon, dtype=float)
    fc = np.clip(np.polyval(coeffs, x_future), 0, None)
    std = max(np.std(series_y) * 0.3, 1.0) if n > 1 else 1.0
    return fc, np.clip(fc - 1.96 * std, 0, None), fc + 1.96 * std


def main():
    logger.info("=== EV Registration Forecasting (Holt-Winters) ===")
    engine = create_engine(DB_URL, pool_pre_ping=True)
    df = load_series(engine)

    if df.empty:
        logger.warning("No EV registration data — skipping forecasting.")
        return

    # State-level aggregates for share computation
    state_totals: dict[str, float] = {}
    state_series: dict[str, np.ndarray] = {}
    for vc in VEHICLE_CLASSES:
        vdf = df[df.vehicle_class == vc].groupby("ds")["y"].sum().sort_index()
        state_totals[vc] = float(vdf.sum())
        state_series[vc] = vdf.values.astype(float)

    # Precompute district shares from latest year
    latest_year = int(df["year"].max())
    state_shares: dict[tuple, float] = {}
    for vc in VEHICLE_CLASSES:
        total = df[(df.vehicle_class == vc) & (df.year == latest_year)]["y"].sum()
        for uid, grp in df[(df.vehicle_class == vc) & (df.year == latest_year)].groupby("admin_unit_id"):
            state_shares[(int(uid), vc)] = float(grp["y"].sum()) / max(total, 1)

    inserted_total = 0
    backtest_rows = []
    cutoff = df["ds"].max() - pd.DateOffset(months=12)

    districts = df["admin_unit_id"].unique()
    for uid in districts:
        for vc in VEHICLE_CLASSES:
            series = df[(df.admin_unit_id == uid) & (df.vehicle_class == vc)].sort_values("ds")
            if series.empty:
                continue

            sy = series["y"].values.astype(float)

            # Backtest
            train_mask = series["ds"] <= cutoff
            test_mask  = series["ds"] > cutoff
            if train_mask.sum() >= 6 and test_mask.sum() > 0:
                try:
                    fc_bt, _, _ = fit_and_forecast(sy[train_mask.values], int(test_mask.sum()))
                    actual = sy[test_mask.values]
                    mape = float(np.mean(np.abs(actual - fc_bt[:len(actual)]) / np.maximum(actual, 1)))
                    backtest_rows.append({"admin_unit_id": uid, "vehicle_class": vc, "mape": round(mape, 4)})
                except Exception:
                    pass

            # Choose series to forecast: district if enough data, else state
            use_district = len(sy) >= MIN_MONTHS
            if use_district:
                fc_vals, lo_vals, hi_vals = fit_and_forecast(sy, HORIZON_MONTHS)
            elif len(state_series.get(vc, [])) >= MIN_MONTHS:
                fc_vals, lo_vals, hi_vals = fit_and_forecast(state_series[vc], HORIZON_MONTHS)
                share = state_shares.get((int(uid), vc), 0.03)
                fc_vals = fc_vals * share
                lo_vals = lo_vals * share
                hi_vals = hi_vals * share
            else:
                continue

            # Future dates
            last_date = series["ds"].max()
            future_dates = pd.date_range(
                start=last_date + pd.DateOffset(months=1),
                periods=HORIZON_MONTHS, freq="MS"
            )

            try:
                with engine.begin() as conn:
                    for scenario, mult in SCENARIOS.items():
                        for i, fdate in enumerate(future_dates):
                            conn.execute(text("""
                                INSERT INTO analytics.forecasts
                                    (admin_unit_id, vehicle_class, scenario, period,
                                     evs_pred, lo, hi, model_version)
                                VALUES (:uid, :vc, :sc, :period, :pred, :lo, :hi, :mv)
                                ON CONFLICT (admin_unit_id, vehicle_class, scenario, period, model_version)
                                DO UPDATE SET evs_pred=EXCLUDED.evs_pred,
                                              lo=EXCLUDED.lo, hi=EXCLUDED.hi
                            """), {
                                "uid":    int(uid),
                                "vc":     vc,
                                "sc":     scenario,
                                "period": fdate.date().replace(day=1),
                                "pred":   round(float(fc_vals[i] * mult), 2),
                                "lo":     round(float(lo_vals[i] * mult), 2),
                                "hi":     round(float(hi_vals[i] * mult), 2),
                                "mv":     MODEL_VERSION,
                            })
                            inserted_total += 1
            except Exception as e:
                logger.warning("DB insert failed for unit %s / %s: %s", uid, vc, e)

    # Backtest report
    if backtest_rows:
        reports_dir = ROOT / "reports"
        reports_dir.mkdir(exist_ok=True)
        bt_df = pd.DataFrame(backtest_rows)
        bt_df.to_csv(reports_dir / "backtest.csv", index=False)
        mean_mape = bt_df["mape"].mean()
        (reports_dir / "backtest.md").write_text(
            f"# Forecast Backtest Report\n\n"
            f"- Model: Holt-Winters ExponentialSmoothing (statsmodels)\n"
            f"- Cutoff: {cutoff.date()}\n"
            f"- Units tested: {bt_df['admin_unit_id'].nunique()}\n"
            f"- Mean MAPE: {mean_mape:.1%}\n\n"
            f"See backtest.csv for per-district results.\n",
            encoding="utf-8",
        )
        logger.info("Backtest mean MAPE: %.1f%%", mean_mape * 100)

    logger.info("Forecasting complete — %d forecast rows inserted.", inserted_total)


if __name__ == "__main__":
    main()
