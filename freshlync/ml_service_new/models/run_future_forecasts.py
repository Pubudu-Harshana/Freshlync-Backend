"""
Freshlync Demand Forecasting: Category-Level Future Forecast Generator
======================================================================

This script trains an XGBoost model on the 2,000-row synthetic orders dataset 
and recursively predicts the future quantity sold (demand) for the next 
7, 14, and 30 days. It aggregates the forecasted quantities (representing kg) 
by product categories (fish, meat, vegetable) and saves the summary CSV.
"""

import pandas as pd
import numpy as np
import os
from datetime import timedelta
from xgboost import XGBRegressor
from sklearn.preprocessing import OneHotEncoder

# Configuration
DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sample_orders.csv')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'outputs')
os.makedirs(OUTPUT_DIR, exist_ok=True)

TARGET_COL = 'quantity_sold'
RANDOM_STATE = 42

def load_data():
    df = pd.read_csv(DATA_PATH)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def create_xgboost_features(df, encoder=None):
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
    df['price_change'] = df.groupby('product_name')['price'].diff().fillna(0)
    
    # Categorical Encoding
    cat_cols = ['category', 'weather_condition']
    if 'is_holiday' in df.columns:
        df['is_holiday'] = df['is_holiday'].astype(int)
        
    if encoder is None:
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded = encoder.fit_transform(df[cat_cols])
    else:
        encoded = encoder.transform(df[cat_cols])
        
    encoded_cols = encoder.get_feature_names_out(cat_cols)
    encoded_df = pd.DataFrame(encoded, columns=encoded_cols, index=df.index)
    
    df = pd.concat([df.drop(columns=cat_cols), encoded_df], axis=1)
    
    return df, encoded_cols.tolist(), encoder

def train_and_forecast():
    print("Loading data...")
    df = load_data()
    
    print("Engineering features...")
    df_feat, encoded_cols, encoder = create_xgboost_features(df)
    df_feat = df_feat.dropna()
    
    features = [c for c in df_feat.columns if c not in [TARGET_COL, 'date', 'product_name']]
    X = df_feat[features]
    y = df_feat[TARGET_COL]
    
    print(f"Training XGBoost forecasting model on {len(X)} rows...")
    model = XGBRegressor(
        random_state=RANDOM_STATE,
        n_estimators=100,
        max_depth=6,
        learning_rate=0.01,
        subsample=0.8,
        colsample_bytree=0.6,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=2,
        verbosity=0
    )
    model.fit(X, y)
    
    last_date = df['date'].max()
    forecasts = {}
    
    print("Generating forecasts for 7, 14, and 30 days ahead...")
    for horizon in [7, 14, 30]:
        current_df = df.copy()
        
        # Iteratively predict next days
        for i in range(1, horizon + 1):
            next_date = last_date + timedelta(days=i)
            # Take last known record for each product and update date
            last_records = current_df.groupby('product_name').last().reset_index()
            last_records['date'] = next_date
            
            # Recreate features with the updated records
            temp_df = pd.concat([current_df, last_records]).reset_index(drop=True)
            temp_feat, _, _ = create_xgboost_features(temp_df, encoder=encoder)
            
            pred_day = temp_feat[temp_feat['date'] == next_date]
            if len(pred_day) > 0:
                pred_input = pred_day[features].fillna(0)
                preds = model.predict(pred_input)
                # Map predicted values to the newly added records
                last_records[TARGET_COL] = np.maximum(0, preds)  # quantities can't be negative
                
            current_df = pd.concat([current_df, last_records]).reset_index(drop=True)
            
        # Get only the future predicted records
        future_df = current_df[current_df['date'] > last_date]
        
        # Aggregate quantity sold by category
        cat_summary = future_df.groupby('category')[TARGET_COL].sum().reset_index()
        forecasts[horizon] = cat_summary

    # Display results
    print("\n" + "="*50)
    print("SUMMARY OF DEMAND FORECAST BY CATEGORY (in KG)")
    print("="*50)
    
    # Merge horizons
    summary_df = pd.DataFrame({'Category': ['fish', 'meat', 'vegetable']})
    for horizon in [7, 14, 30]:
        h_df = forecasts[horizon].rename(columns={TARGET_COL: f'{horizon}_days_forecast_kg'})
        h_df['Category'] = h_df['category']
        h_df = h_df[['Category', f'{horizon}_days_forecast_kg']]
        summary_df = summary_df.merge(h_df, on='Category', how='left')
        
    # Format values
    for col in summary_df.columns:
        if 'forecast' in col:
            summary_df[col] = summary_df[col].round(2)
            
    print(summary_df.to_string(index=False))
    
    summary_path = os.path.join(OUTPUT_DIR, 'category_forecast_summary.csv')
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSaved summary to {summary_path}")

if __name__ == '__main__':
    train_and_forecast()
