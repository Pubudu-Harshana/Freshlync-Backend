# Freshlync ML Model Evaluation Report (2,000 Rows with Patterns)

This report summarizes the performance metrics, evaluation tables, and generated visualizations for the machine learning models trained on the updated dataset of **2,000 synthetic transaction records** incorporating realistic price and demand patterns.

---

## 1. Multi-Output XGBoost Performance

The script [xgboost_model.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/xgboost_model.py) trains models to predict both `quantity_sold` and `price` simultaneously.

### Performance Table

| Model Variant | Test RMSE (qty_sold) | Test RMSE (price) | Train $R^2$ | Test $R^2$ |
| :--- | :---: | :---: | :---: | :---: |
| **Linear Regression (Baseline)** | 13.38 | 232.01 | 0.9126 | 0.9147 |
| **XGBoost (Default)** | 11.27 | 243.76 | 0.9387 | 0.9191 |
| **XGBoost (Tuned)** | **12.49** | **232.39** | **0.9230** | **0.9189** |

---

## 2. Hybrid & Ensemble Models Performance

The script [xgboost_hybrid_model.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/xgboost_hybrid_model.py) implements stacked and blended ensembles combining XGBoost, Random Forest, and Linear Regression.

### Performance Table

| Model | Test RMSE (qty) | Test RMSE (price) | Test $R^2$ |
| :--- | :---: | :---: | :---: |
| **MultiOutput XGBoost (Baseline)** | 11.05 | 242.67 | 0.9205 |
| **XGBoost (qty) + LR (price) Hybrid** | 11.05 | 232.01 | 0.9254 |
| **Stacking Ensemble (Ridge Meta-model)** | **10.78** | **231.81** | **0.9266** |

---

## 3. Study Comparison with Lags and Rolling Features

When incorporating time-series lag and rolling statistics in [model_comparison_study.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/model_comparison_study.py), the XGBoost model achieves near-perfect fit because it learns from historical sequences:

| Model | MAE | RMSE | MAPE (%) | $R^2$ |
| :--- | :---: | :---: | :---: | :---: |
| **Moving Average** | 65.57 | 100.98 | 53.41% | 0.3813 |
| **ARIMA** | 69.42 | 103.68 | 2999.78% | 0.2551 |
| **XGBoost (with Lags)** | **6.95** | **10.20** | **7.53%** | **0.9918** |

---

## 4. Demand Forecast Summary by Category (in KG)

Here is the projected demand aggregated by category for the upcoming 7-day, 14-day, and 30-day windows:

| Category | 7-Day Forecast (kg) | 14-Day Forecast (kg) | 30-Day Forecast (kg) |
| :--- | :---: | :---: | :---: |
| **Fish** | 920.34 | 1,919.72 | 4,430.28 |
| **Meat** | 1,041.44 | 2,117.87 | 4,649.80 |
| **Vegetables** | 3,363.37 | 6,734.95 | 14,084.87 |

*Note: The forecasts were generated using the tuned XGBoost model recursively predicting out-of-sample days.*
