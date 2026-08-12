"""
Freshlync Demand Forecasting: Freshlync-specific Synthetic Data Generation
==========================================================================

This utility generates realistic synthetic transaction data tailored for the Freshlync platform.
It simulates demand factors like holidays and weather conditions (e.g., higher demand on rainy days),
assigns appropriate category mappings (fish, meat, vegetable), and generates sample order histories
used to validate the forecasting models.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
import os

def generate_freshlync_data(num_rows=2000, output_filename='sample_orders.csv'):
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
    # Category base prices
    category_prices = {
        'fish': (1200.0, 2400.0),
        'meat': (800.0, 1600.0),
        'vegetable': (100.0, 350.0)
    }
    
    # Base demand volumes per product
    product_base_demand = {
        'Tuna': 40,
        'Seer Fish': 30,
        'Chicken': 60,
        'Pork': 45,
        'Carrot': 100,
        'Beans': 80,
        'Tomato': 120,
        'Potato': 140
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
        
        # Price: specific to category
        price_min, price_max = category_prices[category]
        price = round(random.uniform(price_min, price_max), 2)
        
        # Get day of week
        day_of_week = order_date.strftime('%A')
        is_weekend = 1 if day_of_week in ['Saturday', 'Sunday'] else 0
        
        # 10% chance of holiday
        is_holiday = random.choices([0, 1], weights=[0.90, 0.10])[0]
        
        # Random weather condition
        weather_condition = random.choice(weathers)
        
        # Quantity based on patterns:
        base_qty = product_base_demand[product_name]
        
        # 1. Price elasticity effect: higher price -> lower quantity
        price_mean = (price_min + price_max) / 2
        elasticity_factor = 1.0 - 0.3 * ((price - price_mean) / price_mean)
        
        # 2. Weekend boost: +30% demand
        weekend_factor = 1.3 if is_weekend else 1.0
        
        # 3. Holiday boost: +40% demand
        holiday_factor = 1.4 if is_holiday else 1.0
        
        # 4. Weather boost: +20% demand on rainy days (home delivery)
        weather_factor = 1.2 if weather_condition == 'rainy' else 1.0
        
        # Compute quantity with some random noise (std=5)
        quantity_sold = base_qty * elasticity_factor * weekend_factor * holiday_factor * weather_factor
        quantity_sold = int(np.random.normal(loc=quantity_sold, scale=5))
        quantity_sold = max(1, quantity_sold)  # Ensure positive quantity
        
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
    print(f"Successfully generated {num_rows} rows of synthetic data!")
    print(f"Saved to: {output_path}\n")
    print("Preview of the first 5 rows:")
    print("-" * 60)
    print(df.head())

if __name__ == "__main__":
    generate_freshlync_data()