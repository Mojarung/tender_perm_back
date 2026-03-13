"""Anomaly detection service using sklearn IsolationForest.

Model: sklearn.ensemble.IsolationForest
Configuration: contamination="auto"
"""

import logging

import numpy as np
from sklearn.ensemble import IsolationForest

from config import ISOLATION_FOREST_CONTAMINATION

logger = logging.getLogger(__name__)


class OutlierDetectionService:
    """Detects price outliers using IsolationForest."""

    def detect(self, prices: list[float]) -> dict:
        """
        Detect outliers in a list of prices.

        Args:
            prices: List of price values.

        Returns:
            {"valid_prices": [...], "outliers": [...]}
        """
        if len(prices) < 3:
            logger.info("Too few prices for outlier detection, returning all as valid")
            return {"valid_prices": prices, "outliers": []}

        # Reshape for sklearn: (n_samples, 1)
        X = np.array(prices).reshape(-1, 1)

        # Fit and predict
        model = IsolationForest(
            contamination=ISOLATION_FOREST_CONTAMINATION,
            random_state=42,
            n_estimators=100,
        )
        predictions = model.fit_predict(X)

        # -1 = outlier, 1 = inlier
        valid_prices = [p for p, pred in zip(prices, predictions) if pred == 1]
        outliers = [p for p, pred in zip(prices, predictions) if pred == -1]

        logger.info(
            f"Outlier detection: {len(valid_prices)} valid, "
            f"{len(outliers)} outliers from {len(prices)} prices"
        )

        # Safety: if all prices are marked as outliers, return original
        if not valid_prices:
            logger.warning("All prices marked as outliers, returning original list")
            return {"valid_prices": prices, "outliers": []}

        return {"valid_prices": valid_prices, "outliers": outliers}


# Singleton
outlier_service = OutlierDetectionService()
