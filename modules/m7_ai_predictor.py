import numpy as np

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
