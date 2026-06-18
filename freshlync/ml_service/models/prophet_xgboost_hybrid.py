"""
Freshlync Demand Forecasting: Prophet + XGBoost Hybrid Model
=============================================================

A production-style hybrid forecasting system for perishable food demand:

Strategy:
1. Prophet captures seasonality, trend, and holiday effects (time-series foundation)
2. XGBoost learns residual patterns and business feature interactions
3. Prophet forecast becomes a feature for XGBoost
4. Final prediction = XGBoost output (uses Prophet as input feature)

Architecture:
- Prophet per category to model category-level seasonality
- XGBoost on individual product records with all features + Prophet forecast
- TimeSeriesSplit to prevent data leakage
- 4-model comparison: Moving Average, Prophet, XGBoost, Hybrid

Author: Freshlync ML Team
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
from datetime import timedelta
from copy import deepcopy

from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor
from prophet import Prophet
from statsmodels.tsa.arima.model import ARIMA

warnings.filterwarnings('ignore')

# ============================================================
# Configuration
# ============================================================
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_orders.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts_prophet_xgb')
os.makedirs(CHARTS_DIR, exist_ok=True)

RANDOM_STATE = 42
TEST_SIZE = 0.2
TARGET_COL = 'quantity_sold'
PROPHET_HORIZON_DAYS = 30

# ============================================================
# 1. Data Loading & Preparation
# ============================================================
def load_and_prepare_data(path=DATA_PATH):
    """
    Load raw order data and prepare time-series structure.
    Returns:
        df_raw: raw orders with date parsed
        df_cat_daily: category-level daily aggregation for Prophet
    """
    df = pd.read_csv(path)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)

    print(f'Raw orders: {df.shape[0]} rows, {df["date"].nunique()} unique days')
    print(f'Date range: {df["date"].min()} to {df["date"].max()}')
    print(f'Categories: {df["category"].unique()}')
    print(f'Products: {df["product_name"].nunique()}')

    # Category-level daily aggregation for Prophet
    cat_daily = df.groupby(['date', 'category']).agg(
        demand=('quantity_sold', 'sum'),
        price_mean=('price', 'mean'),
        orders_count=('quantity_sold', 'count')
    ).reset_index()

    # Fill missing dates per category
    all_categories = df['category'].unique()
    date_range = pd.date_range(start=df['date'].min(), end=df['date'].max(), freq='D')

    filled_dfs = []
    for cat in all_categories:
        cat_df = cat_daily[cat_daily['category'] == cat].copy()
        cat_df = cat_df.set_index('date').reindex(date_range).reset_index()
        cat_df.columns = ['date', 'category', 'demand', 'price_mean', 'orders_count']
        cat_df['category'] = cat
        cat_df['demand'] = cat_df['demand'].fillna(0)
        cat_df['price_mean'] = cat_df['price_mean'].ffill().bfill()
        cat_df['orders_count'] = cat_df['orders_count'].fillna(0)
        filled_dfs.append(cat_df)

    cat_daily_filled = pd.concat(filled_dfs, ignore_index=True)
    print(f'\nCategory daily shape: {cat_daily_filled.shape}')
    print(f'  Days per category: {cat_daily_filled.groupby("category").size().to_dict()}')

    return df, cat_daily_filled


# ============================================================
# 2. Feature Engineering Pipeline
# ============================================================
def create_time_features(df, date_col='date'):
    """Create time-based features from date column."""
    df = df.copy()
    d = pd.to_datetime(df[date_col])
    df['day_of_week'] = d.dt.dayofweek  # 0=Monday
    df['month'] = d.dt.month
    df['week_of_year'] = d.dt.isocalendar().week.astype(int)
    df['is_weekend'] = (d.dt.dayofweek >= 5).astype(int)
    df['day_of_month'] = d.dt.day
    df['quarter'] = d.dt.quarter
    return df


def create_lag_features(group_df, target_col='demand', lags=None):
    """
    Create lag features for time series.
    IMPORTANT: Must be applied per product/category after sorting by date.
    Uses shift() which naturally handles train/test boundaries.
    """
    if lags is None:
        lags = [1, 2, 7, 14]

    df = group_df.copy()
    for lag in lags:
        df[f'{target_col}_lag_{lag}'] = df[target_col].shift(lag)
    return df


def create_rolling_features(group_df, target_col='demand', windows=None):
    """
    Create rolling window statistics.
    IMPORTANT: Uses closed='left' to avoid data leakage:
    - rolling(7) means average of PREVIOUS 7 days (not including current)
    """
    if windows is None:
        windows = [7, 14]

    df = group_df.copy()
    for w in windows:
        df[f'{target_col}_rolling_mean_{w}'] = (
            df[target_col].shift(1).rolling(window=w, min_periods=max(1, w//2)).mean()
        )
        df[f'{target_col}_rolling_std_{w}'] = (
            df[target_col].shift(1).rolling(window=w, min_periods=max(1, w//2)).std()
        )
        df[f'{target_col}_rolling_min_{w}'] = (
            df[target_col].shift(1).rolling(window=w, min_periods=max(1, w//2)).min()
        )
        df[f'{target_col}_rolling_max_{w}'] = (
            df[target_col].shift(1).rolling(window=w, min_periods=max(1, w//2)).max()
        )
    return df


def build_feature_pipeline(df, target_col='quantity_sold', is_training=True):
    """
    Full feature engineering pipeline.
    - Creates time features
    - Creates lags and rolling features PER (category) group
    - Creates price-related features
    - Drops rows with NaN from lag/rolling (only first 14 days)
    """
    print(f'\n{"=" * 60}')
    print(f'Feature Engineering Pipeline')
    print(f'{"=" * 60}')

    df = df.copy()
    df = df.sort_values(['category', 'date']).reset_index(drop=True)

    # 1. Time features
    df = create_time_features(df)

    # 2. Holiday as int
    if 'is_holiday' in df.columns:
        df['is_holiday'] = df['is_holiday'].astype(int)

    # 3. Lag & Rolling features per category (using numpy to avoid groupby issues)
    for cat in df['category'].unique():
        mask = df['category'] == cat
        cat_idx = df[mask].index
        cat_vals = df.loc[cat_idx, target_col].values

        for lag in [1, 2, 7, 14]:
            shifted = np.full(len(cat_vals), np.nan)
            if lag < len(cat_vals):
                shifted[lag:] = cat_vals[:-lag]
            df.loc[cat_idx, f'{target_col}_lag_{lag}'] = shifted

        for w in [7, 14]:
            rolled_mean = np.full(len(cat_vals), np.nan)
            rolled_std = np.full(len(cat_vals), np.nan)
            rolled_min = np.full(len(cat_vals), np.nan)
            rolled_max = np.full(len(cat_vals), np.nan)

            # Shift by 1 to avoid using current value, then rolling
            shifted_1 = np.concatenate([[np.nan], cat_vals[:-1]])
            for i in range(len(cat_vals)):
                if i >= w:
                    window = shifted_1[i - w + 1:i + 1]
                    valid = window[~np.isnan(window)]
                    if len(valid) >= max(1, w // 2):
                        rolled_mean[i] = np.mean(valid)
                        rolled_std[i] = np.std(valid)
                        rolled_min[i] = np.min(valid)
                        rolled_max[i] = np.max(valid)

            df.loc[cat_idx, f'{target_col}_rolling_mean_{w}'] = rolled_mean
            df.loc[cat_idx, f'{target_col}_rolling_std_{w}'] = rolled_std
            df.loc[cat_idx, f'{target_col}_rolling_min_{w}'] = rolled_min
            df.loc[cat_idx, f'{target_col}_rolling_max_{w}'] = rolled_max

    # 4. Weather intensity features
    if 'weather_condition' in df.columns:
        # One-hot already will be done later, but add rolling weather intensity
        for cat in df['category'].unique():
            mask = df['category'] == cat
            cat_idx = df[mask].index
            weather_vals = df.loc[cat_idx, 'weather_condition'].values

            # Weather streak: count consecutive same weather days
            streak = np.ones(len(weather_vals), dtype=int)
            for i in range(1, len(weather_vals)):
                if weather_vals[i] == weather_vals[i-1]:
                    streak[i] = streak[i-1] + 1
                else:
                    streak[i] = 1
            df.loc[cat_idx, 'weather_streak'] = streak

            # Rolling rainy days count (past 7 and 14 days)
            for w in [7, 14]:
                rainy_count = np.zeros(len(weather_vals))
                for i in range(len(weather_vals)):
                    start = max(0, i - w + 1)
                    window = weather_vals[start:i+1]
                    rainy_count[i] = np.sum(np.array([v == 'rainy' for v in window]))
                df.loc[cat_idx, f'rainy_days_last_{w}'] = rainy_count

            # Binary weather flags for rolling (will be used if not one-hot)
            for condition in ['rainy', 'sunny', 'cloudy']:
                flag = np.array([v == condition for v in weather_vals], dtype=float)
                for w in [7, 14]:
                    rolling_pct = np.zeros(len(weather_vals))
                    for i in range(len(weather_vals)):
                        start = max(0, i - w + 1)
                        window = flag[start:i+1]
                        rolling_pct[i] = np.mean(window)
                    df.loc[cat_idx, f'{condition}_pct_last_{w}'] = rolling_pct

    # 5. Holiday intensity features
    if 'is_holiday' in df.columns:
        for cat in df['category'].unique():
            mask = df['category'] == cat
            cat_idx = df[mask].index
            holiday_vals = df.loc[cat_idx, 'is_holiday'].values

            # Days since last holiday
            days_since = np.full(len(holiday_vals), 999, dtype=int)
            last_holiday_idx = -1
            for i in range(len(holiday_vals)):
                if holiday_vals[i] == 1:
                    days_since[i] = 0
                    last_holiday_idx = i
                elif last_holiday_idx >= 0:
                    days_since[i] = i - last_holiday_idx
            df.loc[cat_idx, 'days_since_holiday'] = days_since

            # Days until next holiday (look forward)
            days_until = np.full(len(holiday_vals), 999, dtype=int)
            next_holiday_idx = -1
            for i in range(len(holiday_vals) - 1, -1, -1):
                if holiday_vals[i] == 1:
                    days_until[i] = 0
                    next_holiday_idx = i
                elif next_holiday_idx >= 0:
                    days_until[i] = next_holiday_idx - i
            df.loc[cat_idx, 'days_until_holiday'] = days_until

            # Holiday proximity: Gaussian-style decay from holiday
            proximity = np.zeros(len(holiday_vals))
            for i in range(len(holiday_vals)):
                if days_since[i] < 999 and days_since[i] <= 3:
                    # Post-holiday lift (0-3 days after)
                    proximity[i] = max(0, 1.0 - days_since[i] / 4.0)
                if days_until[i] < 999 and days_until[i] <= 3:
                    # Pre-holiday anticipation (0-3 days before)
                    proximity[i] = max(proximity[i], max(0, 1.0 - days_until[i] / 4.0))
            df.loc[cat_idx, 'holiday_proximity'] = proximity

            # Holiday count in past 7 and 14 days
            for w in [7, 14]:
                holiday_count = np.zeros(len(holiday_vals))
                for i in range(len(holiday_vals)):
                    start = max(0, i - w + 1)
                    window = holiday_vals[start:i+1]
                    holiday_count[i] = np.sum(window)
                df.loc[cat_idx, f'holidays_last_{w}'] = holiday_count

    # 6. Price features (relative price vs category mean)
    if 'price' in df.columns:
        cat_daily_price = df.groupby(['date', 'category'])['price'].mean().reset_index()
        cat_daily_price.columns = ['date', 'category', 'cat_avg_price']
        df = df.merge(cat_daily_price, on=['date', 'category'], how='left')
        df['price_vs_cat_avg'] = df['price'] / df['cat_avg_price'] - 1

        # Price volatility (rolling std of price)
        for cat in df['category'].unique():
            mask = df['category'] == cat
            cat_idx = df[mask].index
            price_vals = df.loc[cat_idx, 'price'].values
            for w in [7, 14]:
                price_std = np.full(len(price_vals), np.nan)
                for i in range(len(price_vals)):
                    if i >= w:
                        window = price_vals[i-w:i]
                        price_std[i] = np.std(window)
                df.loc[cat_idx, f'price_std_{w}d'] = price_std

    # 7. Drop rows with NaN from lag features
    initial_rows = len(df)
    df = df.dropna(subset=[f'{target_col}_lag_{lag}' for lag in [1, 2, 7, 14]])
    print(f'Dropped {initial_rows - len(df)} rows with NaN lags (first 14 days per category)')
    print(f'Final feature set: {len(df)} rows, {df.shape[1]} columns')

    feature_cols = [c for c in df.columns if c not in [target_col, 'date', 'product_name', 'price']]
    print(f'Feature columns ({len(feature_cols)}): {feature_cols}')

    return df, feature_cols


# ============================================================
# 3. Prophet Model (per category)
# ============================================================
def train_prophet_models(cat_daily_df):
    """
    Train Prophet model for each category.
    Prophet captures:
    - Trend (non-linear growth/decline in demand)
    - Weekly seasonality (day-of-week patterns)
    - Yearly seasonality (monthly/seasonal patterns)
    - Holiday effects

    Returns:
        prophet_models: dict of trained Prophet models per category
        prophet_forecasts: DataFrame with Prophet predictions merged
    """
    print(f'\n{"=" * 60}')
    print(f'TRAINING PROPHET MODELS (per category)')
    print(f'{"=" * 60}')

    prophet_models = {}
    all_forecasts = []

    for cat in cat_daily_df['category'].unique():
        print(f'\n  Category: {cat}')

        # Prepare Prophet data: ds (date), y (demand)
        cat_df = cat_daily_df[cat_daily_df['category'] == cat].copy()
        cat_df = cat_df.sort_values('date').reset_index(drop=True)

        prophet_df = cat_df[['date', 'demand']].rename(columns={'date': 'ds', 'demand': 'y'})

        # Add holiday regressor if available
        if 'is_holiday' in cat_df.columns:
            holiday_data = cat_df[['date', 'is_holiday']].rename(
                columns={'date': 'ds', 'is_holiday': 'holiday_flag'}
            )
        else:
            holiday_data = None

        # Configure Prophet
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode='additive',
            changepoint_prior_scale=0.05,
            seasonality_prior_scale=10.0,
            holidays_prior_scale=10.0,
            interval_width=0.95,
            uncertainty_samples=100
        )

        # Add holiday as a regressor if we have the data
        if holiday_data is not None:
            # Add is_holiday as extra regressor
            prophet_df_with_reg = prophet_df.merge(
                holiday_data, on='ds', how='left'
            )
            prophet_df_with_reg['holiday_flag'] = prophet_df_with_reg['holiday_flag'].fillna(0)
            model.add_regressor('holiday_flag')

            model.fit(prophet_df_with_reg[['ds', 'y', 'holiday_flag']])
        else:
            model.fit(prophet_df)

        # Make future DataFrame for in-sample predictions + forecast horizon
        future = model.make_future_dataframe(periods=PROPHET_HORIZON_DAYS)

        if holiday_data is not None:
            # Extend holiday flag for future periods (assume no holiday)
            last_date = prophet_df['ds'].max()
            future_dates = pd.date_range(
                start=prophet_df['ds'].min(),
                end=last_date + timedelta(days=PROPHET_HORIZON_DAYS),
                freq='D'
            )
            future_holiday = pd.DataFrame({'ds': future_dates})
            future_holiday = future_holiday.merge(holiday_data, on='ds', how='left')
            future_holiday['holiday_flag'] = future_holiday['holiday_flag'].fillna(0)
            future = future_holiday

        forecast = model.predict(future)

        # Store only in-sample predictions (for merging back)
        forecast_in = forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper',
                                'trend', 'weekly', 'yearly']].copy()
        forecast_in['category'] = cat

        # Only keep dates that exist in training data for evaluation
        forecast_in = forecast_in.merge(
            prophet_df[['ds']], on='ds', how='inner'
        )

        all_forecasts.append(forecast_in)
        prophet_models[cat] = model

        # Evaluate Prophet fit
        merged = forecast_in.merge(prophet_df, on='ds')
        mae = mean_absolute_error(merged['y'], merged['yhat'])
        rmse = np.sqrt(mean_squared_error(merged['y'], merged['yhat']))
        mape = np.mean(np.abs((merged['y'] - merged['yhat']) / (merged['y'] + 1e-8))) * 100
        print(f'    Prophet fit - MAE: {mae:.2f}, RMSE: {rmse:.2f}, MAPE: {mape:.1f}%')

    prophet_forecast = pd.concat(all_forecasts, ignore_index=True)
    prophet_forecast = prophet_forecast.rename(columns={'ds': 'date'})
    prophet_forecast['date'] = pd.to_datetime(prophet_forecast['date'])

    print(f'\n  Total Prophet forecasts: {len(prophet_forecast)}')
    print(f'  Prophet features: yhat (forecast), trend, weekly, yearly')

    return prophet_models, prophet_forecast


# ============================================================
# 4. Hybrid Model: XGBoost with Prophet Features
# ============================================================
def prepare_hybrid_data(df_raw, prophet_forecast, feature_cols):
    """
    Merge Prophet forecasts into the feature set for XGBoost.
    The Prophet forecast ('yhat') becomes a feature.
    """
    print(f'\n{"=" * 60}')
    print(f'PREPARING HYBRID DATA (Prophet → XGBoost)')
    print(f'{"=" * 60}')

    # Merge Prophet forecast into main data
    prophet_feats = prophet_forecast[['date', 'category', 'yhat', 'trend', 'weekly', 'yearly']].copy()

    df = df_raw.merge(prophet_feats, on=['date', 'category'], how='left')

    # Handle missing prophet features (shouldn't happen for training data)
    print(f'  Missing prophet forecasts: {df["yhat"].isna().sum()} rows')
    df['yhat'] = df['yhat'].fillna(df.groupby('category')['quantity_sold'].transform('mean'))
    df['trend'] = df['trend'].fillna(0)
    df['weekly'] = df['weekly'].fillna(0)
    df['yearly'] = df['yearly'].fillna(0)

    # Combine feature columns + prophet features
    hybrid_features = feature_cols + ['yhat', 'trend', 'weekly', 'yearly']
    hybrid_features = [c for c in hybrid_features if c in df.columns and c != TARGET_COL]

    print(f'  Hybrid features ({len(hybrid_features)}):')
    for f in hybrid_features:
        print(f'    - {f}')

    return df, hybrid_features


def encode_categoricals(df, cat_cols, encoder=None, keep_cols=None):
    """One-hot encode categorical columns. Returns encoded df and encoder.
    
    If keep_cols is provided, those columns are preserved in the output
    alongside the encoded columns.
    """
    if keep_cols is None:
        keep_cols = []
    
    if encoder is None:
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded = encoder.fit_transform(df[cat_cols])
        feature_names = encoder.get_feature_names_out(cat_cols)
    else:
        encoded = encoder.transform(df[cat_cols])
        feature_names = encoder.get_feature_names_out(cat_cols)

    encoded_df = pd.DataFrame(encoded, columns=feature_names, index=df.index)
    
    # Drop original cat cols but keep specified columns
    drop_cols = [c for c in cat_cols if c not in keep_cols]
    df = pd.concat([df.drop(columns=drop_cols), encoded_df], axis=1)
    return df, encoder


def time_series_train_test_split(df, date_col='date', test_size=0.2):
    """
    Time-series aware train/test split.
    No shuffling — preserves temporal order.
    Uses last test_size fraction of time as test.
    """
    df = df.sort_values(date_col).reset_index(drop=True)
    split_idx = int(len(df) * (1 - test_size))
    train = df.iloc[:split_idx].copy()
    test = df.iloc[split_idx:].copy()
    print(f'\nTime-series split: {len(train)} train, {len(test)} test')
    print(f'  Train: {train[date_col].min()} to {train[date_col].max()}')
    print(f'  Test:  {test[date_col].min()} to {test[date_col].max()}')
    return train, test, split_idx


# ============================================================
# 5. Moving Average Baseline
# ============================================================
def moving_average_baseline(train_df, test_df, target_col='quantity_sold', window=7):
    """
    Simple moving average baseline.
    For each category, predicts next day as average of last 'window' days.
    """
    print(f'\n{"=" * 60}')
    print(f'MOVING AVERAGE BASELINE (window={window})')
    print(f'{"=" * 60}')

    train_ma = train_df.copy()
    test_ma = test_df.copy()

    # Per category: compute MA on train, use last window values to predict test
    all_preds = []

    for cat in test_df['category'].unique():
        cat_train = train_df[train_df['category'] == cat].sort_values('date')
        cat_test = test_df[test_df['category'] == cat].sort_values('date')

        train_vals = cat_train[target_col].values
        test_vals = cat_test[target_col].values

        # For each test point, use last `window` values from available history
        preds = []
        history = list(train_vals)

        for i in range(len(test_vals)):
            if len(history) >= window:
                pred = np.mean(history[-window:])
            else:
                pred = np.mean(history) if history else 0
            preds.append(pred)
            history.append(test_vals[i])  # rolling update

        cat_preds = pd.DataFrame({
            'date': cat_test['date'].values,
            'category': cat,
            'actual': test_vals,
            'predicted': preds
        })
        all_preds.append(cat_preds)

    results = pd.concat(all_preds, ignore_index=True)
    mae = mean_absolute_error(results['actual'], results['predicted'])
    rmse = np.sqrt(mean_squared_error(results['actual'], results['predicted']))
    mape = np.mean(np.abs((results['actual'] - results['predicted']) / (results['actual'] + 1e-8))) * 100

    print(f'  MAE:  {mae:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAPE: {mape:.1f}%')

    return {
        'predictions': results,
        'mae': mae,
        'rmse': rmse,
        'mape': mape
    }


# ============================================================
# 6. Train Models
# ============================================================
def train_arima(train_df, test_df, target_col='quantity_sold'):
    """
    ARIMA baseline model: Auto-Regressive Integrated Moving Average.
    Trained per category on daily aggregated demand.
    Uses a fixed (p,d,q) order for simplicity: (2,1,2) with weekly seasonality.
    """
    print(f'\n{"=" * 60}')
    print(f'ARIMA BASELINE MODEL')
    print(f'{"=" * 60}')

    all_preds = []

    for cat in train_df['category'].unique():
        print(f'\n  Category: {cat}')

        cat_train = train_df[train_df['category'] == cat].sort_values('date')
        cat_test = test_df[test_df['category'] == cat].sort_values('date')

        # Aggregate to daily
        daily_train = cat_train.groupby('date')[target_col].sum().reset_index()
        daily_train = daily_train.set_index('date').asfreq('D')
        daily_train['y'] = daily_train[target_col].fillna(0)

        daily_test = cat_test.groupby('date')[target_col].sum().reset_index()
        daily_test = daily_test.set_index('date').asfreq('D')
        daily_test['y'] = daily_test[target_col].fillna(0)

        test_dates = daily_test.index.values

        try:
            # Fit ARIMA model
            # Using (2,1,2) order - differencing=1 to handle trend, AR=2, MA=2
            model = ARIMA(daily_train['y'], order=(2, 1, 2))
            fitted_model = model.fit()

            # Forecast for test period
            n_steps = len(daily_test)
            forecast = fitted_model.forecast(steps=n_steps)
            forecast_values = forecast.values

            if len(forecast_values) < len(test_dates):
                forecast_values = np.pad(forecast_values, 
                    (0, len(test_dates) - len(forecast_values)), 'edge')

        except Exception as e:
            print(f'    ARIMA failed for {cat}: {e}')
            # Fallback: use last known value
            forecast_values = np.full(len(test_dates), daily_train['y'].iloc[-1])

        test_actual = daily_test['y'].values[:len(forecast_values)]
        forecast_values = forecast_values[:len(test_actual)]

        cat_preds = pd.DataFrame({
            'date': test_dates[:len(test_actual)],
            'category': cat,
            'actual': test_actual,
            'predicted': forecast_values
        })
        all_preds.append(cat_preds)

    results = pd.concat(all_preds, ignore_index=True)
    mae = mean_absolute_error(results['actual'], results['predicted'])
    rmse = np.sqrt(mean_squared_error(results['actual'], results['predicted']))
    mape = np.mean(np.abs((results['actual'] - results['predicted']) / (results['actual'] + 1e-8))) * 100

    print(f'\n  Overall ARIMA:')
    print(f'  MAE:  {mae:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAPE: {mape:.1f}%')

    return {
        'predictions': results,
        'mae': mae,
        'rmse': rmse,
        'mape': mape
    }


def train_prophet_only(train_df, test_df, target_col='quantity_sold'):
    """
    Prophet-only model: use Prophet forecasts directly.
    Trained per category on training data, predicts test period.
    """
    print(f'\n{"=" * 60}')
    print(f'PROPHET-ONLY MODEL')
    print(f'{"=" * 60}')

    all_preds = []

    for cat in train_df['category'].unique():
        print(f'\n  Category: {cat}')

        # Prepare training data for Prophet
        cat_train = train_df[train_df['category'] == cat].sort_values('date')
        cat_test = test_df[test_df['category'] == cat].sort_values('date')

        # Aggregate to daily (Prophet needs daily series)
        daily_train = cat_train.groupby('date')[target_col].sum().reset_index()
        daily_train.columns = ['ds', 'y']

        daily_test = cat_test.groupby('date')[target_col].sum().reset_index()
        daily_test.columns = ['ds', 'y']
        daily_test_dates = daily_test['ds'].values

        # Train Prophet
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode='additive',
            changepoint_prior_scale=0.05,
            interval_width=0.95
        )

        # Add holiday regressor
        cat_holiday = cat_train[['date', 'is_holiday']].drop_duplicates('date')
        if len(cat_holiday) > 0:
            prophet_df = daily_train.merge(
                cat_holiday.rename(columns={'date': 'ds'}), on='ds', how='left'
            )
            prophet_df['is_holiday'] = prophet_df['is_holiday'].fillna(0)
            model.add_regressor('is_holiday')
            model.fit(prophet_df[['ds', 'y', 'is_holiday']])

            # Future: all test dates
            future = pd.DataFrame({'ds': pd.date_range(
                start=daily_train['ds'].min(),
                end=daily_test['ds'].max(),
                freq='D'
            )})
            future = future.merge(
                cat_holiday.rename(columns={'date': 'ds'}), on='ds', how='left'
            )
            future['is_holiday'] = future['is_holiday'].fillna(0)
        else:
            model.fit(daily_train[['ds', 'y']])
            future = model.make_future_dataframe(
                periods=len(daily_test)
            )

        forecast = model.predict(future)

        # Extract test period forecasts
        test_forecast = forecast[forecast['ds'].isin(pd.DatetimeIndex(daily_test_dates))]
        test_actual = daily_test.set_index('ds').reindex(
            pd.DatetimeIndex(daily_test_dates)
        )['y'].values

        forecast_values = test_forecast['yhat'].values[:len(test_actual)]

        cat_preds = pd.DataFrame({
            'date': daily_test_dates,
            'category': cat,
            'actual': test_actual,
            'predicted': forecast_values
        })
        all_preds.append(cat_preds)

    results = pd.concat(all_preds, ignore_index=True)
    mae = mean_absolute_error(results['actual'], results['predicted'])
    rmse = np.sqrt(mean_squared_error(results['actual'], results['predicted']))
    mape = np.mean(np.abs((results['actual'] - results['predicted']) / (results['actual'] + 1e-8))) * 100

    print(f'\n  Overall Prophet-Only:')
    print(f'  MAE:  {mae:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAPE: {mape:.1f}%')

    return {
        'predictions': results,
        'mae': mae,
        'rmse': rmse,
        'mape': mape
    }


def train_xgboost_only(train_df, test_df, feature_cols, target_col='quantity_sold'):
    """
    XGBoost-only model: no Prophet features.
    Uses only engineered features (lags, rolling, time, categorical).
    """
    print(f'\n{"=" * 60}')
    print(f'XGBoost-ONLY MODEL')
    print(f'{"=" * 60}')

    # Prepare data (ensure feature cols exist)
    xgb_features = [c for c in feature_cols if c in train_df.columns and c != target_col]

    X_train = train_df[xgb_features].values
    y_train = train_df[target_col].values
    X_test = test_df[xgb_features].values
    y_test = test_df[target_col].values

    print(f'  X_train shape: {X_train.shape}')
    print(f'  X_test shape:  {X_test.shape}')

    # Train XGBoost with TimeSeriesSplit for validation
    tscv = TimeSeriesSplit(n_splits=3)
    val_scores = []

    for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
        X_tr_fold, X_val_fold = X_train[tr_idx], X_train[val_idx]
        y_tr_fold, y_val_fold = y_train[tr_idx], y_train[val_idx]

        model = XGBRegressor(
            n_estimators=300,
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
        val_scores.append(rmse)
        print(f'  Fold {fold+1} validation RMSE: {rmse:.2f}')

    print(f'  Mean CV RMSE: {np.mean(val_scores):.2f}')

    # Retrain on full training set
    final_model = XGBRegressor(
        n_estimators=300,
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

    # Predict on test
    y_pred = final_model.predict(X_test)

    results = pd.DataFrame({
        'actual': y_test,
        'predicted': y_pred,
        'category': test_df['category'].values,
        'date': test_df['date'].values
    })

    mae = mean_absolute_error(results['actual'], results['predicted'])
    rmse = np.sqrt(mean_squared_error(results['actual'], results['predicted']))
    mape = np.mean(np.abs((results['actual'] - results['predicted']) / (results['actual'] + 1e-8))) * 100

    print(f'\n  XGBoost-Only Test:')
    print(f'  MAE:  {mae:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAPE: {mape:.1f}%')

    return {
        'model': final_model,
        'predictions': results,
        'mae': mae,
        'rmse': rmse,
        'mape': mape,
        'feature_importance': dict(zip(xgb_features, final_model.feature_importances_))
    }


def train_hybrid(train_df, test_df, hybrid_features, target_col='quantity_sold'):
    """
    Hybrid model: XGBoost trained with Prophet forecast as a feature.
    Prophet captures seasonality/trend; XGBoost learns residuals + business effects.
    """
    print(f'\n{"=" * 60}')
    print(f'HYBRID MODEL (Prophet + XGBoost)')
    print(f'{"=" * 60}')

    # Use only hybrid features that exist
    hybrid_feats = [c for c in hybrid_features if c in train_df.columns and c != target_col]

    X_train = train_df[hybrid_feats].values
    y_train = train_df[target_col].values
    X_test = test_df[hybrid_feats].values
    y_test = test_df[target_col].values

    print(f'  X_train shape: {X_train.shape}')
    print(f'  X_test shape:  {X_test.shape}')
    print(f'  Features include Prophet: {"yhat" in hybrid_feats}')

    # TimeSeriesSplit validation
    tscv = TimeSeriesSplit(n_splits=3)
    val_scores = []

    for fold, (tr_idx, val_idx) in enumerate(tscv.split(X_train)):
        X_tr_fold, X_val_fold = X_train[tr_idx], X_train[val_idx]
        y_tr_fold, y_val_fold = y_train[tr_idx], y_train[val_idx]

        model = XGBRegressor(
            n_estimators=300,
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
        val_scores.append(rmse)
        print(f'  Fold {fold+1} validation RMSE: {rmse:.2f}')

    print(f'  Mean CV RMSE: {np.mean(val_scores):.2f}')

    # Retrain on full training set
    final_model = XGBRegressor(
        n_estimators=300,
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

    # Predict on test
    y_pred = final_model.predict(X_test)

    results = pd.DataFrame({
        'actual': y_test,
        'predicted': y_pred,
        'category': test_df['category'].values,
        'date': test_df['date'].values
    })

    mae = mean_absolute_error(results['actual'], results['predicted'])
    rmse = np.sqrt(mean_squared_error(results['actual'], results['predicted']))
    mape = np.mean(np.abs((results['actual'] - results['predicted']) / (results['actual'] + 1e-8))) * 100

    print(f'\n  Hybrid Model Test:')
    print(f'  MAE:  {mae:.2f}')
    print(f'  RMSE: {rmse:.2f}')
    print(f'  MAPE: {mape:.1f}%')

    return {
        'model': final_model,
        'predictions': results,
        'mae': mae,
        'rmse': rmse,
        'mape': mape,
        'feature_importance': dict(zip(hybrid_feats, final_model.feature_importances_))
    }


# ============================================================
# 7. Evaluation & Visualization
# ============================================================
def plot_forecast_comparison(all_predictions, filename, description):
    """
    Plot actual vs predicted for all 4 models.
    One plot per category.
    """
    categories = all_predictions['MA']['predictions']['category'].unique()
    fig, axes = plt.subplots(len(categories), 1, figsize=(14, 5 * len(categories)))
    if len(categories) == 1:
        axes = [axes]

    colors = {'MA': '#E74C3C', 'Prophet': '#3498DB', 'XGBoost': '#2ECC71', 'Hybrid': '#9B59B6'}

    for idx, cat in enumerate(categories):
        ax = axes[idx]

        for model_name, model_data in all_predictions.items():
            cat_preds = model_data['predictions']
            cat_data = cat_preds[cat_preds['category'] == cat].sort_values('date')

            if 'actual' in cat_data.columns:
                if idx == 0:
                    ax.plot(cat_data['date'], cat_data['actual'],
                            color='black', linewidth=2, alpha=0.8, label='Actual', zorder=5)
                ax.plot(cat_data['date'], cat_data['predicted'],
                        color=colors[model_name], linewidth=1.5, alpha=0.7,
                        label=f'{model_name} (RMSE: {model_data["rmse"]:.1f})')

        ax.set_title(f'{cat.capitalize()} - Forecast Comparison', fontsize=13, fontweight='bold')
        ax.set_ylabel('Demand (quantity_sold)', fontsize=11)
        ax.legend(loc='upper left', fontsize=8)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_error_heatmap(all_predictions, filename, description):
    """
    Heatmap of errors by model and category.
    """
    models_list = ['MA', 'Prophet', 'XGBoost', 'Hybrid']
    categories = all_predictions['MA']['predictions']['category'].unique()

    error_data = []
    for model in models_list:
        cat_preds = all_predictions[model]['predictions']
        for cat in categories:
            cat_data = cat_preds[cat_preds['category'] == cat]
            if len(cat_data) > 0:
                rmse = np.sqrt(mean_squared_error(cat_data['actual'], cat_data['predicted']))
                error_data.append({'Model': model, 'Category': cat, 'RMSE': rmse})

    error_df = pd.DataFrame(error_data)
    pivot = error_df.pivot(index='Model', columns='Category', values='RMSE')

    plt.figure(figsize=(10, 6))
    sns.heatmap(pivot, annot=True, fmt='.1f', cmap='YlOrRd', cbar_kws={'label': 'RMSE'})
    plt.title('Model RMSE by Category', fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_feature_importance(feat_imp_dict, model_name, filename, description, top_n=15):
    """Plot feature importance for XGBoost models."""
    importances = pd.DataFrame(
        list(feat_imp_dict.items()),
        columns=['Feature', 'Importance']
    ).sort_values('Importance', ascending=False).head(top_n)

    plt.figure(figsize=(10, 6))
    colors = ['teal' if imp > 0.02 else 'slategray' for imp in importances['Importance']]
    plt.barh(importances['Feature'], importances['Importance'], color=colors, edgecolor='black')
    plt.title(f'Top {top_n} Feature Importances ({model_name})', fontsize=13, fontweight='bold')
    plt.xlabel('Importance Score', fontsize=11)
    plt.gca().invert_yaxis()
    plt.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


def plot_residual_analysis(all_predictions, filename, description):
    """
    Residual analysis for all models: distribution + Q-Q style.
    """
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    models_list = ['MA', 'Prophet', 'XGBoost', 'Hybrid']
    colors_list = ['#E74C3C', '#3498DB', '#2ECC71', '#9B59B6']

    for idx, model in enumerate(models_list):
        ax = axes[idx]
        preds = all_predictions[model]['predictions']
        residuals = preds['actual'] - preds['predicted']

        ax.hist(residuals, bins=30, color=colors_list[idx], edgecolor='black', alpha=0.7)
        ax.axvline(x=0, color='red', linestyle='--', linewidth=2)
        ax.set_title(f'{model} - Residual Distribution\n(RMSE: {all_predictions[model]["rmse"]:.1f})',
                     fontsize=11, fontweight='bold')
        ax.set_xlabel('Residual (Actual - Predicted)', fontsize=10)
        ax.set_ylabel('Frequency', fontsize=10)
        ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(CHARTS_DIR, filename), dpi=100)
    plt.close()
    print(f'  Saved: {filename} | {description}')


# ============================================================
# 8. Full Pipeline
# ============================================================
def run_pipeline():
    """Execute full Prophet + XGBoost hybrid pipeline."""
    print('=' * 70)
    print('Freshlync Demand Forecasting: Prophet + XGBoost Hybrid')
    print('Predicting daily product demand for perishable food items')
    print('=' * 70)

    # --- Step 1: Load data ---
    print('\n' + '=' * 70)
    print('STEP 1: LOAD & PREPARE DATA')
    print('=' * 70)
    df_raw, cat_daily = load_and_prepare_data()

    # --- Step 2: Feature Engineering ---
    print('\n' + '=' * 70)
    print('STEP 2: FEATURE ENGINEERING')
    print('=' * 70)
    df_feat, base_feature_cols = build_feature_pipeline(df_raw)

    # --- Step 3: Train Prophet models ---
    print('\n' + '=' * 70)
    print('STEP 3: PROPHET MODEL TRAINING (per category)')
    print('=' * 70)
    prophet_models, prophet_forecast = train_prophet_models(cat_daily)

    # --- Step 4: Prepare Hybrid Data ---
    print('\n' + '=' * 70)
    print('STEP 4: PREPARE HYBRID DATA')
    print('=' * 70)
    df_hybrid, hybrid_features = prepare_hybrid_data(
        df_feat, prophet_forecast, base_feature_cols
    )

    # --- Step 5: Time-Series Train/Test Split (on non-encoded data for baselines) ---
    print('\n' + '=' * 70)
    print('STEP 5: TIME-SERIES TRAIN/TEST SPLIT')
    print('=' * 70)

    # Split before encoding so category column is available for baselines
    train_raw, test_raw, split_idx = time_series_train_test_split(df_hybrid)

    # --- Step 6: Baseline Models ---
    print('\n' + '=' * 70)
    print('STEP 6: BASELINE MODELS')
    print('=' * 70)
    ma_results = moving_average_baseline(train_raw, test_raw)
    prophet_results = train_prophet_only(train_raw, test_raw)
    arima_results = train_arima(train_raw, test_raw)

    # --- Step 7: Encode categoricals for XGBoost ---
    print('\n' + '=' * 70)
    print('STEP 7: ENCODE CATEGORICALS FOR XGBoost')
    print('=' * 70)

    cat_cols = ['product_name', 'category', 'day_of_week', 'weather_condition',
                'supplier_id'] if 'supplier_id' in df_hybrid.columns else \
               ['product_name', 'category', 'day_of_week', 'weather_condition']

    existing_cat_cols = [c for c in cat_cols if c in df_hybrid.columns]

    # Keep category and date columns for evaluation
    keep_cols = ['category', 'date']

    # Encode training and test sets separately
    train_encoded, encoder = encode_categoricals(train_raw, existing_cat_cols, keep_cols=keep_cols)
    test_encoded, _ = encode_categoricals(test_raw, existing_cat_cols, encoder, keep_cols=keep_cols)

    # Update feature lists after encoding
    encoded_base_feats = [c for c in base_feature_cols if c not in existing_cat_cols]
    encoded_base_feats += list(encoder.get_feature_names_out(existing_cat_cols))
    encoded_base_feats = [c for c in encoded_base_feats if c in train_encoded.columns]

    encoded_hybrid_feats = [c for c in hybrid_features if c not in existing_cat_cols]
    encoded_hybrid_feats += list(encoder.get_feature_names_out(existing_cat_cols))
    encoded_hybrid_feats = [c for c in encoded_hybrid_feats if c in train_encoded.columns]

    # Remove target from features
    base_feat = [c for c in encoded_base_feats if c != TARGET_COL]
    hybrid_feat = [c for c in encoded_hybrid_feats if c != TARGET_COL]

    print(f'  Base features: {len(base_feat)}')
    print(f'  Hybrid features: {len(hybrid_feat)}')

    # --- Step 8: XGBoost Models ---
    print('\n' + '=' * 70)
    print('STEP 8: XGBoOST MODEL TRAINING')
    print('=' * 70)

    # 8c. XGBoost-Only
    xgb_results = train_xgboost_only(train_encoded, test_encoded, base_feat)

    # 8d. Hybrid (Prophet + XGBoost)
    hybrid_results = train_hybrid(train_encoded, test_encoded, hybrid_feat)

    # --- Step 7: Comparison Summary ---
    print('\n' + '=' * 70)
    print('STEP 7: FINAL COMPARISON')
    print('=' * 70)

    comparison = pd.DataFrame({
        'Model': ['Moving Average (7d)', 'ARIMA (2,1,2)', 'Prophet Only', 
                  'XGBoost Only', 'Hybrid (Prophet + XGBoost)'],
        'MAE': [ma_results['mae'], arima_results['mae'], prophet_results['mae'],
                xgb_results['mae'], hybrid_results['mae']],
        'RMSE': [ma_results['rmse'], arima_results['rmse'], prophet_results['rmse'],
                 xgb_results['rmse'], hybrid_results['rmse']],
        'MAPE (%)': [ma_results['mape'], arima_results['mape'], prophet_results['mape'],
                     xgb_results['mape'], hybrid_results['mape']],
    })

    print('\n' + '-' * 70)
    print('MODEL PERFORMANCE COMPARISON')
    print('   (Lower MAE/RMSE/MAPE = Better)')
    print('-' * 70)
    print(comparison.to_string(index=False, float_format=lambda x: f'{x:.2f}'))
    print('-' * 70)

    # Calculate improvements over baseline
    baseline_rmse = comparison.loc[0, 'RMSE']
    print('\nImprovement over Moving Average Baseline:')
    for i in range(1, len(comparison)):
        imp = (baseline_rmse - comparison.loc[i, 'RMSE']) / baseline_rmse * 100
        print(f'  {comparison.loc[i, "Model"]}: {imp:+.1f}% RMSE change')

    # --- Step 8: Generate Charts ---
    print('\n' + '=' * 70)
    print('STEP 8: GENERATING CHARTS')
    print('=' * 70)

    all_predictions = {
        'MA': ma_results,
        'Prophet': prophet_results,
        'XGBoost': xgb_results,
        'Hybrid': hybrid_results
    }

    plot_forecast_comparison(
        all_predictions, 'forecast_comparison.png',
        'Time-series forecast comparison across all 4 models, split by category.'
    )
    plot_error_heatmap(
        all_predictions, 'error_heatmap.png',
        'RMSE heatmap showing model performance per category.'
    )
    plot_residual_analysis(
        all_predictions, 'residual_analysis.png',
        'Residual distribution analysis for all 4 models.'
    )

    # Feature importance for XGBoost models
    if 'feature_importance' in xgb_results:
        plot_feature_importance(
            xgb_results['feature_importance'], 'XGBoost Only',
            'xgb_feature_importance.png',
            'Top features driving XGBoost-only predictions.'
        )
    if 'feature_importance' in hybrid_results:
        plot_feature_importance(
            hybrid_results['feature_importance'], 'Hybrid (Prophet + XGBoost)',
            'hybrid_feature_importance.png',
            'Top features including Prophet forecast contribution.'
        )

    # Prophet component plots (with fallback for API compatibility)
    print('\n  -- Prophet Component Plots --')
    for cat, model in prophet_models.items():
        try:
            future_comp = model.make_future_dataframe(periods=30)
            fig = model.plot_components(future_comp)
            fig.suptitle(f'Prophet Components: {cat.capitalize()}', fontsize=13, fontweight='bold')
            fig.savefig(os.path.join(CHARTS_DIR, f'prophet_components_{cat}.png'), dpi=100, bbox_inches='tight')
            plt.close()
            print(f'  Saved: prophet_components_{cat}.png')
        except Exception as e:
            print(f'  (Skipped component plot for {cat}: {e})')

    # --- Step 9: Save Results ---
    print('\n' + '=' * 70)
    print('STEP 9: SAVING RESULTS')
    print('=' * 70)

    comparison.to_csv(os.path.join(OUTPUT_DIR, 'prophet_xgb_comparison.csv'), index=False)

    # Save detailed predictions
    for model_name, model_data in all_predictions.items():
        model_data['predictions'].to_csv(
            os.path.join(OUTPUT_DIR, f'predictions_{model_name.lower().replace(" ", "_")}.csv'),
            index=False
        )

    # --- Step 10: Conclusion ---
    print('\n' + '=' * 70)
    print('CONCLUSION & ANALYSIS')
    print('=' * 70)

    winner = comparison.loc[comparison['RMSE'].idxmin()]
    prophet_contribution = None
    if 'feature_importance' in hybrid_results:
        prophet_contribution = hybrid_results['feature_importance'].get('yhat', 0)

    conclusion = f"""
PROPHET + XGBoost HYBRID FORECASTING - RESULTS
=================================================

HYBRID STRATEGY EXPLANATION
---------------------------
Prophet captures the time-series foundation:
  • Trend: Long-term demand direction per category
  • Weekly seasonality: Day-of-week purchasing patterns
  • Yearly seasonality: Seasonal food demand cycles
  • Holiday effects: Known holiday impacts (via regressor)

XGBoost learns what Prophet cannot:
  • Residual patterns: Corrects Prophet's systematic errors
  • Lag effects: Recent sales momentum and trends (t-1, t-2, t-7, t-14)
  • Rolling statistics: 7d/14d mean, std, min, max of demand
  • Price features: Category avg price, price deviation, price volatility
  • Weather intensity: Weather streak, rainy day counts, weather condition % (7d/14d)
  • Holiday intensity: Days since/until holiday, holiday proximity (pre/post 3-day window),
    holiday count in past 7/14 days
  • Business features: Price effects, product-category interactions

Final prediction = XGBoost(engineered_features + Prophet_forecast)

KEY RESULTS
-----------
                              MAE          RMSE         MAPE(%)
{comparison.to_string(index=False, float_format=lambda x: f'{x:.2f}')}

BEST MODEL: {winner['Model']} (RMSE: {winner['RMSE']:.2f})

MODEL INTERPRETATION
--------------------
1. Moving Average Baseline:
   Simple last-7-days average. Often surprisingly competitive for
   perishable goods with stable demand patterns.

2. Prophet Only:
   Strong on capturing weekly patterns and holiday spikes. May struggle
   with product-level granularity and business factor interactions.

3. XGBoost Only:
   Powerful for tabular features (lags, price, product features) but
   lacks explicit seasonality modeling. Can overfit to noise.

4. Hybrid (Prophet + XGBoost):
   Best of both worlds: Prophet provides seasonality/trend foundation,
   XGBoost refines with business features and lag dynamics.
   """

    if prophet_contribution is not None:
        conclusion += f"""
PROPHET FEATURE IMPORTANCE IN HYBRID
-------------------------------------
Prophet forecast (yhat) importance in XGBoost: {prophet_contribution:.4f}
{'→ High: Prophet strongly influences the final prediction.' if prophet_contribution > 0.05
 else '→ Moderate: Prophet provides useful but secondary signal.' if prophet_contribution > 0.01
 else '→ Low: XGBoost relies more on engineered features than Prophet.'}
"""

    deploy_model_name = winner['Model']
    if deploy_model_name == 'Hybrid (Prophet + XGBoost)':
        deploy_text = 'Deploy the Hybrid model'
        hybrid_value_text = 'The hybrid approach successfully combines Prophet\'s seasonality knowledge with XGBoost\'s feature learning capability.'
    else:
        deploy_text = f'Deploy {deploy_model_name}'
        hybrid_value_text = 'Consider adding more features to improve the hybrid approach further.'

    conclusion += f"""
CHARTS GENERATED
----------------
1. forecast_comparison.png          - Actual vs predicted for all models (per category)
2. error_heatmap.png               - RMSE heatmap by model × category
3. residual_analysis.png            - Residual distributions for all 4 models
4. xgb_feature_importance.png      - XGBoost-only feature importance
5. hybrid_feature_importance.png   - Hybrid model feature importance (includes Prophet)
6. prophet_components_*.png         - Prophet decomposition per category (trend, weekly, yearly)

RECOMMENDATIONS
---------------
- {deploy_text}
  as the primary demand forecasting model.
- {hybrid_value_text}
- Monitor forecast accuracy weekly and retrain monthly as new data arrives.
- Add price elasticity and promotion features to improve accuracy.
- Consider separate models for high-volume vs. low-volume products.
"""
    print(conclusion)

    with open(os.path.join(OUTPUT_DIR, 'prophet_xgb_conclusion.txt'), 'w', encoding='utf-8') as f:
        f.write(conclusion.strip())

    print(f'\nAll outputs saved to: {OUTPUT_DIR}')
    print(f'  - Charts:      {CHARTS_DIR}/')
    print(f'  - Comparison:  prophet_xgb_comparison.csv')
    print(f'  - Predictions: predictions_*.csv (4 models)')
    print(f'  - Conclusion:  prophet_xgb_conclusion.txt')
    print(f'\nRun with: python freshlync/ml_service/models/prophet_xgboost_hybrid.py')
    print('\nDone!')

    return {
        'comparison': comparison,
        'best_model': winner['Model'],
        'results': {
            'MA': {'rmse': ma_results['rmse'], 'mae': ma_results['mae'], 'mape': ma_results['mape']},
            'Prophet': {'rmse': prophet_results['rmse'], 'mae': prophet_results['mae'], 'mape': prophet_results['mape']},
            'XGBoost': {'rmse': xgb_results['rmse'], 'mae': xgb_results['mae'], 'mape': xgb_results['mape']},
            'Hybrid': {'rmse': hybrid_results['rmse'], 'mae': hybrid_results['mae'], 'mape': hybrid_results['mape']},
        }
    }


if __name__ == '__main__':
    results = run_pipeline()