# Ad Exposure → Engagement: Causal Impact Analysis

## Business question
Did the two-week ad campaign *cause* higher post-touchpoint engagement (app
sessions), or does the raw exposed-vs-unexposed gap just reflect who the
campaign targeted?

## The core problem: targeting bias
Exposure was **not randomized**. The targeting logic favored users who
already looked more likely to engage — higher prior engagement scores and
recent activity spikes. That means, before the ad ever ran, exposed users
were already more active than unexposed users. A raw average comparison
mixes this pre-existing gap with any real ad effect. Confirmed in the data:

| | Exposed | Unexposed |
|---|---|---|
| Avg sessions, 7 days *before* exposure | 23.4 | 15.8 |
| Avg prior_engagement_score | 59.5 | 45.6 |

Exposed users were already ~48% more active before seeing a single ad —
so the two groups are not comparable as-is.

## Approach
1. **SQL (`analysis.sql`, DuckDB)** — builds a leakage-safe, one-row-per-user
   analytical table:
   - Outcome: total sessions from `exposure_date` through `exposure_date + 6`
   - Pre-period features (all computed strictly *before* `exposure_date`,
     so nothing from the outcome window leaks into the predictors):
     `sessions_pre_7d`, `sessions_pre_28d`, `active_days_pre_28d`,
     plus `prior_engagement_score`, `country`, `device_type` from `users.csv`.
2. **Python (`causal_analysis.py`)** — regression adjustment (OLS, ANCOVA-style):
   `sessions_post_7d ~ exposed + pre-period covariates + country + device_type`.
   The coefficient on `exposed` estimates the ad's effect *holding the
   observed confounders fixed* — this is what removes the targeting bias
   the naive comparison suffers from.
3. **Power BI** — the exported CSVs (`analysis_dataset.csv`,
   `effect_summary.csv`, `effect_by_tier.csv`, `daily_decay.csv`,
   `exposure_rate_by_device.csv`, `exposure_rate_by_country.csv`) are the
   report's data model; see "Building the Power BI report" below.

## Results

| Estimate | Value |
|---|---|
| Naive difference (exposed − unexposed) | **+10.32 sessions** |
| Regression-adjusted effect | **+3.64 sessions** (95% CI: 3.35 to 3.92, p < 0.001) |
| Share of naive gap explained by pre-existing differences | ~65% |

**Bottom line:** the campaign appears to have a real, statistically
significant positive effect on engagement (~3.6 extra sessions per user in
the week after exposure) — but the naive comparison overstates it by
roughly 3x because it mostly reflects who was targeted, not what the ad did.

## Assumptions & limitations (read before presenting to stakeholders)
- **Unconfoundedness assumption**: this estimate is only valid if
  `sessions_pre_7d`, `sessions_pre_28d`, `active_days_pre_28d`,
  `prior_engagement_score`, `country`, and `device_type` capture the
  *full* targeting logic. If the real ad platform used other signals we
  don't have (e.g. in-app browsing behavior, push notification history),
  some bias likely remains.
- This is regression adjustment, not a randomized experiment — treat it as
  a defensible estimate, not ground truth. A/B testing on future campaigns
  would be the gold-standard follow-up.
- No interference/spillover assumed between users (reasonable for an app
  engagement metric, but worth flagging).

## Three extra insights (not asked for, but useful)
1. **Targeting wasn't just behavioral — it was platform-skewed.** iOS
   users were far more likely to be exposed (62.8%) than Web users
   (44.5%), and US users more than any other country (59.5% vs ~48-52%
   elsewhere). If ad spend allocation wasn't intended to be
   platform/geo-skewed, this is worth a conversation with the media
   buying team.
2. **The effect fades over the week.** Looking day-by-day within the
   7-day post window, the exposed-vs-unexposed session gap shrinks from
   ~1.66/day on day 0 to ~1.27/day on day 6 — a ~24% decline. This
   suggests the lift is concentrated right after exposure rather than a
   durable habit change, which matters for deciding campaign frequency.
3. **The effect is not uniform across users.** Splitting by pre-period
   activity tier, the adjusted effect is smaller for already-low-activity
   users (+2.3 sessions) than for mid/high-activity users (+4.5 / +4.2
   sessions). If the goal is *activating* dormant users rather than
   further engaging already-active ones, this campaign's targeting was
   arguably pointed at the wrong segment.

## Files
- `users.csv`, `ad_exposure.csv`, `activity.csv` — source data (as provided)
- `analysis.sql` — DuckDB SQL: feature build + naive comparison + balance check
- `causal_analysis.py` — Python: regression-adjusted effect + heterogeneity + tables
- `analysis_dataset.csv` — one row per user, all features + outcome (Power BI data source)
- `effect_summary.csv`, `effect_by_tier.csv`, `model_coefficients.csv`,
  `daily_decay.csv`, `exposure_rate_by_device.csv`, `exposure_rate_by_country.csv` —
  small summary tables for the Power BI report / README figures

## Reproducing
```bash
pip install duckdb pandas statsmodels
python3 -c "import duckdb; duckdb.connect().execute(open('analysis.sql').read())"
python3 causal_analysis.py
```

## Building the Power BI report
1. Open Power BI Desktop → Get Data → Text/CSV → load `analysis_dataset.csv`
   as the main fact table, plus the six summary CSVs above.
2. Suggested pages:
   - **Overview**: naive vs. adjusted effect (from `effect_summary.csv`) as
     two KPI cards side by side, with a one-line caption on why they differ.
   - **Balance check**: bar chart of pre-period averages by `exposed`
     (from `analysis_dataset.csv`) — shows why the naive number is biased.
   - **Effect by segment**: bar chart from `effect_by_tier.csv`.
   - **Decay over time**: line chart from `daily_decay.csv`
     (`day_offset` on X, `avg_sessions` on Y, split by `exposed`).
   - **Targeting patterns**: bar charts from `exposure_rate_by_device.csv`
     and `exposure_rate_by_country.csv`.
3. Save as `ad_exposure_impact.pbix`.
