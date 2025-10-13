# FactorExp Research Workspace

Dedicated workspace for ad-hoc factor studies, expression validation, and NaN semantics testing.

## Purpose

This research area provides tools and templates for:

- **Factor Expression Development**: Test and validate new factor formulations before integration
- **NaN Semantics Verification**: Ensure revised NaN handling works correctly on expressions like `Clip(ZScore(TS_Std(When(...))))`
- **Quick Hypothesis Testing**: Iterate on factor ideas without full backtest setup
- **Data Exploration**: Inspect factor value series, distributions, and edge cases

## Directory Structure

```
research/
├── README.md              # This file
├── notebooks/             # Jupyter notebooks for interactive analysis
│   └── factor_playground.ipynb  # Template for factor evaluation
├── utils/                 # Python helper modules
│   ├── __init__.py        # Package exports
│   ├── data_access.py     # Catalog loading and instrument resolution
│   └── factor_runner.py   # Factor expression evaluation engine
├── scripts/               # CLI tools (optional)
└── results/               # Output data (gitignored)
```

## Quick Start

### 1. Environment Setup

Ensure you're using the project's Python environment with all dependencies installed:

```bash
# From nautilus_trader root
make install-debug
```

### 2. Launch Jupyter

Start Jupyter from the research directory:

```bash
cd factorexp_backtest/research
jupyter notebook
```

Or if using VSCode, open `notebooks/factor_playground.ipynb` directly.

### 3. Run the Template

Open `notebooks/factor_playground.ipynb` and:

1. **Configure parameters** in the first code cell:
   - `EXPRESSION`: Your factor expression string
   - `INSTRUMENT_ID`: Target instrument (e.g., "BTCUSDT.BINANCE")
   - `START_DATE` / `END_DATE`: Analysis period
   - `ZSCORE_PERIOD`: Lookback window for ZScore normalization

2. **Run all cells** (Cell → Run All) to:
   - Load bar data from catalog
   - Evaluate the factor expression
   - Generate summary statistics
   - Visualize results
   - Export factor values

3. **Iterate**: Modify the expression and re-run to test variations

## Usage Examples

### Example 1: Evaluate Single Factor

```python
from factorexp_backtest.research.utils import run_expression, FactorRequest

request = FactorRequest(
    expression="Clip(ZScore(TS_Std(When(vwap_return, close > 0, 0), 20), 5760), -2, 2)",
    instrument_id="BTCUSDT.BINANCE",
    start_date="2024-01-01",
    end_date="2024-01-31",
    period=5760
)

result = run_expression(request)
print(result.head())
print(f"NaN count: {result['factor_value'].isna().sum()}")
```

### Example 2: Load Catalog Data Directly

```python
from factorexp_backtest.research.utils import load_catalog_bars

bars = load_catalog_bars(
    instrument_id="ETHUSDT.BINANCE",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

print(f"Loaded {len(bars)} bars")
print(bars.columns)
```

### Example 3: List Available Instruments

```python
from factorexp_backtest.research.utils import get_available_instruments

instruments = get_available_instruments()
print(f"Found {len(instruments)} instruments in catalog")
print(instruments[:10])  # First 10
```

## Data Source

### Catalog Location

Pre-cleaned bar data is stored in:

```
factorexp_backtest/catalog/data/bar/
```

### Data Format

- **Format**: Parquet (via NautilusTrader catalog)
- **Frequency**: 15-minute bars
- **Fields**: `open`, `high`, `low`, `close`, `volume`, `ts_event`, `ts_init`
- **Extended Fields** (when available): `amt`, `vwap_return`, etc.

### Instruments

Currently available instruments can be queried using:

```python
from factorexp_backtest.research.utils import get_available_instruments
instruments = get_available_instruments()
```

## Common Workflows

### Workflow 1: Validate New Expression

**Goal**: Test a new factor expression before adding to `factors.yaml`

1. Open `factor_playground.ipynb`
2. Set `EXPRESSION` to your new formula
3. Run all cells
4. Check:
   - NaN count and patterns
   - Value distribution (should match expectations)
   - Edge cases (beginning/end of data)
5. If valid, copy expression to `configs/factors.yaml`

### Workflow 2: Compare NaN Handling (Legacy vs New)

**Goal**: Verify revised NaN semantics against historical results

1. Create two separate notebook instances
2. Use identical parameters but different operator implementations
3. Compare:
   - Readiness timing (new: time-based, old: value-based)
   - Output during NaN sequences (new: reuses last valid, old: skips)
   - Window advancement behavior
4. Document discrepancies for review

### Workflow 3: Multi-Instrument Comparison

**Goal**: Test factor behavior across different instruments

1. Loop over instrument list:
   ```python
   instruments = ["BTCUSDT.BINANCE", "ETHUSDT.BINANCE", "BNBUSDT.BINANCE"]
   for inst in instruments:
       request.instrument_id = inst
       result = run_expression(request)
       print(f"{inst}: Mean={result['factor_value'].mean():.4f}, Std={result['factor_value'].std():.4f}")
   ```
2. Compare statistics and identify anomalies

## Common Pitfalls

### 1. Data Availability

**Problem**: `ValueError: No data found for instrument between dates`

**Solutions**:
- Check catalog with `get_available_instruments()`
- Verify date range is within available data period
- Ensure instrument ID format matches catalog (e.g., "BTCUSDT.BINANCE" not "btcusdt")

### 2. Timezone Alignment

**Problem**: Unexpected gaps or misalignments in factor values

**Solutions**:
- All timestamps in catalog are UTC
- Use `pd.Timestamp(date, tz='UTC')` for date conversions
- Verify bar alignment with `bars['ts_event'].diff().describe()`

### 3. Extended Field Requirements

**Problem**: Expression uses `amt` or `vwap_return` but data missing

**Solutions**:
- Check if instrument catalog has extended fields: `'amt' in bars.columns`
- Re-run conversion with `--include-extended` if needed
- Use alternative expression without extended fields

### 4. Memory Issues (Large Date Ranges)

**Problem**: Notebook kernel crashes on multi-month evaluations

**Solutions**:
- Reduce date range or process in chunks
- Use `evaluate_factor_series()` instead of `run_expression()` (returns only values, not full DataFrame)
- Clear variables after each iteration: `del result; import gc; gc.collect()`

## Tips & Tricks

### Performance

- **Batch Loading**: Load bars once, reuse for multiple expressions
  ```python
  bars = load_catalog_bars(...)
  result1 = run_expression(request1, bars_df=bars)
  result2 = run_expression(request2, bars_df=bars)
  ```

- **Simplified Output**: Use `evaluate_factor_series()` for lightweight evaluation:
  ```python
  from factorexp_backtest.research.utils import evaluate_factor_series
  factor = evaluate_factor_series(expression, bars, period)
  ```

### Debugging

- **Check Indicator State**: Access indicator internals to debug:
  ```python
  from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
  indicator = FactorExpIndicator(expression, period)
  # Step through bars manually to inspect state
  ```

- **Enable Logging**: Set NautilusTrader log level for detailed output:
  ```python
  import logging
  logging.basicConfig(level=logging.DEBUG)
  ```

### Sharing Results

- **Export to CSV**: For non-Python users:
  ```python
  result.to_csv(f"results/factor_{timestamp}.csv", index=False)
  ```

- **Generate Report**: Use notebook export:
  ```bash
  jupyter nbconvert --to html --execute factor_playground.ipynb
  ```

## Integration with Backtest

Once a factor expression is validated here:

1. **Add to factors.yaml**:
   ```yaml
   factors:
     my_new_factor:
       name: "My New Factor"
       expression: "Clip(ZScore(TS_Std(...), 5760), -2, 2)"
       requires_extended: true  # if uses amt/vwap_return
   ```

2. **Run backtest**:
   ```bash
   cd factorexp_backtest
   python run_backtest.py --factor my_new_factor
   ```

3. **Review results** in `results/` directory

## Environment Notes

### Python Version

Requires Python 3.11+ (same as main NautilusTrader project)

### Key Dependencies

- `nautilus_trader`: Core framework
- `pandas`: Data manipulation
- `matplotlib`, `seaborn`: Visualization
- `jupyter`: Notebook environment

All dependencies are managed via the main project's `pyproject.toml`.

### Running Without Jupyter

For headless execution or CI:

```python
# scripts/batch_evaluate.py
from factorexp_backtest.research.utils import run_expression, FactorRequest

request = FactorRequest(...)
result = run_expression(request)

# Print summary to stdout
print(result['factor_value'].describe())
print(f"NaN count: {result['factor_value'].isna().sum()}")
```

Run with:
```bash
python scripts/batch_evaluate.py
```

## Contributing

When adding new utilities:

1. **Update `utils/__init__.py`**: Export new functions
2. **Add docstrings**: Use NumPy style with examples
3. **Update README**: Document new workflow or example
4. **Test**: Verify with sample data before committing

## Troubleshooting

### Issue: Import errors when running notebook

**Solution**: Ensure the notebook's kernel is using the correct Python environment:

```bash
# Install ipykernel in project environment
poetry run python -m ipykernel install --user --name nautilus --display-name "NautilusTrader"
```

Then select "NautilusTrader" kernel in Jupyter.

### Issue: Catalog path not found

**Solution**: Run notebook from `research/notebooks/` directory, or adjust path in configuration:

```python
from pathlib import Path
catalog_path = Path("/absolute/path/to/factorexp_backtest/catalog")
bars = load_catalog_bars(..., catalog_path=catalog_path)
```

## References

- **Factor Expression Syntax**: See `crates/factorexp/README.md` for DSL reference
- **NaN Semantics**: See `plans/factorexp_nan_251009/rolling_nan_strategy.md`
- **Backtest Configuration**: See `factorexp_backtest/README.md`
- **Catalog Format**: See `factorexp_backtest/tools/convert_feather_to_catalog.py`
