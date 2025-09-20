# FactorExp Rust Operators

High-performance Rust implementations of FactorExp operators for Nautilus Trader.

## Overview

This crate provides Rust implementations of rolling window operators used in factor expressions, offering 10-100x performance improvements over NumPy implementations.

## Features

- **High Performance**: Optimized Rust implementations with zero-copy design
- **Python Bindings**: Seamless integration via PyO3
- **API Compatible**: Drop-in replacement for Python operators
- **Memory Efficient**: Fixed-size buffers with minimal allocations

## Implemented Operators

### Basic Statistics
- `TS_Mean` - Rolling mean/average
- `TS_Sum` - Rolling sum
- `TS_Std` - Rolling standard deviation
- `TS_Var` - Rolling variance
- `TS_Min` - Rolling minimum
- `TS_Max` - Rolling maximum
- `TS_Med` - Rolling median

### Moving Averages
- `TS_EMA` - Exponential moving average
- `TS_WMA` - Weighted moving average

### Advanced Statistics
- `TS_Skew` - Rolling skewness
- `TS_Kurt` - Rolling kurtosis (excess)
- `TS_Mad` - Mean absolute deviation
- `TS_Quantile` - Rolling quantile/percentile with adaptive algorithm

### Other Operators
- `TS_Delta` - Difference between newest and oldest
- `TS_Product` - Rolling product
- `TS_Ref` - Reference value N periods ago
- `TS_Rank` - Rolling rank (percentile position)
- `TS_Argmax` - Index of maximum value
- `TS_Argmin` - Index of minimum value
- `ZScore` - Standardized score (z-score)
- `Demean` - Value minus rolling mean

### Conditional & Utility Operators
- `When` - Conditional expression (if-then-else)
- `Clip` - Bounds value within min/max range

## Building

### Prerequisites

- Rust 1.75+ (install from https://rustup.rs)
- Python 3.11+
- maturin (`pip install maturin`)

### Build Steps

```bash
# Development build
cd crates/factorexp
maturin develop --release

# Production wheel
maturin build --release
```

## Usage

### Python API

```python
from nautilus_trader.indicators.factorexp.core.rust_bridge import create_streaming_computation

# Create a Rust-powered operator
ma = create_streaming_computation("TS_Mean", window_size=20)

# Use exactly like Python operators
for price in prices:
    ma.update(price)
    if ma.is_ready:
        print(f"20-period MA: {ma.value}")
```

### Direct Rust Usage

```rust
use nautilus_factorexp::operators::{RollingOperator, rolling::Mean};

let mut ma = Mean::new(20);
for price in prices {
    ma.update(price);
    if ma.is_ready() {
        println!("MA: {}", ma.value());
    }
}
```

### Quantile Usage

```python
# Python example using FactorExp string
expression = "TS_Quantile($close, 100, 0.75)"  # 75th percentile over 100 periods

# Rust example
use nautilus_factorexp::operators::{RollingOperator, rolling::Quantile};

let mut q75 = Quantile::new(100, 0.75);
for price in prices {
    q75.update(price);
    if q75.is_ready() {
        println!("75th percentile: {}", q75.value());
    }
}
```

### Clip Operator Usage

```python
# Python example - Clip RSI to [30, 70] range
expression = "Clip(RSI($close, 14), 30, 70)"  # Bounds RSI between 30 and 70

# Dynamic bounds based on market data
expression = "Clip($close, $low * 0.95, $high * 1.05)"  # Clip close to 5% beyond day's range

# Normalize values to [0, 1] range
expression = "Clip(($close - $low) / ($high - $low), 0, 1)"
```

## Performance

Benchmark results on M1 MacBook Pro:

| Operator | Window | Python Time | Rust Time | Speedup |
|----------|--------|-------------|-----------|---------|
| TS_Mean  | 20     | 10.5 ms     | 0.12 ms   | 87x     |
| TS_Std   | 20     | 15.3 ms     | 0.28 ms   | 55x     |
| TS_EMA   | 20     | 8.2 ms      | 0.08 ms   | 103x    |

## Architecture

### Buffer Management

Uses `ArrayDeque` for efficient circular buffer operations:
- Fixed-size allocation (no dynamic resizing)
- O(1) push/pop operations
- Cache-friendly memory layout

### Incremental Computation

Many operators maintain running statistics:
- Sum and sum-of-squares for variance calculation
- Avoids recomputing over entire window
- Minimal numerical error accumulation

### Adaptive Algorithm Selection

The `TS_Quantile` operator uses adaptive algorithm selection for optimal performance:
- **Small windows (≤1024)**: Sorted array with binary search insertion
  - Cache-friendly for small data sets
  - O(n) insertion, O(1) quantile computation
- **Large windows (>1024)**: Dual heap with lazy deletion
  - Efficient for large data sets
  - O(log n) amortized operations
- **Interpolation**: R-7 method (pandas default) for accurate percentiles

## Testing

```bash
# Run Rust tests
cargo test

# Run benchmarks
cargo bench

# Run Python integration tests
pytest tests/unit_tests/indicators/factorexp/test_rust_operators.py
```

## Contributing

1. Add new operator in appropriate module under `src/operators/`
2. Implement `RollingOperator` trait
3. Add Python binding in `src/python/mod.rs`
4. Add tests and benchmarks
5. Update documentation

## License

Licensed under GNU Lesser General Public License v3.0. See LICENSE for details.