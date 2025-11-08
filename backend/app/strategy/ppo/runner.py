"""PPO strategy runner for ML-based signal generation.

Uses trained PPO (Proximal Policy Optimization) models to generate trading signals
based on market features.

Architecture:
    1. Load model artifacts (model + scaler) at initialization
    2. Extract features from OHLC dataframe
    3. Run model inference
    4. Apply thresholding to convert predictions to signals
    5. Return SignalCandidate with confidence scores

Model artifacts expected:
    - {PPO_MODEL_PATH}/model.pkl: Trained PPO model
    - {PPO_MODEL_PATH}/scaler.pkl: Feature scaler (StandardScaler)

Example:
    >>> from backend.app.strategy.ppo.runner import PPOStrategy
    >>> strategy = PPOStrategy(
    ...     model_path="/path/to/models",
    ...     threshold=0.65
    ... )
    >>> signal = await strategy.generate_signal(df, "GOLD", datetime.utcnow())
"""

import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd

from backend.app.strategy.fib_rsi.schema import SignalCandidate
from backend.app.strategy.ppo.loader import PPOModelLoader

logger = logging.getLogger(__name__)


class PPOStrategy:
    """PPO model-based trading strategy.

    Generates signals using trained Proximal Policy Optimization model.

    Attributes:
        model_path: Path to model artifacts directory
        threshold: Confidence threshold for signal generation (0.0-1.0)
        loader: PPOModelLoader instance
        model: Loaded PPO model
        scaler: Loaded feature scaler
    """

    def __init__(
        self,
        model_path: str | None = None,
        threshold: float = 0.65,
    ):
        """Initialize PPO strategy.

        Args:
            model_path: Path to model artifacts (default: from PPO_MODEL_PATH env)
            threshold: Confidence threshold for signals (default: from PPO_THRESHOLD env or 0.65)

        Example:
            >>> strategy = PPOStrategy(
            ...     model_path="/models/ppo_gold",
            ...     threshold=0.70
            ... )
        """
        # Load from environment if not provided
        self.model_path = model_path or os.getenv("PPO_MODEL_PATH", "/app/models/ppo")
        self.threshold = float(os.getenv("PPO_THRESHOLD", str(threshold)))

        # Initialize loader
        self.loader = PPOModelLoader(base_path=self.model_path)

        # Load model artifacts
        self.model = None
        self.scaler = None
        self._load_artifacts()

        logger.info(
            "PPOStrategy initialized",
            extra={
                "model_path": self.model_path,
                "threshold": self.threshold,
                "model_loaded": self.model is not None,
            },
        )

    def _load_artifacts(self) -> None:
        """Load model and scaler artifacts.

        Raises:
            FileNotFoundError: If model artifacts not found
            ValueError: If artifacts are corrupt/invalid
        """
        try:
            self.model = self.loader.load_model()
            self.scaler = self.loader.load_scaler()

            logger.info(
                "PPO model artifacts loaded",
                extra={"model_path": self.model_path},
            )

        except Exception as e:
            logger.error(
                "Failed to load PPO model artifacts",
                exc_info=True,
                extra={"model_path": self.model_path, "error": str(e)},
            )
            raise

    async def generate_signal(
        self,
        df: pd.DataFrame,
        instrument: str,
        timestamp: datetime,
    ) -> SignalCandidate | None:
        """Generate trading signal using PPO model.

        Args:
            df: OHLC dataframe with columns [open, high, low, close, volume]
            instrument: Trading instrument (e.g., "GOLD", "EURUSD")
            timestamp: Signal timestamp (UTC)

        Returns:
            SignalCandidate if signal generated, None otherwise

        Example:
            >>> df = pd.DataFrame({
            ...     'open': [1950.0, 1952.0],
            ...     'high': [1955.0, 1957.0],
            ...     'low': [1945.0, 1947.0],
            ...     'close': [1952.0, 1954.0],
            ...     'volume': [1000, 1100]
            ... })
            >>> signal = await strategy.generate_signal(df, "GOLD", datetime.utcnow())
        """
        if self.model is None or self.scaler is None:
            logger.warning(
                "PPO model not loaded, skipping signal generation",
                extra={"instrument": instrument},
            )
            return None

        try:
            # Extract features from dataframe
            features = self._extract_features(df)

            # Normalize features
            features_scaled = self.scaler.transform(features.reshape(1, -1))

            # Run model inference
            prediction = self.model.predict(features_scaled)[0]

            # prediction format: [buy_confidence, sell_confidence]
            buy_confidence = float(prediction[0])
            sell_confidence = float(prediction[1])

            # Determine side and confidence
            if buy_confidence > sell_confidence:
                side = "buy"
                confidence = buy_confidence
            else:
                side = "sell"
                confidence = sell_confidence

            # Apply threshold
            if confidence < self.threshold:
                logger.debug(
                    f"PPO confidence {confidence:.2f} below threshold {self.threshold:.2f}",
                    extra={
                        "instrument": instrument,
                        "confidence": confidence,
                        "threshold": self.threshold,
                    },
                )
                return None

            # Get latest price data
            latest_close = float(df["close"].iloc[-1])

            # Calculate SL/TP based on recent volatility
            atr = self._calculate_atr(df)

            if side == "buy":
                entry_price = latest_close
                stop_loss = latest_close - (2.0 * atr)
                take_profit = latest_close + (3.0 * atr)
            else:  # sell
                entry_price = latest_close
                stop_loss = latest_close + (2.0 * atr)
                take_profit = latest_close - (3.0 * atr)

            # Create signal candidate
            signal = SignalCandidate(
                instrument=instrument,
                side=side,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                confidence=confidence,
                timestamp=timestamp,
                reason=f"ppo_model_{side}_confidence_{confidence:.2f}",
                payload={
                    "strategy": "ppo_gold",
                    "buy_confidence": buy_confidence,
                    "sell_confidence": sell_confidence,
                    "atr": atr,
                    "features": features.tolist(),
                },
            )

            logger.info(
                f"PPO signal generated: {instrument} {side}",
                extra={
                    "instrument": instrument,
                    "side": side,
                    "confidence": confidence,
                    "entry_price": entry_price,
                },
            )

            return signal

        except Exception as e:
            logger.error(
                "PPO signal generation failed",
                exc_info=True,
                extra={
                    "instrument": instrument,
                    "error": str(e),
                },
            )
            return None

    def _extract_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract features from OHLC dataframe.

        Features:
            - Returns (close % change)
            - RSI (14-period)
            - MACD
            - BB position
            - Volume ratio
            - High/Low range

        Args:
            df: OHLC dataframe

        Returns:
            Feature array

        Example:
            >>> df = pd.DataFrame({
            ...     'open': [1950.0, 1952.0],
            ...     'high': [1955.0, 1957.0],
            ...     'low': [1945.0, 1947.0],
            ...     'close': [1952.0, 1954.0],
            ...     'volume': [1000, 1100]
            ... })
            >>> features = strategy._extract_features(df)
            >>> print(features.shape)  # (6,) - 6 features
        """
        # Returns
        returns = df["close"].pct_change().fillna(0.0).iloc[-1]

        # RSI
        rsi = self._calculate_rsi(df["close"], period=14)

        # MACD
        macd = self._calculate_macd(df["close"])

        # Bollinger Bands position
        bb_position = self._calculate_bb_position(df["close"])

        # Volume ratio
        volume_ratio = (
            df["volume"].iloc[-1] / df["volume"].rolling(20).mean().iloc[-1]
            if len(df) >= 20
            else 1.0
        )

        # High/Low range
        hl_range = (df["high"].iloc[-1] - df["low"].iloc[-1]) / df["close"].iloc[-1]

        features = np.array(
            [
                returns,
                rsi,
                macd,
                bb_position,
                volume_ratio,
                hl_range,
            ]
        )

        return features

    def _calculate_rsi(self, series: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator.

        Args:
            series: Price series
            period: RSI period

        Returns:
            RSI value (0-100)
        """
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0

    def _calculate_macd(self, series: pd.Series) -> float:
        """Calculate MACD indicator.

        Args:
            series: Price series

        Returns:
            MACD value
        """
        ema_12 = series.ewm(span=12, adjust=False).mean()
        ema_26 = series.ewm(span=26, adjust=False).mean()
        macd = ema_12 - ema_26

        return float(macd.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0.0

    def _calculate_bb_position(self, series: pd.Series, period: int = 20) -> float:
        """Calculate position within Bollinger Bands.

        Args:
            series: Price series
            period: BB period

        Returns:
            Position (0.0 = lower band, 0.5 = middle, 1.0 = upper band)
        """
        sma = series.rolling(period).mean()
        std = series.rolling(period).std()

        upper = sma + (2 * std)
        lower = sma - (2 * std)

        current = series.iloc[-1]
        bb_range = upper.iloc[-1] - lower.iloc[-1]

        if bb_range == 0:
            return 0.5

        position = (current - lower.iloc[-1]) / bb_range

        return float(np.clip(position, 0.0, 1.0))

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range.

        Args:
            df: OHLC dataframe
            period: ATR period

        Returns:
            ATR value
        """
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(period).mean()

        return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else 10.0
