"""Ensemble model combining logistic regression and random forest.

This module provides pure Python implementations of both models
and combines them for improved upset prediction accuracy.
"""

import math
import statistics
import json
import random
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, asdict


# ===== LOGISTIC REGRESSION =====

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


def standardize_features(X: List[List[float]]) -> Tuple[List[List[float]], List[float], List[float]]:
    """Z-score standardize features."""
    if not X:
        return [], [], []
    
    n_features = len(X[0])
    means = []
    stds = []
    
    for j in range(n_features):
        col = [row[j] for row in X]
        mean = statistics.mean(col)
        std = statistics.pstdev(col)
        if std < 1e-10:
            std = 1.0
        means.append(mean)
        stds.append(std)
    
    X_std = [[( row[j] - means[j]) / stds[j] for j in range(n_features)] for row in X]
    
    return X_std, means, stds


def train_logistic_regression(
    X: List[List[float]],
    y: List[int],
    learning_rate: float = 0.01,
    max_iterations: int = 5000,
    tolerance: float = 1e-6,
    l2_lambda: float = 0.01
) -> Dict:
    """Train logistic regression via gradient descent.
    
    Returns:
        Dict with 'weights', 'means', 'stds'
    """
    X_std, means, stds = standardize_features(X)
    n = len(X_std)
    k = len(X_std[0])
    
    # Add intercept column
    X_with_intercept = [[1.0] + row for row in X_std]
    
    # Initialize weights to zero
    w = [0.0] * (k + 1)
    
    # Gradient descent
    for iteration in range(max_iterations):
        predictions = [sigmoid(dot_product(w, x)) for x in X_with_intercept]
        
        gradients = [0.0] * (k + 1)
        for i in range(n):
            error = y[i] - predictions[i]
            for j in range(k + 1):
                gradients[j] += error * X_with_intercept[i][j]
        
        # Average and add L2 penalty
        for j in range(k + 1):
            gradients[j] /= n
            if j > 0:  # Don't regularize intercept
                gradients[j] -= l2_lambda * w[j]
        
        # Update weights
        for j in range(k + 1):
            w[j] += learning_rate * gradients[j]
        
        # Check convergence every 10 iterations
        if iteration % 10 == 0 and iteration > 50:
            ll = sum(
                y[i] * math.log(max(1e-15, predictions[i])) + (1 - y[i]) * math.log(max(1e-15, 1 - predictions[i]))
                for i in range(n)
            )
            if iteration > 100:
                break  # Early stopping for speed
    
    return {
        "weights": w,
        "means": means,
        "stds": stds
    }


def predict_logistic_regression(model: Dict, x: List[float]) -> float:
    """Predict P(y=1) for a single example."""
    # Standardize
    x_std = [(x[i] - model["means"][i]) / model["stds"][i] for i in range(len(x))]
    
    # Add intercept and predict
    x_with_intercept = [1.0] + x_std
    z = dot_product(model["weights"], x_with_intercept)
    return sigmoid(z)


# ===== RANDOM FOREST =====

@dataclass
class DecisionNode:
    """A node in a decision tree."""
    feature_idx: Optional[int] = None  # Feature to split on
    threshold: Optional[float] = None  # Split threshold
    left: Optional['DecisionNode'] = None
    right: Optional['DecisionNode'] = None
    value: Optional[float] = None  # Leaf value (probability)
    is_leaf: bool = False
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        if self.is_leaf:
            return {"is_leaf": True, "value": self.value}
        return {
            "is_leaf": False,
            "feature_idx": self.feature_idx,
            "threshold": self.threshold,
            "left": self.left.to_dict() if self.left else None,
            "right": self.right.to_dict() if self.right else None
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'DecisionNode':
        """Reconstruct from dict."""
        if d["is_leaf"]:
            return cls(is_leaf=True, value=d["value"])
        return cls(
            feature_idx=d["feature_idx"],
            threshold=d["threshold"],
            left=cls.from_dict(d["left"]) if d.get("left") else None,
            right=cls.from_dict(d["right"]) if d.get("right") else None,
            is_leaf=False
        )


def gini_impurity(y: List[int]) -> float:
    """Compute Gini impurity: 1 - sum(p_i^2)."""
    if not y:
        return 0.0
    n = len(y)
    p1 = sum(y) / n
    return 2 * p1 * (1 - p1)


def split_data(X: List[List[float]], y: List[int], feature_idx: int, threshold: float) -> Tuple:
    """Split data by feature threshold."""
    left_X, left_y = [], []
    right_X, right_y = [], []
    
    for i in range(len(X)):
        if X[i][feature_idx] <= threshold:
            left_X.append(X[i])
            left_y.append(y[i])
        else:
            right_X.append(X[i])
            right_y.append(y[i])
    
    return left_X, left_y, right_X, right_y


def find_best_split(X: List[List[float]], y: List[int], max_features: int) -> Tuple[int, float, float]:
    """Find the best split for the data.
    
    Returns:
        (best_feature_idx, best_threshold, best_gini_gain)
    """
    n_features = len(X[0])
    n_samples = len(X)
    
    # Random feature subset
    feature_indices = random.sample(range(n_features), min(max_features, n_features))
    
    best_gini_gain = 0.0
    best_feature_idx = None
    best_threshold = None
    
    parent_gini = gini_impurity(y)
    
    for feature_idx in feature_indices:
        # Get unique values for this feature
        values = sorted(set(X[i][feature_idx] for i in range(n_samples)))
        
        # Try splits at midpoints
        for i in range(len(values) - 1):
            threshold = (values[i] + values[i + 1]) / 2.0
            
            # Split data
            left_X, left_y, right_X, right_y = split_data(X, y, feature_idx, threshold)
            
            if not left_y or not right_y:
                continue
            
            # Compute weighted Gini
            n_left = len(left_y)
            n_right = len(right_y)
            weighted_gini = (n_left * gini_impurity(left_y) + n_right * gini_impurity(right_y)) / n_samples
            
            gini_gain = parent_gini - weighted_gini
            
            if gini_gain > best_gini_gain:
                best_gini_gain = gini_gain
                best_feature_idx = feature_idx
                best_threshold = threshold
    
    return best_feature_idx, best_threshold, best_gini_gain


def build_tree(
    X: List[List[float]],
    y: List[int],
    max_depth: int = 10,
    min_samples_split: int = 10,
    max_features: int = None,
    current_depth: int = 0
) -> DecisionNode:
    """Recursively build a decision tree."""
    n_samples = len(X)
    
    if max_features is None:
        max_features = int(math.sqrt(len(X[0])))
    
    # Stopping conditions
    if (current_depth >= max_depth or
        n_samples < min_samples_split or
        len(set(y)) == 1):
        # Create leaf node
        leaf_value = sum(y) / len(y) if y else 0.5
        return DecisionNode(is_leaf=True, value=leaf_value)
    
    # Find best split
    feature_idx, threshold, gini_gain = find_best_split(X, y, max_features)
    
    if feature_idx is None or gini_gain < 1e-6:
        # No good split found
        leaf_value = sum(y) / len(y) if y else 0.5
        return DecisionNode(is_leaf=True, value=leaf_value)
    
    # Split data and recurse
    left_X, left_y, right_X, right_y = split_data(X, y, feature_idx, threshold)
    
    left_child = build_tree(left_X, left_y, max_depth, min_samples_split, max_features, current_depth + 1)
    right_child = build_tree(right_X, right_y, max_depth, min_samples_split, max_features, current_depth + 1)
    
    return DecisionNode(
        feature_idx=feature_idx,
        threshold=threshold,
        left=left_child,
        right=right_child,
        is_leaf=False
    )


def predict_tree(node: DecisionNode, x: List[float]) -> float:
    """Predict probability for a single example using a decision tree."""
    if node.is_leaf:
        return node.value
    
    if x[node.feature_idx] <= node.threshold:
        return predict_tree(node.left, x)
    else:
        return predict_tree(node.right, x)


def train_random_forest(
    X: List[List[float]],
    y: List[int],
    n_trees: int = 300,
    max_depth: int = 8,
    min_samples_split: int = 10,
    max_features: int = None,
    sample_fraction: float = 0.8
) -> List[DecisionNode]:
    """Train a random forest classifier.
    
    Returns:
        List of DecisionNode (trees)
    """
    n_samples = len(X)
    trees = []
    
    for _ in range(n_trees):
        # Bootstrap sample
        indices = [random.randint(0, n_samples - 1) for _ in range(int(n_samples * sample_fraction))]
        X_sample = [X[i] for i in indices]
        y_sample = [y[i] for i in indices]
        
        # Build tree
        tree = build_tree(X_sample, y_sample, max_depth, min_samples_split, max_features)
        trees.append(tree)
    
    return trees


def predict_random_forest(trees: List[DecisionNode], x: List[float]) -> float:
    """Predict probability by averaging tree predictions."""
    predictions = [predict_tree(tree, x) for tree in trees]
    return statistics.mean(predictions)


# ===== ENSEMBLE MODEL =====

def train_ensemble(
    X_train: List[List[float]],
    y_train: List[int],
    lr_weight: float = 0.5,
    n_trees: int = 300,
    max_depth: int = 8,
    verbose: bool = True
) -> Dict:
    """Train ensemble model (LR + RF).
    
    Args:
        X_train: Feature matrix [n][k]
        y_train: Binary labels [n]
        lr_weight: Weight for logistic regression (0-1), RF weight = 1 - lr_weight
        n_trees: Number of trees in random forest
        max_depth: Maximum depth of trees
        verbose: Print progress
    
    Returns:
        Dict containing both models
    """
    if verbose:
        print(f"Training ensemble on {len(X_train)} examples...")
    
    # Train logistic regression
    if verbose:
        print("  Training logistic regression...")
    lr_model = train_logistic_regression(X_train, y_train)
    
    # Train random forest
    if verbose:
        print(f"  Training random forest ({n_trees} trees)...")
    rf_trees = train_random_forest(X_train, y_train, n_trees=n_trees, max_depth=max_depth)
    
    return {
        "lr_model": lr_model,
        "rf_trees": [tree.to_dict() for tree in rf_trees],
        "lr_weight": lr_weight,
        "n_trees": n_trees,
        "max_depth": max_depth,
        "training_n": len(X_train)
    }


def predict_ensemble(model: Dict, x: List[float]) -> float:
    """Predict P(upset) using ensemble.
    
    Args:
        model: Trained ensemble model dict
        x: Feature vector [k]
    
    Returns:
        Probability between 0.0 and 1.0
    """
    # Logistic regression prediction
    p_lr = predict_logistic_regression(model["lr_model"], x)
    
    # Random forest prediction
    rf_trees = [DecisionNode.from_dict(d) for d in model["rf_trees"]]
    p_rf = predict_random_forest(rf_trees, x)
    
    # Weighted ensemble
    lr_weight = model.get("lr_weight", 0.5)
    p_ensemble = lr_weight * p_lr + (1.0 - lr_weight) * p_rf
    
    return max(0.01, min(0.99, p_ensemble))


def save_model(model: Dict, path: str) -> None:
    """Save ensemble model to JSON file."""
    with open(path, 'w') as f:
        json.dump(model, f, indent=2)


def load_model(path: str) -> Dict:
    """Load ensemble model from JSON file."""
    with open(path) as f:
        return json.load(f)
