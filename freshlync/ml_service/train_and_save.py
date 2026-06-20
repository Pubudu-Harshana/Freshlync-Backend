import pandas as pd
import numpy as np
import os
import pickle
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.multioutput import MultiOutputRegressor
from xgboost import XGBRegressor

DATA_PATH = os.path.join(os.path.dirname(__file__), 'data', 'sample_orders.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), 'outputs', 'xgboost_model.pkl')
os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)

FEATURE_COLS = ['product_name', 'category', 'day_of_week', 'is_holiday', 'weather_condition']
CATEGORICAL_COLS = ['product_name', 'category', 'day_of_week', 'weather_condition']
TARGET_COLS = ['quantity_sold', 'price']

def main():
    print("Loading data...")
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"Data not found at {DATA_PATH}")
    
    df = pd.read_csv(DATA_PATH)
    
    X = df[FEATURE_COLS]
    y = df[TARGET_COLS]
    
    print("Preprocessing data...")
    # Using handle_unknown='ignore' so it won't crash when encountering new products/categories
    preprocessor = ColumnTransformer(
        transformers=[('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CATEGORICAL_COLS)],
        remainder='passthrough'
    )
    
    X_processed = preprocessor.fit_transform(X)
    
    print("Training XGBoost Multi-Output Model...")
    base_model = XGBRegressor(
        random_state=42,
        subsample=0.6,
        reg_lambda=1,
        reg_alpha=0,
        n_estimators=500,
        min_child_weight=3,
        max_depth=3,
        learning_rate=0.01,
        colsample_bytree=0.6,
        verbosity=0
    )
    model = MultiOutputRegressor(base_model)
    model.fit(X_processed, y.values)
    
    print(f"Saving preprocessor and model to {OUTPUT_PATH}...")
    model_data = {
        'preprocessor': preprocessor,
        'model': model
    }
    
    with open(OUTPUT_PATH, 'wb') as f:
        pickle.dump(model_data, f)
        
    print("Training and saving completed successfully!")

if __name__ == '__main__':
    main()
