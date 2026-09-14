"""
Causal effect of ad exposure on post-touchpoint engagement.

Why not just compare exposed vs unexposed averages?
Exposure was NOT randomized -- targeting favored users who already looked
more likely to engage (higher prior engagement, recent activity spikes).
So exposed and unexposed users differ systematically BEFORE the ad ever
ran. A naive comparison mixes the true ad effect with this pre-existing
gap (selection bias). We adjust for the confounders that drove targeting.

Approach: regression adjustment (ANCOVA-style OLS)
    sessions_post_7d ~ exposed + sessions_pre_7d + sessions_pre_28d
                        + active_days_pre_28d + prior_engagement_score
                        + C(country) + C(device_type)

The coefficient on `exposed` is the estimated average treatment effect
on the treated population, holding the observed pre-period confounders
fixed. This is a standard, transparent, defensible approach for an
observational A/B-like setting with good pre-period covariates -- it is
NOT a substitute for randomization, and it only controls for confounding
we can measure (see caveats in README).
"""
import pandas as pd
import numpy as np
import statsmodels.formula.api as smf

df = pd.read_csv("analysis_dataset.csv")

# ---- 1. Naive (biased) comparison -----------------------------------
naive_exposed = df.loc[df.exposed == 1, "sessions_post_7d"].mean()
naive_unexposed = df.loc[df.exposed == 0, "sessions_post_7d"].mean()
naive_diff = naive_exposed - naive_unexposed

# ---- 2. Covariate balance (evidence of selection into treatment) ----
balance = df.groupby("exposed")[
    ["sessions_pre_7d", "sessions_pre_28d", "active_days_pre_28d", "prior_engagement_score"]
].mean()

# ---- 3. Regression-adjusted effect -----------------------------------
model = smf.ols(
    "sessions_post_7d ~ exposed + sessions_pre_7d + sessions_pre_28d "
    "+ active_days_pre_28d + prior_engagement_score + C(country) + C(device_type)",
    data=df,
).fit(cov_type="HC1")  # robust SEs

adj_effect = model.params["exposed"]
adj_se = model.bse["exposed"]
adj_ci = model.conf_int().loc["exposed"].tolist()
adj_p = model.pvalues["exposed"]

# ---- 4. Sensitivity check: add an interaction for pre-period activity tier
df["pre_tier"] = pd.qcut(df["sessions_pre_28d"], q=3, labels=["low", "mid", "high"], duplicates="drop")
tier_effects = {}
for tier, sub in df.groupby("pre_tier", observed=True):
    m = smf.ols(
        "sessions_post_7d ~ exposed + sessions_pre_7d + sessions_pre_28d "
        "+ active_days_pre_28d + prior_engagement_score + C(country) + C(device_type)",
        data=sub,
    ).fit(cov_type="HC1")
    tier_effects[tier] = (m.params["exposed"], m.bse["exposed"], len(sub))

print("=" * 60)
print("NAIVE (UNADJUSTED) COMPARISON")
print("=" * 60)
print(f"Exposed avg sessions_post_7d:   {naive_exposed:.3f}")
print(f"Unexposed avg sessions_post_7d: {naive_unexposed:.3f}")
print(f"Naive difference:               {naive_diff:.3f}")
print()
print("=" * 60)
print("COVARIATE BALANCE (pre-period, by exposure group)")
print("=" * 60)
print(balance.round(2))
print()
print("=" * 60)
print("REGRESSION-ADJUSTED (CAUSAL) ESTIMATE")
print("=" * 60)
print(f"Adjusted effect of exposure:    {adj_effect:.3f} sessions")
print(f"Robust SE:                      {adj_se:.3f}")
print(f"95% CI:                         [{adj_ci[0]:.3f}, {adj_ci[1]:.3f}]")
print(f"p-value:                        {adj_p:.4f}")
print(f"R-squared:                      {model.rsquared:.3f}")
print()
print("Bias removed by adjustment: naive - adjusted =", round(naive_diff - adj_effect, 3))
print()
print("=" * 60)
print("EFFECT BY PRIOR-ENGAGEMENT TIER (heterogeneity check)")
print("=" * 60)
for tier, (eff, se, n) in tier_effects.items():
    print(f"{tier:>5}  (n={n:4}):  effect={eff:6.3f}  se={se:.3f}")

# Save a tidy summary for Power BI / README
summary = pd.DataFrame({
    "metric": ["naive_exposed_avg", "naive_unexposed_avg", "naive_diff",
               "adjusted_effect", "adjusted_se", "adjusted_ci_low", "adjusted_ci_high", "adjusted_p"],
    "value": [naive_exposed, naive_unexposed, naive_diff,
              adj_effect, adj_se, adj_ci[0], adj_ci[1], adj_p],
})
summary.to_csv("effect_summary.csv", index=False)

tier_df = pd.DataFrame(
    [(t, e, s, n) for t, (e, s, n) in tier_effects.items()],
    columns=["prior_activity_tier", "adjusted_effect", "se", "n"],
)
tier_df.to_csv("effect_by_tier.csv", index=False)

# Full model coefficient table (useful for README appendix / PBI tooltip)
coef_table = pd.DataFrame({
    "term": model.params.index,
    "coef": model.params.values,
    "se": model.bse.values,
    "p_value": model.pvalues.values,
})
coef_table.to_csv("model_coefficients.csv", index=False)

print("\nSaved: effect_summary.csv, effect_by_tier.csv, model_coefficients.csv")
