import numpy as np
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from api.blockchain_client import get_difficulty_history_extended


def prepare_dataset(history: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    X = np.array([item["x"] for item in history], dtype=float)
    y = np.array([item["y"] for item in history], dtype=float)
    
    # Normalize timestamps to start from 0 to prevent numerical instability
    if len(X) > 0:
        X = X - X[0]
        
    return X, y

def train_linear_regression(X: np.ndarray, y: np.ndarray) -> tuple:
    n = len(X)
    if n == 0:
        return 0.0, 0.0
        
    sum_x = np.sum(X)
    sum_y = np.sum(y)
    sum_xy = np.sum(X * y)
    sum_xx = np.sum(X * X)
    
    # Calculate denominator and avoid division by zero
    denominator = (n * sum_xx - sum_x**2)
    if denominator == 0:
        return 0.0, sum_y / n if n > 0 else 0.0
        
    slope = (n * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / n
    
    return slope, intercept

def predict_linear_regression(slope: float, intercept: float, X: np.ndarray) -> np.ndarray:
    return slope * X + intercept

def train_moving_average(y: np.ndarray, window: int = 5) -> np.ndarray:
    if len(y) < window:
        return np.copy(y)
        
    result = np.zeros_like(y)
    for i in range(len(y)):
        if i < window - 1:
            # Partial window for early elements
            result[i] = np.mean(y[:i+1])
        else:
            # Full window average
            result[i] = np.mean(y[i-window+1:i+1])
            
    return result

def evaluate_model(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred)**2)))
    
    # Avoid division by zero by replacing 0s with 1s in denominator
    safe_y_true = np.where(y_true == 0, 1, y_true)
    mape = float(np.mean(np.abs((y_true - y_pred) / safe_y_true)) * 100)
    
    return {
        "MAE": mae,
        "RMSE": rmse,
        "MAPE": mape
    }

def compare_models(metrics_lr: dict, metrics_ma: dict) -> str:
    mae_lr = metrics_lr["MAE"]
    mae_ma = metrics_ma["MAE"]
    
    if mae_lr < mae_ma:
        diff_pct = ((mae_ma - mae_lr) / mae_ma) * 100
        return f"Linear Regression performed better by {diff_pct:.2f}% based on MAE."
    elif mae_ma < mae_lr:
        diff_pct = ((mae_lr - mae_ma) / mae_lr) * 100
        return f"Moving Average performed better by {diff_pct:.2f}% based on MAE."
    else:
        return "Both models performed equally well based on MAE."

def render() -> None:
    st.header("🧠 M7 — AI Predictor")
    
    try:
        # Fetch 300 data points
        history = get_difficulty_history_extended(300)
        if not history:
            st.warning("No difficulty history available.")
            return
            
        X, y = prepare_dataset(history)
        
        # 80-20 split
        split_idx = int(len(X) * 0.8)
        X_train, y_train = X[:split_idx], y[:split_idx]
        X_test, y_test = X[split_idx:], y[split_idx:]
        
        # Train models
        slope, intercept = train_linear_regression(X_train, y_train)
        y_pred_lr = predict_linear_regression(slope, intercept, X)
        y_pred_ma = train_moving_average(y, window=5)
        
        # Evaluate on test set
        y_pred_lr_test = predict_linear_regression(slope, intercept, X_test)
        y_pred_ma_test = y_pred_ma[split_idx:]
        
        metrics_lr = evaluate_model(y_test, y_pred_lr_test)
        metrics_ma = evaluate_model(y_test, y_pred_ma_test)
        
        # KPI metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("MAE Linear Reg.", f"{metrics_lr['MAE']/1e12:.2f} T")
        col2.metric("RMSE Linear Reg.", f"{metrics_lr['RMSE']/1e12:.2f} T")
        col3.metric("MAE Moving Avg.", f"{metrics_ma['MAE']/1e12:.2f} T")
        col4.metric("RMSE Moving Avg.", f"{metrics_ma['RMSE']/1e12:.2f} T")
        
        # Plot chart
        dates = [datetime.fromtimestamp(item["x"]) for item in history]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=y/1e12, mode='lines', name='Actual Difficulty', line=dict(color='#3b82f6')))
        fig.add_trace(go.Scatter(x=dates, y=y_pred_lr/1e12, mode='lines', name='Linear Regression', line=dict(color='#f97316', dash='dash')))
        fig.add_trace(go.Scatter(x=dates, y=y_pred_ma/1e12, mode='lines', name='Moving Average', line=dict(color='#22c55e', dash='dot')))
        
        fig.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#e2e8f0"),
            xaxis_title="Date",
            yaxis_title="Difficulty (Trillions)",
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Compare models side-by-side
        st.subheader("📊 Performance Table")
        t_col1, t_col2 = st.columns(2)
        with t_col1:
            st.markdown("**Linear Regression**")
            st.write(f"MAE: {metrics_lr['MAE']:,.0f}")
            st.write(f"RMSE: {metrics_lr['RMSE']:,.0f}")
            st.write(f"MAPE: {metrics_lr['MAPE']:.2f}%")
        with t_col2:
            st.markdown("**Moving Average**")
            st.write(f"MAE: {metrics_ma['MAE']:,.0f}")
            st.write(f"RMSE: {metrics_ma['RMSE']:,.0f}")
            st.write(f"MAPE: {metrics_ma['MAPE']:.2f}%")
            
        # Summary
        summary_text = compare_models(metrics_lr, metrics_ma)
        st.info(summary_text)
        
        # Expander explanation
        with st.expander("ℹ️ M4 vs M7 Differences"):
            st.write("This M7 AI Predictor uses supervised regression and moving averages to forecast difficulty trends over time.")
            st.write("The M4 Anomaly Detector uses unsupervised isolation to find statistically unusual blocks. They solve entirely different problems.")
            
    except Exception as e:
        st.error(f"Error rendering M7 Predictor: {e}")
