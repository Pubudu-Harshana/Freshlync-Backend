import sys
import json
import os
import pickle
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'outputs', 'xgboost_model.pkl')
FEATURE_COLS = ['product_name', 'category', 'day_of_week', 'is_holiday', 'weather_condition']

def main():
    try:
        # Load serialized model data
        if not os.path.exists(MODEL_PATH):
            print(json.dumps({"error": f"Model file not found at {MODEL_PATH}"}))
            sys.exit(1)
            
        with open(MODEL_PATH, 'rb') as f:
            model_data = pickle.load(f)
            
        preprocessor = model_data['preprocessor']
        model = model_data['model']
        
        # Read JSON input from stdin and decode with utf-8-sig to handle BOM
        stdin_bytes = sys.stdin.buffer.read()
        stdin_str = stdin_bytes.decode('utf-8-sig')
        input_data = json.loads(stdin_str)
        
        # Ensure all required features are present
        for col in FEATURE_COLS:
            if col not in input_data and col != 'is_holiday':
                raise ValueError(f"Missing required feature: {col}")
        
        # Normalize category
        cat = str(input_data.get('category', '')).strip().lower()
        if cat in ['vegetables', 'vegetable']:
            input_data['category'] = 'vegetable'
        elif cat in ['fish']:
            input_data['category'] = 'fish'
        elif cat in ['meat']:
            input_data['category'] = 'meat'
        elif cat in ['grains', 'grain']:
            input_data['category'] = 'grain'
        else:
            input_data['category'] = cat

        # Normalize weather_condition
        weather = str(input_data.get('weather_condition', '')).strip().lower()
        input_data['weather_condition'] = weather

        # Normalize day_of_week
        day = str(input_data.get('day_of_week', '')).strip().capitalize()
        input_data['day_of_week'] = day

        # Normalize is_holiday
        is_val = input_data.get('is_holiday', 0)
        if isinstance(is_val, bool):
            input_data['is_holiday'] = 1 if is_val else 0
        else:
            try:
                input_data['is_holiday'] = 1 if int(is_val) > 0 else 0
            except:
                input_data['is_holiday'] = 0
        
        # Convert input to DataFrame
        df_input = pd.DataFrame([input_data])[FEATURE_COLS]
        
        # Transform features
        X_processed = preprocessor.transform(df_input)
        
        # Predict
        preds = model.predict(X_processed)
        
        # Output results
        result = {
            "quantity_sold": float(preds[0][0]),
            "price": float(preds[0][1])
        }
        print(json.dumps(result))
        
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

if __name__ == '__main__':
    main()
