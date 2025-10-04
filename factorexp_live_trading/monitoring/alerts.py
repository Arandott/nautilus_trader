"""
Alert management system for FactorExp live trading.
Handles email, webhook, and console notifications.
"""

import asyncio
import os
from datetime import UTC
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiohttp
import aiosmtplib
from jinja2 import Template

from monitoring.risk_monitor import RiskAlert
from monitoring.risk_monitor import RiskLevel
from nautilus_trader.common.component import Logger


class AlertManager:
    """
    Comprehensive alert management for FactorExp live trading.
    
    Supports multiple notification channels:
    - Console logging
    - Email notifications
    - Webhook notifications
    - File logging
    """

    def __init__(self, logger: Logger):
        self.logger = logger

        # Email configuration
        self.email_enabled = os.getenv("ENABLE_EMAIL_ALERTS", "false").lower() == "true"
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")

        # Webhook configuration
        self.webhook_enabled = os.getenv("ENABLE_WEBHOOK_ALERTS", "false").lower() == "true"
        self.webhook_url = os.getenv("WEBHOOK_URL", "")

        # Alert rate limiting
        self._alert_counts = {}
        self._last_alert_times = {}

        self.logger.info(f"AlertManager initialized - Email: {self.email_enabled}, Webhook: {self.webhook_enabled}")

    async def send_alert(self, alert: RiskAlert, portfolio_summary: dict | None = None) -> None:
        """
        Send alert through all configured channels.
        
        Parameters
        ----------
        alert : RiskAlert
            The alert to send
        portfolio_summary : Optional[Dict]
            Current portfolio summary for context
        """
        # Rate limiting - prevent spam
        alert_key = f"{alert.category}_{alert.level.value}"
        current_time = datetime.now(UTC)

        if self._should_rate_limit(alert_key, current_time):
            return

        # Update rate limiting counters
        self._alert_counts[alert_key] = self._alert_counts.get(alert_key, 0) + 1
        self._last_alert_times[alert_key] = current_time

        # Send through all enabled channels
        await asyncio.gather(
            self._send_console_alert(alert),
            self._send_email_alert(alert, portfolio_summary) if self.email_enabled else self._noop(),
            self._send_webhook_alert(alert, portfolio_summary) if self.webhook_enabled else self._noop(),
        )

    async def _send_console_alert(self, alert: RiskAlert) -> None:
        """Send alert to console/logs."""
        level_colors = {
            RiskLevel.LOW: "blue",
            RiskLevel.MEDIUM: "yellow",
            RiskLevel.HIGH: "red",
            RiskLevel.CRITICAL: "magenta"
        }

        message = (
            f"🚨 ALERT [{alert.level.value}] {alert.category} 🚨\\n"
            f"Time: {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\\n"
            f"Message: {alert.message}\\n"
        )

        if alert.instrument:
            message += f"Instrument: {alert.instrument}\\n"
        if alert.current_value is not None:
            message += f"Current: {alert.current_value}\\n"
        if alert.threshold_value is not None:
            message += f"Threshold: {alert.threshold_value}\\n"
        if alert.action_required:
            message += f"Action Required: {alert.action_required}\\n"

        if alert.level in [RiskLevel.CRITICAL, RiskLevel.HIGH]:
            self.logger.error(message)
        elif alert.level == RiskLevel.MEDIUM:
            self.logger.warning(message)
        else:
            self.logger.info(message)

    async def _send_email_alert(self, alert: RiskAlert, portfolio_summary: dict | None) -> None:
        """Send alert via email."""
        if not self.smtp_user or not self.smtp_password:
            return

        try:
            # Create email content
            subject = f"FactorExp Trading Alert [{alert.level.value}] - {alert.category}"

            email_template = Template("""
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .alert-header { background-color: {{ alert_color }}; color: white; padding: 10px; border-radius: 5px; }
        .alert-critical { background-color: #dc3545; }
        .alert-high { background-color: #fd7e14; }
        .alert-medium { background-color: #ffc107; color: black; }
        .alert-low { background-color: #17a2b8; }
        .content { margin: 20px 0; }
        .portfolio-summary { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 20px; }
        .footer { margin-top: 30px; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="alert-header alert-{{ alert.level.value.lower() }}">
        <h2>🚨 Trading Alert: {{ alert.category }}</h2>
        <p>Level: {{ alert.level.value }}</p>
    </div>
    
    <div class="content">
        <p><strong>Time:</strong> {{ alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') }}</p>
        <p><strong>Message:</strong> {{ alert.message }}</p>
        
        {% if alert.instrument %}
        <p><strong>Instrument:</strong> {{ alert.instrument }}</p>
        {% endif %}
        
        {% if alert.current_value is not none %}
        <p><strong>Current Value:</strong> {{ "%.4f"|format(alert.current_value) }}</p>
        {% endif %}
        
        {% if alert.threshold_value is not none %}
        <p><strong>Threshold:</strong> {{ "%.4f"|format(alert.threshold_value) }}</p>
        {% endif %}
        
        {% if alert.action_required %}
        <p><strong>Action Required:</strong> <em>{{ alert.action_required }}</em></p>
        {% endif %}
    </div>
    
    {% if portfolio_summary %}
    <div class="portfolio-summary">
        <h3>Portfolio Summary</h3>
        <p><strong>Balance:</strong> {{ "%.2f"|format(portfolio_summary.get('total_balance_usdt', 0)) }} USDT</p>
        <p><strong>Total PnL:</strong> {{ "%.2f"|format(portfolio_summary.get('total_pnl_usdt', 0)) }} USDT ({{ "%.2%"|format(portfolio_summary.get('total_pnl_pct', 0)) }})</p>
        <p><strong>Positions:</strong> {{ portfolio_summary.get('position_count', 0) }}</p>
        <p><strong>Exposure:</strong> {{ "%.2f"|format(portfolio_summary.get('total_exposure_usd', 0)) }} USD</p>
        {% if portfolio_summary.get('margin_ratio') %}
        <p><strong>Margin Ratio:</strong> {{ "%.1%"|format(portfolio_summary.get('margin_ratio', 0)) }}</p>
        {% endif %}
    </div>
    {% endif %}
    
    <div class="footer">
        <p>This alert was generated by FactorExp Live Trading System</p>
        <p>Please review your trading strategy and take appropriate action if required.</p>
    </div>
</body>
</html>
            """)

            html_content = email_template.render(
                alert=alert,
                portfolio_summary=portfolio_summary,
                alert_color=self._get_alert_color(alert.level)
            )

            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.smtp_user  # Send to self by default

            html_part = MIMEText(html_content, "html")
            msg.attach(html_part)

            # Send email
            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=True,
                username=self.smtp_user,
                password=self.smtp_password,
            )

            self.logger.info(f"Email alert sent for {alert.category}")

        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")

    async def _send_webhook_alert(self, alert: RiskAlert, portfolio_summary: dict | None) -> None:
        """Send alert via webhook."""
        if not self.webhook_url:
            return

        try:
            payload = {
                "timestamp": alert.timestamp.isoformat(),
                "level": alert.level.value,
                "category": alert.category,
                "message": alert.message,
                "instrument": alert.instrument,
                "current_value": alert.current_value,
                "threshold_value": alert.threshold_value,
                "action_required": alert.action_required,
                "portfolio_summary": portfolio_summary,
                "source": "factorexp_live_trading"
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        self.logger.info(f"Webhook alert sent for {alert.category}")
                    else:
                        self.logger.warning(f"Webhook alert failed with status {response.status}")

        except Exception as e:
            self.logger.error(f"Failed to send webhook alert: {e}")

    def _should_rate_limit(self, alert_key: str, current_time: datetime) -> bool:
        """Check if alert should be rate limited."""
        # Rate limiting rules:
        # - CRITICAL: No rate limiting
        # - HIGH: Max 1 per 5 minutes
        # - MEDIUM: Max 1 per 15 minutes
        # - LOW: Max 1 per 30 minutes

        if "CRITICAL" in alert_key:
            return False

        last_time = self._last_alert_times.get(alert_key)
        if not last_time:
            return False

        time_diff = (current_time - last_time).total_seconds()

        if "HIGH" in alert_key and time_diff < 300:  # 5 minutes
            return True
        elif "MEDIUM" in alert_key and time_diff < 900:  # 15 minutes
            return True
        elif "LOW" in alert_key and time_diff < 1800:  # 30 minutes
            return True

        return False

    def _get_alert_color(self, level: RiskLevel) -> str:
        """Get color for alert level."""
        colors = {
            RiskLevel.CRITICAL: "#dc3545",
            RiskLevel.HIGH: "#fd7e14",
            RiskLevel.MEDIUM: "#ffc107",
            RiskLevel.LOW: "#17a2b8"
        }
        return colors.get(level, "#17a2b8")

    async def _noop(self) -> None:
        """No-op coroutine for disabled channels."""

    async def send_startup_notification(self) -> None:
        """Send notification when trading system starts."""
        startup_alert = RiskAlert(
            timestamp=datetime.now(UTC),
            level=RiskLevel.LOW,
            category="SYSTEM",
            message="FactorExp live trading system started successfully",
            action_required="MONITOR"
        )
        await self.send_alert(startup_alert)

    async def send_shutdown_notification(self) -> None:
        """Send notification when trading system shuts down."""
        shutdown_alert = RiskAlert(
            timestamp=datetime.now(UTC),
            level=RiskLevel.MEDIUM,
            category="SYSTEM",
            message="FactorExp live trading system shutdown",
            action_required="VERIFY"
        )
        await self.send_alert(shutdown_alert)
