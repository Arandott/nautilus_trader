#!/usr/bin/env python3
"""
Integration tests for Feather to Parquet catalog conversion.

Tests the complete pipeline: Feather files → conversion → Parquet catalog → Bar objects with amt field.
"""

import tempfile
from pathlib import Path

import pytest

from factorexp_backtest.loaders import create_catalog
from factorexp_backtest.loaders import get_catalog_instruments
from factorexp_backtest.tools.convert_feather_to_catalog import main as convert_main
from nautilus_trader.model.data import EXTENDED_BAR_FIELD_SPECS


@pytest.fixture
def sample_feather_path():
    """Path to sample Feather data."""
    return Path(__file__).parent.parent / "data" / "Binance_k_15min"


@pytest.fixture
def temp_catalog():
    """Create a temporary catalog directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "catalog"


class TestFeatherToCatalogConversion:
    """Test the complete conversion pipeline."""

    def test_dry_run_conversion(self, sample_feather_path):
        """Test dry-run conversion without writing data."""
        if not sample_feather_path.exists():
            pytest.skip(f"Sample data not found: {sample_feather_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            catalog_path = Path(tmpdir) / "catalog"

            # Run conversion in dry-run mode
            exit_code = convert_main([
                "--feather-root", str(sample_feather_path),
                "--catalog-path", str(catalog_path),
                "--symbols", "BTCUSDT",
                "--start-date", "2022-01-01",
                "--end-date", "2022-01-03",
                "--dry-run",
            ])

            assert exit_code == 0
            # Catalog should not be created in dry-run mode
            assert not catalog_path.exists() or len(list(catalog_path.glob("**/*.parquet"))) == 0

    def test_full_conversion_with_amt_field(self, sample_feather_path, temp_catalog):
        """Test complete conversion and verify amt field is preserved."""
        if not sample_feather_path.exists():
            pytest.skip(f"Sample data not found: {sample_feather_path}")

        # Run conversion
        exit_code = convert_main([
            "--feather-root", str(sample_feather_path),
            "--catalog-path", str(temp_catalog),
            "--symbols", "BTCUSDT",
            "--start-date", "2022-01-01",
            "--end-date", "2022-01-02",
            "--amt-precision", "0",
        ])

        assert exit_code == 0
        assert temp_catalog.exists()

        # Open catalog and verify data
        catalog = create_catalog(temp_catalog)
        bars = catalog.bars()

        assert len(bars) > 0, "No bars loaded from catalog"

        # Verify amt field exists and has values
        first_bar = bars[0]
        amt = getattr(first_bar, "amt", None)

        # Check if extended bar feature is enabled
        if EXTENDED_BAR_FIELD_SPECS:
            assert amt is not None, "amt field should exist when extended_bar feature is enabled"
            # amt should be a Quantity object with non-zero value for BTCUSDT
            assert amt.raw > 0, f"amt should have positive value, got {amt}"
        else:
            pytest.skip("extended_bar feature not enabled")

    def test_multiple_symbols_conversion(self, sample_feather_path, temp_catalog):
        """Test conversion with multiple symbols."""
        if not sample_feather_path.exists():
            pytest.skip(f"Sample data not found: {sample_feather_path}")

        # Convert multiple symbols (if available in data)
        exit_code = convert_main([
            "--feather-root", str(sample_feather_path),
            "--catalog-path", str(temp_catalog),
            "--symbols", "BTCUSDT,ETHUSDT",
            "--start-date", "2022-01-01",
            "--end-date", "2022-01-02",
        ])

        # Exit code 0 even if some symbols are missing
        assert exit_code == 0

        catalog = create_catalog(temp_catalog)
        instruments = get_catalog_instruments(catalog)

        # At least BTCUSDT should be present
        assert len(instruments) > 0
        assert "BTCUSDT.BINANCE" in instruments

    def test_conversion_preserves_data_integrity(self, sample_feather_path, temp_catalog):
        """Test that conversion preserves OHLCV data integrity."""
        if not sample_feather_path.exists():
            pytest.skip(f"Sample data not found: {sample_feather_path}")

        exit_code = convert_main([
            "--feather-root", str(sample_feather_path),
            "--catalog-path", str(temp_catalog),
            "--symbols", "BTCUSDT",
            "--start-date", "2022-01-01",
            "--end-date", "2022-01-01",  # Single day
        ])

        assert exit_code == 0

        catalog = create_catalog(temp_catalog)
        bars = catalog.bars()

        # Verify basic bar structure
        for bar in bars[:10]:  # Check first 10 bars
            assert bar.open > 0
            assert bar.high >= bar.low
            assert bar.high >= bar.open
            assert bar.high >= bar.close
            assert bar.low <= bar.open
            assert bar.low <= bar.close
            assert bar.volume >= 0
            assert bar.ts_event > 0
            assert bar.ts_init > 0


class TestCatalogRoundTrip:
    """Test reading back converted data."""

    def test_amt_field_roundtrip(self, sample_feather_path, temp_catalog):
        """Test that amt field survives write and read roundtrip."""
        if not sample_feather_path.exists():
            pytest.skip(f"Sample data not found: {sample_feather_path}")

        if not EXTENDED_BAR_FIELD_SPECS:
            pytest.skip("extended_bar feature not enabled")

        # Convert data
        convert_main([
            "--feather-root", str(sample_feather_path),
            "--catalog-path", str(temp_catalog),
            "--symbols", "BTCUSDT",
            "--start-date", "2022-01-01",
            "--end-date", "2022-01-01",
        ])

        # Read back
        catalog = create_catalog(temp_catalog)
        bars = catalog.bars()

        # Verify all bars have amt field with reasonable values
        for bar in bars:
            amt = getattr(bar, "amt", None)
            assert amt is not None, f"Bar missing amt field: {bar}"
            # For BTCUSDT with 15min bars, amt should be substantial
            assert amt.raw >= 0, f"amt should be non-negative, got {amt}"
