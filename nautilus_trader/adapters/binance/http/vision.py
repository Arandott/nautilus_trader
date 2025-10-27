"""
Async helpers for downloading historical Binance data from https://data.binance.vision.

The implementation mirrors the behaviour used by freqtrade, but returns native
Nautilus types so the rest of the adapter can stitch results together with
REST-based fallbacks.
"""

from __future__ import annotations

import asyncio
import csv
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO, TextIOWrapper
from typing import Iterable, Sequence
from zipfile import ZipFile

import aiohttp

from nautilus_trader.adapters.binance.common.enums import BinanceAccountType, BinanceKlineInterval
from nautilus_trader.adapters.binance.common.schemas.market import BinanceAggTrade, BinanceKline
from nautilus_trader.adapters.binance.common.types import BinanceBar
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.model.data import BarType, TradeTick
from nautilus_trader.model.identifiers import InstrumentId


logger = logging.getLogger(__name__)

BINANCE_VISION_BASE_URL = "https://data.binance.vision"
VISION_BAR_ROUTE = "klines"
VISION_AGG_TRADES_ROUTE = "aggTrades"
VISION_CUTOFF = timedelta(days=2)  # Binance Vision lags ~48h

_VISION_SESSION_TIMEOUT = aiohttp.ClientTimeout(total=60)


class BinanceVisionError(Exception):
    """Base class for Binance Vision download problems."""


class BinanceVisionNotFound(BinanceVisionError):
    """Raised when a requested day is missing (HTTP 404)."""


@dataclass(slots=True)
class VisionBarsResult:
    bars: list[BinanceBar]
    last_open_time_ms: int | None


@dataclass(slots=True)
class VisionAggTradesResult:
    ticks: list[TradeTick]
    last_trade_id: int | None
    last_timestamp_ms: int | None


def _segment_for_account(account_type: BinanceAccountType) -> str:
    if account_type.is_spot_or_margin:
        return "spot"
    if account_type == BinanceAccountType.USDT_FUTURE:
        return "futures/um"
    if account_type == BinanceAccountType.COIN_FUTURE:
        return "futures/cm"
    raise ValueError(f"Unsupported BinanceAccountType for vision download: {account_type}")


def _date_range(start: datetime, end: datetime) -> Iterable[datetime]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _clip_end(timestamp_ms: int | None) -> int:
    now = datetime.now(timezone.utc)
    cutoff = now - VISION_CUTOFF
    cutoff_ms = int(cutoff.timestamp() * 1000)
    if timestamp_ms is None:
        return cutoff_ms
    return min(timestamp_ms, cutoff_ms)


def _ms_to_utc_date(timestamp_ms: int) -> datetime:
    return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)


async def _fetch_zip(session: aiohttp.ClientSession, url: str) -> ZipFile:
    try:
        async with session.get(url) as response:
            if response.status == 404:
                raise BinanceVisionNotFound(f"404 for {url}")
            response.raise_for_status()
            body = await response.read()
    except aiohttp.ClientResponseError as exc:  # pragma: no cover - network errors
        logger.warning("Vision request failed for %s: %s", url, exc)
        raise BinanceVisionError(f"Vision request failed for {url}") from exc
    except aiohttp.ClientError as exc:  # pragma: no cover - network errors
        logger.warning("Vision request error for %s: %s", url, exc)
        raise BinanceVisionError(f"Vision request error for {url}") from exc

    return ZipFile(BytesIO(body))


def _read_csv_rows(zf: ZipFile) -> Sequence[list[str]]:
    name = zf.namelist()[0]
    with zf.open(name) as file_handle:
        wrapper = TextIOWrapper(file_handle, encoding="utf-8")
        reader = csv.reader(wrapper)
        rows: list[list[str]] = []
        for row in reader:
            if not row:
                continue
            if row[0].lower() == "open_time" or row[0].lower() == "id":
                # Skip header rows when present
                continue
            rows.append(row)

    return rows


def _render_progress_bar(current: int, total: int, width: int = 20) -> str:
    if total <= 0:
        return "[####################] 100.0% (0/0)"
    fraction = min(max(current / total, 0.0), 1.0)
    filled = min(width, max(0, int(round(fraction * width))))
    if filled == 0 and current > 0:
        filled = 1
    bar = "#" * filled + "." * (width - filled)
    return f"[{bar}] {fraction * 100:5.1f}% ({current}/{total})"


def _log_vision_progress(
    kind: str,
    symbol: str,
    current: int,
    total: int,
    *,
    progress_logger: logging.Logger | None = None,
) -> None:
    progress = _render_progress_bar(current, total)
    target_logger = progress_logger or logger
    target_logger.info("Vision %s download progress for %s %s", kind, symbol, progress)


async def download_vision_bars(
    *,
    account_type: BinanceAccountType,
    vision_symbol: str,
    interval: BinanceKlineInterval,
    bar_type: BarType,
    ts_init: int,
    start_ms: int,
    end_ms: int | None,
    progress_logger: logging.Logger | None = None,
) -> VisionBarsResult:
    """Download Binance Vision klines and return as `BinanceBar` instances."""
    if start_ms is None:  # Defensive: vision needs explicit start
        return VisionBarsResult([], None)

    clipped_end = _clip_end(end_ms)
    if start_ms >= clipped_end:
        return VisionBarsResult([], None)

    start_date = _ms_to_utc_date(start_ms).date()
    end_date = _ms_to_utc_date(clipped_end - 1).date()

    segment = _segment_for_account(account_type)
    base_url = f"{BINANCE_VISION_BASE_URL}/data/{segment}/daily/{VISION_BAR_ROUTE}"
    url_prefix = f"{base_url}/{vision_symbol}/{interval.value}"

    bars: list[BinanceBar] = []
    last_open_time_ms: int | None = None
    total_days = max((end_date - start_date).days + 1, 1)
    processed_days = 0

    async with aiohttp.ClientSession(timeout=_VISION_SESSION_TIMEOUT) as session:
        async def _download_day(day: datetime) -> None:
            nonlocal last_open_time_ms
            date_str = day.strftime("%Y-%m-%d")
            url = f"{url_prefix}/{vision_symbol}-{interval.value}-{date_str}.zip"
            try:
                zf = await _fetch_zip(session, url)
            except BinanceVisionNotFound as exc:
                raise exc
            except BinanceVisionError:
                logger.warning(
                    "Skipping Vision klines for %s %s due to error.", vision_symbol, date_str
                )
                return

            for row in _read_csv_rows(zf):
                try:
                    open_time = int(row[0])
                    close_time = int(row[6])
                except (ValueError, IndexError):
                    continue
                if open_time < start_ms or open_time >= clipped_end:
                    continue
                kline = BinanceKline(
                    open_time=open_time,
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                    close_time=close_time,
                    asset_volume=row[7],
                    trades_count=int(row[8]),
                    taker_base_volume=row[9],
                    taker_quote_volume=row[10],
                    ignore=row[11] if len(row) > 11 else "0",
                )
                bars.append(kline.parse_to_binance_bar(bar_type=bar_type, ts_init=ts_init))
                last_open_time_ms = open_time

        try:
            for day in _date_range(
                datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
                datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc),
            ):
                try:
                    await _download_day(day)
                except BinanceVisionNotFound:
                    if day.date() == start_date:
                        raise
                    logger.info("Vision klines missing from %s onwards for %s, stopping.", day.date(), vision_symbol)
                    break
                else:
                    processed_days += 1
                    _log_vision_progress(
                        kind=f"klines {interval.value}",
                        symbol=vision_symbol,
                        current=processed_days,
                        total=total_days,
                        progress_logger=progress_logger,
                    )
        except BinanceVisionNotFound:
            # Surface to caller so REST fallback can kick in immediately
            raise

    bars.sort(key=lambda bar: bar.ts_event)
    return VisionBarsResult(bars=bars, last_open_time_ms=last_open_time_ms)


def _parse_bool(value: str) -> bool:
    return value.lower() in {"true", "1"}


async def download_vision_agg_trade_ticks(
    *,
    account_type: BinanceAccountType,
    instrument_id: InstrumentId,
    vision_symbol: str,
    ts_init: int,
    start_ms: int,
    end_ms: int | None,
    progress_logger: logging.Logger | None = None,
) -> VisionAggTradesResult:
    """Download Binance Vision aggregate trades and map to `TradeTick`s."""
    if start_ms is None:
        return VisionAggTradesResult([], None, None)

    clipped_end = _clip_end(end_ms)
    if start_ms >= clipped_end:
        return VisionAggTradesResult([], None, None)

    start_date = _ms_to_utc_date(start_ms).date()
    end_date = _ms_to_utc_date(clipped_end - 1).date()

    segment = _segment_for_account(account_type)
    base_url = f"{BINANCE_VISION_BASE_URL}/data/{segment}/daily/{VISION_AGG_TRADES_ROUTE}"
    url_prefix = f"{base_url}/{vision_symbol}"

    ticks: list[TradeTick] = []
    last_trade_id: int | None = None
    last_timestamp_ms: int | None = None
    total_days = max((end_date - start_date).days + 1, 1)
    processed_days = 0

    async with aiohttp.ClientSession(timeout=_VISION_SESSION_TIMEOUT) as session:
        async def _download_day(day: datetime) -> None:
            nonlocal last_trade_id, last_timestamp_ms
            date_str = day.strftime("%Y-%m-%d")
            url = f"{url_prefix}/{vision_symbol}-aggTrades-{date_str}.zip"
            try:
                zf = await _fetch_zip(session, url)
            except BinanceVisionNotFound as exc:
                raise exc
            except BinanceVisionError:
                logger.warning("Skipping Vision aggTrades for %s %s due to error.", vision_symbol, date_str)
                return

            for row in _read_csv_rows(zf):
                try:
                    agg_trade = BinanceAggTrade(
                        a=int(row[0]),
                        p=row[1],
                        q=row[2],
                        f=int(row[3]),
                        l=int(row[4]),
                        T=int(row[5]),
                        m=_parse_bool(row[6]),
                        M=_parse_bool(row[7]) if len(row) > 7 else None,
                    )
                except (ValueError, IndexError):
                    continue

                if agg_trade.T < start_ms or agg_trade.T >= clipped_end:
                    continue

                ticks.append(
                    agg_trade.parse_to_trade_tick(
                        instrument_id=instrument_id,
                        ts_init=ts_init,
                    )
                )
                last_trade_id = agg_trade.a
                last_timestamp_ms = agg_trade.T

        try:
            for day in _date_range(
                datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc),
                datetime.combine(end_date, datetime.min.time(), tzinfo=timezone.utc),
            ):
                try:
                    await _download_day(day)
                except BinanceVisionNotFound:
                    if day.date() == start_date:
                        raise
                    logger.info("Vision aggTrades missing from %s onwards for %s, stopping.", day.date(), vision_symbol)
                    break
                else:
                    processed_days += 1
                    _log_vision_progress(
                        kind="aggTrades",
                        symbol=vision_symbol,
                        current=processed_days,
                        total=total_days,
                        progress_logger=progress_logger,
                    )
        except BinanceVisionNotFound:
            raise

    ticks.sort(key=lambda tick: tick.ts_event)
    return VisionAggTradesResult(
        ticks=ticks,
        last_trade_id=last_trade_id,
        last_timestamp_ms=last_timestamp_ms,
    )
