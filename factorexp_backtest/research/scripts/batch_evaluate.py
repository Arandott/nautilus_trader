#!/usr/bin/env python3
"""
Batch factor evaluation script for headless/CLI workflows.

This script allows evaluating factor expressions from the command line
without requiring Jupyter, useful for CI pipelines or automated testing.

Examples
--------
# Evaluate single factor
python batch_evaluate.py \
    --expression "Clip(ZScore(TS_Std(close, 20), 5760), -2, 2)" \
    --instrument "BTCUSDT.BINANCE" \
    --start "2024-01-01" \
    --end "2024-01-31"

# Save results to file
python batch_evaluate.py \
    --expression "..." \
    --instrument "ETHUSDT.BINANCE" \
    --start "2024-01-01" \
    --end "2024-01-31" \
    --output results/factor_output.feather
"""

import argparse
import sys
from pathlib import Path


# Add parent directories to path for imports
script_dir = Path(__file__).parent
research_dir = script_dir.parent
backtest_dir = research_dir.parent
sys.path.insert(0, str(backtest_dir))


from research.utils import evaluate_factor


def main():
    """Parse arguments and run factor evaluation."""
    parser = argparse.ArgumentParser(
        description="Batch factor expression evaluation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--expression",
        "-e",
        required=True,
        help="Factor expression string (e.g., 'ZScore(TS_Std($close, 20), 5760)')",
    )
    parser.add_argument(
        "--instrument",
        "-i",
        required=True,
        help="Instrument ID (e.g., 'BTCUSDT.BINANCE')",
    )
    parser.add_argument(
        "--start",
        "-s",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        "-e",
        dest="end_date",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output file path (feather or csv format)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress detailed output, show only summary",
    )

    args = parser.parse_args()

    if not args.quiet:
        print("Evaluating factor expression:")
        print(f"  Expression: {args.expression}")
        print(f"  Instrument: {args.instrument}")
        print(f"  Date Range: {args.start} to {args.end_date}")
        print()

    # Run evaluation
    try:
        result = evaluate_factor(
            expression=args.expression,
            instrument_id=args.instrument,
            start_date=args.start,
            end_date=args.end_date,
            verbose=not args.quiet,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Print summary
    print("=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total values: {len(result)}")
    print(f"NaN count: {result['factor_value'].isna().sum()} "
          f"({result['factor_value'].isna().sum() / len(result) * 100:.2f}%)")
    print()
    print("Factor Value Statistics:")
    print(result["factor_value"].describe())
    print()
    print(f"Skewness: {result['factor_value'].skew():.4f}")
    print(f"Kurtosis: {result['factor_value'].kurtosis():.4f}")
    print()

    # Save to file if requested
    if args.output:
        output_path = args.output
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix == ".csv":
            result.to_csv(output_path, index=False)
        elif output_path.suffix == ".feather":
            result.reset_index(drop=True).to_feather(output_path)
        else:
            print(f"Warning: Unknown output format '{output_path.suffix}', "
                  "defaulting to feather")
            result.reset_index(drop=True).to_feather(output_path)

        print(f"✅ Results saved to: {output_path}")
        print(f"File size: {output_path.stat().st_size / 1024:.2f} KB")
    else:
        if not args.quiet:
            print("\nFirst 10 values:")
            print(result.head(10))

    print()
    print("✅ Evaluation complete")


if __name__ == "__main__":
    main()
