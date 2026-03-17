"""Public API for the upset prediction model.

Usage:
    from upset_model.predict import UpsetPredictor
    
    predictor = UpsetPredictor()
    p_upset = predictor.predict(
        team_a={'seed': 5, 'adj_em': 14, 'adj_o': 110, 'adj_d': 96, 'adj_t': 67},
        team_b={'seed': 12, 'adj_em': 11, 'adj_o': 108, 'adj_d': 97, 'adj_t': 65},
        round_num=1
    )
"""

from pathlib import Path
from typing import Optional
import joblib
import numpy as np

try:
    # Try relative imports first (when imported as module)
    from .features import extract_features
except ImportError:
    # Fall back to absolute imports (when run as script)
    from features import extract_features


class UpsetPredictor:
    """Predict upset probability using sklearn ensemble model."""
    
    def __init__(self, model_path: Optional[str] = None):
        """Load the trained sklearn model.

        Args:
            model_path: Path to sklearn_model.joblib.
                       Defaults to data/upset_model/sklearn_model.joblib
        """
        if model_path is None:
            model_path = Path(__file__).resolve().parent.parent / "data" / "upset_model" / "sklearn_model.joblib"

        self.model_package = joblib.load(str(model_path))
        self.scaler = self.model_package['scaler']
        self.lr = self.model_package['logistic']
        self.model_type = self.model_package.get('model_type', 'ensemble')

        # Feature selection indices (Phase 2D) — which features to keep from extract_features()
        self.feature_indices = self.model_package.get('feature_indices')

        # Backward compat: load RF/GBM if present (old ensemble format)
        self.rf = self.model_package.get('random_forest')
        self.gb = self.model_package.get('gradient_boosting')
        self.lr_uncalibrated = self.model_package.get('logistic_uncalibrated')
        self.model_path = str(model_path)
    
    def predict(self, team_a: dict, team_b: dict, round_num: int = 1,
                team_a_lrmc: Optional[dict] = None, team_b_lrmc: Optional[dict] = None,
                team_a_torvik: Optional[dict] = None, team_b_torvik: Optional[dict] = None,
                team_a_momentum: Optional[dict] = None, team_b_momentum: Optional[dict] = None,
                spread: Optional[float] = None) -> float:
        """Predict P(upset) where team_a is favorite, team_b is underdog.

        Args:
            team_a: Favorite team dict with keys: seed, adj_em, adj_o, adj_d, adj_t, luck (optional)
            team_b: Underdog team dict with keys: seed, adj_em, adj_o, adj_d, adj_t, luck (optional)
            round_num: Tournament round (1-6)
            team_a_lrmc: Optional LRMC stats for team_a (top25_wins, top25_losses, top25_games)
            team_b_lrmc: Optional LRMC stats for team_b
            team_a_torvik: Optional Torvik stats (barthag, wab)
            team_b_torvik: Optional Torvik stats
            team_a_momentum: Optional momentum stats (last10_adj_em, last10_win_pct)
            team_b_momentum: Optional momentum stats
            spread: Optional Vegas point spread (negative = favorite favored)

        Returns:
            P(team_b wins) between 0.01 and 0.99
        """
        # Extract features
        x = extract_features(team_a, team_b, round_num, team_a_lrmc, team_b_lrmc,
                             team_a_torvik, team_b_torvik,
                             team_a_momentum, team_b_momentum, spread)
        x = np.array(x).reshape(1, -1)

        # Apply feature selection if model was trained with it
        if self.feature_indices is not None:
            x = x[:, self.feature_indices]

        # Scale for logistic regression
        x_scaled = self.scaler.transform(x)

        if self.model_type in ('logistic_only', 'logistic_calibrated') or self.rf is None:
            # LR-only or calibrated LR model
            p_upset = self.lr.predict_proba(x_scaled)[0, 1]
        else:
            # Legacy ensemble (simple average)
            lr_pred = self.lr.predict_proba(x_scaled)[0, 1]
            rf_pred = self.rf.predict_proba(x)[0, 1]
            gb_pred = self.gb.predict_proba(x)[0, 1]
            p_upset = (lr_pred + rf_pred + gb_pred) / 3.0
        
        # Clip to reasonable range
        return max(0.01, min(0.99, p_upset))
    
    def predict_from_teams(self, favorite: 'Team', underdog: 'Team', round_num: int = 1) -> float:
        """Same as predict() but accepts Team dataclass objects from bracket optimizer.
        
        Args:
            favorite: Team object with attributes: seed, adj_em, adj_o, adj_d, adj_t
            underdog: Team object with attributes: seed, adj_em, adj_o, adj_d, adj_t
            round_num: Tournament round (1-6)
        
        Returns:
            P(underdog wins) between 0.01 and 0.99
        """
        # Convert Team objects to dicts
        fav_dict = {
            'seed': favorite.seed,
            'adj_em': favorite.adj_em,
            'adj_o': favorite.adj_o,
            'adj_d': favorite.adj_d,
            'adj_t': favorite.adj_t,
            'luck': getattr(favorite, 'luck', 0.0)
        }
        
        dog_dict = {
            'seed': underdog.seed,
            'adj_em': underdog.adj_em,
            'adj_o': underdog.adj_o,
            'adj_d': underdog.adj_d,
            'adj_t': underdog.adj_t,
            'luck': getattr(underdog, 'luck', 0.0)
        }
        
        # Try to get LRMC stats if available
        fav_lrmc = None
        dog_lrmc = None

        if hasattr(favorite, 'top25_games') and favorite.top25_games is not None:
            fav_lrmc = {
                'top25_wins': getattr(favorite, 'top25_wins', 0),
                'top25_losses': getattr(favorite, 'top25_losses', 0),
                'top25_games': favorite.top25_games
            }

        if hasattr(underdog, 'top25_games') and underdog.top25_games is not None:
            dog_lrmc = {
                'top25_wins': getattr(underdog, 'top25_wins', 0),
                'top25_losses': getattr(underdog, 'top25_losses', 0),
                'top25_games': underdog.top25_games
            }

        # Torvik stats
        fav_torvik = None
        dog_torvik = None
        if hasattr(favorite, 'barthag') and favorite.barthag is not None:
            fav_torvik = {'barthag': favorite.barthag, 'wab': getattr(favorite, 'wab', 0.0)}
        if hasattr(underdog, 'barthag') and underdog.barthag is not None:
            dog_torvik = {'barthag': underdog.barthag, 'wab': getattr(underdog, 'wab', 0.0)}

        # Momentum stats
        fav_momentum = None
        dog_momentum = None
        if hasattr(favorite, 'last10_adj_em') and favorite.last10_adj_em is not None:
            fav_momentum = {
                'last10_adj_em': favorite.last10_adj_em,
                'last10_win_pct': getattr(favorite, 'last10_win_pct', 0.5)
            }
        if hasattr(underdog, 'last10_adj_em') and underdog.last10_adj_em is not None:
            dog_momentum = {
                'last10_adj_em': underdog.last10_adj_em,
                'last10_win_pct': getattr(underdog, 'last10_win_pct', 0.5)
            }

        # Spread
        spread_val = getattr(favorite, 'spread', None)

        return self.predict(fav_dict, dog_dict, round_num, fav_lrmc, dog_lrmc,
                            fav_torvik, dog_torvik, fav_momentum, dog_momentum, spread_val)
    
    def get_model_info(self) -> dict:
        """Return model metadata."""
        cv_results = self.model_package.get('cv_results', {})
        return {
            "model_type": self.model_type,
            "training_n": self.model_package.get('training_n', 0),
            "n_upsets": self.model_package.get('n_upsets', 0),
            "years": self.model_package.get('years', []),
            "cv_auc": cv_results.get('best_auc', cv_results.get('ensemble_auc', 0.0)),
            "baseline_auc": cv_results.get('baseline_auc', 0.0),
            "feature_names": self.model_package.get('feature_names', []),
            "model_path": self.model_path
        }

    def get_model_internals(self) -> dict:
        """Return data needed for client-side prediction and visualization in HTML output."""
        pkg = self.model_package
        lr = pkg.get('logistic_uncalibrated')
        scaler = pkg.get('scaler')
        cv = pkg.get('cv_results', {})
        return {
            'feature_names': pkg.get('feature_names', []),
            'coefficients': lr.coef_[0].tolist() if lr is not None else [],
            'intercept': float(lr.intercept_[0]) if lr is not None else 0.0,
            'scaler_mean': scaler.mean_.tolist() if scaler is not None else [],
            'scaler_std': scaler.scale_.tolist() if scaler is not None else [],
            'baseline_auc': cv.get('baseline_auc'),
            'seed_kenpom_auc': cv.get('seed_kenpom_auc'),
            'model_auc': cv.get('best_auc'),
            'brier': cv.get('best_brier'),
            'training_n': pkg.get('training_n'),
            'n_upsets': pkg.get('n_upsets'),
            'years': pkg.get('years', []),
        }
