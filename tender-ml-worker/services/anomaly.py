from sklearn.ensemble import IsolationForest
import numpy as np

def detect_anomalies(prices: list[float]) -> tuple[list[float], list[float]]:
    """
    Detects pricing outliers using Scikit-Learn IsolationForest.
    Returns a tuple of (valid_prices, outliers).
    """
    if not prices:
        return [], []
    if len(prices) < 3:
        # Too little data to detect outliers statistically
        return prices, []
        
    X = np.array(prices).reshape(-1, 1)
    
    clf = IsolationForest(contamination="auto", random_state=42)
    predictions = clf.fit_predict(X)
    
    valid_prices = []
    outliers = []
    
    for i, pred in enumerate(predictions):
        if pred == -1:
            outliers.append(float(prices[i]))
        else:
            valid_prices.append(float(prices[i]))
            
    return valid_prices, outliers
