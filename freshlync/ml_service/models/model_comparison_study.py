import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import os
import warnings
from datetime import timedelta
import json

from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder
from sklearn.model_selection import TimeSeriesSplit, RandomizedSearchCV
from xgboost import XGBRegressor
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings('ignore')

# Configuration
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_orders.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts_comparison')
FORECASTS_DIR = os.path.join(OUTPUT_DIR, 'forecasts')
os.makedirs(CHARTS_DIR, exist_ok=True)
os.makedirs(FORECASTS_DIR, exist_ok=True)

TARGET_COL = 'quantity_sold'
TEST_RATIO = 0.2
RANDOM_STATE = 42

def calculate_metrics(actual, predicted):
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    # FIX 1: Clip actuals to min=1 to prevent MAPE blow-up on near-zero values
    actual_clipped = np.maximum(actual, 1.0)
    mape = np.mean(np.abs((actual_clipped - predicted) / actual_clipped)) * 100
    r2 = r2_score(actual, predicted)
    return {'MAE': mae, 'RMSE': rmse, 'MAPE': mape, 'R2': r2}

def load_data():
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def split_data(df, test_ratio=TEST_RATIO):
    # Determine split date based on unique dates to ensure clean time split
    unique_dates = df['date'].sort_values().unique()
    split_idx = int(len(unique_dates) * (1 - test_ratio))
    split_date = unique_dates[split_idx]
    
    train_df = df[df['date'] < split_date].copy()
    test_df = df[df['date'] >= split_date].copy()
    return train_df, test_df, split_date

def run_moving_average(train_df, test_df, window=7):
    print("Running Moving Average...")
    all_preds = []
    for cat in test_df['category'].unique():
        cat_train = train_df[train_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index()
        cat_test = test_df[test_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index()
        
        train_vals = cat_train[TARGET_COL].values
        test_vals = cat_test[TARGET_COL].values
        
        preds = []
        history = list(train_vals)
        for i in range(len(test_vals)):
            if len(history) >= window:
                pred = np.mean(history[-window:])
            else:
                pred = np.mean(history) if history else 0
            preds.append(pred)
            history.append(test_vals[i])
            
        all_preds.append(pd.DataFrame({'date': cat_test['date'], 'category': cat, 'actual': test_vals, 'predicted': preds}))
    
    results = pd.concat(all_preds)
    return calculate_metrics(results['actual'], results['predicted']), results

def run_arima(train_df, test_df):
    print("Running ARIMA...")
    all_preds = []
    for cat in train_df['category'].unique():
        cat_train = train_df[train_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index()
        cat_train = cat_train.set_index('date').asfreq('D').fillna(0)
        
        cat_test = test_df[test_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index()
        cat_test = cat_test.set_index('date').asfreq('D').fillna(0)
        test_dates = cat_test.index
        
        try:
            model = ARIMA(cat_train[TARGET_COL], order=(2, 1, 2))
            fitted = model.fit()
            forecast = fitted.forecast(steps=len(cat_test))
            preds = forecast.values
        except Exception as e:
            # FIX 2: Log the actual error instead of silently swallowing it
            print(f'    ARIMA failed for category "{cat}": {e}. Falling back to last known value.')
            preds = np.full(len(cat_test), cat_train[TARGET_COL].iloc[-1])
            
        all_preds.append(pd.DataFrame({'date': test_dates, 'category': cat, 'actual': cat_test[TARGET_COL].values, 'predicted': preds}))
        
    results = pd.concat(all_preds)
    return calculate_metrics(results['actual'], results['predicted']), results

def run_prophet(train_df, test_df):
    print("Running Prophet...")
    all_preds = []
    for cat in train_df['category'].unique():
        cat_train = train_df[train_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index().rename(columns={'date': 'ds', TARGET_COL: 'y'})
        cat_test = test_df[test_df['category'] == cat].groupby('date')[TARGET_COL].sum().reset_index().rename(columns={'date': 'ds', TARGET_COL: 'y'})
        
        model = Prophet(yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False)
        model.fit(cat_train)
        
        future_dates = pd.concat([cat_train['ds'], cat_test['ds']]).drop_duplicates().sort_values()
        future = pd.DataFrame({'ds': future_dates})
        forecast = model.predict(future)
        test_forecast = forecast[forecast['ds'].isin(cat_test['ds'])]['yhat'].values
        
        all_preds.append(pd.DataFrame({'date': cat_test['ds'], 'category': cat, 'actual': cat_test['y'], 'predicted': test_forecast}))
        
    results = pd.concat(all_preds)
    return calculate_metrics(results['actual'], results['predicted']), results

def create_xgboost_features(df, encoder=None):
    """Create all XGBoost features. If encoder is provided, transform only (no fit).
    FIX 3: Encoder must be fit on train data only to prevent data leakage.
    """
    df = df.copy()
    df = df.sort_values(['product_name', 'date']).reset_index(drop=True)
    
    # Time features
    d = df['date'].dt
    df['month'] = d.month
    df['quarter'] = d.quarter
    df['day_of_week'] = d.dayofweek
    df['is_weekend'] = (d.dayofweek >= 5).astype(int)
    
    # Lag and Rolling features
    lags = [1, 2, 3, 7, 14, 30]
    windows = [7, 14, 30]
    
    for lag in lags:
        df[f'lag_{lag}'] = df.groupby('product_name')[TARGET_COL].shift(lag)
        
    shifted = df.groupby('product_name')[TARGET_COL].shift(1)
    for w in windows:
        df[f'rolling_mean_{w}'] = shifted.groupby(df['product_name']).transform(lambda x: x.rolling(w, min_periods=max(1, w//2)).mean())
        df[f'rolling_std_{w}'] = shifted.groupby(df['product_name']).transform(lambda x: x.rolling(w, min_periods=max(1, w//2)).std())
        
    # Price change
    df['price_change'] = df.groupby('product_name')['price'].diff()
    df['price_change'] = df['price_change'].fillna(0)
    
    # Categorical Encoding
    cat_cols = ['category', 'weather_condition']
    if 'is_holiday' in df.columns:
        df['is_holiday'] = df['is_holiday'].astype(int)
        
    if encoder is None:
        # FIX 3: Fit encoder only on the provided data (caller must pass train data only)
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded = encoder.fit_transform(df[cat_cols])
    else:
        encoded = encoder.transform(df[cat_cols])
        
    encoded_cols = encoder.get_feature_names_out(cat_cols)
    encoded_df = pd.DataFrame(encoded, columns=encoded_cols, index=df.index)
    
    df = pd.concat([df.drop(columns=cat_cols), encoded_df], axis=1)
    
    return df, encoded_cols.tolist(), encoder

def run_xgboost(train_df, test_df, full_df, split_date):
    print("Running XGBoost with Feature Engineering and Tuning...")

    # FIX 3: Fit encoder on train only, then apply to full dataset
    train_feat, encoded_cols, encoder = create_xgboost_features(train_df)
    train_feat = train_feat.dropna()  # FIX 4: dropna only on train

    # Apply the SAME encoder (no re-fit) to test data to prevent leakage
    test_feat, _, _ = create_xgboost_features(test_df, encoder=encoder)
    test_feat = test_feat.dropna()

    features = [c for c in train_feat.columns if c not in [TARGET_COL, 'date', 'product_name']]
    
    X_train = train_feat[features]
    y_train = train_feat[TARGET_COL]
    X_test = test_feat[features]
    y_test = test_feat[TARGET_COL]

    print(f"  Train shape: {X_train.shape}, Test shape: {X_test.shape}")
    
    param_grid = {
        'n_estimators': [100, 300, 500],
        'max_depth': [3, 5, 7],
        'learning_rate': [0.01, 0.05, 0.1],
        'subsample': [0.6, 0.8, 1.0],
        'colsample_bytree': [0.6, 0.8, 1.0],
        'reg_alpha': [0, 0.1, 1],
        'reg_lambda': [1, 2, 5]
    }
    
    tscv = TimeSeriesSplit(n_splits=3)
    base_model = XGBRegressor(random_state=RANDOM_STATE, verbosity=0)
    
    print("  Tuning hyperparameters via RandomizedSearchCV...")
    random_search = RandomizedSearchCV(
        base_model, param_distributions=param_grid, n_iter=10, 
        scoring='neg_root_mean_squared_error', cv=tscv, random_state=RANDOM_STATE, n_jobs=-1
    )
    
    random_search.fit(X_train, y_train)
    best_model = random_search.best_estimator_
    print(f"  Best params: {random_search.best_params_}")
    
    preds = best_model.predict(X_test)
    
    # Aggregate product-level predictions to category-level for fair comparison
    test_feat = test_feat.copy()
    test_feat['predicted'] = preds
    test_feat_mapped = test_feat.merge(
        test_df[['date', 'product_name', 'category']].drop_duplicates(),
        on=['date', 'product_name'], how='left'
    )
    
    cat_results = test_feat_mapped.groupby(['date', 'category']).agg(
        {'quantity_sold': 'sum', 'predicted': 'sum'}
    ).reset_index().rename(columns={'quantity_sold': 'actual'})
    
    metrics = calculate_metrics(cat_results['actual'], cat_results['predicted'])

    # Also build full_df features for future forecasting (fit new encoder on full data)
    df_feat, _, _ = create_xgboost_features(full_df, encoder=encoder)

    return metrics, cat_results, best_model, features, df_feat, encoder

def generate_charts(results_dict, metrics_df):
    print("Generating charts...")
    
    # 1. Bar chart of metrics
    metrics_df.set_index('Model')[['MAE', 'RMSE']].plot(kind='bar', figsize=(10, 6))
    plt.title('Model Comparison: MAE and RMSE')
    plt.ylabel('Error')
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'metrics_comparison.png'))
    plt.close()
    
    # 2. MAPE comparison
    metrics_df.set_index('Model')[['MAPE']].plot(kind='bar', color='orange', figsize=(8, 5))
    plt.title('Model Comparison: MAPE (%)')
    plt.ylabel('MAPE (%)')
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'mape_comparison.png'))
    plt.close()
    
    # 3. Actual vs Predicted Scatter Plots
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    axes = axes.flatten()
    for i, (name, df) in enumerate(results_dict.items()):
        if i >= 4: break
        ax = axes[i]
        ax.scatter(df['actual'], df['predicted'], alpha=0.5, color='teal')
        min_val = min(df['actual'].min(), df['predicted'].min())
        max_val = max(df['actual'].max(), df['predicted'].max())
        ax.plot([min_val, max_val], [min_val, max_val], 'r--')
        ax.set_title(f'{name}: Actual vs Predicted')
        ax.set_xlabel('Actual')
        ax.set_ylabel('Predicted')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, 'actual_vs_predicted_all.png'))
    plt.close()

def generate_future_forecasts(xgb_model, features, full_df, encoder):
    print("Generating future forecasts (7, 14, 30 days)...")
    
    last_date = full_df['date'].max()
    forecasts = {}
    
    for horizon in [7, 14, 30]:
        current_df = full_df.copy()
        
        # Iteratively predict the next day
        for i in range(1, horizon + 1):
            next_date = last_date + timedelta(days=i)
            last_records = current_df.groupby('product_name').last().reset_index()
            last_records['date'] = next_date
            
            # Recalculate features — use same encoder (FIX 3: no re-fit)
            temp_df = pd.concat([current_df, last_records]).reset_index(drop=True)
            temp_feat, _, _ = create_xgboost_features(temp_df, encoder=encoder)
            
            # Predict the new day
            pred_day = temp_feat[temp_feat['date'] == next_date]
            if len(pred_day) > 0:
                # Fill any remaining NaN in features with 0 for robustness
                pred_input = pred_day[features].fillna(0)
                preds = xgb_model.predict(pred_input)
                last_records[TARGET_COL] = preds
            
            current_df = pd.concat([current_df, last_records]).reset_index(drop=True)
            
        forecast_df = current_df[current_df['date'] > last_date]
        
        product_to_cat = full_df[['product_name', 'category']].drop_duplicates()
        forecast_df = forecast_df.drop(columns=['category'], errors='ignore').merge(
            product_to_cat, on='product_name', how='left'
        )
        
        cat_forecast = forecast_df.groupby(['date', 'category'])[TARGET_COL].sum().reset_index()
        cat_forecast.to_csv(os.path.join(FORECASTS_DIR, f'forecast_xgb_{horizon}d.csv'), index=False)
        forecasts[horizon] = cat_forecast
        
    return forecasts

def main():
    print("Starting Model Comparison Study...")
    full_df = load_data()
    train_df, test_df, split_date = split_data(full_df)
    
    print(f"Data Split Date: {split_date}")
    print(f"Train samples: {len(train_df)}, Test samples: {len(test_df)}")
    
    results_dict = {}
    metrics_dict = {}
    
    # 1. Moving Average
    ma_metrics, ma_res = run_moving_average(train_df, test_df)
    results_dict['Moving Average'] = ma_res
    metrics_dict['Moving Average'] = ma_metrics
    
    # 2. ARIMA
    arima_metrics, arima_res = run_arima(train_df, test_df)
    results_dict['ARIMA'] = arima_res
    metrics_dict['ARIMA'] = arima_metrics
    
    # 3. Prophet
    prophet_metrics, prophet_res = run_prophet(train_df, test_df)
    results_dict['Prophet'] = prophet_res
    metrics_dict['Prophet'] = prophet_metrics
    
    # 4. XGBoost
    xgb_metrics, xgb_res, xgb_model, xgb_features, df_feat, encoder = run_xgboost(train_df, test_df, full_df, split_date)
    results_dict['XGBoost'] = xgb_res
    metrics_dict['XGBoost'] = xgb_metrics
    
    # Save Metrics Table
    metrics_df = pd.DataFrame(metrics_dict).T.reset_index().rename(columns={'index': 'Model'})
    metrics_df = metrics_df[['Model', 'MAE', 'RMSE', 'MAPE', 'R2']]
    metrics_df.to_csv(os.path.join(OUTPUT_DIR, 'model_comparison.csv'), index=False)
    
    print("\nModel Comparison Results:")
    print(metrics_df.to_string(index=False))
    
    # Generate Charts
    generate_charts(results_dict, metrics_df)
    
    # Future Forecasts
    generate_future_forecasts(xgb_model, xgb_features, full_df, encoder)
    
    print("\nStudy Complete! Outputs saved to freshlync/ml_service/outputs/")

if __name__ == '__main__':
    main()
