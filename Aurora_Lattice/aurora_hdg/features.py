"""Feature extraction helpers built on Nautilus order book objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.objects import Price


@dataclass(slots=True)
class L1Snapshot:
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float
    mid: float
    microprice: float
    imbalance: float


def snapshot_from_book(book: OrderBook) -> Optional[L1Snapshot]:
    """Build an L1 snapshot (returns None if book missing sides)."""
    best_bid = book.best_bid()
    best_ask = book.best_ask()
    if best_bid is None or best_ask is None:
        return None

    bid_price: Price = best_bid.price
    ask_price: Price = best_ask.price
    bid_qty = best_bid.quantity.as_double()
    ask_qty = best_ask.quantity.as_double()

    mid = (bid_price.as_double() + ask_price.as_double()) * 0.5
    total = bid_qty + ask_qty
    micro = (
        (ask_price.as_double() * bid_qty + bid_price.as_double() * ask_qty) / total
        if total > 0
        else mid
    )
    imbalance = (bid_qty - ask_qty) / total if total > 0 else 0.0

    return L1Snapshot(
        bid=bid_price.as_double(),
        ask=ask_price.as_double(),
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        mid=mid,
        microprice=micro,
        imbalance=imbalance,
    )


class MidPriceVolEstimator:
    """EWMA realized volatility estimator."""

    def __init__(self, decay: float = 0.94) -> None:
        self._last_mid: Optional[float] = None
        self._decay = decay
        self._var: float = 0.0

    def update(self, mid: float) -> None:
        if self._last_mid is None:
            self._last_mid = mid
            return

        ret = (mid - self._last_mid) / max(self._last_mid, 1e-12)
        self._last_mid = mid
        self._var = self._decay * self._var + (1.0 - self._decay) * ret * ret

    @property
    def sigma_rel(self) -> float:
        return self._var**0.5

    def sigma_px(self, mid: float) -> float:
        return self.sigma_rel * mid
