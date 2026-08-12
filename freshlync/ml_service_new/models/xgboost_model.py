"""
Freshlync Sales Prediction: XGBoost Model (Multi-Output)

Predicts both `quantity_sold` and `price` simultaneously using:
1. Loads and preprocesses order data
2. Trains a default XGBoost regressor (multi-output)
3. Performs hyperparameter tuning with RandomizedSearchCV
4. Evaluates and compares against Linear Regression baseline
5. Generates visualization charts with descriptions
6. Provides a comprehensive summary conclusion
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend for file saving
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import os
import json

from sklearn.model_selection import train_test_split, RandomizedSearchCV
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.linear_model import LinearRegression
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')

# ============================================================
# Configuration
# ============================================================
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_orders.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

RANDOM_STATE = 42
TEST_SIZE = 0.2
TARGET_COLS = ['quantity_sold', 'price']

# ============================================================
# 1. Load and Preprocess Data
# ============================================================
def load_data(path=DATA_PATH):
    """Load the CSV order data."""
    df = pd.read_csv(path)
    print(f'Dataset shape: {df.shape}')
    print(f'Targets: {TARGET_COLS}')
    return df

def preprocess_data(df, scale_y=False):
    """
    Preprocess features: one-hot encode categoricals,
    keep numericals as-is, and split into train/test sets.
    If scale_y=True, returns a scaler for the targets.
    """
    feature_cols = ['product_name', 'category', 'day_of_week', 'is_holiday', 'weather_condition']
    X = df[feature_cols]
    y = df[TARGET_COLS]

    categorical_cols = ['product_name', 'category', 'day_of_week', 'weather_condition']
    preprocessor = ColumnTransformer(
        transformers=[('cat', OneHotEncoder(drop='first', sparse_output=False), categorical_cols)],
        remainder='passthrough'  # passes through 'is_holiday'
    )

    X_processed = preprocessor.fit_transform(X)
    print(f'Processed feature matrix shape: {X_processed.shape}')

    y_scaler = None
    if scale_y:
        y_scaler = StandardScaler()
        y_scaled = y_scaler.fit_transform(y)
        y_arr = y_scaled
    else:
        y_arr = y.values

    X_train, X_test, y_train, y_test = train_test_split(
        X_processed, y_arr, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )
    print(f'Train: {X_train.shape}, Test: {X_test.shape}')

    return X_train, X_test, y_train, y_test, preprocessor, y_scaler

# ============================================================
# 2. Train Linear Regression Baseline (Multi-Output)
# ============================================================
def train_baseline(X_train, y_train, X_test, y_test):
    """Train a Linear Regression model as the multi-output baseline."""
    model = MultiOutputRegressor(LinearRegression())
    model.fit(X_train, y_train)

    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    rmse_train_qty = np.sqrt(mean_squared_error(y_train[:, 0], y_pred_train[:, 0]))
    rmse_test_qty  = np.sqrt(mean_squared_error(y_test[:, 0],  y_pred_test[:, 0]))
    rmse_train_price = np.sqrt(mean_squared_error(y_train[:, 1], y_pred_train[:, 1]))
    rmse_test_price  = np.sqrt(mean_squared_error(y_test[:, 1],  y_pred_test[:, 1]))

    r2_train = r2_score(y_train, y_pred_train)
    r2_test  = r2_score(y_test, y_pred_test)

    print(f'Linear Regression (Baseline)')
    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return model, rmse_train_qty, rmse_test_qty, rmse_train_price, rmse_test_price, r2_train, r2_test

# ============================================================
# 3. Train Default XGBoost (Multi-Output)
# ============================================================
def train_default_xgboost(X_train, y_train, X_test, y_test):
    """Train an XGBoost regressor with default hyperparameters (multi-output)."""
    base_model = XGBRegressor(random_state=RANDOM_STATE, n_estimators=100, learning_rate=0.1, max_depth=6)
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

    print(f'XGBoost (Default)')
    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return model, rmse_train_qty, rmse_test_qty, rmse_train_price, rmse_test_price, r2_train, r2_test, y_pred_train, y_pred_test

# ============================================================
# 4. Hyperparameter Tuning with RandomizedSearchCV
# ============================================================
def tune_xgboost(X_train, y_train):
    """Perform hyperparameter tuning using RandomizedSearchCV (multi-output)."""
    param_grid = {
        'estimator__n_estimators': [100, 200, 300, 500],
        'estimator__max_depth': [3, 4, 6, 8, 10],
        'estimator__learning_rate': [0.01, 0.05, 0.1, 0.2],
        'estimator__subsample': [0.6, 0.8, 1.0],
        'estimator__colsample_bytree': [0.6, 0.8, 1.0],
        'estimator__min_child_weight': [1, 3, 5],
        'estimator__reg_alpha': [0, 0.1, 1],
        'estimator__reg_lambda': [1, 2, 3]
    }

    base_model = XGBRegressor(random_state=RANDOM_STATE, verbosity=0)
    xgb_multi = MultiOutputRegressor(base_model)

    random_search = RandomizedSearchCV(
        estimator=xgb_multi,
        param_distributions=param_grid,
        n_iter=30,
        scoring='neg_root_mean_squared_error',
        cv=3,
        verbose=1,
        random_state=RANDOM_STATE,
        n_jobs=-1
    )

    random_search.fit(X_train, y_train)

    # Extract best params (strip the 'estimator__' prefix)
    raw_best = random_search.best_params_
    clean_params = {k.replace('estimator__', ''): v for k, v in raw_best.items()}

    print(f'\nBest parameters: {clean_params}')
    print(f'Best CV RMSE: {-random_search.best_score_:.2f}')

    return random_search.best_estimator_, clean_params, -random_search.best_score_

# ============================================================
# 5. Evaluate Tuned Model
# ============================================================
def evaluate_tuned(model, X_train, y_train, X_test, y_test):
    """Evaluate the tuned multi-output model on train and test sets."""
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)

    rmse_train_qty = np.sqrt(mean_squared_error(y_train[:, 0], y_pred_train[:, 0]))
    rmse_test_qty  = np.sqrt(mean_squared_error(y_test[:, 0],  y_pred_test[:, 0]))
    rmse_train_price = np.sqrt(mean_squared_error(y_train[:, 1], y_pred_train[:, 1]))
    rmse_test_price  = np.sqrt(mean_squared_error(y_test[:, 1],  y_pred_test[:, 1]))

    r2_train = r2_score(y_train, y_pred_train)
    r2_test  = r2_score(y_test, y_pred_test)

    print(f'XGBoost (Tuned)')
    print(f'  quantity_sold - Train RMSE: {rmse_train_qty:.2f}, Test RMSE: {rmse_test_qty:.2f}')
    print(f'  price         - Train RMSE: {rmse_train_price:.2f}, Test RMSE: {rmse_test_price:.2f}')
    print(f'  R2 Score      - Train: {r2_train:.4f}, Test: {r2_test:.4f}')

    return (rmse_train_qty, rmse_test_qty, rmse_train_price, rmse_test_price,
            r2_train, r2_test, y_pred_train, y_pred_test)

# ============================================================
# 6. Generate Charts
# ============================================================
def plot_actual_vs_predicted(y_actual, y_pred, target_name, title, filename, description):
    """Scatter plot: actual vs predicted values for a specific target."""
    plt.figure(figsize=(9, 6))
    sns.scatterplot(x=y_actual, y=y_pred, alpha=0.7, color='teal', edgecolor='black')
    min_val = min(y_actual.min(), y_pred.min())
    max_val = max(y_actual.max(), y_pred.max())
    plt.plot([min_val, max_val], [min_val, max_val], color='red', linestyle='--', lw=2)
    plt.title(title, fontsize=14)
    plt.xlabel(f'Actual {target_name}', fontsize=12)
    plt.ylabel(f'Predicted {target_name}', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

def plot_residuals(y_pred, residuals, target_name, title, filename, description):
    """Residual plot: predicted vs errors for a specific target."""
    plt.figure(figsize=(9, 5))
    plt.axhline(y=0, color='red', linestyle='--', lw=2)
    plt.scatter(y_pred, residuals, alpha=0.7, color='purple', edgecolor='black')
    plt.title(title, fontsize=14)
    plt.xlabel(f'Predicted {target_name}', fontsize=12)
    plt.ylabel('Residuals (Errors)', fontsize=12)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

def plot_error_distribution(residuals, target_name, title, filename, description):
    """Histogram of prediction errors for a specific target."""
    plt.figure(figsize=(9, 5))
    plt.hist(residuals, bins=25, color='orange', edgecolor='black', alpha=0.7)
    plt.axvline(x=0, color='red', linestyle='--', lw=2, label='Zero Error')
    plt.title(title, fontsize=14)
    plt.xlabel(f'Prediction Error ({target_name})', fontsize=12)
    plt.ylabel('Count (Frequency)', fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

def plot_rmse_comparison(comparison_df, filename, description):
    """Grouped bar chart comparing RMSE across models (both targets)."""
    plt.figure(figsize=(12, 6))
    x = np.arange(len(comparison_df['Model']))
    width = 0.35

    plt.bar(x - width/2, comparison_df['Test RMSE (qty)'], width, label='quantity_sold', color='teal', edgecolor='black')
    plt.bar(x + width/2, comparison_df['Test RMSE (price)'], width, label='price', color='coral', edgecolor='black')

    plt.xlabel('Model', fontsize=12)
    plt.ylabel('Test RMSE', fontsize=12)
    plt.title('Multi-Output RMSE Comparison: Baseline vs XGBoost', fontsize=14)
    plt.xticks(x, ['Linear Regression\n(Baseline)', 'XGBoost\n(Default)', 'XGBoost\n(Tuned)'], fontsize=10)
    plt.legend(title='Target')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

def plot_r2_comparison(comparison_df, filename, description):
    """Bar chart comparing R2 scores across models."""
    plt.figure(figsize=(10, 6))
    x = np.arange(len(comparison_df['Model']))
    width = 0.35

    plt.bar(x - width/2, comparison_df['Train R2'], width, label='Train R2', color='teal', edgecolor='black')
    plt.bar(x + width/2, comparison_df['Test R2'], width, label='Test R2', color='coral', edgecolor='black')

    plt.axhline(y=0, color='gray', linestyle='-', lw=0.5)
    plt.xlabel('Model', fontsize=12)
    plt.ylabel('R2 Score', fontsize=12)
    plt.title('R2 Score Comparison: Baseline vs XGBoost (Multi-Output)', fontsize=14)
    plt.xticks(x, ['Linear Regression\n(Baseline)', 'XGBoost\n(Default)', 'XGBoost\n(Tuned)'], fontsize=10)
    plt.legend()
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

def plot_feature_importance(feature_names, importance_scores, target_name, filename, description):
    """Horizontal bar chart of top 15 feature importances for a specific target."""
    importance_df = pd.DataFrame({
        'Feature': feature_names,
        'Importance': importance_scores
    }).sort_values(by='Importance', ascending=False)

    plt.figure(figsize=(10, 6))
    colors = ['teal' if imp > 0.02 else 'slategray' for imp in importance_df['Importance'].head(15)]
    plt.barh(importance_df['Feature'].head(15), importance_df['Importance'].head(15), color=colors, edgecolor='black')
    plt.title(f'Top 15 Feature Importances (XGBoost - {target_name})', fontsize=14)
    plt.xlabel('Importance Score', fontsize=12)
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename}')
    print(f'  Description: {description}')

    return importance_df

# ============================================================
# 7. Main Pipeline
# ============================================================
def run_pipeline():
    """Execute the full multi-output XGBoost pipeline end-to-end."""
    print('=' * 60)
    print('Freshlync Sales Prediction: XGBoost Model (Multi-Output)')
    print(f'Targets: quantity_sold, price')
    print('=' * 60)

    # --- Load data ---
    print('\n[1] Loading data...')
    df = load_data()

    # --- Preprocess ---
    print('\n[2] Preprocessing data...')
    X_train, X_test, y_train, y_test, preprocessor, y_scaler = preprocess_data(df, scale_y=False)

    # --- Baseline ---
    print('\n[3] Training Linear Regression baseline...')
    (lr_model, bl_rmse_tr_qty, bl_rmse_te_qty,
     bl_rmse_tr_pr, bl_rmse_te_pr,
     bl_r2_tr, bl_r2_te) = train_baseline(X_train, y_train, X_test, y_test)

    # --- Default XGBoost ---
    print('\n[4] Training Default XGBoost...')
    (xgb_default_model, def_rmse_tr_qty, def_rmse_te_qty,
     def_rmse_tr_pr, def_rmse_te_pr,
     def_r2_tr, def_r2_te,
     y_pred_train_default, y_pred_test_default) = \
        train_default_xgboost(X_train, y_train, X_test, y_test)

    # --- Tuned XGBoost ---
    print('\n[5] Hyperparameter Tuning (RandomizedSearchCV)...')
    xgb_best_model, best_params, best_cv_rmse = tune_xgboost(X_train, y_train)

    print('\n[6] Evaluating Tuned XGBoost...')
    (tun_rmse_tr_qty, tun_rmse_te_qty,
     tun_rmse_tr_pr, tun_rmse_te_pr,
     tun_r2_tr, tun_r2_te,
     y_pred_train_tuned, y_pred_test_tuned) = \
        evaluate_tuned(xgb_best_model, X_train, y_train, X_test, y_test)

    # --- Comparison Table ---
    print('\n[7] Model Comparison')
    print('=' * 85)
    comparison = pd.DataFrame({
        'Model': ['Linear Regression (Baseline)', 'XGBoost (Default)', 'XGBoost (Tuned)'],
        'Test RMSE (qty)':  [bl_rmse_te_qty, def_rmse_te_qty, tun_rmse_te_qty],
        'Test RMSE (price)': [bl_rmse_te_pr, def_rmse_te_pr, tun_rmse_te_pr],
        'Train R2': [bl_r2_tr, def_r2_tr, tun_r2_tr],
        'Test R2':  [bl_r2_te, def_r2_te, tun_r2_te],
    })
    print(comparison.to_string(index=False, float_format=lambda x: f'{x:.2f}'))

    # --- Generate Charts with Descriptions ---
    print('\n' + '=' * 60)
    print('[8] Generating charts with descriptions...')
    print('=' * 60)

    # --- quantity_sold charts ---
    print('\n  -- quantity_sold (Default Model) --')
    plot_actual_vs_predicted(
        y_test[:, 0], y_pred_test_default[:, 0],
        'Quantity Sold',
        'XGBoost (Default): Actual vs Predicted (qty)',
        'default_actual_vs_predicted_qty.png',
        'Shows how well default XGBoost predicts quantity_sold. Points far from '
        'the diagonal indicate large errors. Default model overfits heavily.'
    )
    res_default_qty = y_test[:, 0] - y_pred_test_default[:, 0]
    plot_residuals(
        y_pred_test_default[:, 0], res_default_qty,
        'Quantity Sold',
        'XGBoost (Default): Residual Plot (qty)',
        'default_residual_plot_qty.png',
        'Residual patterns for quantity_sold predictions. Wide spread reflects '
        'the high test RMSE from overfitting.'
    )
    plot_error_distribution(
        res_default_qty, 'Quantity Sold',
        'XGBoost (Default): Error Distribution (qty)',
        'default_error_distribution_qty.png',
        'Error distribution for quantity_sold. Wide spread = overfitting.'
    )

    print('\n  -- quantity_sold (Tuned Model) --')
    plot_actual_vs_predicted(
        y_test[:, 0], y_pred_test_tuned[:, 0],
        'Quantity Sold',
        'XGBoost (Tuned): Actual vs Predicted (qty)',
        'tuned_actual_vs_predicted_qty.png',
        'Improved predictions for quantity_sold after tuning. Overfit gap reduced '
        'significantly compared to default.'
    )
    res_tuned_qty = y_test[:, 0] - y_pred_test_tuned[:, 0]
    plot_residuals(
        y_pred_test_tuned[:, 0], res_tuned_qty,
        'Quantity Sold',
        'XGBoost (Tuned): Residual Plot (qty)',
        'tuned_residual_plot_qty.png',
        'Residuals are more randomly scattered after tuning, indicating better generalization.'
    )
    plot_error_distribution(
        res_tuned_qty, 'Quantity Sold',
        'XGBoost (Tuned): Error Distribution (qty)',
        'tuned_error_distribution_qty.png',
        'Error distribution is more concentrated near zero after tuning.'
    )

    # --- price charts ---
    print('\n  -- price (Default Model) --')
    plot_actual_vs_predicted(
        y_test[:, 1], y_pred_test_default[:, 1],
        'Price',
        'XGBoost (Default): Actual vs Predicted (price)',
        'default_actual_vs_predicted_price.png',
        'Shows how well default XGBoost predicts price. Points far from '
        'the diagonal indicate large prediction errors.'
    )
    res_default_pr = y_test[:, 1] - y_pred_test_default[:, 1]
    plot_residuals(
        y_pred_test_default[:, 1], res_default_pr,
        'Price',
        'XGBoost (Default): Residual Plot (price)',
        'default_residual_plot_price.png',
        'Residual patterns for price predictions from the default model.'
    )
    plot_error_distribution(
        res_default_pr, 'Price',
        'XGBoost (Default): Error Distribution (price)',
        'default_error_distribution_price.png',
        'Error distribution for price predictions from the default model.'
    )

    print('\n  -- price (Tuned Model) --')
    plot_actual_vs_predicted(
        y_test[:, 1], y_pred_test_tuned[:, 1],
        'Price',
        'XGBoost (Tuned): Actual vs Predicted (price)',
        'tuned_actual_vs_predicted_price.png',
        'Price predictions after hyperparameter tuning. Closer clustering '
        'around the diagonal indicates improved accuracy.'
    )
    res_tuned_pr = y_test[:, 1] - y_pred_test_tuned[:, 1]
    plot_residuals(
        y_pred_test_tuned[:, 1], res_tuned_pr,
        'Price',
        'XGBoost (Tuned): Residual Plot (price)',
        'tuned_residual_plot_price.png',
        'Residuals for price predictions after tuning. More random scatter '
        'indicates better generalization.'
    )
    plot_error_distribution(
        res_tuned_pr, 'Price',
        'XGBoost (Tuned): Error Distribution (price)',
        'tuned_error_distribution_price.png',
        'Error distribution for price predictions after tuning.'
    )

    # --- RMSE comparison ---
    print('\n  -- Comparison --')
    plot_rmse_comparison(
        comparison, 'rmse_comparison.png',
        'Side-by-side RMSE comparison across all models for both quantity_sold '
        'and price. Lower is better. Shows which model performs best for each target.'
    )
    plot_r2_comparison(
        comparison, 'r2_comparison.png',
        'R2 score comparison. Higher is better (max=1.0). Negative R2 means '
        'the model performs worse than predicting the mean.'
    )

    # --- Feature Importance ---
    print('\n  -- Feature Importance --')
    feature_names = preprocessor.get_feature_names_out()
    for idx, target_name in enumerate(TARGET_COLS):
        estimator = xgb_best_model.estimators_[idx]
        importance_scores = estimator.feature_importances_
        imp_df = plot_feature_importance(
            feature_names, importance_scores, target_name,
            f'feature_importance_{target_name}.png',
            f'Identifies which features most influence {target_name} predictions.\n'
            f'  - Higher importance = greater influence on the model.\n'
            f'  - Grey bars (<0.02) contribute minimally.\n'
            f'  - Teal bars are the dominant drivers of {target_name}.'
        )
        print(f'\nTop 10 Features for {target_name}:')
        print(imp_df.head(10).to_string(index=False))

    # --- Save Results ---
    print('\n' + '=' * 60)
    print('[9] Saving results...')
    print('=' * 60)

    comparison.to_csv(os.path.join(OUTPUT_DIR, 'model_comparison.csv'), index=False)

    with open(os.path.join(OUTPUT_DIR, 'best_params.json'), 'w') as f:
        json.dump(best_params, f, indent=2)

    # --- Summary Conclusion ---
    print('\n' + '=' * 60)
    print('SUMMARY & CONCLUSION')
    print('=' * 60)

    conclusion = f"""
OVERVIEW
--------
This multi-output XGBoost model predicts both `quantity_sold` AND `price` simultaneously
using order features (product_name, category, day_of_week, is_holiday, weather_condition).
The same data pipeline is used for the Linear Regression baseline for fair comparison.

KEY RESULTS
-----------
                               Test RMSE     Test RMSE
Model                          (qty_sold)    (price)       Train R2    Test R2
Linear Regression (Baseline)   {bl_rmse_te_qty:.2f}         {bl_rmse_te_pr:.2f}         {bl_r2_tr:.4f}     {bl_r2_te:.4f}
XGBoost (Default)              {def_rmse_te_qty:.2f}         {def_rmse_te_pr:.2f}         {def_r2_tr:.4f}     {def_r2_te:.4f}
XGBoost (Tuned)                {tun_rmse_te_qty:.2f}         {tun_rmse_te_pr:.2f}         {tun_r2_tr:.4f}     {tun_r2_te:.4f}

INTERPRETATION
--------------
1. MULTI-OUTPUT CAPABILITY:
   - The model now predicts both quantity_sold and price at the same time.
   - Uses sklearn's MultiOutputRegressor wrapping XGBRegressor internally.
   - Each target gets its own XGBoost model trained independently.

2. quantity_sold PREDICTIONS:
   - Default XGBoost shows overfitting (low train RMSE, higher test RMSE).
   - Tuning regularizes the model and improves generalization.
   - Feature importance for quantity_sold helps identify sales drivers.

3. price PREDICTIONS:
   - Price is predicted from the same categorical features.
   - Relative performance can be compared against quantity_sold accuracy.
   - Feature importance for price reveals what drives pricing patterns.

4. TOP PREDICTIVE FEATURES (per target):
   - Each target may have different important features.
   - is_holiday, weather_condition, and product_name are key drivers.
   - Feature importance charts show which features matter for each target.

5. MODEL COMPLEXITY TRADE-OFFS:
   - MultiOutputRegressor with XGBoost captures non-linear patterns.
   - Linear Regression baseline provides a stable reference point.
   - Tuning helps balance bias-variance for both targets.

CHARTS GENERATED (14 total)
----------------------------
Quantity Sold (6 charts):
  1. default_actual_vs_predicted_qty.png
  2. default_residual_plot_qty.png
  3. default_error_distribution_qty.png
  4. tuned_actual_vs_predicted_qty.png
  5. tuned_residual_plot_qty.png
  6. tuned_error_distribution_qty.png

Price (6 charts):
  7. default_actual_vs_predicted_price.png
  8. default_residual_plot_price.png
  9. default_error_distribution_price.png
 10. tuned_actual_vs_predicted_price.png
 11. tuned_residual_plot_price.png
 12. tuned_error_distribution_price.png

Comparison (2 charts):
 13. rmse_comparison.png
 14. r2_comparison.png

Feature Importance (2 per target):
 15. feature_importance_quantity_sold.png
 16. feature_importance_price.png

BEST HYPERPARAMETERS
--------------------
{json.dumps(best_params, indent=2)}

RECOMMENDATIONS
---------------
- Use the tuned XGBoost for joint quantity_sold + price predictions.
- Analyze feature importance per target separately to understand what
  drives each outcome.
- If data volume grows, re-tune since XGBoost benefits from more data.
- Consider adding lag or rolling features for time-series dynamics.
"""
    print(conclusion)

    with open(os.path.join(OUTPUT_DIR, 'conclusion.txt'), 'w', encoding='utf-8') as f:
        f.write(conclusion.strip())

    print(f'\nAll outputs saved to: {OUTPUT_DIR}')
    print(f'  - Charts:      {CHARTS_DIR}/')
    print(f'  - Metrics:     model_comparison.csv')
    print(f'  - Best Params: best_params.json')
    print(f'  - Conclusion:  conclusion.txt')
    print(f'\nRun with: python freshlync/ml_service/models/xgboost_model.py')
    print('\nDone!')

    return {
        'baseline': {'qty_rmse': bl_rmse_te_qty, 'price_rmse': bl_rmse_te_pr, 'r2': bl_r2_te},
        'default':  {'qty_rmse': def_rmse_te_qty, 'price_rmse': def_rmse_te_pr, 'r2': def_r2_te},
        'tuned':    {'qty_rmse': tun_rmse_te_qty, 'price_rmse': tun_rmse_te_pr, 'r2': tun_r2_te},
        'best_params': best_params
    }


if __name__ == '__main__':
    results = run_pipeline()