#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Iterator, TypeVar
from numpy import isnan, nan

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:
    raise SystemExit("pyarrow is required to write Parquet output.") from exc

from nautilus_trader.adapters.tardis import TardisCSVDataLoader
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import OrderBookDepth10
from nautilus_trader.model.data import OrderBookDeltas
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import InstrumentId


def _ts_to_date(ts_ns: int) -> dt.date:
    return dt.datetime.utcfromtimestamp(ts_ns / 1_000_000_000).date()


T = TypeVar("T")
BookUpdate = OrderBookDepth10 | OrderBookDeltas


def _iter_stream(stream: Iterator[list[T]]) -> Iterator[T]:
    for chunk in stream:
        for item in chunk:
            yield item


def _next_or_none(items: Iterator[T]) -> T | None:
    try:
        return next(items)
    except StopIteration:
        return None


def _merge_by_ts(
    book_updates: Iterator[BookUpdate],
    trades: Iterator[TradeTick],
) -> Iterator[BookUpdate | TradeTick]:
    # Assumes each stream is already ordered by ts_init (Tardis CSV order).
    book_update = _next_or_none(book_updates)
    trade = _next_or_none(trades)
    while book_update is not None or trade is not None:
        if trade is None or (book_update is not None and book_update.ts_init <= trade.ts_init):
            yield book_update
            book_update = _next_or_none(book_updates)
        else:
            yield trade
            trade = _next_or_none(trades)


def _price_to_float(price) -> float | None:
    if price is None:
        return None
    return price.as_double()

def safe_div(a, b) -> float | None:
    if b is None or isnan(b) or abs(b) > 1e-5:
        return nan
    return a/b 


class SharedState:
    def __init__(self) -> None:
        self.mid_price: float | None = None
        self.mid_price_prev: float | None = None
        self.last_trade_price: float | None = None
        self.last_event_type: str | None = None
        self.last_ts_event: int | None = None
        self.last_ts_init: int | None = None
        self.bid_levels, self.ask_levels = None, None

    def _roll_mid(self, mid_price: float | None) -> None:
        self.mid_price_prev = self.mid_price
        self.mid_price = mid_price

    def _serilize_book(self, book: OrderBook) -> None:
        self.bid_levels = book.bids()
        self.ask_levels = book.asks()

    def on_book(self, book: OrderBook, ts_event: int, ts_init: int) -> None:
        self._roll_mid(book.midpoint())
        self._serilize_book(book)
        self.last_event_type = "book"
        self.last_ts_event = ts_event
        self.last_ts_init = ts_init

    def on_trade(self, trade: TradeTick, book: OrderBook | None) -> None:
        self.last_trade_price = trade.price.as_double()
        mid_price = book.midpoint() if book else None
        self._roll_mid(mid_price)
        self.last_event_type = "trade"
        self.last_ts_event = trade.ts_event
        self.last_ts_init = trade.ts_init


class FactorBase:
    name: str = "factor"

    def __init__(self, state: SharedState, book: OrderBook) -> None:
        self._state = state
        self._book = book
        self._value: float | nan = nan

    @property
    def names(self) -> list[str]:
        return [self.name]

    def on_book(self, update: BookUpdate) -> None:
        pass

    def on_trade(self, trade: TradeTick) -> None:
        pass

    def reset(self) -> None:
        self._value = None

    def dump(self) -> dict[str, float | None]:
        result = {self.name: self._value}
        self.reset()
        return result


class FactorCluster(FactorBase):
    def __init__(self, state: SharedState, book: OrderBook, names: list[str]) -> None:
        if not names:
            raise ValueError("FactorCluster requires at least one factor name.")
        if len(set(names)) != len(names):
            raise ValueError("FactorCluster factor names must be unique.")
        super().__init__(state, book)
        self._names = list(names)
        self._values: dict[str, float | nan] = {name: nan for name in self._names}

    @property
    def names(self) -> list[str]:
        return list(self._names)

    def __len__(self) -> int:
        return len(self._names)

    def set_value(self, name: str, value: float | nan) -> None:
        if name not in self._values:
            raise KeyError(f"Unknown factor name '{name}' in cluster.")
        self._values[name] = value

    def set_values(self, values: dict[str, float | nan]) -> None:
        unknown = set(values).difference(self._values)
        if unknown:
            unknown_list = ", ".join(sorted(unknown))
            raise KeyError(f"Unknown factor name(s) in cluster: {unknown_list}.")
        self._values.update(values)

    def reset(self) -> None:
        self._values = {name: nan for name in self._names}

    def dump(self) -> dict[str, float | None]:
        result = dict(self._values)
        self.reset()
        return result


class MidReturnFactor(FactorBase):
    name = "mid_return_1"

    def _update(self) -> None:
        mid = self._state.mid_price
        prev = self._state.mid_price_prev
        if mid is None or prev is None or prev == 0.0:
            self._value = nan
        else:
            self._value = (mid / prev) - 1.0

    def on_book(self, update: BookUpdate) -> None:
        self._update()

    def on_trade(self, trade: TradeTick) -> None:
        self._update()


class RustEmaFactor(FactorBase):
    def __init__(self, state: SharedState, book: OrderBook, period: int) -> None:
        super().__init__(state, book)
        self._ema = ExponentialMovingAverage(period)
        self.name = f"rust_ema_mid_{period}"

    def _update(self) -> None:
        mid = self._state.mid_price
        if mid is None:
            return
        self._ema.update_raw(mid)

    def on_book(self, update: BookUpdate) -> None:
        self._update()

    def reset(self) -> None:
        self._ema.reset()
        super().reset()

    def dump(self) -> dict[str, float | None]:
        value = self._ema.value if self._ema.initialized else None
        self.reset()
        return {self.name: value}


class PythonImbalanceFactor(FactorBase):
    name = "py_imbalance_l1"

    def _update(self) -> None:
        bid_levels = self._book.bids()
        ask_levels = self._book.asks()
        if not bid_levels or not ask_levels:
            self._value = nan
            return
        bid_size = bid_levels[0].size()
        ask_size = ask_levels[0].size()
        denom = bid_size + ask_size
        if denom == 0.0:
            self._value = 0.0
        else:
            self._value = (bid_size - ask_size) / denom

    def on_book(self, update: BookUpdate) -> None:
        self._update()

    def on_trade(self, trade: TradeTick) -> None:
        self._update()

class OrderbookVolumeCls(FactorCluster):
    def __init__(self, state: SharedState, book: OrderBook) -> None:
        self.factor_names = [
                "orderbook@vol@bid@l1",
                "orderbook@vol@ask@l1",
                "orderbook@vol@bid@l5",
                "orderbook@vol@ask@l5",
                "orderbook@vol@bid@l10",
                "orderbook@vol@ask@l10",
                "orderbook@vol@total@l10"
        ]
        self.MAX_LEVELS = 10
        super.__init__(self, book, factor_names)

    def on_book(self, update: BookUpdate) -> None:
        bid_levels = self._state.bid_levels
        ask_levels = self._state.ask_levels
        if not bid_levels or not ask_levels:
            self.set_values(
                    {k: nan for k in self.factor_names}
            )
            return

        bid_levels_num = len(bid_levels)
        ask_levels_num = len(ask_levels)
        bid_levels_num = min(self.MAX_LEVELS, bid_levels_num)
        ask_levels_num = min(self.MAX_LEVELS, bid_levels_num)
        max_levels = min(bid_levels, ask_levels)

        factors = [nan] * len(self)
        fidx = 0
        for n in [1, 5, 10]:
            bv, av = 0, 0
            for lvl in bid_levels[:min(n, max_levels)]:
                bv += lvl.size()
            for lvl in ask_levels[:min(n, max_levels)]:
                av += lvl.size()
            factors[fidx] = bv
            fidx += 1
            factors[fidx] = av
            fidx += 1
        total_volume = bv + av # 10 lvl total
        factors[fidx] = bv + av
        for i in range(len(factors)-1):
            factors[i] = safe_div(factors[i], total_volume)
        
        self.set_values({
            self.names[i]: factors[i] for i in range(len(self))
            }
        )



    
            



class OrderbookVolumeImbCls(FactorCluster):
    def __init__(self, state: SharedState, book: OrderBook) -> None:
        self.factor_names = [
            "orderbook_imb@vol@l1",
            "orderbook_imb@vol@l5",
            "orderbook_imb@vol@l10",
        ]
        self.MAX_LEVELS=10
        super().__init__(state, book, factor_names)

    def _update_values(self) -> None:
        bid_levels = self._state.bid_levels
        ask_levels = self._state.ask_levels
        if not bid_levels or not ask_levels:
            self.set_values(
                    {k: nan for k in self.factor_names}
            )
            return

        bid_levels_num = len(bid_levels)
        ask_levels_num = len(ask_levels)
        bid_levels_num = min(self.MAX_LEVELS, bid_levels_num)
        ask_levels_num = min(self.MAX_LEVELS, bid_levels_num)
        max_levels = min(bid_levels, ask_levels)

        factors = [nan] * len(self)
        fidx = 0

        # 1-lvl vol imb
        bv, av = 0, 0
        for lvl in bid_levels[:min(1, max_levels)]:
            bv += lvl.size()
        for lvl in ask_levels[:min(1, max_levels)]:
            av += lvl.size()
        factors[fidx] = (safe_div(bv-av, bv+av))
        fidx += 1

        # 5-lvl vol imb
        bv, av = 0, 0
        for lvl in bid_levels[:min(5, max_levels)]:
            bv += lvl.size()
        for lvl in ask_levels[:min(5, max_levels)]:
            av += lvl.size()
        factors[fidx] = (safe_div(bv-av, bv+av))
        fidx += 1

        # 10-lvl vol imb
        bv, av = 0, 0
        for lvl in bid_levels[:min(10, max_levels)]:
            bv += lvl.size()
        for lvl in ask_levels[:min(10, max_levels)]:
            av += lvl.size()
        factors[fidx] = (safe_div(bv-av, bv+av))
        fidx += 1
        
        self.set_values(
            {
                self.factor_names[i]: factors[i] for i in range(len(self))
            },
        )

    def on_book(self, update: BookUpdate) -> None:
        self._update_values()

    def on_trade(self, trade: TradeTick) -> None:
        pass

class BookImbalanceFactor(FactorBase):
    name = "book_imbalance"

    def __init__(
        self,
        state: SharedState,
        book: OrderBook,
        max_levels: int | None,
    ) -> None:
        super().__init__(state, book)
        self._max_levels = max_levels

    def _update(self) -> None:
        bid_levels = self._book.bids()
        ask_levels = self._book.asks()
        if self._max_levels is not None:
            bid_levels = bid_levels[: self._max_levels]
            ask_levels = ask_levels[: self._max_levels]
        if not bid_levels or not ask_levels:
            self._value = None
            return
        bid_size = sum(level.size() for level in bid_levels)
        ask_size = sum(level.size() for level in ask_levels)
        denom = bid_size + ask_size
        if denom == 0.0:
            self._value = 0.0
        else:
            self._value = (bid_size - ask_size) / denom

    def on_book(self, update: BookUpdate) -> None:
        self._update()

    def on_trade(self, trade: TradeTick) -> None:
        self._update()


class FactorEngine:
    def __init__(self, factors: list[FactorBase]) -> None:
        self._factors = factors
        factor_names: list[str] = []
        seen: set[str] = set()
        for factor in factors:
            for name in factor.names:
                if name in seen:
                    raise ValueError(f"Duplicate factor name: {name}")
                seen.add(name)
                factor_names.append(name)
        self.factor_names = factor_names

    def on_book(self, update: BookUpdate) -> None:
        for factor in self._factors:
            factor.on_book(update)

    def on_trade(self, trade: TradeTick) -> None:
        for factor in self._factors:
            factor.on_trade(trade)

    def dump(self) -> dict[str, float | None]:
        result: dict[str, float | None] = {}
        for factor in self._factors:
            result.update(factor.dump())
        return result


class UnifiedBookEngine:
    def __init__(self, book: OrderBook, state: SharedState, factors: FactorEngine) -> None:
        self.book = book
        self.state = state
        self.factors = factors

    def on_book_update(self, update: BookUpdate) -> None:
        if isinstance(update, OrderBookDepth10):
            self.book.apply_depth(update)
            ts_event = update.ts_event
            ts_init = update.ts_init
        else:
            self.book.apply_deltas(update)
            ts_event = update.ts_event
            ts_init = update.ts_init
        self.state.on_book(self.book, ts_event, ts_init)
        self.factors.on_book(update)

    def on_trade(self, trade: TradeTick) -> None:
        self.state.on_trade(trade, self.book)
        self.factors.on_trade(trade)


class ParquetFactorSink:
    def __init__(self, path: Path, factor_names: list[str]) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            pa.field("instrument", pa.string()),
            pa.field("event_type", pa.string()),
            pa.field("exchange_ts", pa.int64()),
            pa.field("recv_ts", pa.int64()),
            pa.field("date", pa.date32()),
            pa.field("mid_price", pa.float64()),
            pa.field("mid_price_prev", pa.float64()),
            pa.field("last_trade_price", pa.float64()),
            pa.field("best_bid", pa.float64()),
            pa.field("best_ask", pa.float64()),
        ]
        for name in factor_names:
            fields.append(pa.field(name, pa.float64()))
        self._factor_names = list(factor_names)
        self._schema = pa.schema(fields)
        self.rows = 0
        self._columns: dict[str, list[object]] = {name: [] for name in self._schema.names}

    def write(
        self,
        instrument: str,
        event_type: str,
        exchange_ts: int,
        recv_ts: int,
        date: dt.date,
        mid_price: float | None,
        mid_price_prev: float | None,
        last_trade_price: float | None,
        best_bid: float | None,
        best_ask: float | None,
        factor_values: dict[str, float | None],
    ) -> None:
        self._columns["instrument"].append(instrument)
        self._columns["event_type"].append(event_type)
        self._columns["exchange_ts"].append(exchange_ts)
        self._columns["recv_ts"].append(recv_ts)
        self._columns["date"].append(date)
        self._columns["mid_price"].append(mid_price)
        self._columns["mid_price_prev"].append(mid_price_prev)
        self._columns["last_trade_price"].append(last_trade_price)
        self._columns["best_bid"].append(best_bid)
        self._columns["best_ask"].append(best_ask)
        for name in self._factor_names:
            self._columns[name].append(factor_values.get(name))
        self.rows += 1

    def close(self) -> None:
        if not self.rows:
            return
        arrays = [
            pa.array(self._columns[name], type=self._schema.field(name).type)
            for name in self._schema.names
        ]
        table = pa.Table.from_arrays(arrays, schema=self._schema)
        pq.write_table(table, self._path)


class Sampler:
    def __init__(
        self,
        engine: UnifiedBookEngine,
        sink: ParquetFactorSink,
    ) -> None:
        self._engine = engine
        self._sink = sink
        self._prev_price_sum: int | None = None
        self._bid_d1: int | None = None
        self._ask_d1: int | None = None
        self.book_count = 0
        self.trade_count = 0
        self.dump_count = 0

    def _write_row(
        self,
        event_type: str,
        instrument: str,
        ts_event: int,
        ts_init: int,
    ) -> None:
        best_bid = _price_to_float(self._engine.book.best_bid_price())
        best_ask = _price_to_float(self._engine.book.best_ask_price())
        factor_values = self._engine.factors.dump()
        self._sink.write(
            instrument=instrument,
            event_type=event_type,
            exchange_ts=ts_event,
            recv_ts=ts_init,
            date=_ts_to_date(ts_event),
            mid_price=self._engine.state.mid_price,
            mid_price_prev=self._engine.state.mid_price_prev,
            last_trade_price=self._engine.state.last_trade_price,
            best_bid=best_bid,
            best_ask=best_ask,
            factor_values=factor_values,
        )
        self.dump_count += 1

    def on_book_update(self, update: BookUpdate) -> None:
        self.book_count += 1
        self._engine.on_book_update(update)
        best_bid = self._engine.book.best_bid_price()
        best_ask = self._engine.book.best_ask_price()
        bidp = best_bid.raw if best_bid is not None else None
        askp = best_ask.raw if best_ask is not None else None

        bid_valid = bidp is not None and self._bid_d1 is not None
        bid_improve = bid_valid and bidp > self._bid_d1
        ask_valid = askp is not None and self._ask_d1 is not None
        ask_improve = ask_valid and askp < self._ask_d1

        price_sum = bidp + askp if bidp is not None and askp is not None else None

        if bid_improve or ask_improve:
            self._write_row(
                event_type="book",
                instrument=update.instrument_id.value,
                ts_event=update.ts_event,
                ts_init=update.ts_init,
            )
            self._prev_price_sum = price_sum

        self._bid_d1 = bidp
        self._ask_d1 = askp

    def on_trade(self, trade: TradeTick) -> None:
        self.trade_count += 1
        self._engine.on_trade(trade)
        # Trades update factors/state, but dumping is gated by bid/ask improvements.


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified order book demo (snapshot or deltas) with shared state.",
    )
    parser.add_argument(
        "--book-mode",
        choices=["depth10", "deltas"],
        required=True,
        help="Use depth10 snapshots or incremental deltas.",
    )
    parser.add_argument(
        "--book",
        type=Path,
        default=None,
        help="Path to Tardis book_snapshot_5/25 CSV (when --book-mode=depth10).",
    )
    parser.add_argument(
        "--levels",
        type=int,
        default=25,
        help="Snapshot levels in the CSV (5 or 25).",
    )
    parser.add_argument(
        "--deltas",
        type=Path,
        default=None,
        help="Path to Tardis incremental_book_L2 CSV (when --book-mode=deltas).",
    )
    parser.add_argument(
        "--trades",
        type=Path,
        required=True,
        help="Path to Tardis trades CSV (can be .gz).",
    )
    parser.add_argument(
        "--instrument",
        default="BTCUSDT-PERP.BINANCE",
        help="InstrumentId string (default: BTCUSDT-PERP.BINANCE).",
    )
    parser.add_argument(
        "--price-precision",
        type=int,
        default=None,
        help="Optional price precision override (e.g., 1 for 0.1).",
    )
    parser.add_argument(
        "--size-precision",
        type=int,
        default=None,
        help="Optional size precision override (e.g., 3 for 0.001).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for each CSV.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=2**16,
        help="Stream chunk size for each CSV (smaller uses less memory).",
    )
    parser.add_argument(
        "--ema-period",
        type=int,
        default=20,
        help="EMA period for the depth cluster.",
    )
    parser.add_argument(
        "--imbalance-levels",
        type=int,
        default=0,
        help="Levels used for book imbalance (0 uses all available levels).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tardis_unified_factors.parquet"),
        help="Output Parquet file path.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    if args.book_mode == "depth10" and args.book is None:
        raise SystemExit("--book is required when --book-mode=depth10")
    if args.book_mode == "deltas" and args.deltas is None:
        raise SystemExit("--deltas is required when --book-mode=deltas")

    instrument_id = InstrumentId.from_str(args.instrument)
    book = OrderBook(instrument_id, book_type=BookType.L2_MBP)

    loader = TardisCSVDataLoader(
        price_precision=args.price_precision,
        size_precision=args.size_precision,
        instrument_id=instrument_id,
    )

    if args.book_mode == "depth10":
        book_stream = loader.stream_depth10(
            args.book,
            levels=args.levels,
            chunk_size=args.chunk_size,
            limit=args.limit,
        )
    else:
        book_stream = loader.stream_batched_deltas(
            args.deltas,
            chunk_size=args.chunk_size,
            limit=args.limit,
        )

    trade_stream = loader.stream_trades(
        args.trades,
        chunk_size=args.chunk_size,
        limit=args.limit,
    )

    book_updates = _iter_stream(book_stream)
    trades = _iter_stream(trade_stream)

    state = SharedState()
    imbalance_levels = args.imbalance_levels if args.imbalance_levels > 0 else None
    factors: list[FactorBase] = [
        DepthFactorCluster(state, book, ema_period=args.ema_period),
        MidReturnFactor(state, book),
        BookImbalanceFactor(state, book, imbalance_levels),
    ]
    factor_engine = FactorEngine(factors)
    unified = UnifiedBookEngine(book, state, factor_engine)
    sink = ParquetFactorSink(args.out, factor_engine.factor_names)
    sampler = Sampler(unified, sink)

    try:
        for event in _merge_by_ts(book_updates, trades):
            if isinstance(event, TradeTick):
                sampler.on_trade(event)
            else:
                sampler.on_book_update(event)
    finally:
        sink.close()

    print(
        "done "
        f"books={sampler.book_count} "
        f"trades={sampler.trade_count} "
        f"dumps={sampler.dump_count} "
        f"rows={sink.rows} "
        f"out={args.out}",
    )
