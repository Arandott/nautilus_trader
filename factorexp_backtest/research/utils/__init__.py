"""
Research utilities for factor exploration and validation.

This module provides tools for ad-hoc factor studies, including:
- Data loading from Parquet catalog
- Factor expression evaluation
- Helper functions for notebook workflows
"""

from .data_access import get_available_instruments
from .data_access import load_catalog_bars
from .factor_runner import evaluate_factor


__all__ = [
    "evaluate_factor",
    "get_available_instruments",
    "load_catalog_bars",
]
