"""
Portfolio monitoring component for FactorExp live trading.
Tracks real-time portfolio metrics using Nautilus Trader's Portfolio API.
"""

import time
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime

from nautilus_trader.adapters.binance import BINANCE_VENUE
from nautilus_trader.common.component import Logger
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.portfolio.portfolio import Portfolio


@dataclass
class PortfolioSnapshot:
    """Portfolio snapshot for monitoring and analysis."""

    timestamp: datetime

    # Account information
    total_balance: dict[str, float]
    free_balance: dict[str, float]
    locked_balance: dict[str, float]

    # Margin information (for futures)
    initial_margin: dict[str, float]
    maintenance_margin: dict[str, float]
    margin_ratio: float | None

    # PnL information
    realized_pnl: dict[str, float]
    unrealized_pnl: dict[str, float]
    total_pnl: dict[str, float]
    total_pnl_pct: float

    # Position information
    net_positions: dict[str, float]
    net_exposures: dict[str, float]
    position_count: int

    # Risk metrics
    total_exposure_usd: float
    max_drawdown: float
    daily_pnl: float


class PortfolioMonitor:
    """
    Real-time portfolio monitoring using Nautilus Trader Portfolio API.
    
    This monitor tracks all portfolio metrics available through the native
    Portfolio interface and provides alerts and analytics.
    """

    def __init__(self, portfolio: Portfolio, logger: Logger):
        self.portfolio = portfolio
        self.logger = logger
        self.venue = BINANCE_VENUE

        # Monitoring state
        self._snapshots: list[PortfolioSnapshot] = []
        self._last_snapshot_time: float = 0
        self._daily_start_balance: dict[str, float] | None = None
        self._session_start_time = time.time()

        # Alert thresholds
        self.pnl_alert_threshold = 0.02  # 2% change
        self.exposure_alert_threshold = 0.8  # 80% of available balance
        self.margin_alert_threshold = 0.9  # 90% margin utilization

        self.logger.info("PortfolioMonitor initialized")

    def update_snapshot(self, instruments: list[InstrumentId]) -> PortfolioSnapshot:
        """
        Create current portfolio snapshot using Nautilus Portfolio API.
        
        Parameters
        ----------
        instruments : List[InstrumentId]
            List of instruments to monitor
            
        Returns
        -------
        PortfolioSnapshot
            Current portfolio state
        """
        current_time = datetime.now(UTC)

        # Get account information using Portfolio.account()
        account = self.portfolio.account(self.venue)
        if account is None:
            self.logger.error(f"No account found for venue {self.venue}")
            return None

        # Extract balance information from account
        balances = account.balances()
        total_balance = {str(currency): float(balance.total) for currency, balance in balances.items()}
        free_balance = {str(currency): float(balance.free) for currency, balance in balances.items()}
        locked_balance = {str(currency): float(balance.locked) for currency, balance in balances.items()}

        # Get locked balances using Portfolio.balances_locked()
        locked_balances_dict = self.portfolio.balances_locked(self.venue) or {}
        for currency, money in locked_balances_dict.items():
            locked_balance[str(currency)] = float(money.as_double())

        # Get margin information using Portfolio.margins_init() and Portfolio.margins_maint()
        initial_margins = self.portfolio.margins_init(self.venue) or {}
        maintenance_margins = self.portfolio.margins_maint(self.venue) or {}

        initial_margin = {str(currency): float(money.as_double()) for currency, money in initial_margins.items()}
        maintenance_margin = {str(currency): float(money.as_double()) for currency, money in maintenance_margins.items()}

        # Calculate margin ratio
        margin_ratio = None
        if account.is_margin_account and "USDT" in total_balance and "USDT" in maintenance_margin:
            if total_balance["USDT"] > 0:
                margin_ratio = maintenance_margin.get("USDT", 0) / total_balance["USDT"]

        # Get PnL information using Portfolio PnL methods
        realized_pnls = self.portfolio.realized_pnls(self.venue) or {}
        unrealized_pnls = self.portfolio.unrealized_pnls(self.venue) or {}
        total_pnls = self.portfolio.total_pnls(self.venue) or {}

        realized_pnl = {str(currency): float(money.as_double()) for currency, money in realized_pnls.items()}
        unrealized_pnl = {str(currency): float(money.as_double()) for currency, money in unrealized_pnls.items()}
        total_pnl = {str(currency): float(money.as_double()) for currency, money in total_pnls.items()}

        # Calculate total PnL percentage
        total_pnl_pct = 0.0
        if "USDT" in total_balance and total_balance["USDT"] > 0:
            total_pnl_pct = total_pnl.get("USDT", 0) / total_balance["USDT"]

        # Get position information using Portfolio.net_position() for each instrument
        net_positions = {}
        net_exposures = {}
        position_count = 0

        for instrument_id in instruments:
            # Use Portfolio.net_position() to get net position
            net_pos = self.portfolio.net_position(instrument_id)
            if net_pos is not None:
                net_positions[str(instrument_id)] = float(net_pos)
                if abs(float(net_pos)) > 1e-8:  # Consider non-zero positions
                    position_count += 1

            # Use Portfolio.net_exposure() to get net exposure
            net_exp = self.portfolio.net_exposure(instrument_id)
            if net_exp is not None:
                net_exposures[str(instrument_id)] = float(net_exp.as_double())

        # Calculate total exposure in USD
        total_exposure_usd = sum(abs(exposure) for exposure in net_exposures.values())

        # Calculate daily PnL and max drawdown
        daily_pnl = self._calculate_daily_pnl(total_pnl)
        max_drawdown = self._calculate_max_drawdown()

        # Create snapshot
        snapshot = PortfolioSnapshot(
            timestamp=current_time,
            total_balance=total_balance,
            free_balance=free_balance,
            locked_balance=locked_balance,
            initial_margin=initial_margin,
            maintenance_margin=maintenance_margin,
            margin_ratio=margin_ratio,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            net_positions=net_positions,
            net_exposures=net_exposures,
            position_count=position_count,
            total_exposure_usd=total_exposure_usd,
            max_drawdown=max_drawdown,
            daily_pnl=daily_pnl
        )

        # Store snapshot
        self._snapshots.append(snapshot)
        self._last_snapshot_time = time.time()

        # Keep only last 1000 snapshots
        if len(self._snapshots) > 1000:
            self._snapshots.pop(0)

        return snapshot

    def check_position_status(self, instrument_id: InstrumentId) -> dict[str, bool]:
        """
        Check position status using Portfolio position query methods.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Instrument to check
            
        Returns
        -------
        Dict[str, bool]
            Position status flags
        """
        return {
            "is_flat": self.portfolio.is_flat(instrument_id),
            "is_net_long": self.portfolio.is_net_long(instrument_id),
            "is_net_short": self.portfolio.is_net_short(instrument_id),
            "is_completely_flat": self.portfolio.is_completely_flat(),
        }

    def get_real_time_pnl(self, instrument_id: InstrumentId) -> dict[str, float | None]:
        """
        Get real-time PnL for specific instrument.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Instrument to get PnL for
            
        Returns
        -------
        Dict[str, Optional[float]]
            PnL information
        """
        realized = self.portfolio.realized_pnl(instrument_id)
        unrealized = self.portfolio.unrealized_pnl(instrument_id)
        total = self.portfolio.total_pnl(instrument_id)

        return {
            "realized_pnl": float(realized.as_double()) if realized else None,
            "unrealized_pnl": float(unrealized.as_double()) if unrealized else None,
            "total_pnl": float(total.as_double()) if total else None,
        }

    def get_latest_snapshot(self) -> PortfolioSnapshot | None:
        """Get the most recent portfolio snapshot."""
        return self._snapshots[-1] if self._snapshots else None

    def get_portfolio_summary(self) -> dict:
        """Get summary of current portfolio state."""
        latest = self.get_latest_snapshot()
        if not latest:
            return {}

        return {
            "timestamp": latest.timestamp.isoformat(),
            "total_balance_usdt": latest.total_balance.get("USDT", 0),
            "total_pnl_usdt": latest.total_pnl.get("USDT", 0),
            "total_pnl_pct": latest.total_pnl_pct,
            "position_count": latest.position_count,
            "total_exposure_usd": latest.total_exposure_usd,
            "margin_ratio": latest.margin_ratio,
            "daily_pnl": latest.daily_pnl,
            "max_drawdown": latest.max_drawdown,
        }

    def _calculate_daily_pnl(self, total_pnl: dict[str, float]) -> float:
        """Calculate daily PnL in USDT."""
        if not self._daily_start_balance:
            self._daily_start_balance = total_pnl.copy()
            return 0.0

        current_pnl = total_pnl.get("USDT", 0)
        start_pnl = self._daily_start_balance.get("USDT", 0)
        return current_pnl - start_pnl

    def _calculate_max_drawdown(self) -> float:
        """Calculate maximum drawdown from snapshots."""
        if len(self._snapshots) < 2:
            return 0.0

        peak_pnl = float("-inf")
        max_drawdown = 0.0

        for snapshot in self._snapshots:
            current_pnl = snapshot.total_pnl.get("USDT", 0)
            peak_pnl = max(peak_pnl, current_pnl)

            if peak_pnl > 0:
                drawdown = (peak_pnl - current_pnl) / peak_pnl
                max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def log_portfolio_status(self, snapshot: PortfolioSnapshot) -> None:
        """Log current portfolio status."""
        self.logger.info(
            f"Portfolio Status: "
            f"Balance={snapshot.total_balance.get('USDT', 0):.2f} USDT, "
            f"PnL={snapshot.total_pnl.get('USDT', 0):.2f} USDT ({snapshot.total_pnl_pct:.2%}), "
            f"Positions={snapshot.position_count}, "
            f"Exposure={snapshot.total_exposure_usd:.2f} USD"
        )
