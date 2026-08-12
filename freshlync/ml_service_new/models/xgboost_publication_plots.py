"""
XGBoost Publication-Ready Diagnostic Plots  (v2)
=================================================
Reads 'predictions_xgboost.csv' (product-level rows), aggregates to
category-day level (matching what model_comparison_study.py evaluates on),
then produces two research-quality charts:

  1. Actual vs Predicted scatter plot  –  category-coloured, equal aspect,
     y=x reference, R2 / RMSE / MAE annotation, 300 DPI.

  2. Residual plot  –  category-coloured, y=0 reference, bias annotation.

Does NOT modify the model, predictions, or dataset.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

# ─────────────────────────── Paths ─────────────────────────────────────────
BASE_DIR   = os.path.dirname(__file__)
PRED_CSV   = os.path.join(BASE_DIR, '..', 'outputs', 'predictions_xgboost.csv')
OUTPUT_DIR = os.path.join(BASE_DIR, '..', 'outputs', 'charts_publication')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────── Palette (Wong / IBM colorblind-safe) ───────────
CATEGORY_COLORS = {
    'fish':      '#0072B2',   # blue
    'meat':      '#D55E00',   # vermillion
    'vegetable': '#009E73',   # teal-green
}
DEFAULT_COLOR  = '#999999'
REF_LINE_COLOR = '#CC3311'
GRID_COLOR     = '#E8E8E8'
SPINE_COLOR    = '#BBBBBB'

# ─────────────────────────── Typography & size ──────────────────────────────
FONT_FAMILY = 'DejaVu Sans'
TITLE_SIZE  = 16
LABEL_SIZE  = 13
TICK_SIZE   = 11
ANNOT_SIZE  = 11
LEGEND_SIZE = 11

DPI         = 300
FIG_W       = 10
FIG_H       = 9
ALPHA       = 0.70
MARKER_SIZE = 55
MARGIN      = 0.05     # 5 % padding on each axis

# ─────────────────────────── Helpers ────────────────────────────────────────
def _style(ax):
    ax.set_facecolor('white')
    ax.figure.patch.set_facecolor('white')
    ax.grid(True, color=GRID_COLOR, linewidth=0.75, linestyle='--', zorder=0)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_edgecolor(SPINE_COLOR)
        sp.set_linewidth(0.9)
    ax.tick_params(axis='both', labelsize=TICK_SIZE, colors='#333333', length=4)
    ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))


def _lims(arrays, margin=MARGIN):
    combined = np.concatenate([np.asarray(a).ravel() for a in arrays])
    lo, hi   = combined.min(), combined.max()
    pad      = margin * (hi - lo) if hi != lo else 1.0
    return lo - pad, hi + pad


def _annot_box(ax, text, loc='upper left'):
    xpos = 0.04 if 'left' in loc else 0.97
    ypos = 0.97 if 'upper' in loc else 0.04
    ha   = 'left' if 'left' in loc else 'right'
    va   = 'top' if 'upper' in loc else 'bottom'
    ax.text(xpos, ypos, text,
            transform=ax.transAxes, fontsize=ANNOT_SIZE,
            fontfamily=FONT_FAMILY, ha=ha, va=va,
            bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                      edgecolor=SPINE_COLOR, linewidth=0.9, alpha=0.90),
            zorder=6)


def _category_legend(ax, categories, extra_handles=None):
    handles = [
        Line2D([0], [0], marker='o', color='none',
               markerfacecolor=CATEGORY_COLORS.get(c, DEFAULT_COLOR),
               markeredgecolor='none', markersize=8, label=c.capitalize())
        for c in sorted(categories)
    ]
    if extra_handles:
        handles = extra_handles + handles
    ax.legend(handles=handles, fontsize=LEGEND_SIZE,
              framealpha=0.92, edgecolor=SPINE_COLOR, loc='lower right')


# ─────────────────────────── Load & aggregate ───────────────────────────────
def load_and_aggregate(csv_path):
    """
    The CSV has one row per product per (date, category).
    Aggregate to (date, category) level to match the evaluation granularity
    used in model_comparison_study.py.
    """
    df = pd.read_csv(csv_path)
    df['date'] = pd.to_datetime(df['date'])

    # Sum product-level actual & predicted -> category-day level
    agg = (df.groupby(['date', 'category'])
             .agg(actual=('actual', 'sum'), predicted=('predicted', 'sum'))
             .reset_index())
    return agg


# ─────────────────────────── Plot 1: Actual vs Predicted ────────────────────
def plot_actual_vs_predicted(df, save_path):
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)
    cats      = df['category'].values

    r2   = r2_score(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    mae  = mean_absolute_error(actual, predicted)

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)

    # ── per-category scatter ──────────────────────────────────────────────
    for cat in sorted(df['category'].unique()):
        mask = cats == cat
        ax.scatter(actual[mask], predicted[mask],
                   s=MARKER_SIZE, alpha=ALPHA,
                   color=CATEGORY_COLORS.get(cat, DEFAULT_COLOR),
                   edgecolors='none', zorder=3,
                   label=cat.capitalize())

    # ── y = x ideal line ──────────────────────────────────────────────────
    lo, hi = _lims([actual, predicted])
    ref_line = ax.plot([lo, hi], [lo, hi],
                       color=REF_LINE_COLOR, linewidth=1.8,
                       linestyle='--', zorder=4,
                       label='Ideal  y = x')[0]

    # ── equal aspect & limits ─────────────────────────────────────────────
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect('equal', adjustable='box')

    # ── metrics annotation ────────────────────────────────────────────────
    metrics_txt = (
        f"$R^2$  = {r2:.4f}\n"
        f"RMSE = {rmse:.2f} units\n"
        f"MAE  = {mae:.2f} units"
    )
    _annot_box(ax, metrics_txt, loc='upper left')

    # ── n label ───────────────────────────────────────────────────────────
    ax.text(0.97, 0.04, f"n = {len(actual)} category-days",
            transform=ax.transAxes, fontsize=ANNOT_SIZE - 1,
            ha='right', va='bottom', color='#555555',
            fontfamily=FONT_FAMILY)

    # ── labels & title ────────────────────────────────────────────────────
    ax.set_xlabel('Actual Demand (units / category-day)',
                  fontsize=LABEL_SIZE, fontfamily=FONT_FAMILY,
                  color='#222222', labelpad=8)
    ax.set_ylabel('Predicted Demand (units / category-day)',
                  fontsize=LABEL_SIZE, fontfamily=FONT_FAMILY,
                  color='#222222', labelpad=8)
    ax.set_title('XGBoost — Actual vs. Predicted Demand',
                 fontsize=TITLE_SIZE, fontfamily=FONT_FAMILY,
                 color='#111111', pad=14, fontweight='semibold')

    # ── legend (category dots + ideal line) ───────────────────────────────
    ref_handle = Line2D([0], [0], color=REF_LINE_COLOR, linewidth=1.8,
                        linestyle='--', label='Ideal  y = x')
    _category_legend(ax, df['category'].unique(), extra_handles=[ref_handle])

    _style(ax)
    fig.tight_layout()
    fig.savefig(save_path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"  [OK] Actual vs Predicted -> {save_path}")
    return r2, rmse, mae


# ─────────────────────────── Plot 2: Residual plot ──────────────────────────
def plot_residuals(df, save_path):
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)
    residuals = actual - predicted
    cats      = df['category'].values

    bias   = float(np.mean(residuals))
    res_sd = float(np.std(residuals))

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H), dpi=DPI)

    # ── per-category scatter ──────────────────────────────────────────────
    for cat in sorted(df['category'].unique()):
        mask = cats == cat
        ax.scatter(actual[mask], residuals[mask],
                   s=MARKER_SIZE, alpha=ALPHA,
                   color=CATEGORY_COLORS.get(cat, DEFAULT_COLOR),
                   edgecolors='none', zorder=3)

    # ── y = 0 reference ───────────────────────────────────────────────────
    x_lo, x_hi = _lims([actual])
    ax.axhline(y=0, color=REF_LINE_COLOR, linewidth=1.8,
               linestyle='--', zorder=4, label='Zero residual  (y = 0)')

    # ── shaded ±1 std band ────────────────────────────────────────────────
    ax.axhspan(bias - res_sd, bias + res_sd,
               color='#888888', alpha=0.08, zorder=1,
               label=r'$\pm 1\,\sigma$ band')

    # ── axis limits ───────────────────────────────────────────────────────
    ax.set_xlim(x_lo, x_hi)
    y_lo, y_hi = _lims([residuals])
    ax.set_ylim(y_lo, y_hi)

    # ── annotation ────────────────────────────────────────────────────────
    annot = (f"Mean residual = {bias:+.2f} units\n"
             f"Std(residual)  = {res_sd:.2f} units")
    _annot_box(ax, annot, loc='upper left')

    ax.text(0.97, 0.04, f"n = {len(actual)} category-days",
            transform=ax.transAxes, fontsize=ANNOT_SIZE - 1,
            ha='right', va='bottom', color='#555555',
            fontfamily=FONT_FAMILY)

    # ── labels & title ────────────────────────────────────────────────────
    ax.set_xlabel('Actual Demand (units / category-day)',
                  fontsize=LABEL_SIZE, fontfamily=FONT_FAMILY,
                  color='#222222', labelpad=8)
    ax.set_ylabel('Residual  (Actual \u2212 Predicted)',
                  fontsize=LABEL_SIZE, fontfamily=FONT_FAMILY,
                  color='#222222', labelpad=8)
    ax.set_title('XGBoost — Residual Analysis',
                 fontsize=TITLE_SIZE, fontfamily=FONT_FAMILY,
                 color='#111111', pad=14, fontweight='semibold')

    # ── legend ────────────────────────────────────────────────────────────
    ref_handle  = Line2D([0], [0], color=REF_LINE_COLOR, linewidth=1.8,
                         linestyle='--', label='Zero residual  (y = 0)')
    band_handle = plt.Rectangle((0, 0), 1, 1, fc='#888888', alpha=0.18,
                                 label=r'$\pm 1\,\sigma$ band')
    _category_legend(ax, df['category'].unique(),
                     extra_handles=[ref_handle, band_handle])

    _style(ax)
    fig.tight_layout()
    fig.savefig(save_path, dpi=DPI, bbox_inches='tight')
    plt.close(fig)
    print(f"  [OK] Residual plot      -> {save_path}")
    return bias, res_sd


# ─────────────────────────── Main ───────────────────────────────────────────
def main():
    print("=" * 62)
    print("  XGBoost Publication-Ready Diagnostic Plots  (v2)")
    print("=" * 62)

    if not os.path.exists(PRED_CSV):
        raise FileNotFoundError(
            f"Predictions CSV not found:\n  {PRED_CSV}\n"
            "Run model_comparison_study.py first."
        )

    df = load_and_aggregate(PRED_CSV)
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)

    print(f"\n  Loaded & aggregated to {len(df)} category-day rows")
    print(f"  Categories : {sorted(df['category'].unique())}")
    print(f"  Actual  range : [{actual.min():.1f}, {actual.max():.1f}]")
    print(f"  Predicted range: [{predicted.min():.1f}, {predicted.max():.1f}]\n")

    avp_path = os.path.join(OUTPUT_DIR, 'xgb_actual_vs_predicted.png')
    res_path = os.path.join(OUTPUT_DIR, 'xgb_residuals.png')

    r2, rmse, mae = plot_actual_vs_predicted(df, avp_path)
    bias, res_sd  = plot_residuals(df, res_path)

    print("\n" + "-" * 62)
    print("  Diagnostic Metrics  (category-day level)")
    print("-" * 62)
    print(f"  R2            : {r2:.4f}")
    print(f"  RMSE          : {rmse:.2f}  units")
    print(f"  MAE           : {mae:.2f}  units")
    print(f"  Mean residual : {bias:+.2f} units (bias)")
    print(f"  Std(residual) : {res_sd:.2f}  units")
    print("-" * 62)
    print(f"\n  Saved to: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 62)


if __name__ == '__main__':
    main()
