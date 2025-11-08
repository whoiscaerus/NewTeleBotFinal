"""PPO model artifact loader.

Loads trained PPO model and feature scaler from disk with validation and error handling.

Expected artifacts:
    - model.pkl: Trained PPO model (pickle format)
    - scaler.pkl: Feature scaler (scikit-learn StandardScaler)

Example:
    >>> from backend.app.strategy.ppo.loader import PPOModelLoader
    >>> loader = PPOModelLoader(base_path="/app/models/ppo")
    >>> model = loader.load_model()
    >>> scaler = loader.load_scaler()
"""

import logging
import pickle
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PPOModelLoader:
    """Loader for PPO model artifacts.

    Handles loading and validation of ML model files with caching.

    Attributes:
        base_path: Base directory containing model artifacts
        model_cache: Cached model object
        scaler_cache: Cached scaler object
    """

    def __init__(self, base_path: str):
        """Initialize model loader.

        Args:
            base_path: Path to directory containing model.pkl and scaler.pkl

        Example:
            >>> loader = PPOModelLoader(base_path="/app/models/ppo")
        """
        self.base_path = Path(base_path)
        self.model_cache: Any = None
        self.scaler_cache: Any = None

        logger.info(
            "PPOModelLoader initialized",
            extra={"base_path": str(self.base_path)},
        )

    def load_model(self, force_reload: bool = False) -> Any:
        """Load PPO model from disk.

        Args:
            force_reload: If True, reload even if cached

        Returns:
            Loaded model object

        Raises:
            FileNotFoundError: If model.pkl not found
            ValueError: If model file is corrupt/invalid

        Example:
            >>> loader = PPOModelLoader(base_path="/app/models/ppo")
            >>> model = loader.load_model()
        """
        if self.model_cache is not None and not force_reload:
            logger.debug("Returning cached model")
            return self.model_cache

        model_path = self.base_path / "model.pkl"

        if not model_path.exists():
            logger.error(
                f"Model file not found: {model_path}",
                extra={"model_path": str(model_path)},
            )
            raise FileNotFoundError(f"Model file not found: {model_path}")

        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)

            # Validate model has predict method
            if not hasattr(model, "predict"):
                raise ValueError("Loaded model missing predict() method")

            self.model_cache = model

            logger.info(
                "PPO model loaded",
                extra={
                    "model_path": str(model_path),
                    "model_type": type(model).__name__,
                },
            )

            return model

        except Exception as e:
            logger.error(
                "Failed to load model",
                exc_info=True,
                extra={
                    "model_path": str(model_path),
                    "error": str(e),
                },
            )
            raise ValueError(f"Failed to load model from {model_path}: {e}") from e

    def load_scaler(self, force_reload: bool = False) -> Any:
        """Load feature scaler from disk.

        Args:
            force_reload: If True, reload even if cached

        Returns:
            Loaded scaler object

        Raises:
            FileNotFoundError: If scaler.pkl not found
            ValueError: If scaler file is corrupt/invalid

        Example:
            >>> loader = PPOModelLoader(base_path="/app/models/ppo")
            >>> scaler = loader.load_scaler()
        """
        if self.scaler_cache is not None and not force_reload:
            logger.debug("Returning cached scaler")
            return self.scaler_cache

        scaler_path = self.base_path / "scaler.pkl"

        if not scaler_path.exists():
            logger.error(
                f"Scaler file not found: {scaler_path}",
                extra={"scaler_path": str(scaler_path)},
            )
            raise FileNotFoundError(f"Scaler file not found: {scaler_path}")

        try:
            with open(scaler_path, "rb") as f:
                scaler = pickle.load(f)

            # Validate scaler has transform method
            if not hasattr(scaler, "transform"):
                raise ValueError("Loaded scaler missing transform() method")

            self.scaler_cache = scaler

            logger.info(
                "Feature scaler loaded",
                extra={
                    "scaler_path": str(scaler_path),
                    "scaler_type": type(scaler).__name__,
                },
            )

            return scaler

        except Exception as e:
            logger.error(
                "Failed to load scaler",
                exc_info=True,
                extra={
                    "scaler_path": str(scaler_path),
                    "error": str(e),
                },
            )
            raise ValueError(f"Failed to load scaler from {scaler_path}: {e}") from e

    def clear_cache(self) -> None:
        """Clear cached model and scaler.

        Example:
            >>> loader.clear_cache()
            >>> model = loader.load_model()  # Will reload from disk
        """
        self.model_cache = None
        self.scaler_cache = None

        logger.debug("Model cache cleared")

    def validate_artifacts(self) -> dict[str, bool]:
        """Validate that all required artifacts exist and are loadable.

        Returns:
            Dict with validation results for each artifact

        Example:
            >>> loader = PPOModelLoader(base_path="/app/models/ppo")
            >>> status = loader.validate_artifacts()
            >>> print(status)
            {"model": True, "scaler": True}
        """
        results = {
            "model": False,
            "scaler": False,
        }

        # Check model
        try:
            self.load_model(force_reload=True)
            results["model"] = True
        except Exception as e:
            logger.warning(
                f"Model validation failed: {e}",
                extra={"error": str(e)},
            )

        # Check scaler
        try:
            self.load_scaler(force_reload=True)
            results["scaler"] = True
        except Exception as e:
            logger.warning(
                f"Scaler validation failed: {e}",
                extra={"error": str(e)},
            )

        logger.info(
            "Artifact validation complete",
            extra={
                "model_valid": results["model"],
                "scaler_valid": results["scaler"],
            },
        )

        return results
