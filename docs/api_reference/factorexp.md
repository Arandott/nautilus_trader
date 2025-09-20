# FactorExp Integration

## Overview

FactorExp adds a high-performance expression language to Nautilus Trader so
researchers can describe factors as strings (for example,
`TS_Mean($close, 20) / TS_Std($close, 20)`) and have them parsed, compiled, and
executed entirely in Rust. The refreshed integration removes the legacy
Python-only parser and AST, replacing it with native components that are exposed
through a PyO3 bridge for Python consumption.

The processing pipeline is:

1. **Parser (`crates/factorexp::parser`)** – converts raw expression text into a
typed AST (`Expr`).
2. **Compiler (`CompiledExpression`)** – wraps each node in metadata (feature
usage, maximum window, operator list) and provides a serialisable
representation for downstream consumers.
3. **Computation engine (`ComputationEngine`)** – constructs an execution tree of
`ExpressionNode` implementors which update incrementally as new samples arrive.
4. **Indicator façade** – packages the engine behind a conventional
`FactorExpIndicator` that plugs into Nautilus Trader strategies via Cython.

## Expression syntax

FactorExp supports a small, explicit DSL:

- **Features** begin with `$` (for example `$close`, `$volume`). The parser
strips the sigil internally but metadata preserves the identifier for buffer
allocation.
- **Constants** accept standard floating-point literals, including scientific
notation (e.g. `1.23e-4`).
- **Unary operators** use the `Fn(arg)` style (`Neg`, `Abs`, `Log`, `Exp`,
`Sin`, `Cos`, `Tan`, etc.).
- **Binary operators** include arithmetic (`Add`, `Sub`, `Mul`, `Div`, `Pow`),
comparisons (`Greater`, `Less`, `GreaterEq`, `LessEq`, `Equal`, `NotEqual`),
logical combinators (`And`, `Or`), extrema (`Max`, `Min`) and the ternary-like
`When(condition, then, else)`.
- **Rolling operators** are normally prefixed with `TS_` and take two arguments –
a signal and a window length. `ZScore` and `Demean` are accepted without the
prefix for convenience.
- **Clipping operator** `Clip(value, min, max)` bounds an expression between dynamic or constant limits; this is useful for enforcing exposure caps such as the [-2, 2] leverage band.
- **Pair rolling operators** (`TS_Corr`, `TS_Cov`, `TS_Beta`) require two signals
plus a window length.

The parser is whitespace tolerant, right-associative for exponentiation, and
emits descriptive `ExpressionError::ParseError` messages pinpointing the failing
character offset.

### Rolling operators

| Operator | Description |
| --- | --- |
| `TS_Mean` | Rolling arithmetic mean. |
| `TS_Sum` | Rolling sum. |
| `TS_Std` / `TS_Var` | Rolling standard deviation / variance (sample ddof=1). |
| `TS_Min` / `TS_Max` | Rolling extrema. |
| `TS_Med` / `TS_Median` | Rolling median. |
| `TS_EMA` / `TS_WMA` | Exponential / weighted moving averages. |
| `TS_Skew`, `TS_Kurt`, `TS_Mad` | Higher-moment statistics. |
| `TS_Delta` | Difference between the most recent value and the value `window` periods ago. |
| `TS_Ref` | Raw value `window` periods ago with no differencing. |
| `TS_Rank`, `TS_Argmax`, `TS_Argmin` | Ranking utilities across the window. |
| `TS_Product` | Rolling product. |
| `TS_Quantile` | Empirical quantile; expects `(expr, window, phi)` with `0 ≤ phi ≤ 1`. |
| `ZScore`, `Demean` | Statistical normalisation helpers (aliases without `TS_`). |

Pairwise statistics (`TS_Corr`, `TS_Cov`, `TS_Beta`) operate on two child
expressions and share the same window parameter semantics.

## Computation engine

`ComputationEngine` translates a `CompiledExpression` into a tree of runtime
nodes:

- `FeatureNode` mirrors the latest feature values sourced from the indicator's
per-feature `RollingBuffer`s.
- `ConstantNode` injects literal values.
- `InstantOperatorNode` evaluates stateless operators immediately from their
children's current outputs.
- `OperatorNode` encapsulates stateful rolling operators returned by
`operators::get_rolling_operator` (or `get_pair_rolling_operator` for
pair-statistics) and advances their buffers on each update.

Each node supports `update`, `current_value`, `reset`, and `name` for debugging.
Consumers typically build the tree once and reuse it:

```rust
use factorexp::{parser::Parser, CompiledExpression, ComputationEngine, RollingBuffer};
use std::collections::HashMap;

let mut parser = Parser::new("TS_Mean($close, 20)");
let parsed = parser.parse().unwrap();
let compiled = CompiledExpression::new(factorexp::parser::convert_to_expr_node(parsed));

let mut engine = ComputationEngine::new();
engine.build_tree(&compiled).unwrap();

let mut buffers = HashMap::new();
buffers.insert("close".into(), RollingBuffer::new(20));
let value = engine.update_and_compute(&buffers).unwrap();
```

`ComputationEngine::compute` is kept for backward compatibility but internally
invokes the incremental path.

## Python indicator API

`nautilus_trader.indicators.factorexp.indicator` provides the Cython-backed
`FactorExpIndicator`, which integrates seamlessly with the existing indicator
infrastructure.

```python
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.core.nautilus_pyo3 import PriceType

alpha = FactorExpIndicator("TS_Mean($close, 20) / TS_Std($close, 20)")

momentum = FactorExpIndicator(
    "TS_Delta($close, 5)",
    period=5,
    price_type=PriceType.LAST,
    name="Momentum"
)

for bar in feed:
    momentum.handle_bar(bar)
    if momentum.initialized:
        emit_signal(momentum.value)
```

Key behaviours:

- Parsing, compilation, and tree construction happen in Rust on instantiation.
- Feature buffers sized to `expression.metadata.max_window` are allocated
automatically.
- `handle_quote`, `handle_trade`, and `handle_bar` push data into those buffers
and advance the computation engine.
- `value`, `count`, and `initialized` expose the latest indicator state; `reset`
clears all buffers and operator history.
- A convenience factory `create_factor_indicator` mirrors the constructor for
callers who prefer a functional interface.

## Rust API surface

Rust consumers can use the same components directly when embedding FactorExp in
custom services. The key exports from `factorexp` are:

- `parser::Parser` and `parser::convert_to_expr_node` to obtain a
`CompiledExpression` from a string.
- `ComputationEngine` for incremental evaluation.
- `operators::*` if you need direct access to rolling operator implementations.
- `RollingBuffer` and `BufferStats` for managing time-series windows.

`ExpressionResult<T>` aliases `Result<T, ExpressionError>` and is used across the
API to surface parsing, operator lookup, and runtime errors.

## Error handling and diagnostics

`ExpressionError` enumerates parse errors, unknown operators, invalid parameter
configurations, and runtime computation failures. Python bindings translate
these into clear `ValueError` or `RuntimeError` exceptions. Rust callers can use
the variants directly for control flow or logging.

Many rolling operators maintain a `staleness_count` and emit warnings if they
receive repeated `NaN` inputs. Enable `RUST_LOG=debug` when diagnosing data flow
issues.

## Testing and benchmarking

- `cargo test -p factorexp` covers the parser, engine, and operator suites.
- Python smoke and regression tests reside in
  `tests/unit_tests/indicators/factorexp/` and can be run via `pytest`.
- Micro-benchmarks in `crates/factorexp/benches` explore dispatch costs; execute
  with `cargo bench`.

## Current limitations

- Cross-sectional operators (for example, multi-instrument rankings) are not yet
ported from the legacy Python implementation. The previous code remains under
`nautilus_trader/indicators/factorexp/_backup` for reference.
- Feature buffers assume that the upstream data stream populates every feature
referenced by the expression; missing values propagate as `NaN` and may prevent
operators from becoming ready.
- Rolling operators require sufficient history (e.g. `TS_Mean($close, 20)` needs
20 observations) before `FactorExpIndicator.initialized` flips to `True`.

