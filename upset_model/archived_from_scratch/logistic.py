"""Logistic regression implementation from scratch.

No sklearn, pandas, or numpy - pure Python stdlib only.
"""

import math
import statistics
import json
from dataclasses import dataclass, asdict
from typing import List, Tuple, Optional


@dataclass
class LogisticModel:
    """Trained logistic regression model."""
    coefficients: List[float]  # [intercept, w1, w2, ..., wk]
    feature_names: List[str]
    feature_means: List[float]
    feature_stds: List[float]
    regularization: float
    n_iterations: int
    final_log_likelihood: float
    training_n: int
    
    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'LogisticModel':
        data = json.loads(json_str)
        return cls(**data)
    
    def save(self, path: str) -> None:
        with open(path, 'w') as f:
            f.write(self.to_json())
    
    @classmethod
    def load(cls, path: str) -> 'LogisticModel':
        with open(path) as f:
            return cls.from_json(f.read())


def sigmoid(z: float) -> float:
    """Numerically stable sigmoid function."""
    if z > 500:
        return 1.0 - 1e-15
    if z < -500:
        return 1e-15
    return 1.0 / (1.0 + math.exp(-z))


def dot_product(a: List[float], b: List[float]) -> float:
    """Dot product of two vectors."""
    return sum(ai * bi for ai, bi in zip(a, b))


def log_likelihood(X: List[List[float]], y: List[int], w: List[float]) -> float:
    """Compute log-likelihood: Σ[y log(p) + (1-y) log(1-p)]."""
    ll = 0.0
    for i, x in enumerate(X):
        z = dot_product(w, x)
        p = sigmoid(z)
        # Clip for numerical stability
        p = max(1e-15, min(1.0 - 1e-15, p))
        ll += y[i] * math.log(p) + (1 - y[i]) * math.log(1.0 - p)
    return ll


def standardize_features(X: List[List[float]]) -> Tuple[List[List[float]], List[float], List[float]]:
    """Z-score standardize features.
    
    Args:
        X: Feature matrix [n_samples][n_features] WITHOUT intercept
    
    Returns:
        (X_standardized, means, stds)
    """
    if not X:
        return [], [], []
    
    n_features = len(X[0])
    means = []
    stds = []
    
    # Compute means and stds
    for j in range(n_features):
        col = [row[j] for row in X]
        mean = statistics.mean(col)
        std = statistics.pstdev(col)
        if std < 1e-10:
            std = 1.0  # Constant feature
        means.append(mean)
        stds.append(std)
    
    # Standardize
    X_std = []
    for row in X:
        std_row = [(row[j] - means[j]) / stds[j] for j in range(n_features)]
        X_std.append(std_row)
    
    return X_std, means, stds


def add_intercept(X: List[List[float]]) -> List[List[float]]:
    """Prepend intercept column (all 1.0) to feature matrix."""
    return [[1.0] + row for row in X]


def train_logistic(
    X: List[List[float]],
    y: List[int],
    learning_rate: float = 0.01,
    max_iterations: int = 10000,
    tolerance: float = 1e-7,
    l2_lambda: float = 0.01,
    verbose: bool = False
) -> LogisticModel:
    """Train logistic regression via gradient descent.
    
    Args:
        X: Feature matrix [n][k] (raw, will be standardized)
        y: Binary labels [n]
        learning_rate: Initial learning rate
        max_iterations: Max gradient descent steps
        tolerance: Convergence threshold
        l2_lambda: L2 regularization strength
        verbose: Print progress
    
    Returns:
        Trained LogisticModel
    """
    n = len(X)
    if n == 0:
        raise ValueError("Empty training data")
    
    # Standardize features
    X_std, means, stds = standardize_features(X)
    
    # Add intercept
    X_with_intercept = add_intercept(X_std)
    
    # Initialize weights to zero
    k = len(X_with_intercept[0])
    w = [0.0] * k
    
    # Gradient descent
    prev_ll = float('-inf')
    alpha = learning_rate
    
    for iteration in range(max_iterations):
        # Compute predictions
        predictions = [sigmoid(dot_product(w, x)) for x in X_with_intercept]
        
        # Compute gradients
        gradients = [0.0] * k
        for i in range(n):
            error = y[i] - predictions[i]
            for j in range(k):
                gradients[j] += error * X_with_intercept[i][j]
        
        # Average and add L2 penalty (not on intercept)
        for j in range(k):
            gradients[j] /= n
            if j > 0:  # Don't regularize intercept
                gradients[j] -= l2_lambda * w[j]
        
        # Update weights
        for j in range(k):
            w[j] += alpha * gradients[j]
        
        # Check convergence every 10 iterations
        if iteration % 10 == 0:
            ll = log_likelihood(X_with_intercept, y, w)
            delta_ll = abs(ll - prev_ll)
            
            if verbose and iteration % 100 == 0:
                print(f"Iteration {iteration}: LL={ll:.4f}, ΔLL={delta_ll:.6f}")
            
            if delta_ll < tolerance and iteration > 50:
                if verbose:
                    print(f"Converged at iteration {iteration}")
                break
            
            prev_ll = ll
    
    final_ll = log_likelihood(X_with_intercept, y, w)
    
    return LogisticModel(
        coefficients=w,
        feature_names=[],  # Set by caller
        feature_means=means,
        feature_stds=stds,
        regularization=l2_lambda,
        n_iterations=iteration + 1,
        final_log_likelihood=final_ll,
        training_n=n
    )


def predict_logistic(model: LogisticModel, x_raw: List[float]) -> float:
    """Predict P(y=1) for a single example.
    
    Args:
        model: Trained LogisticModel
        x_raw: Raw feature vector [k]
    
    Returns:
        Probability in [0, 1]
    """
    # Standardize
    x_std = [
        (x_raw[i] - model.feature_means[i]) / model.feature_stds[i]
        for i in range(len(x_raw))
    ]
    
    # Add intercept and predict
    x_with_intercept = [1.0] + x_std
    z = dot_product(model.coefficients, x_with_intercept)
    return sigmoid(z)


def predict_logistic_batch(model: LogisticModel, X_raw: List[List[float]]) -> List[float]:
    """Predict P(y=1) for a batch of examples."""
    return [predict_logistic(model, x) for x in X_raw]


def compute_aic(ll: float, k: int) -> float:
    """Compute AIC = -2*LL + 2*k."""
    return -2.0 * ll + 2.0 * k


def compute_bic(ll: float, k: int, n: int) -> float:
    """Compute BIC = -2*LL + k*ln(n)."""
    return -2.0 * ll + k * math.log(n)


def brier_score(y_true: List[int], y_pred: List[float]) -> float:
    """Compute Brier score = mean((p - y)²)."""
    return statistics.mean((p - y) ** 2 for y, p in zip(y_true, y_pred))


def accuracy(y_true: List[int], y_pred: List[float], threshold: float = 0.5) -> float:
    """Compute classification accuracy."""
    correct = sum(1 for y, p in zip(y_true, y_pred) if (p >= threshold) == y)
    return correct / len(y_true)
