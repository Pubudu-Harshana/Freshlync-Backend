import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_synthetic_data(num_rows=1000, output_path='freshlync/ml_service/data/sample_orders.csv'):
    np.random.seed(42)
    random.seed(42)
    
    categories = ['fish', 'meat', 'vegetable']
    products = {
        'fish': ['Salmon', 'Tuna', 'Cod', 'Tilapia'],
        'meat': ['Beef Steak', 'Chicken Breast', 'Pork Chops', 'Lamb'],
        'vegetable': ['Carrot', 'Broccoli', 'Spinach', 'Tomato']
    }
    weather = ['Sunny', 'Rainy', 'Cloudy', 'Snowy']
    
    start_date = datetime(2025, 1, 1)
    
    data = []
    for _ in range(num_rows):
        days_offset = random.randint(0, 365)
        order_date = start_date + timedelta(days=days_offset)
        
        category = random.choice(categories)
        product_name = random.choice(products[category])
        
        # Simulating quantity with a normal distribution
        quantity_sold = int(np.random.normal(loc=50, scale=15))
        quantity_sold = max(1, quantity_sold) # Ensure at least 1 item is sold
        
        # Determine price range based on category
        if category == 'fish':
            price = random.uniform(10.0, 25.0)
        elif category == 'meat':
            price = random.uniform(8.0, 20.0)
        else:
            price = random.uniform(1.5, 5.0)
            
        day_of_week = order_date.strftime('%A')
        # Simulate ~5% chance of being a holiday
        is_holiday = random.choices([0, 1], weights=[0.95, 0.05])[0] 
        weather_condition = random.choice(weather)
        
        data.append({
            'date': order_date.strftime('%Y-%m-%d'),
            'product_name': product_name,
            'category': category,
            'quantity_sold': quantity_sold,
            'price': round(price, 2),
            'day_of_week': day_of_week,
            'is_holiday': is_holiday,
            'weather_condition': weather_condition
        })
        
    df = pd.DataFrame(data)
    
    # Sort by date for better chronological order
    df = df.sort_values(by='date').reset_index(drop=True)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    df.to_csv(output_path, index=False)
    print(f"Generated {num_rows} rows of synthetic data at {output_path}")

if __name__ == "__main__":
    generate_synthetic_data()