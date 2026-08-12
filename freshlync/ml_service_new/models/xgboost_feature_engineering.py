"""
Freshlync Demand Forecasting: XGBoost Feature Engineering & Training
=====================================================================

A production-ready ML pipeline for perishable food demand forecasting.

Pipeline Flow:
1. Load raw_dataset.csv
2. Feature Engineering:
   - Lag features (t-1, t-7, t-14) per product
   - Rolling statistics (7d, 14d mean/std)
   - Time features (month, week_of_year, day_of_month, is_weekend)
   - One-hot encoding (product_name, category, weather_condition)
3. TimeSeriesSplit cross-validation (no data leakage)
4. XGBoost Regression training & evaluation
5. Output: processed dataset, metrics, feature importance plot

Author: Freshlync ML Team
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import warnings
import os
import json

from sklearn.preprocessing import OneHotEncoder, LabelEncoder
from sklearn.metrics import mean_squared_error, mean_absolute_error
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')

# ============================================================
# Configuration
# ============================================================
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'raw_dataset.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)

OUTPUT_DATASET_PATH = os.path.join(OUTPUT_DIR, 'xgboost_ready_dataset.csv')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts_xgb_fe')
os.makedirs(CHARTS_DIR, exist_ok=True)

RANDOM_STATE = 42
TEST_SPLIT_RATIO = 0.2
TARGET_COL = 'quantity_sold'

# ============================================================
# STEP 1: Load Raw Dataset
# ============================================================
def load_raw_data(path=DATA_PATH):
    """Load the raw CSV dataset."""
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values(['product_name', 'date']).reset_index(drop=True)
    
    print(f'{"=" * 60}')
    print(f'STEP 1: LOAD RAW DATASET')
    print(f'{"=" * 60}')
    print(f'Rows: {df.shape[0]}')
    print(f'Products: {df["product_name"].nunique()}')
    print(f'Categories: {df["category"].unique()}')
    print(f'Date range: {df["date"].min().date()} to {df["date"].max().date()}')
    print(f'Target: {TARGET_COL}')
    
    return df


# ============================================================
# STEP 2: Feature Engineering
# ============================================================
def create_time_features(df):
    """Create time-based features from the date column."""
    d = df['date'].dt
    df['month'] = d.month
    df['week_of_year'] = d.isocalendar().week.astype(int)
    df['day_of_month'] = d.day
    df['is_weekend'] = (d.dayofweek >= 5).astype(int)
    return df


def create_lag_features(df, target_col=TARGET_COL, lags=None):
    """
    Create lag features per product.
    CRITICAL: Uses shift() within each product group to prevent data leakage.
    Lag 1 = previous day, Lag 7 = one week ago, Lag 14 = two weeks ago.
    """
    if lags is None:
        lags = [1, 7, 14]
    
    df = df.copy()
    df = df.sort_values(['product_name', 'date'])
    
    for lag in lags:
        df[f'lag_{lag}'] = df.groupby('product_name')[target_col].shift(lag)
    
    return df


def create_rolling_features(df, target_col=TARGET_COL, windows=None):
    """
    Create rolling window statistics per product.
    CRITICAL: Uses shift(1) before rolling to avoid using the current value.
    """
    if windows is None:
        windows = [7, 14]
    
    df = df.copy()
    df = df.sort_values(['product_name', 'date'])
    
    for w in windows:
        # Shift by 1 to exclude current row, then rolling
        shifted = df.groupby('product_name')[target_col].shift(1)
        df[f'rolling_mean_{w}'] = shifted.groupby(df['product_name']).transform(
            lambda x: x.rolling(window=w, min_periods=max(1, w//2)).mean()
        )
        df[f'rolling_std_{w}'] = shifted.groupby(df['product_name']).transform(
            lambda x: x.rolling(window=w, min_periods=max(1, w//2)).std()
        )
    
    return df


def encode_categoricals(df):
    """
    One-hot encode categorical columns.
    Encodes all string-type columns (product_name, category, day_of_week, weather_condition).
    """
    df = df.copy()
    
    # Columns to encode: any column with string/object dtype (except target and date)
    cat_cols = []
    for c in df.columns:
        if c in [TARGET_COL, 'date']:
            continue
        dtype_str = str(df[c].dtype)
        # Detect string types: 'str', 'object', 'string', 'string[python]', 'string[pyarrow]'
        if dtype_str in ('str', 'object', 'string') or 'string[' in dtype_str:
            cat_cols.append(c)
    
    print(f'\n  Categorical columns to encode ({len(cat_cols)}): {cat_cols}')
    
    if len(cat_cols) == 0:
        print('  (No categorical columns found - all features are numeric)')
        return df, None, []
    
    # One-hot encode
    encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    encoded = encoder.fit_transform(df[cat_cols])
    feature_names = encoder.get_feature_names_out(cat_cols)
    
    encoded_df = pd.DataFrame(encoded, columns=feature_names, index=df.index)
    
    # Drop original cat cols, append encoded
    df = pd.concat([df.drop(columns=cat_cols), encoded_df], axis=1)
    
    print(f'\n  Encoded features ({len(feature_names)}):')
    for name in feature_names[:10]:
        print(f'    - {name}')
    if len(feature_names) > 10:
        print(f'    ... and {len(feature_names) - 10} more')
    
    return df, encoder, feature_names


def build_feature_pipeline(df):
    """
    Execute the complete feature engineering pipeline.
    Order matters:
    1. Time features (no leakage)
    2. Lag features (shift per product)
    3. Rolling features (shift then roll per product)
    4. Drop NaN rows from lag/rolling
    5. Encode categoricals
    6. Separate features (X) and target (y)
    """
    print(f'\n{"=" * 60}')
    print(f'STEP 2: FEATURE ENGINEERING')
    print(f'{"=" * 60}')
    
    df = df.copy()
    
    # --- Step 2a: Time features ---
    print('\n[2a] Creating time features...')
    df = create_time_features(df)
    
    # --- Step 2b: Lag features (CRITICAL: per product, using shift) ---
    print('[2b] Creating lag features (lag_1, lag_7, lag_14)...')
    df = create_lag_features(df, lags=[1, 7, 14])
    
    # --- Step 2c: Rolling features (CRITICAL: shift(1) before rolling) ---
    print('[2c] Creating rolling features (rolling_mean_7, rolling_mean_14, rolling_std_7)...')
    df = create_rolling_features(df, windows=[7, 14])
    
    # --- Step 2d: Drop rows with NaN from lag/rolling features ---
    initial_rows = len(df)
    lag_cols = ['lag_1', 'lag_7', 'lag_14']
    rolling_cols = ['rolling_mean_7', 'rolling_mean_14', 'rolling_std_7']
    required_cols = lag_cols + rolling_cols
    
    df = df.dropna(subset=required_cols)
    dropped = initial_rows - len(df)
    print(f'\n[2d] Dropped {dropped} rows with NaN (first 14 days per product)')
    print(f'  Remaining: {len(df)} rows')
    
    # --- Step 2e: One-hot encode categoricals ---
    print('\n[2e] Encoding categorical features...')
    df, encoder, encoded_feature_names = encode_categoricals(df)
    
    # --- Step 2f: Separate features and target ---
    feature_cols = (
        [c for c in df.columns if c not in [TARGET_COL, 'date']]
    )
    X = df[feature_cols].copy()
    y = df[TARGET_COL].copy()
    
    print(f'\n  Final feature matrix: {X.shape}')
    print(f'  Features: {len(feature_cols)}')
    
    # Save processed dataset
    df.to_csv(OUTPUT_DATASET_PATH, index=False)
    print(f'\n  Saved processed dataset to: {OUTPUT_DATASET_PATH}')
    
    return df, X, y, feature_cols, encoder


# ============================================================
# STEP 3: Time-Series Train/Test Split
# ============================================================
def time_series_split(df, test_ratio=TEST_SPLIT_RATIO):
    """
    Time-series aware split.
    NO SHUFFLING — preserves temporal order.
    Splits by date: first (1-test_ratio) for train, last test_ratio for test.
    """
    print(f'\n{"=" * 60}')
    print(f'STEP 3: TIME-SERIES TRAIN/TEST SPLIT')
    print(f'{"=" * 60}')
    
    df = df.sort_values('date').reset_index(drop=True)
    split_idx = int(len(df) * (1 - test_ratio))
    
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()
    
    print(f'\n  Train: {len(train)} rows')
    print(f'    Date range: {train["date"].min().date()} to {train["date"].max().date()}')
    print(f'  Test:  {len(test)} rows')
    print(f'    Date range: {test["date"].min().date()} to {test["date"].max().date()}')
    
    return train, test


# ============================================================
# STEP 4: Train XGBoost with TimeSeriesSplit CV
# ============================================================
def train_xgboost(X_train, y_train, X_test, y_test):
    """
    Train XGBoost Regressor with TimeSeriesSplit cross-validation.
    Uses 3-fold time-series CV to tune early stopping.
    """
    print(f'\n{"=" * 60}')
    print(f'STEP 4: XGBoost MODEL TRAINING')
    print(f'{"=" * 60}')
    
    # --- TimeSeriesSplit Cross-Validation ---
    print('\n[4a] TimeSeriesSplit Cross-Validation (3 folds)...')
    tscv = TimeSeriesSplit(n_splits=3)
    cv_scores = []
    
    for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
        X_tr_fold, X_val_fold = X_train.iloc[tr_idx], X_train.iloc[val_idx]
        y_tr_fold, y_val_fold = y_train.iloc[tr_idx], y_train.iloc[val_idx]
        
        model = XGBRegressor(
            n_estimators=500,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_weight=3,
            reg_alpha=0.1,
            reg_lambda=2.0,
            random_state=RANDOM_STATE,
            verbosity=0
        )
        model.fit(
            X_tr_fold, y_tr_fold,
            eval_set=[(X_val_fold, y_val_fold)],
            verbose=False
        )
        
        val_pred = model.predict(X_val_fold)
        rmse = np.sqrt(mean_squared_error(y_val_fold, val_pred))
        cv_scores.append(rmse)
        print(f'    Fold {fold+1} - Validation RMSE: {rmse:.2f}')
    
    print(f'  Mean CV RMSE: {np.mean(cv_scores):.2f} (+/- {np.std(cv_scores):.2f})')
    
    # --- Retrain on full training set ---
    print('\n[4b] Training final model on full training set...')
    final_model = XGBRegressor(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=2.0,
        random_state=RANDOM_STATE,
        verbosity=0
    )
    final_model.fit(X_train, y_train)
    
    # --- Predict on test set ---
    print('[4c] Predicting on test set...')
    y_pred_train = final_model.predict(X_train)
    y_pred_test = final_model.predict(X_test)
    
    return final_model, y_pred_train, y_pred_test, cv_scores


# ============================================================
# STEP 5: Evaluation
# ============================================================
def evaluate_model(y_train, y_pred_train, y_test, y_pred_test):
    """
    Evaluate model using MAE, RMSE, MAPE.
    Computes both train and test metrics to check for overfitting.
    """
    print(f'\n{"=" * 60}')
    print(f'STEP 5: MODEL EVALUATION')
    print(f'{"=" * 60}')
    
    # Train metrics
    mae_train = mean_absolute_error(y_train, y_pred_train)
    rmse_train = np.sqrt(mean_squared_error(y_train, y_pred_train))
    mape_train = np.mean(np.abs((y_train - y_pred_train) / (y_train + 1e-8))) * 100
    
    # Test metrics
    mae_test = mean_absolute_error(y_test, y_pred_test)
    rmse_test = np.sqrt(mean_squared_error(y_test, y_pred_test))
    mape_test = np.mean(np.abs((y_test - y_pred_test) / (y_test + 1e-8))) * 100
    
    print(f'\n  {"Metric":<20} {"Train":<15} {"Test":<15}')
    print(f'  {"-" * 50}')
    print(f'  {"MAE":<20} {mae_train:<15.2f} {mae_test:<15.2f}')
    print(f'  {"RMSE":<20} {rmse_train:<15.2f} {rmse_test:<15.2f}')
    print(f'  {"MAPE (%)":<20} {mape_train:<15.1f} {mape_test:<15.1f}')
    
    overfit_pct = (rmse_test - rmse_train) / rmse_train * 100
    print(f'\n  Overfit Gap (RMSE test - train): {overfit_pct:+.1f}%')
    if overfit_pct > 20:
        print(f'  ⚠️  Warning: Possible overfitting. Consider more regularization.')
    elif overfit_pct > 0:
        print(f'  ✓ Acceptable generalization gap.')
    else:
        print(f'  ✓ Excellent generalization (test < train).')
    
    return {
        'mae_train': mae_train, 'mae_test': mae_test,
        'rmse_train': rmse_train, 'rmse_test': rmse_test,
        'mape_train': mape_train, 'mape_test': mape_test,
        'overfit_pct': overfit_pct
    }


# ============================================================
# STEP 6: Feature Importance Visualization
# ============================================================
def plot_feature_importance(model, feature_names, top_n=15):
    """
    Plot top-N feature importances from the trained XGBoost model.
    """
    print(f'\n{"=" * 60}')
    print(f'STEP 6: FEATURE IMPORTANCE')
    print(f'{"=" * 60}')
    
    importances = pd.DataFrame({
        'Feature': feature_names,
        'Importance': model.feature_importances_
    }).sort_values('Importance', ascending=False).head(top_n)
    
    print(f'\n  Top {top_n} Features:')
    for i, row in importances.iterrows():
        print(f'    {row["Feature"]:<45} {row["Importance"]:.4f}')
    
    plt.figure(figsize=(10, 7))
    colors = ['teal' if imp > 0.02 else 'slategray' for imp in importances['Importance']]
    plt.barh(importances['Feature'], importances['Importance'], 
             color=colors, edgecolor='black', height=0.6)
    plt.title(f'Top {top_n} Feature Importances (XGBoost)', fontsize=14, fontweight='bold')
    plt.xlabel('Importance Score', fontsize=12)
    plt.gca().invert_yaxis()
    plt.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    
    filename = 'feature_importance.png'
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'\n  Saved chart to: {CHARTS_DIR}/{filename}')
    
    return importances


# ============================================================
# STEP 7: Prediction vs Actual Plot
# ============================================================
def plot_predictions(y_test, y_pred, df_test):
    """
    Scatter plot of actual vs predicted values, colored by product.
    """
    plt.figure(figsize=(10, 8))
    
    # Get product names from the processed df (one-hot encoded -> not available)
    # Use index-based coloring instead
    scatter = plt.scatter(y_test, y_pred, alpha=0.7, c='teal', 
                          edgecolor='black', s=60)
    
    # Perfect prediction line
    min_val = min(y_test.min(), y_pred.min())
    max_val = max(y_test.max(), y_pred.max())
    plt.plot([min_val, max_val], [min_val, max_val], 
             color='red', linestyle='--', linewidth=2, label='Perfect Prediction')
    
    plt.title('XGBoost: Actual vs Predicted Demand', fontsize=14, fontweight='bold')
    plt.xlabel('Actual Quantity Sold', fontsize=12)
    plt.ylabel('Predicted Quantity Sold', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    
    filename = 'actual_vs_predicted.png'
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved chart to: {CHARTS_DIR}/{filename}')


def plot_residuals(y_test, y_pred):
    """
    Residual distribution plot.
    """
    residuals = y_test - y_pred
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Histogram
    axes[0].hist(residuals, bins=15, color='purple', edgecolor='black', alpha=0.7)
    axes[0].axvline(x=0, color='red', linestyle='--', linewidth=2)
    axes[0].set_title('Residual Distribution', fontsize=13, fontweight='bold')
    axes[0].set_xlabel('Residual (Actual - Predicted)', fontsize=11)
    axes[0].set_ylabel('Frequency', fontsize=11)
    axes[0].grid(True, alpha=0.3)
    
    # Residuals vs Predicted
    axes[1].scatter(y_pred, residuals, alpha=0.6, c='orange', edgecolor='black')
    axes[1].axhline(y=0, color='red', linestyle='--', linewidth=2)
    axes[1].set_title('Residuals vs Predicted', fontsize=13, fontweight='bold')
    axes[1].set_xlabel('Predicted Quantity Sold', fontsize=11)
    axes[1].set_ylabel('Residual', fontsize=11)
    axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    filename = 'residual_analysis.png'
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved chart to: {CHARTS_DIR}/{filename}')


# ============================================================
# Full Pipeline
# ============================================================
def run_pipeline():
    """Execute the complete XGBoost demand forecasting pipeline."""
    print('=' * 60)
    print('Freshlync Demand Forecasting Pipeline')
    print('XGBoost Feature Engineering & Training')
    print('=' * 60)
    
    # --- Step 1: Load ---
    df_raw = load_raw_data()
    
    # --- Step 2: Feature Engineering ---
    df_feat, X, y, feature_cols, encoder = build_feature_pipeline(df_raw)
    
    # --- Step 3: Time-Series Split ---
    # Split the FULL dataframe, then extract X and y
    train_df, test_df = time_series_split(df_feat)
    
    # Split features and target
    X_train = train_df[feature_cols]
    y_train = train_df[TARGET_COL]
    X_test = test_df[feature_cols]
    y_test = test_df[TARGET_COL]
    
    # --- Step 4: Train XGBoost ---
    model, y_pred_train, y_pred_test, cv_scores = train_xgboost(
        X_train, y_train, X_test, y_test
    )
    
    # --- Step 5: Evaluate ---
    metrics = evaluate_model(y_train, y_pred_train, y_test, y_pred_test)
    
    # --- Step 6: Feature Importance ---
    importance_df = plot_feature_importance(model, feature_cols)
    
    # --- Step 7: Prediction Plots ---
    print(f'\n{"=" * 60}')
    print(f'STEP 7: GENERATING CHARTS')
    print(f'{"=" * 60}')
    plot_predictions(y_test, y_pred_test, test_df)
    plot_residuals(y_test, y_pred_test)
    
    # --- Summary ---
    print(f'\n{"=" * 60}')
    print(f'PIPELINE COMPLETE')
    print(f'{"=" * 60}')
    print(f'\nOutputs generated:')
    print(f'  1. Raw dataset:        {DATA_PATH}')
    print(f'  2. Processed dataset:  {OUTPUT_DATASET_PATH}')
    print(f'  3. Charts:             {CHARTS_DIR}/')
    print(f'     - feature_importance.png')
    print(f'     - actual_vs_predicted.png')
    print(f'     - residual_analysis.png')
    print(f'  4. Metrics (test):')
    print(f'     - MAE:  {metrics["mae_test"]:.2f}')
    print(f'     - RMSE: {metrics["rmse_test"]:.2f}')
    print(f'     - MAPE: {metrics["mape_test"]:.1f}%')
    
    # Save metrics to JSON
    metrics_clean = {k: float(v) for k, v in metrics.items()}
    with open(os.path.join(OUTPUT_DIR, 'xgb_metrics.json'), 'w') as f:
        json.dump(metrics_clean, f, indent=2)
    
    print(f'\n  Metrics saved to: {OUTPUT_DIR}/xgb_metrics.json')
    print(f'\n  Run again: python freshlync/ml_service/models/xgboost_feature_engineering.py')
    print(f'\nDone!')
    
    return model, metrics, importance_df


if __name__ == '__main__':
    model, metrics, importance_df = run_pipeline()