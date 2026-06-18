"""
Freshlync Sales Prediction: XGBoost Hybrid Model (Multi-Output)

Implements a hybrid approach that combines XGBoost and Linear Regression:
1. Target-specific models: XGBoost for quantity_sold, Linear Regression for price
2. Stacking ensemble: meta-model trained on base predictions
3. Compares against standalone models for both targets
4. Generates comprehensive evaluation charts
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import os
import json

from sklearn.model_selection import train_test_split, KFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')

# ============================================================
# Configuration
# ============================================================
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_orders.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts_hybrid')
os.makedirs(CHARTS_DIR, exist_ok=True)

RANDOM_STATE = 42
TEST_SIZE = 0.2
TARGET_COLS = ['quantity_sold', 'price']
N_FOLDS = 5  # for stacking out-of-fold predictions

# ============================================================
# 1. Load and Preprocess Data
# ============================================================
def load_data(path=DATA_PATH):
    """Load the CSV order data."""
    df = pd.read_csv(path)
    print(f'Dataset shape: {df.shape}')
    print(f'Targets: {TARGET_COLS}')
    return df

def preprocess_data(df):
    """
    Preprocess features: one-hot encode categoricals,
    return processed X, y, and preprocessor.
    """
    feature_cols = ['product_name', 'category', 'day_of_week', 'is_holiday', 'weather_condition']
    X = df[feature_cols]
    y = df[TARGET_COLS]

    categorical_cols = ['product_name', 'category', 'day_of_week', 'weather_condition']
    preprocessor = ColumnTransformer(
        transformers=[('cat', OneHotEncoder(drop='first', sparse_output=False), categorical_cols)],
        remainder='passthrough'
    )

    X_processed = preprocessor.fit_transform(X)
    print(f'Processed feature matrix shape: {X_processed.shape}')

    feature_names = preprocessor.get_feature_names_out()
    print(f'Feature names ({len(feature_names)}): {list(feature_names)}')

    X_train, X_test, y_train, y_test = train_test_split(
        X_processed, y.values, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    print(f'Train: {X_train.shape}, Test: {X_test.shape}')

    return X_train, X_test, y_train, y_test, preprocessor


# ============================================================
# 2. Standalone Models (for comparison)
# ============================================================
def train_standalone_models(X_train, y_train, X_test, y_test):
    """
    Train separate models for each target to compare:
    - XGBoost on quantity_sold
    - Linear Regression on quantity_sold
    - XGBoost on price
    - Linear Regression on price
    """
    results = {}

    for idx, target_name in enumerate(TARGET_COLS):
        y_tr = y_train[:, idx]
        y_te = y_test[:, idx]

        print(f'\n  --- {target_name} ---')

        # --- XGBoost ---
        xgb = XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=RANDOM_STATE, verbosity=0
        )
        xgb.fit(X_train, y_tr)
        pred_tr_xgb = xgb.predict(X_train)
        pred_te_xgb = xgb.predict(X_test)

        rmse_tr = np.sqrt(mean_squared_error(y_tr, pred_tr_xgb))
        rmse_te = np.sqrt(mean_squared_error(y_te, pred_te_xgb))
        r2_tr = r2_score(y_tr, pred_tr_xgb)
        r2_te = r2_score(y_te, pred_te_xgb)

        print(f'  XGBoost          - Train RMSE: {rmse_tr:.2f}, Test RMSE: {rmse_te:.2f}, R2: {r2_te:.4f}')
        results[f'xgb_{target_name}'] = {
            'model': xgb, 'pred_train': pred_tr_xgb, 'pred_test': pred_te_xgb,
            'rmse_train': rmse_tr, 'rmse_test': rmse_te, 'r2_train': r2_tr, 'r2_test': r2_te
        }

        # --- Linear Regression ---
        lr = LinearRegression()
        lr.fit(X_train, y_tr)
        pred_tr_lr = lr.predict(X_train)
        pred_te_lr = lr.predict(X_test)

        rmse_tr = np.sqrt(mean_squared_error(y_tr, pred_tr_lr))
        rmse_te = np.sqrt(mean_squared_error(y_te, pred_te_lr))
        r2_tr = r2_score(y_tr, pred_tr_lr)
        r2_te = r2_score(y_te, pred_te_lr)

        print(f'  Linear Regression - Train RMSE: {rmse_tr:.2f}, Test RMSE: {rmse_te:.2f}, R2: {r2_te:.4f}')
        results[f'lr_{target_name}'] = {
            'model': lr, 'pred_train': pred_tr_lr, 'pred_test': pred_te_lr,
            'rmse_train': rmse_tr, 'rmse_test': rmse_te, 'r2_train': r2_tr, 'r2_test': r2_te
        }

    return results


# ============================================================
# 3. Target-Specific Hybrid Model
#    (XGBoost for quantity_sold, LR for price)
# ============================================================
def train_target_specific_hybrid(X_train, y_train, X_test, y_test):
    """
    Hybrid approach: use the best model per target.
    - XGBoost for quantity_sold (captures non-linear demand)
    - Linear Regression for price (more linear relationship)
    """
    print('\n[Target-Specific Hybrid]')
    print('  quantity_sold -> XGBoost')
    print('  price         -> Linear Regression')

    y_pred_train = np.zeros_like(y_train)
    y_pred_test = np.zeros_like(y_test)

    # quantity_sold → XGBoost
    xgb_qty = XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        random_state=RANDOM_STATE, verbosity=0
    )
    xgb_qty.fit(X_train, y_train[:, 0])
    y_pred_train[:, 0] = xgb_qty.predict(X_train)
    y_pred_test[:, 0] = xgb_qty.predict(X_test)

    # price → Linear Regression
    lr_price = LinearRegression()
    lr_price.fit(X_train, y_train[:, 1])
    y_pred_train[:, 1] = lr_price.predict(X_train)
    y_pred_test[:, 1] = lr_price.predict(X_test)

    # Evaluate
    rmse_train_qty = np.sqrt(mean_squared_error(y_train[:, 0], y_pred_train[:, 0]))
    rmse_test_qty  = np.sqrt(mean_squared_error(y_test[:, 0],  y_pred_test[:, 0]))
    rmse_train_price = np.sqrt(mean_squared_error(y_train[:, 1], y_pred_train[:, 1]))
    rmse_test_price  = np.sqrt(mean_squared_error(y_test[:, 1],  y_pred_test[:, 1]))
    r2_train = r2_score(y_train, y_pred_train)
    r2_test  = r2_score(y_test, y_pred_test)

    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return {
        'models': {'qty': xgb_qty, 'price': lr_price},
        'pred_train': y_pred_train, 'pred_test': y_pred_test,
        'rmse_train_qty': rmse_train_qty, 'rmse_test_qty': rmse_test_qty,
        'rmse_train_price': rmse_train_price, 'rmse_test_price': rmse_test_price,
        'r2_train': r2_train, 'r2_test': r2_test
    }


# ============================================================
# 4. Blending Ensemble (Simple Average / Weighted)
# ============================================================
def train_blending_ensemble(X_train, y_train, X_test, y_test, standalone_results):
    """
    Blend XGBoost and Linear Regression predictions for each target.
    Tests: simple average and weighted average (based on validation performance).
    """
    print('\n[Blending Ensemble]')

    blending_results = {}

    for idx, target_name in enumerate(TARGET_COLS):
        y_te = y_test[:, idx]
        xgb_pred_te = standalone_results[f'xgb_{target_name}']['pred_test']
        lr_pred_te  = standalone_results[f'lr_{target_name}']['pred_test']

        # --- Simple Average ---
        avg_pred_te = (xgb_pred_te + lr_pred_te) / 2.0
        rmse_avg = np.sqrt(mean_squared_error(y_te, avg_pred_te))
        r2_avg = r2_score(y_te, avg_pred_te)

        print(f'  {target_name} - Simple Average: Test RMSE={rmse_avg:.2f}, R2={r2_avg:.4f}')

        # --- Weighted Average (find best weight via validation split) ---
        # Use 20% of training as validation to find optimal weight
        X_tr, X_val, y_tr, y_val = train_test_split(
            X_train, y_train[:, idx], test_size=0.2, random_state=RANDOM_STATE
        )
        xgb_val = XGBRegressor(
            n_estimators=200, max_depth=4, learning_rate=0.1,
            subsample=0.8, colsample_bytree=0.8,
            random_state=RANDOM_STATE, verbosity=0
        )
        xgb_val.fit(X_tr, y_tr)
        lr_val = LinearRegression()
        lr_val.fit(X_tr, y_tr)

        xgb_val_pred = xgb_val.predict(X_val)
        lr_val_pred = lr_val.predict(X_val)

        # Search best weight w for: w * xgb + (1-w) * lr
        best_w = 0.5
        best_w_rmse = float('inf')
        for w in np.arange(0, 1.05, 0.05):
            blended = w * xgb_val_pred + (1 - w) * lr_val_pred
            rmse_w = np.sqrt(mean_squared_error(y_val, blended))
            if rmse_w < best_w_rmse:
                best_w_rmse = rmse_w
                best_w = w

        # Apply best weight to test set
        # Re-fetch original test predictions from standalone (already fit on full train)
        xgb_full_pred_te = standalone_results[f'xgb_{target_name}']['pred_test']
        lr_full_pred_te  = standalone_results[f'lr_{target_name}']['pred_test']
        weighted_pred_te = best_w * xgb_full_pred_te + (1 - best_w) * lr_full_pred_te
        rmse_w_test = np.sqrt(mean_squared_error(y_te, weighted_pred_te))
        r2_w_test = r2_score(y_te, weighted_pred_te)

        print(f'  {target_name} - Weighted Blend (w={best_w:.2f}): Test RMSE={rmse_w_test:.2f}, R2={r2_w_test:.4f}')

        blending_results[target_name] = {
            'simple_avg_rmse': rmse_avg, 'simple_avg_r2': r2_avg,
            'best_weight': best_w,
            'weighted_rmse': rmse_w_test, 'weighted_r2': r2_w_test,
            'weighted_pred_test': weighted_pred_te
        }

    return blending_results


# ============================================================
# 5. Stacking Ensemble (Meta-Model using OOF predictions)
# ============================================================
def train_stacking_ensemble(X_train, y_train, X_test, y_test):
    """
    Stacking ensemble using K-Fold out-of-fold predictions.
    Base models: XGBoost, RandomForest, Linear Regression
    Meta-model: Ridge Regression
    """
    print('\n[Stacking Ensemble (K-Fold Cross-Validation)]')

    n_train = X_train.shape[0]
    n_test = X_test.shape[0]
    n_targets = y_train.shape[1]

    # Store out-of-fold predictions (train) and test predictions
    oof_train = np.zeros((n_train, n_targets * 3))  # 3 base models × 2 targets
    oof_test = np.zeros((n_test, n_targets * 3))

    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)
    base_models_info = []

    for idx, target_name in enumerate(TARGET_COLS):
        print(f'\n  Target: {target_name}')
        y_tr = y_train[:, idx]
        y_te = y_test[:, idx]

        fold_oof_train = np.zeros((n_train, 3))  # 3 base models
        fold_oof_test = np.zeros((n_test, 3))

        for m_idx, (model_name, ModelClass, params) in enumerate([
            ('XGBoost', XGBRegressor, {
                'n_estimators': 200, 'max_depth': 4, 'learning_rate': 0.1,
                'subsample': 0.8, 'colsample_bytree': 0.8,
                'random_state': RANDOM_STATE, 'verbosity': 0
            }),
            ('RandomForest', RandomForestRegressor, {
                'n_estimators': 200, 'max_depth': 6,
                'random_state': RANDOM_STATE, 'n_jobs': -1
            }),
            ('LinearRegression', LinearRegression, {})
        ]):
            print(f'    Base model: {model_name}')
            test_preds = np.zeros((n_test, N_FOLDS))

            for fold, (tr_idx, val_idx) in enumerate(kf.split(X_train)):
                X_tr_fold, X_val_fold = X_train[tr_idx], X_train[val_idx]
                y_tr_fold, y_val_fold = y_tr[tr_idx], y_tr[val_idx]

                model = ModelClass(**params) if params else ModelClass()
                model.fit(X_tr_fold, y_tr_fold)

                # Out-of-fold predictions
                oof_val_pred = model.predict(X_val_fold)
                fold_oof_train[val_idx, m_idx] = oof_val_pred

                # Test predictions (average across folds)
                test_preds[:, fold] = model.predict(X_test)

            fold_oof_test[:, m_idx] = test_preds.mean(axis=1)

        # Store for this target
        oof_train[:, idx * 3:(idx + 1) * 3] = fold_oof_train
        oof_test[:, idx * 3:(idx + 1) * 3] = fold_oof_test

    # --- Train meta-model (Ridge Regression) ---
    print('\n  Training meta-model (Ridge Regression)...')

    # Meta-model expects: [xgb_qty, rf_qty, lr_qty, xgb_price, rf_price, lr_price]
    # We actually need separate meta-models per target
    meta_models = []
    meta_pred_train = np.zeros_like(y_train)
    meta_pred_test = np.zeros_like(y_test)

    for idx, target_name in enumerate(TARGET_COLS):
        y_tr = y_train[:, idx]
        y_te = y_test[:, idx]

        # Features for meta: OOF predictions from all base models for this target
        X_meta_train = oof_train[:, idx * 3:(idx + 1) * 3]
        X_meta_test = oof_test[:, idx * 3:(idx + 1) * 3]

        # Add predictions from other target's models as features (cross-target info)
        other_idx = 1 - idx
        X_meta_train = np.column_stack([
            X_meta_train,
            oof_train[:, other_idx * 3:(other_idx + 1) * 3]
        ])
        X_meta_test = np.column_stack([
            X_meta_test,
            oof_test[:, other_idx * 3:(other_idx + 1) * 3]
        ])

        meta_model = Ridge(alpha=1.0, random_state=RANDOM_STATE)
        meta_model.fit(X_meta_train, y_tr)

        meta_pred_train[:, idx] = meta_model.predict(X_meta_train)
        meta_pred_test[:, idx] = meta_model.predict(X_meta_test)
        meta_models.append(meta_model)

    # Evaluate stacking
    rmse_train_qty = np.sqrt(mean_squared_error(y_train[:, 0], meta_pred_train[:, 0]))
    rmse_test_qty  = np.sqrt(mean_squared_error(y_test[:, 0],  meta_pred_test[:, 0]))
    rmse_train_price = np.sqrt(mean_squared_error(y_train[:, 1], meta_pred_train[:, 1]))
    rmse_test_price  = np.sqrt(mean_squared_error(y_test[:, 1],  meta_pred_test[:, 1]))
    r2_train = r2_score(y_train, meta_pred_train)
    r2_test  = r2_score(y_test, meta_pred_test)

    print(f'\n  Stacking Ensemble Results:')
    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return {
        'meta_models': meta_models,
        'pred_train': meta_pred_train, 'pred_test': meta_pred_test,
        'rmse_train_qty': rmse_train_qty, 'rmse_test_qty': rmse_test_qty,
        'rmse_train_price': rmse_train_price, 'rmse_test_price': rmse_test_price,
        'r2_train': r2_train, 'r2_test': r2_test
    }


# ============================================================
# 6. Multi-Output XGBoost (Standard Baseline)
# ============================================================
def train_multioutput_xgboost(X_train, y_train, X_test, y_test):
    """Standard MultiOutputRegressor with XGBoost (same as original)."""
    from sklearn.multioutput import MultiOutputRegressor

    print('\n[Multi-Output XGBoost (Baseline)]')
    base_model = XGBRegressor(
        n_estimators=200, max_depth=4, learning_rate=0.1,
        subsample=0.8, colsample_bytree=0.8,
        random_state=RANDOM_STATE, verbosity=0
    )
    model = MultiOutputRegressor(base_model)
    model.fit(X_train, y_train)

    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    rmse_train_qty = np.sqrt(mean_squared_error(y_train[:, 0], y_pred_train[:, 0]))
    rmse_test_qty  = np.sqrt(mean_squared_error(y_test[:, 0],  y_pred_test[:, 0]))
    rmse_train_price = np.sqrt(mean_squared_error(y_train[:, 1], y_pred_train[:, 1]))
    rmse_test_price  = np.sqrt(mean_squared_error(y_test[:, 1],  y_pred_test[:, 1]))
    r2_train = r2_score(y_train, y_pred_train)
    r2_test  = r2_score(y_test, y_pred_test)

    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return {
        'model': model, 'pred_train': y_pred_train, 'pred_test': y_pred_test,
        'rmse_train_qty': rmse_train_qty, 'rmse_test_qty': rmse_test_qty,
        'rmse_train_price': rmse_train_price, 'rmse_test_price': rmse_test_price,
        'r2_train': r2_train, 'r2_test': r2_test
    }


# ============================================================
# 7. Visualization
# ============================================================
def plot_actual_vs_predicted(y_actual, y_pred, target_name, model_name, chart_type, description):
    """Scatter plot: actual vs predicted."""
    plt.figure(figsize=(8, 5))
    sns.scatterplot(x=y_actual, y=y_pred, alpha=0.6, color='teal', edgecolor='black')
    min_val = min(y_actual.min(), y_pred.min())
    max_val = max(y_actual.max(), y_pred.max())
    plt.plot([min_val, max_val], [min_val, max_val], color='red', linestyle='--', lw=2)
    plt.title(f'{model_name}: Actual vs Predicted ({target_name})', fontsize=13)
    plt.xlabel(f'Actual {target_name}', fontsize=11)
    plt.ylabel(f'Predicted {target_name}', fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    filename = f'{chart_type}_actual_vs_predicted_{target_name}.png'
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_residuals(y_pred, residuals, target_name, model_name, chart_type, description):
    """Residual plot."""
    plt.figure(figsize=(8, 4))
    plt.axhline(y=0, color='red', linestyle='--', lw=2)
    plt.scatter(y_pred, residuals, alpha=0.6, color='purple', edgecolor='black')
    plt.title(f'{model_name}: Residual Plot ({target_name})', fontsize=13)
    plt.xlabel(f'Predicted {target_name}', fontsize=11)
    plt.ylabel('Residuals (Errors)', fontsize=11)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    filename = f'{chart_type}_residual_plot_{target_name}.png'
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_all_model_comparison(comparison_df, filename, description):
    """
    Comprehensive grouped bar chart comparing all models across both targets.
    Shows: Test RMSE (qty), Test RMSE (price), Test R2.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    metrics = [
        ('Test RMSE (qty)', 'Test RMSE (quantity_sold)', 'teal', 'Lower is better'),
        ('Test RMSE (price)', 'Test RMSE (price)', 'coral', 'Lower is better'),
        ('Test R2', 'Test R2 Score', 'forestgreen', 'Higher is better')
    ]

    for ax, (col, title, color, note) in zip(axes, metrics):
        bars = ax.barh(comparison_df['Model'], comparison_df[col], color=color, edgecolor='black', height=0.6)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.set_xlabel(f'{note}', fontsize=10)
        ax.grid(True, alpha=0.3, axis='x')

        # Add value labels
        for bar, val in zip(bars, comparison_df[col]):
            ax.text(val + 0.1, bar.get_y() + bar.get_height()/2,
                    f'{val:.2f}', va='center', fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_hybrid_improvement(comparison_df, filename, description):
    """
    Bar chart showing % improvement of hybrid/stacking over baseline.
    """
    baseline_qty = comparison_df.loc[comparison_df['Model'] == 'MultiOutput XGBoost', 'Test RMSE (qty)'].values[0]
    baseline_price = comparison_df.loc[comparison_df['Model'] == 'MultiOutput XGBoost', 'Test RMSE (price)'].values[0]

    models = comparison_df['Model'].values
    pct_change_qty = (comparison_df['Test RMSE (qty)'].values - baseline_qty) / baseline_qty * 100
    pct_change_price = (comparison_df['Test RMSE (price)'].values - baseline_price) / baseline_price * 100

    fig, ax = plt.subplots(figsize=(10, 5))
    x = np.arange(len(models))
    width = 0.35

    bars1 = ax.bar(x - width/2, pct_change_qty, width, label='quantity_sold',
                   color=['gray' if v > 0 else 'teal' for v in pct_change_qty],
                   edgecolor='black')
    bars2 = ax.bar(x + width/2, pct_change_price, width, label='price',
                   color=['gray' if v > 0 else 'coral' for v in pct_change_price],
                   edgecolor='black')

    ax.axhline(y=0, color='black', linestyle='-', lw=1)
    ax.set_xticks(x)
    ax.set_xticklabels(models, fontsize=9, rotation=15, ha='right')
    ax.set_ylabel('% Change in Test RMSE vs MultiOutput XGBoost', fontsize=11)
    ax.set_title('Hybrid Model Improvement Over Baseline', fontsize=13, fontweight='bold')
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')

    # Add value labels
    for bar in bars1:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h, f'{h:+.1f}%',
                ha='center', va='bottom' if h >= 0 else 'top', fontsize=8)
    for bar in bars2:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2, h, f'{h:+.1f}%',
                ha='center', va='bottom' if h >= 0 else 'top', fontsize=8)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


# ============================================================
# 8. Main Pipeline
# ============================================================
def run_pipeline():
    """Execute the full hybrid model pipeline."""
    print('=' * 60)
    print('Freshlync Sales Prediction: XGBoost Hybrid Model')
    print(f'Targets: quantity_sold, price')
    print('=' * 60)

    # --- Load & Preprocess ---
    print('\n[1] Loading data...')
    df = load_data()

    print('\n[2] Preprocessing data...')
    X_train, X_test, y_train, y_test, preprocessor = preprocess_data(df)

    # --- Multi-Output XGBoost Baseline ---
    print('\n[3] Training Multi-Output XGBoost (baseline)...')
    mo_xgb = train_multioutput_xgboost(X_train, y_train, X_test, y_test)

    # --- Standalone models ---
    print('\n[4] Training standalone models (per target)...')
    standalone = train_standalone_models(X_train, y_train, X_test, y_test)

    # --- Target-Specific Hybrid ---
    print('\n[5] Training Target-Specific Hybrid (XGBoost→qty, LR→price)...')
    hybrid = train_target_specific_hybrid(X_train, y_train, X_test, y_test)

    # --- Blending Ensemble ---
    print('\n[6] Training Blending Ensemble...')
    blending = train_blending_ensemble(X_train, y_train, X_test, y_test, standalone)

    # --- Stacking Ensemble ---
    print('\n[7] Training Stacking Ensemble (K-Fold)...')
    stacking = train_stacking_ensemble(X_train, y_train, X_test, y_test)

    # --- Comparison Table ---
    print('\n' + '=' * 60)
    print('[8] Model Comparison')
    print('=' * 60)

    comparison_data = {
        'Model': [
            'MultiOutput XGBoost',
            'XGBoost (qty) + LR (price) Hybrid',
            'Blend: Simple Avg',
            'Blend: Weighted Avg',
            'Stacking Ensemble (3 models)'
        ],
        'Test RMSE (qty)': [
            mo_xgb['rmse_test_qty'],
            hybrid['rmse_test_qty'],
            (blending['quantity_sold']['simple_avg_rmse'] +
             blending['price']['simple_avg_rmse']) / 2,  # placeholder
            (blending['quantity_sold']['weighted_rmse'] +
             blending['price']['weighted_rmse']) / 2,
            stacking['rmse_test_qty']
        ],
        'Test RMSE (price)': [
            mo_xgb['rmse_test_price'],
            hybrid['rmse_test_price'],
            (blending['quantity_sold']['simple_avg_rmse'] +
             blending['price']['simple_avg_rmse']) / 2,
            (blending['quantity_sold']['weighted_rmse'] +
             blending['price']['weighted_rmse']) / 2,
            stacking['rmse_test_price']
        ],
        'Test R2': [
            mo_xgb['r2_test'],
            hybrid['r2_test'],
            (blending['quantity_sold']['simple_avg_r2'] +
             blending['price']['simple_avg_r2']) / 2,
            (blending['quantity_sold']['weighted_r2'] +
             blending['price']['weighted_r2']) / 2,
            stacking['r2_test']
        ],
    }

    # Fix blending values (they were averaged across targets incorrectly above)
    # Simple avg is per-target; for overall view we keep individual
    comparison = pd.DataFrame(comparison_data)

    # Actually build proper comparison with per-target metrics for blending
    # Rebuild with correct values
    comparison = pd.DataFrame({
        'Model': [
            'MultiOutput XGBoost',
            'XGBoost (qty) + LR (price)',
            'Blend: Simple Avg (qty)',
            'Blend: Simple Avg (price)',
            'Blend: Weighted Avg (qty)',
            'Blend: Weighted Avg (price)',
            'Stacking Ensemble'
        ],
        'Test RMSE (qty)': [
            mo_xgb['rmse_test_qty'],
            hybrid['rmse_test_qty'],
            blending['quantity_sold']['simple_avg_rmse'],
            np.nan,
            blending['quantity_sold']['weighted_rmse'],
            np.nan,
            stacking['rmse_test_qty']
        ],
        'Test RMSE (price)': [
            mo_xgb['rmse_test_price'],
            hybrid['rmse_test_price'],
            np.nan,
            blending['price']['simple_avg_rmse'],
            np.nan,
            blending['price']['weighted_rmse'],
            stacking['rmse_test_price']
        ],
        'Train R2': [
            mo_xgb['r2_train'],
            hybrid['r2_train'],
            np.nan,
            np.nan,
            np.nan,
            np.nan,
            stacking['r2_train']
        ],
        'Test R2': [
            mo_xgb['r2_test'],
            hybrid['r2_test'],
            blending['quantity_sold']['simple_avg_r2'],
            blending['price']['simple_avg_r2'],
            blending['quantity_sold']['weighted_r2'],
            blending['price']['weighted_r2'],
            stacking['r2_test']
        ],
    })

    print('\nFull Comparison (all models):')
    print(comparison.to_string(index=False, float_format=lambda x: f'{x:.2f}' if not np.isnan(x) else '  -  '))

    # --- Compact summary table ---
    print('\n\nCompact Summary (main models only):')
    summary = pd.DataFrame({
        'Model': [
            'MultiOutput XGBoost',
            'XGBoost (qty) + LR (price)',
            'Stacking Ensemble'
        ],
        'Test RMSE (qty)': [
            mo_xgb['rmse_test_qty'],
            hybrid['rmse_test_qty'],
            stacking['rmse_test_qty']
        ],
        'Test RMSE (price)': [
            mo_xgb['rmse_test_price'],
            hybrid['rmse_test_price'],
            stacking['rmse_test_price']
        ],
        'Test R2': [
            mo_xgb['r2_test'],
            hybrid['r2_test'],
            stacking['r2_test']
        ],
    })
    print(summary.to_string(index=False, float_format=lambda x: f'{x:.2f}'))

    # --- Generate Charts ---
    print('\n' + '=' * 60)
    print('[9] Generating charts...')
    print('=' * 60)

    # Individual model charts for key models
    models_to_plot = [
        ('MultiOutput XGBoost', mo_xgb, 'mo_xgb'),
        ('Hybrid (XGB+LR)', hybrid, 'hybrid'),
        ('Stacking Ensemble', stacking, 'stacking'),
    ]

    for model_name, model_data, chart_prefix in models_to_plot:
        print(f'\n  -- {model_name} --')

        for idx, target in enumerate(TARGET_COLS):
            y_act = y_test[:, idx]
            y_prd = model_data['pred_test'][:, idx]
            residuals = y_act - y_prd

            plot_actual_vs_predicted(
                y_act, y_prd, target, model_name, chart_prefix,
                f'{model_name}: actual vs predicted for {target}'
            )
            plot_residuals(
                y_prd, residuals, target, model_name, chart_prefix,
                f'{model_name}: residual distribution for {target}'
            )

    # Clean comparison for charts (only complete multi-target models)
    chart_comparison = pd.DataFrame({
        'Model': [
            'MultiOutput XGBoost',
            'XGBoost (qty) + LR (price)',
            'Stacking Ensemble'
        ],
        'Test RMSE (qty)': [
            mo_xgb['rmse_test_qty'],
            hybrid['rmse_test_qty'],
            stacking['rmse_test_qty']
        ],
        'Test RMSE (price)': [
            mo_xgb['rmse_test_price'],
            hybrid['rmse_test_price'],
            stacking['rmse_test_price']
        ],
        'Test R2': [
            mo_xgb['r2_test'],
            hybrid['r2_test'],
            stacking['r2_test']
        ],
    })

    plot_all_model_comparison(
        chart_comparison, 'hybrid_model_comparison.png',
        'Side-by-side comparison of all hybrid approaches vs baseline.'
    )
    plot_hybrid_improvement(
        chart_comparison, 'hybrid_improvement.png',
        'Percentage improvement of hybrid models over MultiOutput XGBoost baseline. '
        'Negative = improvement (lower RMSE is better).'
    )

    # --- Individual stand-alone per-target performance chart ---
    print('\n  -- Standalone Per-Target Performance --')
    standalone_df = pd.DataFrame({
        'Model': [
            'XGBoost (qty)', 'Linear Reg (qty)',
            'XGBoost (price)', 'Linear Reg (price)'
        ],
        'Test RMSE': [
            standalone['xgb_quantity_sold']['rmse_test'],
            standalone['lr_quantity_sold']['rmse_test'],
            standalone['xgb_price']['rmse_test'],
            standalone['lr_price']['rmse_test']
        ],
        'Test R2': [
            standalone['xgb_quantity_sold']['r2_test'],
            standalone['lr_quantity_sold']['r2_test'],
            standalone['xgb_price']['r2_test'],
            standalone['lr_price']['r2_test']
        ],
        'Target': ['qty', 'qty', 'price', 'price']
    })
    print(standalone_df.to_string(index=False, float_format=lambda x: f'{x:.2f}'))

    # --- Save Results ---
    print('\n' + '=' * 60)
    print('[10] Saving results...')
    print('=' * 60)

    comparison.to_csv(os.path.join(OUTPUT_DIR, 'hybrid_model_comparison.csv'), index=False)
    standalone_df.to_csv(os.path.join(OUTPUT_DIR, 'standalone_per_target.csv'), index=False)

    # --- Summary Conclusion ---
    print('\n' + '=' * 60)
    print('HYBRID MODEL SUMMARY & CONCLUSION')
    print('=' * 60)

    # Determine best model for each target
    best_qty_model = min([
        ('MultiOutput XGBoost', mo_xgb['rmse_test_qty']),
        ('Hybrid (XGB+LR)', hybrid['rmse_test_qty']),
        ('Stacking Ensemble', stacking['rmse_test_qty']),
        ('XGBoost standalone', standalone['xgb_quantity_sold']['rmse_test']),
        ('LR standalone', standalone['lr_quantity_sold']['rmse_test']),
    ], key=lambda x: x[1])

    best_price_model = min([
        ('MultiOutput XGBoost', mo_xgb['rmse_test_price']),
        ('Hybrid (XGB+LR)', hybrid['rmse_test_price']),
        ('Stacking Ensemble', stacking['rmse_test_price']),
        ('XGBoost standalone', standalone['xgb_price']['rmse_test']),
        ('LR standalone', standalone['lr_price']['rmse_test']),
    ], key=lambda x: x[1])

    # Blending best weights
    blend_w_qty = blending['quantity_sold']['best_weight']
    blend_w_price = blending['price']['best_weight']

    conclusion = f"""
HYBRID MODEL ANALYSIS
=====================
This experiment explores hybrid approaches combining XGBoost and Linear Regression
for multi-output sales prediction (quantity_sold AND price simultaneously).

MODELS COMPARED
---------------
1. MultiOutput XGBoost      - Standard XGBoost for both targets (baseline)
2. Target-Specific Hybrid   - XGBoost for qty_sold, Linear Regression for price
3. Blending Ensemble        - Weighted average of XGBoost + LR per target
4. Stacking Ensemble        - K-Fold OOF predictions + Ridge meta-model (3 base models)

KEY RESULTS
-----------
                              Test RMSE     Test RMSE
Model                         (qty_sold)    (price)        Test R2
MultiOutput XGBoost           {mo_xgb['rmse_test_qty']:.2f}          {mo_xgb['rmse_test_price']:.2f}          {mo_xgb['r2_test']:.4f}
XGBoost (qty) + LR (price)    {hybrid['rmse_test_qty']:.2f}          {hybrid['rmse_test_price']:.2f}          {hybrid['r2_test']:.4f}
Stacking Ensemble              {stacking['rmse_test_qty']:.2f}          {stacking['rmse_test_price']:.2f}          {stacking['r2_test']:.4f}

BEST MODEL PER TARGET
---------------------
quantity_sold -> {best_qty_model[0]} (RMSE: {best_qty_model[1]:.2f})
price         -> {best_price_model[0]} (RMSE: {best_price_model[1]:.2f})

BLENDING ANALYSIS
-----------------
quantity_sold: Optimal blend weight w (XGBoost) = {blend_w_qty:.2f}, 1-w (LR) = {1-blend_w_qty:.2f}
price        : Optimal blend weight w (XGBoost) = {blend_w_price:.2f}, 1-w (LR) = {1-blend_w_price:.2f}

INTERPRETATION
--------------
1. TARGET-SPECIFIC MODELING:
   - quantity_sold benefits from XGBoost's ability to capture non-linear
     demand patterns (product-category interactions, holiday effects).
   - price tends toward linear relationships with the given categorical
     features, making Linear Regression competitive.
   - Using the right model per target often outperforms a one-size-fits-all.

2. BLENDING EFFECTIVENESS:
   - Weighted blending finds the optimal contribution of each model.
   - The optimal weight reveals which model captures more signal.
   - Blending typically reduces variance compared to either model alone.

3. STACKING ENSEMBLE:
   - K-Fold stacking prevents data leakage via out-of-fold predictions.
   - Multiple base models (XGBoost, RF, LR) provide diverse perspectives.
   - Meta-model (Ridge) learns how to combine base model outputs.
   - Cross-target features (price predictions for qty model) can add value.

4. WHEN HYBRID MODELS HELP:
   - When different targets have different data generating processes.
   - When base models have complementary strengths/weaknesses.
   - When reducing prediction variance is more important than minimal bias.
   - Warning: stacking adds complexity; only use if it meaningfully improves
     over simpler approaches.

CHARTS GENERATED
----------------
Per-model (3 models × 2 targets × 2 charts = 12 charts):
  1-4.  mo_xgb/hybrid/stacking_actual_vs_predicted_qty/price.png
  5-8.  mo_xgb/hybrid/stacking_residual_plot_qty/price.png

Comparison (2 charts):
  13. hybrid_model_comparison.png
  14. hybrid_improvement.png

RECOMMENDATIONS
---------------
- Deploy the model that best balances accuracy and simplicity for your use case.
- If all targets have similar RMSE improvement direction, the hybrid adds value.
- Re-evaluate when more data becomes available (stacking especially benefits).
- Consider adding time-series features to further improve qty_sold predictions.
"""
    print(conclusion)

    with open(os.path.join(OUTPUT_DIR, 'hybrid_conclusion.txt'), 'w', encoding='utf-8') as f:
        f.write(conclusion.strip())

    print(f'\nAll outputs saved to: {OUTPUT_DIR}')
    print(f'  - Charts:      {CHARTS_DIR}/')
    print(f'  - Metrics:     hybrid_model_comparison.csv')
    print(f'  - Conclusion:  hybrid_conclusion.txt')
    print(f'\nRun with: python freshlync/ml_service/models/xgboost_hybrid_model.py')
    print('\nDone!')

    return {
        'multioutput_xgb': {
            'qty_rmse': mo_xgb['rmse_test_qty'],
            'price_rmse': mo_xgb['rmse_test_price'],
            'r2': mo_xgb['r2_test']
        },
        'target_specific_hybrid': {
            'qty_rmse': hybrid['rmse_test_qty'],
            'price_rmse': hybrid['rmse_test_price'],
            'r2': hybrid['r2_test']
        },
        'stacking_ensemble': {
            'qty_rmse': stacking['rmse_test_qty'],
            'price_rmse': stacking['rmse_test_price'],
            'r2': stacking['r2_test']
        },
        'blending': {
            'qty_weight': blend_w_qty,
            'price_weight': blend_w_price
        },
        'best_for_qty': best_qty_model[0],
        'best_for_price': best_price_model[0]
    }


if __name__ == '__main__':
    results = run_pipeline()