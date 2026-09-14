-- ============================================================
-- Ad Exposure -> Engagement: Analytical Dataset Build
-- Engine: DuckDB (works directly on the CSV files, no server needed)
-- Run in VS Code with the DuckDB / SQLTools extension, or:
--   duckdb < analysis.sql
-- ============================================================

-- 1. Load raw files -------------------------------------------------
CREATE OR REPLACE TABLE users        AS SELECT * FROM read_csv_auto('users.csv');
CREATE OR REPLACE TABLE ad_exposure  AS SELECT * FROM read_csv_auto('ad_exposure.csv');
CREATE OR REPLACE TABLE activity     AS SELECT * FROM read_csv_auto('activity.csv');

-- 2. Outcome: sessions in the 7 days FROM exposure_date (inclusive) through +6 days
--    Window: [exposure_date, exposure_date + 6]  -- strictly AFTER the touchpoint window starts
CREATE OR REPLACE TABLE outcome AS
SELECT
    e.user_id,
    SUM(a.sessions) AS sessions_post_7d
FROM ad_exposure e
JOIN activity a
  ON a.user_id = e.user_id
 AND a.date BETWEEN e.exposure_date AND e.exposure_date + INTERVAL 6 DAY
GROUP BY e.user_id;

-- 3. Pre-period features (all computed strictly BEFORE exposure_date to avoid leakage)
CREATE OR REPLACE TABLE pre_features AS
SELECT
    e.user_id,
    SUM(CASE WHEN a.date BETWEEN e.exposure_date - INTERVAL 7 DAY  AND e.exposure_date - INTERVAL 1 DAY THEN a.sessions ELSE 0 END) AS sessions_pre_7d,
    SUM(CASE WHEN a.date BETWEEN e.exposure_date - INTERVAL 28 DAY AND e.exposure_date - INTERVAL 1 DAY THEN a.sessions ELSE 0 END) AS sessions_pre_28d,
    COUNT(DISTINCT CASE WHEN a.date BETWEEN e.exposure_date - INTERVAL 28 DAY AND e.exposure_date - INTERVAL 1 DAY
                          AND a.sessions > 0 THEN a.date END) AS active_days_pre_28d
FROM ad_exposure e
JOIN activity a ON a.user_id = e.user_id
GROUP BY e.user_id;

-- 4. Final analytical table: one row per user
CREATE OR REPLACE TABLE analysis_dataset AS
SELECT
    e.user_id,
    e.exposed,
    e.exposure_date,
    u.country,
    u.device_type,
    u.prior_engagement_score,
    u.signup_date,
    COALESCE(f.sessions_pre_7d, 0)      AS sessions_pre_7d,
    COALESCE(f.sessions_pre_28d, 0)     AS sessions_pre_28d,
    COALESCE(f.active_days_pre_28d, 0)  AS active_days_pre_28d,
    COALESCE(o.sessions_post_7d, 0)     AS sessions_post_7d
FROM ad_exposure e
JOIN users u        ON u.user_id = e.user_id
LEFT JOIN pre_features f ON f.user_id = e.user_id
LEFT JOIN outcome o      ON o.user_id = e.user_id;

COPY analysis_dataset TO 'analysis_dataset.csv' (HEADER, DELIMITER ',');

-- 5. Naive (unadjusted) comparison -- this is the biased baseline the brief warns about
SELECT
    exposed,
    COUNT(*)                                  AS n_users,
    ROUND(AVG(sessions_post_7d), 3)           AS avg_sessions_post_7d,
    ROUND(AVG(sessions_pre_7d), 3)            AS avg_sessions_pre_7d,
    ROUND(AVG(prior_engagement_score), 2)     AS avg_prior_engagement_score
FROM analysis_dataset
GROUP BY exposed
ORDER BY exposed;

-- 6. Covariate balance check: are the two groups comparable pre-treatment?
--    Large gaps here are exactly what makes the naive comparison biased.
SELECT
    exposed,
    ROUND(AVG(sessions_pre_28d), 2)        AS avg_sessions_pre_28d,
    ROUND(AVG(active_days_pre_28d), 2)     AS avg_active_days_pre_28d,
    ROUND(AVG(prior_engagement_score), 2)  AS avg_prior_engagement_score
FROM analysis_dataset
GROUP BY exposed;

-- Note: the causal (confounder-adjusted) effect estimate itself is computed with
-- OLS regression in Python (see causal_analysis.py) because plain SQL aggregates
-- cannot fit a multivariate regression. SQL's job here is the leakage-safe
-- feature build above; Python's job is the adjustment model.
