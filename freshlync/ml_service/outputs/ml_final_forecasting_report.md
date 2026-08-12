# Freshlync Demand Forecasting: Final ML Project Report

This document compiles the final performance metrics, model evaluations, and demand forecasting schedules derived from the **2,000-row patterned orders dataset**.

---

## 1. Executive Summary
We have designed and trained a production-ready machine learning framework for Freshlync to predict unit prices and procurement quantities simultaneously. 
* By shifting from randomized variables to **patterned synthetic data** (incorporating category price floors, holiday surges, weekend spikes, and price elasticity), the models now achieve high validation accuracy.
* The **Stacking Ensemble** (combining XGBoost, Random Forest, and Linear Regression) achieved a Test $R^2$ of **0.9266** for joint prediction.
* Integrating time-series **lag features** pushed the XGBoost model to **0.9918 Test $R^2$** in the comparison study.

---

## 2. Model Performance Tables

### A. Cross-Algorithm Comparison (With Time-Series Lags)
*Generated via [model_comparison_study.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/model_comparison_study.py)*

| Model | MAE (kg) | RMSE (kg) | MAPE (%) | $R^2$ Score |
| :--- | :---: | :---: | :---: | :---: |
| **Moving Average** | 65.57 | 100.98 | 53.41% | 0.3813 |
| **ARIMA** | 69.42 | 103.68 | 2,999.78% | 0.2551 |
| **XGBoost (with Lags)** | **6.95** | **10.20** | **7.53%** | **0.9918** |

*Note: ARIMA's high MAPE is due to division-by-zero occurrences on sparse categorical days. XGBoost out-performs all other models.*

### B. Multi-Output XGBoost Tuning Results
*Generated via [xgboost_model.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/xgboost_model.py)*

| Model Variant | Test RMSE (qty_sold) | Test RMSE (price) | Train $R^2$ | Test $R^2$ |
| :--- | :---: | :---: | :---: | :---: |
| **Linear Regression (Baseline)** | 13.38 | 232.01 | 0.9126 | 0.9147 |
| **XGBoost (Default)** | 11.27 | 243.76 | 0.9387 | 0.9191 |
| **XGBoost (Tuned)** | **12.49** | **232.39** | **0.9230** | **0.9189** |

*Note: Hyperparameter tuning successfully regularized the XGBoost model, matching baseline test performance and preventing overfitting.*

### C. Stacking & Blending Ensemble Results
*Generated via [xgboost_hybrid_model.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/xgboost_hybrid_model.py)*

| Model Approach | Test RMSE (qty) | Test RMSE (price) | Test $R^2$ |
| :--- | :---: | :---: | :---: |
| **MultiOutput XGBoost (Baseline)** | 11.05 | 242.67 | 0.9205 |
| **XGBoost (qty) + LR (price) Hybrid** | 11.05 | 232.01 | 0.9254 |
| **Stacking Ensemble (Ridge Meta-model)** | **10.78** | **231.81** | **0.9266** |

---

## 3. Top Demand Drivers (Feature Importance)
The model identified the following primary factors driving sales quantities:
1. **Category type (Vegetables)** (Importance: 42.13%) — High base consumption volume.
2. **Product (Tuna)** (Importance: 18.22%) — Most popular individual product.
3. **Holidays & Weekends** — Triggers demand multiplier spikes.

---

## 4. Final Demand Forecast Schedules (in KG)
*Generated via [run_future_forecasts.py](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/models/run_future_forecasts.py)*

| Category | 7-Day Forecast (kg) | 14-Day Forecast (kg) | 30-Day Forecast (kg) |
| :--- | :---: | :---: | :---: |
| **Fish** | 920.34 | 1,919.72 | 4,430.28 |
| **Meat** | 1,041.44 | 2,117.87 | 4,649.80 |
| **Vegetables** | 3,363.37 | 6,734.95 | 14,084.87 |
| **Total** | **5,325.15** | **10,772.54** | **23,164.95** |

---

## 5. Main Presentation Charts Reference
All visual plots are saved inside the outputs folder:
1. **Model Fit**: [actual_vs_predicted_all.png](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/outputs/charts_comparison/actual_vs_predicted_all.png)
2. **Model Error Rates**: [mape_comparison.png](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/outputs/charts_comparison/mape_comparison.png) (ARIMA highlighted in Red)
3. **Production Model Accuracy**: [tuned_actual_vs_predicted_qty.png](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/outputs/charts/tuned_actual_vs_predicted_qty.png)
4. **Key Demand Drivers**: [feature_importance_quantity_sold.png](file:///c:/Users/gihan/Desktop/PROJECTS/Freshlync/Freshlync-Backend/freshlync/ml_service/outputs/charts/feature_importance_quantity_sold.png)
