"""Research utilities for factor exploration and validation.

This module provides tools for ad-hoc factor studies, including:
- Data loading from Parquet catalog
- Factor expression evaluation
- Helper functions for notebook workflows
"""

from .data_access import load_catalog_bars, get_available_instruments
from .factor_runner import run_expression, FactorRequest

__all__ = [
    'load_catalog_bars',
    'get_available_instruments',
    'run_expression',
    'FactorRequest',
]
