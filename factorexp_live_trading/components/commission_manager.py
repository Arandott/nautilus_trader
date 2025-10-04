"""
Dynamic Commission Rate Manager for FactorExp Live Trading

Professional component for managing real-time commission rates from Binance.
Replaces hardcoded commission rates with dynamic queries.
"""

import logging
from datetime import UTC
from datetime import datetime
from decimal import Decimal

from nautilus_trader.adapters.binance.futures.http.wallet import BinanceFuturesWalletHttpAPI
from nautilus_trader.adapters.binance.futures.schemas.wallet import BinanceFuturesCommissionRate
from nautilus_trader.model.identifiers import InstrumentId


class CommissionManager:
    """
    Professional commission rate management component.
    
    Features:
    - Dynamic commission rate queries from Binance
    - Maker/Taker rate distinction  
    - Intelligent caching with TTL
    - Fallback mechanisms for API failures
    - Comprehensive logging and monitoring
    """

    def __init__(
        self,
        wallet_api: BinanceFuturesWalletHttpAPI,
        logger: logging.Logger,
        cache_ttl_minutes: int = 60
    ):
        """
        Initialize commission manager.
        
        Parameters
        ----------
        wallet_api : BinanceFuturesWalletHttpAPI
            Binance wallet API for commission queries
        logger : logging.Logger
            Logger for monitoring and debugging
        cache_ttl_minutes : int
            Cache time-to-live in minutes
        """
        self._wallet_api = wallet_api
        self._logger = logger
        self._cache_ttl_minutes = cache_ttl_minutes

        # Commission rate cache: {symbol: (rates, timestamp)}
        self._rate_cache: dict[str, tuple[BinanceFuturesCommissionRate, datetime]] = {}

        # Fallback rates (industry standards)
        self._fallback_rates = {
            "maker": Decimal("0.0002"),  # 0.02% (VIP 1 level)
            "taker": Decimal("0.0004"),  # 0.04% (VIP 1 level)
        }

        self._logger.info("CommissionManager initialized with dynamic rate management")

    async def get_commission_rate(
        self,
        instrument_id: InstrumentId,
        is_maker: bool = False
    ) -> Decimal:
        """
        Get accurate commission rate for an instrument.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Trading instrument
        is_maker : bool
            True for maker orders (limit), False for taker orders (market)
            
        Returns
        -------
        Decimal
            Accurate commission rate
        """
        symbol = self._extract_symbol(instrument_id)

        try:
            # Check cache first
            rates = await self._get_cached_or_fetch_rates(symbol)

            if rates:
                rate = Decimal(rates.makerCommissionRate if is_maker else rates.takerCommissionRate)

                self._logger.debug(
                    f"Retrieved {('maker' if is_maker else 'taker')} rate for {symbol}: {rate:.4%}"
                )
                return rate
            else:
                # Fallback to industry standards
                fallback_rate = self._fallback_rates["maker" if is_maker else "taker"]
                self._logger.warning(
                    f"Using fallback {('maker' if is_maker else 'taker')} rate for {symbol}: {fallback_rate:.4%}"
                )
                return fallback_rate

        except Exception as e:
            # Emergency fallback
            fallback_rate = self._fallback_rates["taker"]  # Always use taker (higher rate) for safety
            self._logger.error(
                f"Commission rate query failed for {symbol}: {e}. "
                f"Using emergency fallback: {fallback_rate:.4%}"
            )
            return fallback_rate

    async def _get_cached_or_fetch_rates(self, symbol: str) -> BinanceFuturesCommissionRate | None:
        """
        Get rates from cache or fetch from API.
        
        Parameters
        ----------
        symbol : str
            Trading symbol (e.g., 'BTCUSDT')
            
        Returns
        -------
        Optional[BinanceFuturesCommissionRate]
            Commission rates or None if failed
        """
        now = datetime.now(UTC)

        # Check cache
        if symbol in self._rate_cache:
            rates, timestamp = self._rate_cache[symbol]
            age_minutes = (now - timestamp).total_seconds() / 60

            if age_minutes < self._cache_ttl_minutes:
                self._logger.debug(f"Using cached rates for {symbol} (age: {age_minutes:.1f}min)")
                return rates
            else:
                self._logger.debug(f"Cache expired for {symbol} (age: {age_minutes:.1f}min)")

        # Fetch fresh rates
        try:
            self._logger.info(f"Fetching commission rates for {symbol} from Binance API")
            rates = await self._wallet_api.query_futures_commission_rate(symbol)

            # Cache the results
            self._rate_cache[symbol] = (rates, now)

            self._logger.info(
                f"Commission rates updated for {symbol}: "
                f"maker={rates.makerCommissionRate}, taker={rates.takerCommissionRate}"
            )

            return rates

        except Exception as e:
            self._logger.error(f"Failed to fetch commission rates for {symbol}: {e}")
            return None

    def _extract_symbol(self, instrument_id: InstrumentId) -> str:
        """
        Extract symbol from instrument ID.
        
        Parameters
        ----------
        instrument_id : InstrumentId
            Nautilus instrument ID
            
        Returns
        -------
        str
            Binance symbol (e.g., 'BTCUSDT')
        """
        # Extract symbol from instrument ID (e.g., 'BTCUSDT-PERP.BINANCE' -> 'BTCUSDT')
        symbol = str(instrument_id).split("-")[0]
        return symbol

    def get_cached_rates_summary(self) -> dict[str, dict]:
        """
        Get summary of cached commission rates for monitoring.
        
        Returns
        -------
        Dict[str, Dict]
            Summary of cached rates
        """
        now = datetime.now(UTC)
        summary = {}

        for symbol, (rates, timestamp) in self._rate_cache.items():
            age_minutes = (now - timestamp).total_seconds() / 60
            summary[symbol] = {
                "maker_rate": rates.makerCommissionRate,
                "taker_rate": rates.takerCommissionRate,
                "cached_at": timestamp.isoformat(),
                "age_minutes": round(age_minutes, 1),
                "expired": age_minutes >= self._cache_ttl_minutes
            }

        return summary

    async def refresh_all_rates(self, symbols: list[str]) -> dict[str, bool]:
        """
        Force refresh of commission rates for multiple symbols.
        
        Parameters
        ----------
        symbols : list[str]
            List of symbols to refresh
            
        Returns
        -------
        Dict[str, bool]
            Success status for each symbol
        """
        results = {}

        for symbol in symbols:
            try:
                # Remove from cache to force refresh
                if symbol in self._rate_cache:
                    del self._rate_cache[symbol]

                rates = await self._get_cached_or_fetch_rates(symbol)
                results[symbol] = rates is not None

            except Exception as e:
                self._logger.error(f"Failed to refresh rates for {symbol}: {e}")
                results[symbol] = False

        self._logger.info(f"Commission rate refresh completed: {results}")
        return results


class CommissionCalculator:
    """
    Utility class for commission calculations using dynamic rates.
    """

    @staticmethod
    def calculate_total_commission(
        notional_value: Decimal,
        commission_rate: Decimal,
        is_round_turn: bool = True
    ) -> Decimal:
        """
        Calculate total commission cost.
        
        Parameters
        ----------
        notional_value : Decimal
            Notional value of the trade
        commission_rate : Decimal
            Commission rate (e.g., 0.0004 for 0.04%)
        is_round_turn : bool
            If True, double the commission for round-turn calculation
            
        Returns
        -------
        Decimal
            Total commission cost
        """
        commission = notional_value * commission_rate
        return commission * 2 if is_round_turn else commission

    @staticmethod
    def calculate_break_even_price(
        entry_price: Decimal,
        commission_rate: Decimal,
        is_long: bool = True
    ) -> Decimal:
        """
        Calculate break-even price including commissions.
        
        Parameters
        ----------
        entry_price : Decimal
            Entry price
        commission_rate : Decimal
            Commission rate
        is_long : bool
            True for long position, False for short
            
        Returns
        -------
        Decimal
            Break-even price
        """
        # Round-turn commission (entry + exit)
        total_commission_rate = commission_rate * 2

        if is_long:
            # Long: need price to rise to cover commissions
            return entry_price * (1 + total_commission_rate)
        else:
            # Short: need price to fall to cover commissions
            return entry_price * (1 - total_commission_rate)
