"""
Catalog factory utilities for FactorExp backtests.

Provides helper functions to create and configure ParquetDataCatalog instances
for Phase C backtest consumption.
"""

from __future__ import annotations

from pathlib import Path

from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog


def create_catalog(
    catalog_path: str | Path,
    *,
    create_if_missing: bool = False,
    validate_readable: bool = True,
) -> ParquetDataCatalog:
    """
    Create a configured ParquetDataCatalog instance.

    Parameters
    ----------
    catalog_path : str | Path
        Path to the catalog root directory.
    create_if_missing : bool, default False
        If True, create the catalog directory if it doesn't exist.
    validate_readable : bool, default True
        If True, verify the catalog path exists and is readable.

    Returns
    -------
    ParquetDataCatalog
        Configured catalog instance ready for data access.

    Raises
    ------
    FileNotFoundError
        If catalog_path doesn't exist and create_if_missing is False.
    PermissionError
        If catalog_path exists but is not readable.

    Examples
    --------
    >>> catalog = create_catalog("factorexp_backtest/catalog")
    >>> bars = catalog.bars()

    >>> catalog = create_catalog("/tmp/new_catalog", create_if_missing=True)

    """
    catalog_path = Path(catalog_path).resolve()

    if not catalog_path.exists():
        if create_if_missing:
            catalog_path.mkdir(parents=True, exist_ok=True)
        else:
            raise FileNotFoundError(
                f"Catalog path not found: {catalog_path}\n"
                "Use create_if_missing=True to create it automatically."
            )

    if validate_readable and not catalog_path.is_dir():
        raise NotADirectoryError(f"Catalog path is not a directory: {catalog_path}")

    if validate_readable and not _is_readable(catalog_path):
        raise PermissionError(f"Catalog path is not readable: {catalog_path}")

    return ParquetDataCatalog(str(catalog_path))


def get_catalog_instruments(catalog: ParquetDataCatalog) -> list[str]:
    """
    Get list of instruments available in the catalog.

    Parameters
    ----------
    catalog : ParquetDataCatalog
        The catalog to query.

    Returns
    -------
    list[str]
        List of instrument IDs found in the catalog.

    Examples
    --------
    >>> catalog = create_catalog("factorexp_backtest/catalog")
    >>> instruments = get_catalog_instruments(catalog)
    >>> print(instruments)
    ['BTCUSDT.BINANCE', 'ETHUSDT.BINANCE']

    """
    # Query all bars to extract instrument IDs
    bars = catalog.bars()

    # Extract unique instrument IDs
    instrument_ids = set()
    for bar in bars:
        instrument_id = str(bar.bar_type.instrument_id)
        instrument_ids.add(instrument_id)

    return sorted(instrument_ids)


def _is_readable(path: Path) -> bool:
    """
    Check if a path is readable.

    Parameters
    ----------
    path : Path
        Path to check.

    Returns
    -------
    bool
        True if path exists and is readable.

    """
    try:
        # Try to list contents (works for directories)
        if path.is_dir():
            list(path.iterdir())
            return True
        # Try to read (works for files)
        if path.is_file():
            with path.open("r"):
                pass
            return True
        return False
    except (PermissionError, OSError):
        return False
