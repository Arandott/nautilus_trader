#!/usr/bin/env python3
"""
Verification script to test research workspace setup.

Checks:
- Catalog accessibility
- Data availability
- Import paths
- Basic evaluation workflow
"""

import sys
from pathlib import Path


# Add parent directories to path
script_dir = Path(__file__).parent
research_dir = script_dir.parent
backtest_dir = research_dir.parent
sys.path.insert(0, str(backtest_dir))


def check_imports():
    """Verify all required modules can be imported."""
    print("Checking imports...")
    try:
        from research.utils import evaluate_factor
        from research.utils import get_available_instruments
        from research.utils import load_catalog_bars
        print("  ✅ All utils modules imported successfully")
        return True
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        return False


def check_catalog():
    """Verify catalog directory exists and is accessible."""
    print("\nChecking catalog...")
    try:
        from research.utils.data_access import get_catalog_path

        catalog_path = get_catalog_path()
        print(f"  ✅ Catalog found at: {catalog_path}")

        # Check for bar data
        bar_path = catalog_path / "data" / "bar"
        if bar_path.exists():
            # Count instrument directories (each contains parquet files)
            instrument_dirs = [d for d in bar_path.iterdir() if d.is_dir()]
            instrument_count = len(instrument_dirs)
            print(f"  ✅ Found {instrument_count} instruments in catalog")
            if instrument_count > 0:
                print(f"     Sample instruments: {', '.join([d.name.split('.')[0] for d in instrument_dirs[:5]])}")
        else:
            print(f"  ⚠️  Bar data directory not found: {bar_path}")

        return True
    except FileNotFoundError as e:
        print(f"  ❌ Catalog error: {e}")
        return False


def check_instruments():
    """List available instruments."""
    print("\nChecking available instruments...")
    try:
        from research.utils import get_available_instruments

        instruments = get_available_instruments()
        print(f"  ✅ Found {len(instruments)} instruments")

        if instruments:
            print("\n  First 10 instruments:")
            for inst in instruments[:10]:
                print(f"    - {inst}")
        else:
            print("  ⚠️  No instruments found in catalog")

        return True
    except Exception as e:
        print(f"  ❌ Error listing instruments: {e}")
        return False


def check_evaluation():
    """Test basic factor evaluation workflow."""
    print("\nTesting factor evaluation...")
    try:
        from research.utils import evaluate_factor
        from research.utils import get_available_instruments

        # Get first available instrument
        instruments = get_available_instruments()
        if not instruments:
            print("  ⚠️  No instruments available, skipping evaluation test")
            return True

        test_instrument = instruments[0]
        print(f"  Testing with instrument: {test_instrument}")

        # Run simple test evaluation
        result = evaluate_factor(
            expression="TS_Mean($close, 5)",  # Simple 5-bar moving average
            instrument_id=test_instrument,
            start_date="2024-01-01",
            end_date="2024-01-03",  # Just 2 days for quick test
            verbose=True,
        )

        if len(result) > 0:
            print("  ✅ Evaluation successful")
            print(f"    Generated {len(result)} values")
            print(f"    NaN count: {result['factor_value'].isna().sum()}")
            return True
        else:
            print("  ⚠️  Evaluation returned empty result")
            print("     (May be due to limited date range or data availability)")
            return True

    except Exception as e:
        print(f"  ❌ Evaluation error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all verification checks."""
    print("=" * 70)
    print("Research Workspace Setup Verification")
    print("=" * 70)
    print()

    checks = [
        ("Imports", check_imports),
        ("Catalog", check_catalog),
        ("Instruments", check_instruments),
        ("Evaluation", check_evaluation),
    ]

    results = {}
    for name, check_func in checks:
        results[name] = check_func()

    # Summary
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)

    all_passed = all(results.values())

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {name}")

    print()

    if all_passed:
        print("✅ All checks passed! Research workspace is ready to use.")
        print()
        print("Next steps:")
        print("  1. Launch Jupyter: cd research && jupyter notebook")
        print("  2. Open: notebooks/factor_playground.ipynb")
        print("  3. Or run CLI: python scripts/batch_evaluate.py --help")
        return 0
    else:
        print("⚠️  Some checks failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
