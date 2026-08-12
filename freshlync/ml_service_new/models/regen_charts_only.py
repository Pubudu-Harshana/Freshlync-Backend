"""
Regenerate charts only — reads saved predictions_xgboost.csv, no retraining.
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error

BASE_DIR    = os.path.dirname(__file__)
OUT_ROOT    = os.path.join(BASE_DIR, '..', 'outputs')
CHARTS_COMP = os.path.join(OUT_ROOT, 'charts_comparison')
CHARTS_PUB  = os.path.join(OUT_ROOT, 'charts_publication')
os.makedirs(CHARTS_COMP, exist_ok=True)
os.makedirs(CHARTS_PUB,  exist_ok=True)

_CAT_COLORS  = {'fish': '#0072B2', 'meat': '#D55E00', 'vegetable': '#009E73'}
_REF_COLOR   = '#CC3311'
_GRID_COLOR  = '#E8E8E8'
_SPINE_COLOR = '#BBBBBB'
_FONT        = 'DejaVu Sans'
_DPI         = 300

def _style(ax, small=False):
    ax.set_facecolor('white')
    ax.grid(True, color=_GRID_COLOR, lw=0.75, ls='--', zorder=0)
    ax.set_axisbelow(True)
    for sp in ax.spines.values():
        sp.set_edgecolor(_SPINE_COLOR); sp.set_linewidth(0.9)
    ax.tick_params(axis='both', labelsize=9 if small else 11,
                   colors='#333333', length=4)
    ax.xaxis.set_minor_locator(mticker.AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(mticker.AutoMinorLocator(2))

def _lims(arrays, m=0.05):
    c = np.concatenate([np.asarray(a).ravel() for a in arrays])
    lo, hi = c.min(), c.max()
    p = m*(hi-lo) if hi != lo else 1.0
    return lo-p, hi+p

def _annot(ax, txt, loc='upper left', fs=10.5):
    x  = 0.04 if 'left' in loc else 0.97
    y  = 0.97 if 'upper' in loc else 0.04
    ha = 'left' if 'left' in loc else 'right'
    va = 'top'  if 'upper' in loc else 'bottom'
    ax.text(x, y, txt, transform=ax.transAxes, fontsize=fs,
            fontfamily=_FONT, ha=ha, va=va,
            bbox=dict(boxstyle='round,pad=0.45', facecolor='white',
                      edgecolor=_SPINE_COLOR, lw=0.8, alpha=0.92), zorder=6)

def _draw_avp(ax, df, title, small=False):
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)
    cats      = df['category'].values if 'category' in df.columns \
                else np.full(len(actual), 'all')
    for cat in sorted(np.unique(cats)):
        mask = cats == cat
        ax.scatter(actual[mask], predicted[mask],
                   s=35 if small else 55, alpha=0.75,
                   color=_CAT_COLORS.get(cat, '#555599'),
                   edgecolors='none', zorder=3)
    lo, hi = _lims([actual, predicted])
    ax.plot([lo, hi], [lo, hi], color=_REF_COLOR, lw=1.8, ls='--', zorder=4)
    ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
    ax.set_aspect('equal', adjustable='box')
    r2   = r2_score(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    mae  = mean_absolute_error(actual, predicted)
    n    = len(actual)
    fs   = 7.5 if small else 10.5
    _annot(ax, f"$R^2$  = {r2:.4f}\nRMSE = {rmse:.2f}\nMAE  = {mae:.2f}\nn = {n}",
           loc='upper left', fs=fs)
    lfs = 8 if small else 11
    ax.set_title(title, fontsize=10 if small else 13,
                 fontfamily=_FONT, fontweight='semibold', color='#111111', pad=8)
    ax.set_xlabel('Actual Demand (units)',    fontsize=lfs, fontfamily=_FONT,
                  color='#333333', labelpad=5)
    ax.set_ylabel('Predicted Demand (units)', fontsize=lfs, fontfamily=_FONT,
                  color='#333333', labelpad=5)
    _style(ax, small=small)
    return r2, rmse, mae

def _draw_residual(ax, df, title, small=False):
    actual    = df['actual'].values.astype(float)
    predicted = df['predicted'].values.astype(float)
    resid     = actual - predicted
    cats      = df['category'].values if 'category' in df.columns \
                else np.full(len(actual), 'all')
    for cat in sorted(np.unique(cats)):
        mask = cats == cat
        ax.scatter(actual[mask], resid[mask], s=35 if small else 55,
                   alpha=0.75, color=_CAT_COLORS.get(cat,'#555599'),
                   edgecolors='none', zorder=3)
    x_lo, x_hi = _lims([actual])
    bias, sd    = float(np.mean(resid)), float(np.std(resid))
    ax.axhline(y=0, color=_REF_COLOR, lw=1.8, ls='--', zorder=4)
    ax.axhspan(bias-sd, bias+sd, color='#888888', alpha=0.08, zorder=1)
    ax.set_xlim(x_lo, x_hi)
    y_lo, y_hi = _lims([resid])
    ax.set_ylim(y_lo, y_hi)
    fs = 7.5 if small else 10.5
    _annot(ax, f"Mean residual = {bias:+.2f}\nStd(residual)  = {sd:.2f}",
           loc='upper left', fs=fs)
    lfs = 8 if small else 11
    ax.set_title(title, fontsize=10 if small else 13,
                 fontfamily=_FONT, fontweight='semibold', color='#111111', pad=8)
    ax.set_xlabel('Actual Demand (units)', fontsize=lfs,
                  fontfamily=_FONT, color='#333333', labelpad=5)
    ax.set_ylabel('Residual (Actual \u2212 Predicted)', fontsize=lfs,
                  fontfamily=_FONT, color='#333333', labelpad=5)
    _style(ax, small=small)

def _legend(fig, cats, extra_handles=None):
    handles = (extra_handles or []) + [
        Line2D([0],[0], marker='o', color='none',
               markerfacecolor=_CAT_COLORS.get(c,'#555599'),
               markeredgecolor='none', markersize=9, label=c.capitalize())
        for c in sorted(cats)
    ] + [Line2D([0],[0], color=_REF_COLOR, lw=1.8, ls='--', label='Ideal  y = x')]
    fig.legend(handles=handles, loc='lower center', ncol=len(handles),
               fontsize=10, framealpha=0.92, edgecolor=_SPINE_COLOR,
               bbox_to_anchor=(0.5, -0.01))

cat_agg = pd.read_csv(os.path.join(OUT_ROOT, 'predictions_xgboost.csv'))
cats    = sorted(cat_agg['category'].unique())

actual    = cat_agg['actual'].values.astype(float)
predicted = cat_agg['predicted'].values.astype(float)
cats_col  = cat_agg['category'].values

cat_hs = [Line2D([0],[0], marker='o', color='none',
                 markerfacecolor=_CAT_COLORS[c], markeredgecolor='none',
                 markersize=9, label=c.capitalize()) for c in cats]
ref_h  = Line2D([0],[0], color=_REF_COLOR, lw=1.8, ls='--', label='Ideal  y = x')

# ── Chart 1: Dual-panel Linear + Log-Log ────────────────────────────────────
fig, (ax_lin, ax_log) = plt.subplots(1, 2, figsize=(18, 8), dpi=_DPI)
fig.patch.set_facecolor('white')

# Left — linear
_draw_avp(ax_lin, cat_agg, 'Linear Scale\n(Axis span dominated by Vegetable range)')
ax_lin.legend(handles=cat_hs+[ref_h], fontsize=10,
              framealpha=0.92, edgecolor=_SPINE_COLOR, loc='lower right')

# Right — log-log
for cat in sorted(np.unique(cats_col)):
    mask = cats_col == cat
    ax_log.scatter(actual[mask], predicted[mask], s=55, alpha=0.75,
                   color=_CAT_COLORS.get(cat,'#555599'),
                   edgecolors='none', zorder=3)

lo_log = max(1, float(np.min([actual, predicted])))
hi_log = float(np.max([actual, predicted])) * 1.1
ax_log.plot([lo_log, hi_log], [lo_log, hi_log],
            color=_REF_COLOR, lw=1.8, ls='--', zorder=4)
ax_log.set_xscale('log'); ax_log.set_yscale('log')
ax_log.set_xlim(lo_log * 0.85, hi_log)
ax_log.set_ylim(lo_log * 0.85, hi_log)
ax_log.set_aspect('equal', adjustable='box')

r2   = r2_score(actual, predicted)
rmse = np.sqrt(mean_squared_error(actual, predicted))
mae  = mean_absolute_error(actual, predicted)
_annot(ax_log,
       f"$R^2$  = {r2:.4f}\nRMSE = {rmse:.2f}\nMAE  = {mae:.2f}\nn = {len(actual)}",
       loc='upper left', fs=10.5)
ax_log.set_title('Log-Log Scale\n(All 3 categories spread evenly along reference line)',
                 fontsize=13, fontfamily=_FONT, fontweight='semibold',
                 color='#111111', pad=8)
ax_log.set_xlabel('Actual Demand — log scale (units)', fontsize=11,
                  fontfamily=_FONT, color='#333333', labelpad=5)
ax_log.set_ylabel('Predicted Demand — log scale (units)', fontsize=11,
                  fontfamily=_FONT, color='#333333', labelpad=5)
ax_log.legend(handles=cat_hs+[ref_h], fontsize=10,
              framealpha=0.92, edgecolor=_SPINE_COLOR, loc='lower right')
_style(ax_log)

fig.suptitle('XGBoost — Actual vs. Predicted Demand  '
             '(70/15/15 split · product-level model · category-day evaluation)',
             fontsize=14, fontfamily=_FONT, fontweight='semibold',
             color='#111111', y=1.01)
fig.tight_layout()
p1 = os.path.join(CHARTS_PUB, 'xgb_actual_vs_predicted.png')
fig.savefig(p1, dpi=_DPI, bbox_inches='tight')
plt.close(fig)
print(f"[OK] Dual-scale AVP -> {p1}")

# ── Chart 2: Residuals ───────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(10, 9), dpi=_DPI)
fig.patch.set_facecolor('white')
_draw_residual(ax, cat_agg,
               'XGBoost — Residual Analysis\n'
               '(70/15/15 split · category-day evaluation)')
ref_h2 = Line2D([0],[0], color=_REF_COLOR, lw=1.8, ls='--', label='Zero residual')
band_h = plt.Rectangle((0,0),1,1, fc='#888888', alpha=0.18,
                        label=r'$\pm 1\,\sigma$ band')
ax.legend(handles=[ref_h2, band_h]+cat_hs, fontsize=10.5,
          framealpha=0.92, edgecolor=_SPINE_COLOR, loc='upper right')
fig.tight_layout()
p2 = os.path.join(CHARTS_PUB, 'xgb_residuals.png')
fig.savefig(p2, dpi=_DPI, bbox_inches='tight')
plt.close(fig)
print(f"[OK] Residual      -> {p2}")

# ── Chart 3: Per-category 3-panel ────────────────────────────────────────────
fig, axes = plt.subplots(1, 3, figsize=(18, 7), dpi=_DPI)
fig.patch.set_facecolor('white')
for ax_i, cat in zip(axes, cats):
    sub = cat_agg[cat_agg['category'] == cat]
    _draw_avp(ax_i, sub, cat.capitalize(), small=True)
_legend(fig, cats)
fig.suptitle('XGBoost — Actual vs. Predicted by Category  (test set)',
             fontsize=14, fontfamily=_FONT, fontweight='semibold',
             color='#111111', y=1.02)
fig.tight_layout(rect=[0, 0.06, 1, 1])
p3 = os.path.join(CHARTS_PUB, 'xgb_per_category.png')
fig.savefig(p3, dpi=_DPI, bbox_inches='tight')
plt.close(fig)
print(f"[OK] Per-category  -> {p3}")

# ── Chart 4: Model comparison ────────────────────────────────────────────────
def _load_agg(path):
    d = pd.read_csv(path)
    d['date'] = pd.to_datetime(d['date'])
    gk = ['date','category'] if 'category' in d.columns else ['date']
    if d.groupby(gk).size().max() > 1:
        d = (d.groupby(gk)
              .agg(actual=('actual','sum'), predicted=('predicted','sum'))
              .reset_index())
    return d

panels = {'XGBoost\n(improved)': cat_agg}
for nm, fn in [('Moving Average','predictions_ma.csv'),
               ('Prophet','predictions_prophet.csv')]:
    fp = os.path.join(OUT_ROOT, fn)
    if os.path.exists(fp):
        panels[nm] = _load_agg(fp)

n_p = len(panels)
ncols = min(n_p, 3)
nrows = (n_p + ncols - 1) // ncols
fig, axes = plt.subplots(nrows, ncols, figsize=(7*ncols, 7*nrows), dpi=_DPI)
fig.patch.set_facecolor('white')
axes = np.array(axes).flatten()
for i, (nm, d) in enumerate(panels.items()):
    _draw_avp(axes[i], d, nm, small=True)
for j in range(n_p, len(axes)):
    axes[j].set_visible(False)
_legend(fig, cats)
fig.suptitle('Model Comparison — Actual vs. Predicted Demand',
             fontsize=14, fontfamily=_FONT, fontweight='semibold',
             color='#111111', y=1.01)
fig.tight_layout(rect=[0, 0.06, 1, 1])
p4 = os.path.join(CHARTS_COMP, 'actual_vs_predicted_all.png')
fig.savefig(p4, dpi=_DPI, bbox_inches='tight')
plt.close(fig)
print(f"[OK] Comparison    -> {p4}")

print("\nDone.")
