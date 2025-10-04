"""
Risk monitoring component for FactorExp live trading.
Implements comprehensive risk management with real-time alerts.
"""

import time
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from enum import Enum

from monitoring.portfolio_monitor import PortfolioMonitor
from monitoring.portfolio_monitor import PortfolioSnapshot
from nautilus_trader.common.component import Logger
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.portfolio.portfolio import Portfolio


class RiskLevel(Enum):
    """Risk level classifications."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class RiskAlert:
    """Risk alert information."""

    timestamp: datetime
    level: RiskLevel
    category: str
    message: str
    instrument: str | None = None
    current_value: float | None = None
    threshold_value: float | None = None
    action_required: str = ""


class RiskMonitor:
    """
    Comprehensive risk monitoring for FactorExp live trading.
    
    Monitors portfolio exposure, drawdown, margin requirements,
    and position sizing to prevent excessive risk.
    """

    def __init__(self, portfolio: Portfolio, portfolio_monitor: PortfolioMonitor,
                 logger: Logger, risk_config: dict):
        self.portfolio = portfolio
        self.portfolio_monitor = portfolio_monitor
        self.logger = logger
        self.config = risk_config

        # Risk limits from configuration
        self.max_daily_loss = risk_config.get("max_daily_loss_usd", 1000)
        self.max_drawdown_pct = risk_config.get("max_drawdown_pct", 0.05)
        self.max_position_value = risk_config.get("max_position_value_usd", 10000)
        self.margin_warning_threshold = risk_config.get("margin_warning_threshold", 0.8)
        self.margin_critical_threshold = risk_config.get("margin_critical_threshold", 0.9)

        # Risk state tracking
        self._risk_alerts: list[RiskAlert] = []
        self._daily_trade_count = 0
        self._daily_reset_time = time.time()
        self._emergency_stop_triggered = False

        # Risk limits per instrument
        self.max_position_sizes = risk_config.get("max_position_sizes", {})

        self.logger.info("RiskMonitor initialized with comprehensive risk controls")

    def check_all_risks(self, instruments: list[InstrumentId]) -> list[RiskAlert]:
        """
        Perform comprehensive risk assessment.
        
        Parameters
        ----------
        instruments : List[InstrumentId]
            Instruments to check
            
        Returns
        -------
        List[RiskAlert]
            List of current risk alerts
        """
        alerts = []
        snapshot = self.portfolio_monitor.get_latest_snapshot()

        if not snapshot:
            return alerts

        # Check daily loss limits
        alerts.extend(self._check_daily_loss_limits(snapshot))

        # Check drawdown limits
        alerts.extend(self._check_drawdown_limits(snapshot))

        # Check margin requirements
        alerts.extend(self._check_margin_requirements(snapshot))

        # Check position size limits
        alerts.extend(self._check_position_size_limits(snapshot, instruments))

        # Check exposure limits
        alerts.extend(self._check_exposure_limits(snapshot))

        # Check portfolio balance
        alerts.extend(self._check_portfolio_balance(snapshot))

        # Store new alerts
        for alert in alerts:
            self._risk_alerts.append(alert)
            self.logger.warning(f"RISK ALERT [{alert.level.value}] {alert.category}: {alert.message}")

        # Keep only recent alerts (last 100)
        if len(self._risk_alerts) > 100:
            self._risk_alerts = self._risk_alerts[-100:]

        return alerts

    def _check_daily_loss_limits(self, snapshot: PortfolioSnapshot) -> list[RiskAlert]:
        """Check daily loss limits."""
        alerts = []

        daily_pnl = snapshot.daily_pnl
        loss_pct = abs(daily_pnl) / snapshot.total_balance.get("USDT", 1) if daily_pnl < 0 else 0

        if daily_pnl < -self.max_daily_loss:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.CRITICAL,
                category="DAILY_LOSS",
                message=f"Daily loss limit exceeded: {daily_pnl:.2f} USD (limit: {self.max_daily_loss:.2f})",
                current_value=daily_pnl,
                threshold_value=-self.max_daily_loss,
                action_required="STOP_TRADING"
            ))
        elif daily_pnl < -self.max_daily_loss * 0.8:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.HIGH,
                category="DAILY_LOSS",
                message=f"Approaching daily loss limit: {daily_pnl:.2f} USD",
                current_value=daily_pnl,
                threshold_value=-self.max_daily_loss * 0.8,
                action_required="REDUCE_POSITIONS"
            ))

        return alerts

    def _check_drawdown_limits(self, snapshot: PortfolioSnapshot) -> list[RiskAlert]:
        """Check maximum drawdown limits."""
        alerts = []

        max_drawdown = snapshot.max_drawdown

        if max_drawdown > self.max_drawdown_pct:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.CRITICAL,
                category="DRAWDOWN",
                message=f"Maximum drawdown exceeded: {max_drawdown:.2%} (limit: {self.max_drawdown_pct:.2%})",
                current_value=max_drawdown,
                threshold_value=self.max_drawdown_pct,
                action_required="STOP_TRADING"
            ))
        elif max_drawdown > self.max_drawdown_pct * 0.8:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.HIGH,
                category="DRAWDOWN",
                message=f"Approaching drawdown limit: {max_drawdown:.2%}",
                current_value=max_drawdown,
                threshold_value=self.max_drawdown_pct * 0.8,
                action_required="REDUCE_RISK"
            ))

        return alerts

    def _check_margin_requirements(self, snapshot: PortfolioSnapshot) -> list[RiskAlert]:
        """Check margin requirements for futures trading."""
        alerts = []

        if snapshot.margin_ratio is None:
            return alerts

        margin_ratio = snapshot.margin_ratio

        if margin_ratio > self.margin_critical_threshold:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.CRITICAL,
                category="MARGIN",
                message=f"Critical margin usage: {margin_ratio:.1%} (critical: {self.margin_critical_threshold:.1%})",
                current_value=margin_ratio,
                threshold_value=self.margin_critical_threshold,
                action_required="CLOSE_POSITIONS"
            ))
        elif margin_ratio > self.margin_warning_threshold:
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.HIGH,
                category="MARGIN",
                message=f"High margin usage: {margin_ratio:.1%} (warning: {self.margin_warning_threshold:.1%})",
                current_value=margin_ratio,
                threshold_value=self.margin_warning_threshold,
                action_required="MONITOR_CLOSELY"
            ))

        return alerts

    def _check_position_size_limits(self, snapshot: PortfolioSnapshot,
                                  instruments: list[InstrumentId]) -> list[RiskAlert]:
        """Check individual position size limits."""
        alerts = []

        for instrument_id in instruments:
            instrument_str = str(instrument_id)
            position_value = abs(snapshot.net_exposures.get(instrument_str, 0))
            max_allowed = self.max_position_sizes.get(instrument_str, self.max_position_value)

            if position_value > max_allowed:
                alerts.append(RiskAlert(
                    timestamp=datetime.now(UTC),
                    level=RiskLevel.HIGH,
                    category="POSITION_SIZE",
                    message=f"Position size limit exceeded for {instrument_str}: {position_value:.2f} USD (limit: {max_allowed:.2f})",
                    instrument=instrument_str,
                    current_value=position_value,
                    threshold_value=max_allowed,
                    action_required="REDUCE_POSITION"
                ))

        return alerts

    def _check_exposure_limits(self, snapshot: PortfolioSnapshot) -> list[RiskAlert]:
        """Check total exposure limits."""
        alerts = []

        total_balance = snapshot.total_balance.get("USDT", 0)
        total_exposure = snapshot.total_exposure_usd

        if total_balance > 0:
            exposure_ratio = total_exposure / total_balance

            if exposure_ratio > 0.9:  # 90% of balance
                alerts.append(RiskAlert(
                    timestamp=datetime.now(UTC),
                    level=RiskLevel.HIGH,
                    category="EXPOSURE",
                    message=f"High total exposure: {exposure_ratio:.1%} of balance",
                    current_value=exposure_ratio,
                    threshold_value=0.9,
                    action_required="REDUCE_EXPOSURE"
                ))

        return alerts

    def _check_portfolio_balance(self, snapshot: PortfolioSnapshot) -> list[RiskAlert]:
        """Check portfolio balance health."""
        alerts = []

        total_balance = snapshot.total_balance.get("USDT", 0)
        free_balance = snapshot.free_balance.get("USDT", 0)

        if total_balance < 100:  # Minimum balance threshold
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.CRITICAL,
                category="BALANCE",
                message=f"Low account balance: {total_balance:.2f} USDT",
                current_value=total_balance,
                threshold_value=100,
                action_required="ADD_FUNDS"
            ))

        if total_balance > 0 and free_balance / total_balance < 0.1:  # Less than 10% free
            alerts.append(RiskAlert(
                timestamp=datetime.now(UTC),
                level=RiskLevel.MEDIUM,
                category="BALANCE",
                message=f"Low free balance: {free_balance:.2f} USDT ({free_balance/total_balance:.1%})",
                current_value=free_balance / total_balance,
                threshold_value=0.1,
                action_required="MANAGE_POSITIONS"
            ))

        return alerts

    def should_allow_new_position(self, instrument_id: InstrumentId, position_size: float) -> tuple[bool, str]:
        """
        Check if a new position should be allowed.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Instrument for the new position
        position_size : float
            Size of the new position
            
        Returns
        -------
        Tuple[bool, str]
            (allowed, reason)
        """
        if self._emergency_stop_triggered:
            return False, "Emergency stop triggered"

        # Check recent critical alerts
        recent_critical = [a for a in self._risk_alerts[-10:] if a.level == RiskLevel.CRITICAL]
        if recent_critical:
            return False, f"Critical risk alert active: {recent_critical[-1].message}"

        # Check daily trade limits
        if self._daily_trade_count >= 50:  # Configurable
            return False, "Daily trade limit exceeded"

        # Check position size
        instrument_str = str(instrument_id)
        max_allowed = self.max_position_sizes.get(instrument_str, self.max_position_value)
        if position_size > max_allowed:
            return False, f"Position size exceeds limit: {position_size:.2f} > {max_allowed:.2f}"

        return True, "Position allowed"

    def record_trade(self, instrument_id: InstrumentId) -> None:
        """Record a new trade for daily limits."""
        self._daily_trade_count += 1

        # Reset daily counter if new day
        if time.time() - self._daily_reset_time > 86400:  # 24 hours
            self._daily_trade_count = 1
            self._daily_reset_time = time.time()

    def trigger_emergency_stop(self, reason: str) -> None:
        """Trigger emergency stop."""
        self._emergency_stop_triggered = True
        self.logger.error(f"EMERGENCY STOP TRIGGERED: {reason}")

        alert = RiskAlert(
            timestamp=datetime.now(UTC),
            level=RiskLevel.CRITICAL,
            category="EMERGENCY_STOP",
            message=f"Emergency stop triggered: {reason}",
            action_required="MANUAL_INTERVENTION"
        )
        self._risk_alerts.append(alert)

    def reset_emergency_stop(self) -> None:
        """Reset emergency stop (manual intervention required)."""
        self._emergency_stop_triggered = False
        self.logger.info("Emergency stop reset - trading resumed")

    def get_risk_summary(self) -> dict:
        """Get current risk assessment summary."""
        recent_alerts = self._risk_alerts[-10:] if self._risk_alerts else []
        critical_count = len([a for a in recent_alerts if a.level == RiskLevel.CRITICAL])
        high_count = len([a for a in recent_alerts if a.level == RiskLevel.HIGH])

        return {
            "emergency_stop_active": self._emergency_stop_triggered,
            "recent_critical_alerts": critical_count,
            "recent_high_alerts": high_count,
            "daily_trade_count": self._daily_trade_count,
            "latest_alert": recent_alerts[-1].message if recent_alerts else None,
        }
