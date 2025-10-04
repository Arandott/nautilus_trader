#!/usr/bin/env python3
"""
Unit tests for catalog_factory module.

Tests the helper functions for creating and configuring ParquetDataCatalog instances.
"""

from pathlib import Path

import pytest

from factorexp_backtest.loaders import create_catalog
from factorexp_backtest.loaders import get_catalog_instruments


class TestCreateCatalog:
    """Tests for create_catalog function."""

    def test_create_catalog_existing_path(self, tmp_path):
        """Test creating catalog from existing path."""
        catalog = create_catalog(tmp_path)
        assert catalog is not None
        assert catalog.path == str(tmp_path)

    def test_create_catalog_with_str_path(self, tmp_path):
        """Test creating catalog with string path."""
        catalog = create_catalog(str(tmp_path))
        assert catalog is not None
        assert Path(catalog.path) == tmp_path

    def test_create_catalog_missing_path_without_create(self):
        """Test that missing path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Catalog path not found"):
            create_catalog("/nonexistent/path")

    def test_create_catalog_missing_path_with_create(self, tmp_path):
        """Test creating catalog with missing path and create_if_missing=True."""
        new_path = tmp_path / "new_catalog"
        assert not new_path.exists()

        catalog = create_catalog(new_path, create_if_missing=True)
        assert catalog is not None
        assert new_path.exists()
        assert new_path.is_dir()

    def test_create_catalog_file_instead_of_directory(self, tmp_path):
        """Test that passing a file path raises NotADirectoryError."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        with pytest.raises(NotADirectoryError, match="not a directory"):
            create_catalog(file_path)

    def test_create_catalog_without_validation(self, tmp_path):
        """Test creating catalog without validation."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("test")

        # Should not raise when validation is disabled
        catalog = create_catalog(file_path, validate_readable=False)
        assert catalog is not None


class TestGetCatalogInstruments:
    """Tests for get_catalog_instruments function."""

    def test_get_instruments_empty_catalog(self, tmp_path):
        """Test getting instruments from empty catalog."""
        catalog = create_catalog(tmp_path)
        instruments = get_catalog_instruments(catalog)
        assert instruments == []

    def test_get_instruments_with_data(self):
        """
        Test getting instruments from catalog with data.

        This test uses the test catalog created by convert_feather_to_catalog
        in the previous test run.
        """
        catalog_path = Path("/tmp/test_catalog_factorexp")
        if not catalog_path.exists():
            pytest.skip("Test catalog not found")

        catalog = create_catalog(catalog_path)
        instruments = get_catalog_instruments(catalog)

        assert len(instruments) > 0
        assert "BTCUSDT.BINANCE" in instruments


class TestCatalogFactoryIntegration:
    """Integration tests for catalog factory."""

    def test_roundtrip_catalog_creation_and_query(self, tmp_path):
        """Test creating a catalog, writing data, and querying it back."""
        catalog = create_catalog(tmp_path, create_if_missing=True)
        assert catalog is not None

        # Initially empty
        instruments = get_catalog_instruments(catalog)
        assert instruments == []

        # Note: Writing data requires BarDataWranglerV2 which is tested separately
        # This test only verifies the factory functions work correctly
