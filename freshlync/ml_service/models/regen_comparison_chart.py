"""
Regenerate actual_vs_predicted_all.png
=======================================
Reads the saved prediction CSVs from outputs/ and rebuilds the
publication-ready 4-panel Actual vs Predicted comparison chart
WITHOUT retraining any model.

Handles two CSV shapes:
  - product-level rows  (predictions_ma.csv, predictions_xgboost.csv)
    -> aggregated to category-day level before plotting
  - category-day rows   (predictions_prophet.csv)
    -> used as-is

Output: outputs/charts_comparison/actual_vs_predicted_all.png
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
OUT_ROOT   = os.path.join(BASE_DIR, '..', 'outputs')
CHARTS_DIR = os.path.join(OUT_ROOT, 'charts_comparison')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ─────────────────────────── Palette ────────────────────────────────────────
_CAT_COLORS = {
    'fish':      '#0072B2',   # IBM / Wong blue
    'meat':      '#D55E00',   # vermillion
    'vegetable': '#009E73',   # teal-green
}
_REF_COLOR   = '#CC3311'
_GRID_COLOR  = '#E8E8E8'
_SPINE_COLOR = '#BBBBBB'
_FONT        = 'DejaVu Sans'
_DPI         = 300
_ALPHA       = 0.70
_MS          = 55
_MARGIN      = 0.05

# ─────────────────────────── Helpers ────────────────────────────────────────
def _lims(arrays, margin=_MARGIN):
    combined = np.concatenate([np.asarray(a).ravel() for a in arrays])
    lo, hi   = combined.min(), combined.max()
    pad      = margin * (hi - lo) if hi != lo else 1.0
    return lo - pad, hi + pad

def _style(ax):
    ax.set_facecolor('white')
    ax.grid(True, color=_GRID_COLOR, linewidth=0.75, linestyle='--', zorder=0)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_edgecolor(_SPINE_COLOR)
        sp.set_linewidth(0.9)
    ax.tick_params(axis='both', labelsize=9, colors='#333333', length=3)
    ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))

def _draw_panel(ax, df, name):
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)
    cats      = df['category'].values if 'category' in df.columns \
                else np.full(len(actual), 'all')

    for cat in sorted(np.unique(cats)):
        mask = cats == cat
        ax.scatter(actual[mask], predicted[mask],
                   s=_MS, alpha=_ALPHA,
                   color=_CAT_COLORS.get(cat, '#555599'),
                   edgecolors='none', zorder=3)

    lo, hi = _lims([actual, predicted])
    ax.plot([lo, hi], [lo, hi], color=_REF_COLOR,
            linewidth=1.6, linestyle='--', zorder=4)
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect('equal', adjustable='box')

    r2   = r2_score(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    mae  = mean_absolute_error(actual, predicted)
    n    = len(actual)
    annot = f"$R^2$={r2:.3f}\nRMSE={rmse:.1f}\nMAE={mae:.1f}\nn={n}"
    ax.text(0.04, 0.97, annot,
            transform=ax.transAxes, fontsize=8.5, va='top',
            fontfamily=_FONT,
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                      edgecolor=_SPINE_COLOR, linewidth=0.8, alpha=0.90),
            zorder=5)

    ax.set_title(f'{name}',
                 fontsize=12, fontfamily=_FONT,
                 fontweight='semibold', color='#111111', pad=10)
    ax.set_xlabel('Actual Demand (units)', fontsize=9,
                  fontfamily=_FONT, color='#333333', labelpad=5)
    ax.set_ylabel('Predicted Demand (units)', fontsize=9,
                  fontfamily=_FONT, color='#333333', labelpad=5)
    _style(ax)
    return r2, rmse, mae

def load_csv(path):
    """Load a predictions CSV and aggregate product-level rows if needed."""
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])

    # Detect shape: if there are multiple rows per (date, category) pair
    # we're at product level -> aggregate
    group_key = ['date', 'category'] if 'category' in df.columns else ['date']
    counts = df.groupby(group_key).size()
    if counts.max() > 1:
        df = (df.groupby(group_key)
                .agg(actual=('actual', 'sum'),
                     predicted=('predicted', 'sum'))
                .reset_index())
    return df

# ─────────────────────────── Load all predictions ───────────────────────────
CSVS = {
    'Moving Average': os.path.join(OUT_ROOT, 'predictions_ma.csv'),
    'Prophet':        os.path.join(OUT_ROOT, 'predictions_prophet.csv'),
    'XGBoost':        os.path.join(OUT_ROOT, 'predictions_xgboost.csv'),
}

def main():
    print("=" * 60)
    print("  Regenerating actual_vs_predicted_all.png")
    print("=" * 60)

    panels = {}
    for name, path in CSVS.items():
        if os.path.exists(path):
            panels[name] = load_csv(path)
            agg = panels[name]
            print(f"  {name:20s}: {len(agg)} category-day rows  "
                  f"actual=[{agg['actual'].min():.0f},{agg['actual'].max():.0f}]  "
                  f"pred=[{agg['predicted'].min():.0f},{agg['predicted'].max():.0f}]")
        else:
            print(f"  {name:20s}: CSV not found, skipping.")

    if not panels:
        raise RuntimeError("No prediction CSVs found in outputs/. "
                           "Run model_comparison_study.py first.")

    n       = len(panels)
    ncols   = 2
    nrows   = (n + 1) // ncols

    fig, axes = plt.subplots(nrows, ncols,
                             figsize=(16, 7 * nrows),
                             dpi=_DPI)
    fig.patch.set_facecolor('white')
    axes = np.array(axes).flatten()

    print()
    for i, (name, df) in enumerate(panels.items()):
        r2, rmse, mae = _draw_panel(axes[i], df, name)
        print(f"  {name:20s} -> R2={r2:.4f}  RMSE={rmse:.2f}  MAE={mae:.2f}")

    # Hide any unused panels
    for j in range(n, len(axes)):
        axes[j].set_visible(False)

    # Shared legend
    legend_handles = [
        Line2D([0], [0], marker='o', color='none',
               markerfacecolor=_CAT_COLORS[c], markeredgecolor='none',
               markersize=9, label=c.capitalize())
        for c in ['fish', 'meat', 'vegetable']
    ] + [
        Line2D([0], [0], color=_REF_COLOR, linewidth=1.6,
               linestyle='--', label='Ideal  y = x')
    ]
    fig.legend(handles=legend_handles,
               loc='lower center', ncol=4, fontsize=10,
               framealpha=0.92, edgecolor=_SPINE_COLOR,
               bbox_to_anchor=(0.5, -0.02))

    fig.suptitle('Model Comparison — Actual vs. Predicted Demand',
                 fontsize=15, fontfamily=_FONT,
                 fontweight='semibold', color='#111111', y=1.01)

    fig.tight_layout(rect=[0, 0.04, 1, 1])
    out_path = os.path.join(CHARTS_DIR, 'actual_vs_predicted_all.png')
    fig.savefig(out_path, dpi=_DPI, bbox_inches='tight')
    plt.close(fig)

    print(f"\n  Saved -> {os.path.abspath(out_path)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
