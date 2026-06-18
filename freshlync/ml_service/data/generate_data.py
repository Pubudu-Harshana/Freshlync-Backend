import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_freshlync_data(num_rows=1000, output_filename='sample_orders.csv'):
    # Fix seeds for reproducibility
    np.random.seed(42)
    random.seed(42)
    
    # Product mapping to categories
    product_map = {
        'Tuna': 'fish',
        'Seer Fish': 'fish',
        'Chicken': 'meat',
        'Pork': 'meat',
        'Carrot': 'vegetable',
        'Beans': 'vegetable',
        'Tomato': 'vegetable',
        'Potato': 'vegetable'
    }
    products = list(product_map.keys())
    weathers = ['sunny', 'rainy', 'cloudy']
    
    # Date range
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 12, 31)
    delta_days = (end_date - start_date).days
    
    data = []
    for _ in range(num_rows):
        # Generate random date
        random_days = random.randint(0, delta_days)
        order_date = start_date + timedelta(days=random_days)
        
        # Select product
        product_name = random.choice(products)
        category = product_map[product_name]
        
        # Generate random price between 200 and 2000 LKR
        price = round(random.uniform(200.0, 2000.0), 2)
        
        # Get day of week
        day_of_week = order_date.strftime('%A')
        
        # 10% chance of holiday
        is_holiday = random.choices([0, 1], weights=[0.90, 0.10])[0]
        
        # Random weather condition
        weather_condition = random.choice(weathers)
        
        # Calculate quantity based on conditions
        # Base quantity between 10 and 130
        base_qty = random.randint(10, 130)
        bonus = 0
        
        if is_holiday == 1:
            bonus += random.randint(20, 50)  # Increase on holidays
        if weather_condition == 'rainy':
            bonus += random.randint(10, 30)  # Increase on rainy days simulating higher delivery demand
            
        quantity_sold = base_qty + bonus
        # Ensure it does not exceed 200
        quantity_sold = min(200, quantity_sold)
        
        data.append({
            'date': order_date.strftime('%Y-%m-%d'),
            'product_name': product_name,
            'category': category,
            'quantity_sold': quantity_sold,
            'price': price,
            'day_of_week': day_of_week,
            'is_holiday': is_holiday,
            'weather_condition': weather_condition
        })
        
    df = pd.DataFrame(data)
    
    # Sort chronologically
    df = df.sort_values(by='date').reset_index(drop=True)
    
    # Determine the directory of the script and save the csv there
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, output_filename)
    
    df.to_csv(output_path, index=False)
    
    # Print confirmation and sample
    print(f"✅ Successfully generated {num_rows} rows of synthetic data!")
    print(f"📂 Saved to: {output_path}\n")
    print("Preview of the first 5 rows:")
    print("-" * 60)
    print(df.head())

if __name__ == "__main__":
    generate_freshlync_data()