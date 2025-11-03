"""
Secure configuration management for FactorExp live trading.
Handles API key encryption and environment variable validation.
"""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv


class SecureConfigManager:
    """Secure configuration manager for API credentials."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.env_file = project_root / ".env"
        self.key_file = project_root / "encryption.key"
        self.encrypted_file = project_root / "keys.enc"

        # Load environment variables
        if self.env_file.exists():
            load_dotenv(self.env_file)

    def _get_or_create_key(self) -> bytes:
        """Get or create encryption key."""
        if self.key_file.exists():
            return self.key_file.read_bytes()
        else:
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)
            self.key_file.chmod(0o600)  # Read-only by owner
            return key

    def encrypt_credentials(self, credentials: dict[str, str]) -> None:
        """Encrypt and store credentials."""
        key = self._get_or_create_key()
        fernet = Fernet(key)

        encrypted_data = fernet.encrypt(json.dumps(credentials).encode())
        self.encrypted_file.write_bytes(encrypted_data)
        self.encrypted_file.chmod(0o600)  # Read-only by owner

    def decrypt_credentials(self) -> dict[str, str]:
        """Decrypt and return credentials."""
        if not self.encrypted_file.exists():
            raise FileNotFoundError("Encrypted credentials file not found")

        key = self._get_or_create_key()
        fernet = Fernet(key)

        encrypted_data = self.encrypted_file.read_bytes()
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode())

    def get_api_credentials(self, use_encrypted: bool = False) -> dict[str, str | None]:
        """
        Get API credentials from environment variables or encrypted file.
        
        Parameters
        ----------
        use_encrypted : bool
            If True, load from encrypted file. Otherwise, use environment variables.
            
        Returns
        -------
        Dict[str, Optional[str]]
            Dictionary containing API credentials
        """
        if use_encrypted:
            return self.decrypt_credentials()

        # Load from environment variables
        trading_mode = os.getenv("TRADING_MODE", "testnet")

        if trading_mode == "testnet":
            return {
                "api_key": os.getenv("BINANCE_TESTNET_API_KEY"),
                "api_secret": os.getenv("BINANCE_TESTNET_API_SECRET"),
                "testnet": True
            }
        else:
            return {
                "api_key": os.getenv("BINANCE_API_KEY"),
                "api_secret": os.getenv("BINANCE_API_SECRET"),
                "testnet": False
            }

    def validate_credentials(self, credentials: dict[str, str | None]) -> bool:
        """
        Validate that all required credentials are present.
        
        Parameters
        ----------
        credentials : Dict[str, Optional[str]]
            Credentials dictionary to validate
            
        Returns
        -------
        bool
            True if all required credentials are present
        """
        required_keys = ["api_key", "api_secret"]

        for key in required_keys:
            if not credentials.get(key):
                raise ValueError(f"Missing required credential: {key}")

        return True

    def get_risk_parameters(self) -> dict[str, float]:
        """Get risk management parameters from environment."""
        return {
            "max_position_size_btc": float(os.getenv("MAX_POSITION_SIZE_BTC", 0.01)),
            "max_position_size_eth": float(os.getenv("MAX_POSITION_SIZE_ETH", 0.1)),
            "risk_limit_daily_usd": float(os.getenv("RISK_LIMIT_DAILY_USD", 1000)),
            "max_drawdown_pct": float(os.getenv("MAX_DRAWDOWN_PCT", 0.05)),
            "portfolio_update_interval": int(os.getenv("PORTFOLIO_UPDATE_INTERVAL_SEC", 5)),
        }

    def get_factorexp_parameters(self) -> dict[str, float | int | str]:
        """Get FactorExp strategy parameters from environment."""
        return {
            "factor_config_path": os.getenv(
                "FACTOREXP_CONFIG_PATH", "../factorexp_backtest/configs/factors.yaml"
            ),
            "factor_id": os.getenv("FACTOREXP_FACTOR_ID", "vwap_return_std"),
            "factor_ids": self._parse_factor_ids(os.getenv("FACTOREXP_FACTOR_IDS")),
            "zscore_period": int(os.getenv("FACTOREXP_ZSCORE_PERIOD", 5760)),
            "clip_min": float(os.getenv("FACTOREXP_CLIP_MIN", -2.0)),
            "clip_max": float(os.getenv("FACTOREXP_CLIP_MAX", 2.0)),
            "min_signal_magnitude": float(os.getenv("FACTOREXP_MIN_SIGNAL", 0.05)),
            "capital_allocation_usd": self._parse_optional_float(
                os.getenv("FACTOREXP_CAPITAL_ALLOCATION_USD")
            ),
            "target_notional_usd": self._parse_optional_float(
                os.getenv("FACTOREXP_TARGET_NOTIONAL_USD")
            ),
            "max_leverage": self._parse_optional_float(os.getenv("FACTOREXP_MAX_LEVERAGE")),
        }

    @staticmethod
    def _parse_factor_ids(raw: str | None) -> tuple[str, ...] | None:
        """Parse comma-separated factor IDs from environment variables."""
        if not raw:
            return None

        parts = [part.strip() for part in raw.split(",")]
        normalized = tuple(part for part in parts if part)
        return normalized or None

    @staticmethod
    def _parse_optional_float(raw: str | None) -> float | None:
        """Safely parse optional float values from environment variables."""
        if raw is None or raw == "":
            return None
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"Invalid float value '{raw}' for FACTOREXP_CAPITAL_ALLOCATION_USD") from exc
