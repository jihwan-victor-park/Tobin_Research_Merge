"""Build the paper's figures from results/*.csv. No database access.

    .venv/bin/python analysis/make_figures.py
"""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
FIG = os.path.abspath(os.path.join(ROOT, "..", "paper", "figures"))
os.makedirs(FIG, exist_ok=True)

# Validated categorical slots (light mode, all-pairs safe): blue, orange, aqua.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#b9b8b2"
GRID = "#e6e5e0"

plt.rcParams.update({
    "figure.dpi": 160, "savefig.dpi": 160, "savefig.bbox": "tight",
    "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
    "axes.edgecolor": INK2, "axes.linewidth": 0.7,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.labelcolor": INK2, "legend.frameon": False,
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.facecolor": "white", "axes.facecolor": "white",
})


def csv(name):
    return pd.read_csv(os.path.join(RES, name))


def grid(ax, axis="y"):
    ax.grid(axis=axis, color=GRID, linewidth=0.6, zorder=0)
    ax.set_axisbelow(True)


def save(fig, name):
    p = os.path.join(FIG, name)
    fig.savefig(p)
    plt.close(fig)
    print(f"  -> paper/figures/{name}")


# ── Fig 1: AI formation over time — counts and share as small multiples ────
def fig_trend():
    t = csv("11_ai_formation_by_year.csv")
    t = t[(t.year >= 2000) & (t.year <= 2025)]
    rb = csv("14_trend_constant_selection.csv")
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(6.4, 5.2), sharex=True,
                                 gridspec_kw={"height_ratios": [1, 1.15], "hspace": 0.18})

    a1.bar(t.year, t.n / 1000, color=MUTED, width=0.72, zorder=2, label="all firms")
    a1.bar(t.year, t.ai / 1000, color=BLUE, width=0.72, zorder=3, label="AI firms")
    grid(a1)
    a1.set_ylabel("firms founded (thousands)")
    a1.set_title("A.  Observed firm formation — recent cohorts are thinly observed",
                 loc="left", color=INK)
    a1.legend(loc="upper left", fontsize=8)
    a1.annotate("register\nentry lag", xy=(2024, 11), xytext=(2020.4, 34),
                fontsize=7.5, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.7))

    a2.fill_between(t.year, t.share_lo, t.share_hi, color=BLUE, alpha=0.16, lw=0, zorder=2)
    a2.plot(t.year, t.ai_share, color=BLUE, lw=2, zorder=4)
    m = rb[(rb.year >= 2005) & (rb.year <= 2025)]
    a2.plot(m.year, m.share_funded, color=ORANGE, lw=2, ls=(0, (4, 2)), zorder=3)
    a2.axvline(2022.9, color=INK2, lw=0.7, ls=":", zorder=1)
    a2.text(2022.75, 62, "ChatGPT\nNov 2022", fontsize=7.5, color=INK2, ha="right", va="top")
    a2.text(2025.2, t.ai_share.iloc[-1], "all firms", color=BLUE, fontsize=8, va="center")
    a2.text(2025.2, m.share_funded.iloc[-1], "financed\nfirms only", color=ORANGE,
            fontsize=8, va="center")
    grid(a2)
    a2.set_ylabel("AI share of the cohort (%)")
    a2.set_xlabel("founding year")
    a2.set_xlim(1999, 2028.5)
    a2.set_ylim(0, 75)
    a2.set_title("B.  AI share rises on both the full sample and a constant-selection sample",
                 loc="left", color=INK)
    save(fig, "fig1_ai_formation.pdf")


# ── Fig 2: coverage bias across AI definitions ─────────────────────────────
def fig_coverage():
    d = csv("01_ai_share_by_bucket.csv")
    order = ["canonical", "no_mention", "pre_llm", "mention", "evidence"]
    pretty = {"canonical": "canonical\n(pipeline)", "no_mention": "without\nmention flag",
              "pre_llm": "pre-LLM\n(tag or score)", "mention": "mention only\n(common support)",
              "evidence": "vendor tag or\nLLM verdict"}
    buckets = ["Unlisted", "Commercial A", "Commercial B"]
    cols = {"Unlisted": BLUE, "Commercial A": ORANGE, "Commercial B": AQUA}
    fig, ax = plt.subplots(figsize=(6.6, 3.5))
    w = 0.26
    x = np.arange(len(order))
    for k, b in enumerate(buckets):
        s = d[d.bucket == b].set_index("ai_definition").loc[order]
        pos = x + (k - 1) * w
        ax.bar(pos, s.ai_pct, width=w * 0.9, color=cols[b], zorder=3, label=b)
        ax.errorbar(pos, s.ai_pct, yerr=[s.ai_pct - s.ci_lo, s.ci_hi - s.ai_pct],
                    fmt="none", ecolor=INK2, elinewidth=0.8, capsize=1.8, zorder=4)
        for xi, v in zip(pos, s.ai_pct):
            ax.text(xi, v + 0.7, f"{v:.1f}", ha="center", fontsize=6.6, color=INK2, zorder=5)
    ax.axvspan(3.5, 4.5, color="#f4f3ef", zorder=0)
    ax.text(4, 16.5, "not comparable:\nvendor tags and LLM\nverdicts do not exist\nfor unlisted firms",
            ha="center", fontsize=7, color=INK2, style="italic", zorder=6)
    ax.set_xticks(x)
    ax.set_xticklabels([pretty[o] for o in order], fontsize=7.6)
    grid(ax)
    ax.set_ylabel("AI share of the bucket (%)")
    ax.set_ylim(0, 30)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, 1.16), fontsize=8, ncol=3)
    ax.set_title("AI prevalence by coverage status, under five definitions of the AI label",
                 loc="left", color=INK, pad=26)
    save(fig, "fig2_coverage_bias.pdf")


# ── Fig 3: robustness of the gap — LOO and measurement correction ──────────
def fig_robust():
    loo = csv("05b_leave_one_out_common_support.csv")
    cor = csv("08_corrected_coverage_gap.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 3.2),
                                 gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.62})

    lab = {"(none)": "full unlisted layer", "code_host_scan": "drop code-host scan",
           "portfolio_or_accelerator": "drop portfolios", "public_funder": "drop funder records",
           "scraped_site": "drop web scrapes"}
    loo = loo.iloc[::-1].reset_index(drop=True)
    y = np.arange(len(loo))
    a1.hlines(y, loo.gap_lo, loo.gap_hi, color=INK2, lw=1.1, zorder=3)
    a1.scatter(loo.gap_vs_A, y, s=34, color=BLUE, zorder=4)
    a1.axvline(0, color=INK2, lw=0.8, zorder=2)
    a1.set_yticks(y)
    a1.set_yticklabels([lab.get(v, v) for v in loo.dropped], fontsize=8)
    for yi, v in zip(y, loo.gap_vs_A):
        a1.text(v, yi - 0.36, f"{v:+.1f}", ha="center", fontsize=7, color=INK2)
    grid(a1, "x")
    a1.set_xlabel("gap vs Commercial A (percentage points)")
    a1.set_xlim(-1, 11)
    a1.set_ylim(-0.7, len(loo) - 0.3)
    a1.set_title("A.  Leave-one-channel-out\n(common-support label)", loc="left", color=INK,
                 fontsize=9, pad=10)

    names = ["raw label,\nCommercial A", "raw label,\nCommercial B",
             "error-corrected,\nCommercial A", "error-corrected,\nCommercial B"]
    vals = [cor.observed_gap_pp[0], cor.observed_gap_pp[1],
            cor.corrected_gap_pp[0], cor.corrected_gap_pp[1]]
    los = [np.nan, np.nan, cor.lo[0], cor.lo[1]]
    his = [np.nan, np.nan, cor.hi[0], cor.hi[1]]
    y2 = np.arange(len(names))[::-1]
    cols = [MUTED, MUTED, BLUE, ORANGE]
    a2.scatter(vals, y2, s=34, color=cols, zorder=4)
    for i in (2, 3):
        a2.hlines(y2[i], los[i], his[i], color=INK2, lw=1.1, zorder=3)
    a2.axvline(0, color=INK2, lw=0.8, zorder=2)
    a2.set_yticks(y2)
    a2.set_yticklabels(names, fontsize=7.6)
    for v, yi in zip(vals, y2):
        a2.text(v, yi - 0.38, f"{v:+.1f}", ha="center", fontsize=7, color=INK2)
    grid(a2, "x")
    a2.set_xlabel("gap (percentage points)")
    a2.set_xlim(-13, 26)
    a2.set_ylim(-0.7, len(names) - 0.3)
    a2.set_title("B.  Corrected for per-bucket\nclassification error", loc="left", color=INK,
                 fontsize=9, pad=10)
    save(fig, "fig3_gap_robustness.pdf")


# ── Fig 4: geography — early vs late AI intensity ──────────────────────────
def fig_geo():
    g = csv("21_country_ai_growth.csv").nlargest(18, "n_late").sort_values("share_late")
    fig, ax = plt.subplots(figsize=(6.2, 5.0))
    y = np.arange(len(g))
    ax.hlines(y, g.share_early, g.share_late, color=MUTED, lw=2.2, zorder=2)
    ax.scatter(g.share_early, y, s=26, color=ORANGE, zorder=3, label="founded 2010–2016")
    ax.scatter(g.share_late, y, s=26, color=BLUE, zorder=4, label="founded 2020–2025")
    for yi, v in zip(y, g.share_late):
        ax.text(v + 0.9, yi, f"{v:.0f}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(g.country, fontsize=8)
    grid(ax, "x")
    ax.set_xlabel("AI share of the country's firms in that cohort (%)")
    ax.set_xlim(0, 45)
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("AI intensity rose everywhere, but the spread between\necosystems widened",
                 loc="left", color=INK)
    save(fig, "fig4_geography.pdf")


# ── Fig 5: concentration ───────────────────────────────────────────────────
def fig_conc():
    c = csv("22_concentration_by_cohort.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 3.0))
    a1.plot(c.year, c.hhi_ai, color=BLUE, lw=2, zorder=4)
    a1.plot(c.year, c.hhi_all, color=MUTED, lw=2, zorder=3)
    a1.axvspan(2020, 2025, color="#f4f3ef", zorder=0)
    a1.text(2022.5, 0.68, "coverage\nthins", ha="center", fontsize=7, color=INK2, style="italic")
    a1.text(2001, c.hhi_ai.iloc[1] + 0.03, "AI firms", color=BLUE, fontsize=8)
    a1.text(2001, c.hhi_all.iloc[1] - 0.05, "all firms", color=INK2, fontsize=8)
    grid(a1)
    a1.set_ylabel("HHI across countries")
    a1.set_xlabel("founding year")
    a1.set_title("A.  Geographic concentration", loc="left", color=INK, fontsize=9)

    d = c.hhi_ai - c.hhi_all
    a2.axhline(0, color=INK2, lw=0.8, zorder=2)
    a2.bar(c.year, d, color=[BLUE if v > 0 else AQUA for v in d], width=0.72, zorder=3)
    a2.axvspan(2019.5, 2025.5, color="#f4f3ef", zorder=0)
    grid(a2)
    a2.set_ylabel("HHI(AI) − HHI(all firms)")
    a2.set_xlabel("founding year")
    a2.set_title("B.  AI-specific excess concentration", loc="left", color=INK, fontsize=9)
    a2.text(2010, -0.028, "AI more dispersed\nthan firms generally", fontsize=7,
            color=INK2, ha="center", style="italic")
    save(fig, "fig5_concentration.pdf")


# ── Fig 6: sectors ─────────────────────────────────────────────────────────
def fig_sector():
    s = csv("30_sector_ai.csv").sort_values("share_late")
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    y = np.arange(len(s))
    ax.hlines(y, s.share_early, s.share_late, color=MUTED, lw=2.2, zorder=2)
    ax.scatter(s.share_early, y, s=26, color=ORANGE, zorder=3, label="founded 2010–2016")
    ax.scatter(s.share_late, y, s=26, color=BLUE, zorder=4, label="founded 2020–2025")
    for yi, v in zip(y, s.share_late):
        ax.text(v + 1.4, yi, f"{v:.0f}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels(s.sector, fontsize=8)
    grid(ax, "x")
    ax.set_xlabel("AI share of the sector's firms in that cohort (%)")
    ax.set_xlim(0, 82)
    ax.legend(loc="lower right", fontsize=8)
    ax.set_title("Every sector became more AI-intensive; the ordering barely moved",
                 loc="left", color=INK)
    save(fig, "fig6_sectors.pdf")


# ── Fig 7: imputation experiment ───────────────────────────────────────────
def fig_imputation():
    e = csv("40_imputation_estimate_mode.csv")
    fill = csv("42_imputation_fill_rate.csv")
    DECLINE = {"nan", "none", "null", "unknown", "n/a", "", "not stated", "unspecified"}

    def clean(series, as_year=False):
        v = series.dropna().astype(str).str.strip().str.lower()
        v = v[~v.isin(DECLINE)]
        if as_year:
            v = pd.to_numeric(v, errors="coerce").dropna().astype(int).astype(str)
        return v

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.0), gridspec_kw={"wspace": 0.42})

    # A. cities — union of the two top-6 lists so both series are visible
    ax = axes[0]
    pv = clean(e.p_city).value_counts(normalize=True) * 100
    tv = clean(e.t_city).value_counts(normalize=True) * 100
    keys = list(dict.fromkeys(list(pv.head(5).index) + list(tv.head(4).index)))[:7]
    yy = np.arange(len(keys))
    ax.barh(yy + 0.2, [pv.get(k, 0) for k in keys], height=0.38, color=ORANGE, zorder=3)
    ax.barh(yy - 0.2, [tv.get(k, 0) for k in keys], height=0.38, color=BLUE, zorder=3)
    ax.set_yticks(yy)
    ax.set_yticklabels([k[:14] for k in keys], fontsize=7.5)
    ax.invert_yaxis()
    grid(ax, "x")
    ax.set_xlim(0, 13)
    ax.set_xlabel("share of firms (%)")
    ax.set_title("A.  City", loc="left", color=INK, fontsize=9)
    ax.text(12.7, -0.62, "model", color=ORANGE, fontsize=7.5, va="center", ha="right")
    ax.text(12.7, -0.15, "truth", color=BLUE, fontsize=7.5, va="center", ha="right")

    # B. founding year — the full distribution, where the round-number spikes show
    ax = axes[1]
    pv = clean(e.p_year, as_year=True).astype(int)
    tv = clean(e.t_year, as_year=True).astype(int)
    yrs = np.arange(2000, 2026)
    pc = np.array([100 * (pv == y).sum() / len(pv) for y in yrs])
    tc = np.array([100 * (tv == y).sum() / len(tv) for y in yrs])
    ax.bar(yrs + 0.2, pc, width=0.4, color=ORANGE, zorder=3, label="model estimate")
    ax.bar(yrs - 0.2, tc, width=0.4, color=BLUE, zorder=3, label="truth")
    grid(ax)
    ax.set_xlabel("founding year")
    ax.set_ylabel("share of firms (%)")
    ax.set_title("B.  Founding year", loc="left", color=INK, fontsize=9)
    ax.legend(fontsize=7.5, loc="upper right", bbox_to_anchor=(1.03, 1.04))
    for y in (2010, 2015, 2018):
        ax.annotate("", xy=(y + 0.2, pc[list(yrs).index(y)] + 0.6),
                    xytext=(y + 0.2, pc[list(yrs).index(y)] + 3.2),
                    arrowprops=dict(arrowstyle="->", color=INK2, lw=0.6))
    ax.text(2004.5, 13.5, "round\nnumbers", fontsize=7, color=INK2, ha="center", style="italic")
    ax.set_ylim(0, 21)

    # C. fill rate
    ax = axes[2]
    p = fill.pivot(index="field", columns="mode", values="fill_rate").loc[
        ["country", "city", "founded_year", "team_size"]]
    yy = np.arange(len(p))
    ax.barh(yy + 0.2, p["ESTIMATE"], height=0.38, color=ORANGE, zorder=3)
    ax.barh(yy - 0.2, p["GROUNDED"], height=0.38, color=BLUE, zorder=3)
    for yi, v in zip(yy + 0.2, p["ESTIMATE"]):
        ax.text(v + 3, yi, f"{v:.0f}", va="center", fontsize=7, color=INK2)
    for yi, v in zip(yy - 0.2, p["GROUNDED"]):
        ax.text(v + 3, yi, f"{v:.0f}", va="center", fontsize=7, color=INK2)
    ax.set_yticks(yy)
    ax.set_yticklabels(["country", "city", "founding\nyear", "team\nsize"], fontsize=7.5)
    ax.invert_yaxis()
    grid(ax, "x")
    ax.set_xlim(0, 135)
    ax.set_xlabel("fill rate (%)")
    ax.set_title("C.  Same inputs, one instruction apart", loc="left", color=INK, fontsize=9)
    ax.barh([], [], color=ORANGE, label="told to estimate")
    ax.barh([], [], color=BLUE, label='told "only if stated"')
    ax.legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2,
              columnspacing=1.0, handlelength=1.1)
    save(fig, "fig7_imputation.pdf")


# ── Fig 8: novelty by tier and collection cost ─────────────────────────────
def fig_novelty():
    t = csv("26_novelty_by_tier.csv").sort_values("novelty_pct")
    ct = csv("27_collection_cost_by_tier.csv")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.8, 2.9), gridspec_kw={"width_ratios": [1.3, 1]})
    y = np.arange(len(t))
    a1.barh(y, t.novelty_pct, color=BLUE, height=0.55, zorder=3)
    a1.hlines(y, t.lo, t.hi, color=INK2, lw=1.0, zorder=4)
    for yi, v, n in zip(y, t.novelty_pct, t.n):
        a1.text(v + 1.5, yi, f"{v:.1f}%  (n={n:,})", va="center", fontsize=7.5, color=INK2)
    a1.set_yticks(y)
    a1.set_yticklabels([s.replace(" / ", " /\n") for s in t.tier], fontsize=8)
    grid(a1, "x")
    a1.set_xlim(0, 88)
    a1.set_xlabel("share of collected firms absent from both registers (%)")
    a1.set_title("A.  Novelty by portfolio tier", loc="left", color=INK, fontsize=9)

    lab = {"easy": "deterministic\nscraper", "hard": "LLM agent\ntier"}
    x = np.arange(len(ct))
    a2.bar(x - 0.19, ct.success_rate, width=0.36, color=BLUE, zorder=3, label="run success rate")
    a2.bar(x + 0.19, 100 * ct.new_per_record, width=0.36, color=ORANGE, zorder=3,
           label="new records per record")
    for xi, v in zip(x - 0.19, ct.success_rate):
        a2.text(xi, v + 1.5, f"{v:.0f}%", ha="center", fontsize=7, color=INK2)
    for xi, v in zip(x + 0.19, 100 * ct.new_per_record):
        a2.text(xi, v + 1.5, f"{v:.0f}%", ha="center", fontsize=7, color=INK2)
    a2.set_xticks(x)
    a2.set_xticklabels([lab.get(v, v) for v in ct.tier], fontsize=8)
    grid(a2)
    a2.set_ylim(0, 95)
    a2.set_ylabel("percent")
    a2.legend(fontsize=7.5, loc="upper right")
    a2.set_title("B.  Collection tier", loc="left", color=INK, fontsize=9)
    save(fig, "fig8_novelty.pdf")


if __name__ == "__main__":
    for f in (fig_trend, fig_coverage, fig_robust, fig_geo, fig_conc,
              fig_sector, fig_imputation, fig_novelty):
        f()
    print("done")
