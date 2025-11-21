"""Aurora fill probability bindings."""

from __future__ import annotations

from nautilus_trader.core.nautilus_pyo3 import aurora as aurora_bindings

QueueStats = aurora_bindings.AuroraQueueStats
HittingQueueFillModel = aurora_bindings.AuroraFillModel

__all__ = ["QueueStats", "HittingQueueFillModel"]
