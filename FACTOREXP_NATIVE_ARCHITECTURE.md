# FactorExp Native Architecture Design

## Overview

This document outlines the new architecture for FactorExp integration with Nautilus Trader, following the native indicator implementation patterns. The goal is to create a high-performance, expression-based factor system that seamlessly integrates with Nautilus Trader's event-driven architecture.

## Current Issues

1. **Pure Python Implementation**: Handle functions in `indicator.py` are implemented in Python, not following the Cython + Rust pattern
2. **Unused Code**: `adapters/` and `core/bridge.py` are not being used
3. **Architectural Mismatch**: Not following the native indicator pattern of Rust → PyO3 → Cython
4. **Performance**: Missing the performance benefits of Rust implementation

## Native Nautilus Trader Indicator Pattern

```
┌─────────────────┐
│  Rust Core      │  crates/indicators/src/
│  - Trait impl   │  - Core logic
│  - Performance  │  - Data structures
└────────┬────────┘
         │
         │ PyO3 Bindings
         ▼
┌─────────────────┐
│  Python Module  │  crates/indicators/src/python/
│  - #[pymethods] │  - Python API
│  - Type mapping │  - Method exposure
└────────┬────────┘
         │
         │ Import
         ▼
┌─────────────────┐
│  Cython Wrapper │  nautilus_trader/indicators/
│  - .pyx file    │  - Type declarations
│  - C imports    │  - Performance
└─────────────────┘
```

## New FactorExp Architecture

### 1. Rust Core (`crates/factorexp/`)

```rust
// crates/factorexp/src/indicator.rs
use nautilus_model::data::{Bar, QuoteTick, TradeTick};
use crate::expression::{Expression, CompiledExpression};
use crate::engine::ComputationEngine;

pub trait FactorIndicator {
    fn handle_quote(&mut self, quote: &QuoteTick);
    fn handle_trade(&mut self, trade: &TradeTick);
    fn handle_bar(&mut self, bar: &Bar);
    fn value(&self) -> f64;
    fn reset(&mut self);
}

pub struct ExpressionIndicator {
    expression: CompiledExpression,
    engine: ComputationEngine,
    buffers: HashMap<String, RollingBuffer>,
    value: f64,
    period: usize,
    count: usize,
    initialized: bool,
}

impl FactorIndicator for ExpressionIndicator {
    fn handle_bar(&mut self, bar: &Bar) {
        // Extract data
        let data = extract_bar_data(bar);
        
        // Update buffers
        for (feature, value) in data {
            if let Some(buffer) = self.buffers.get_mut(&feature) {
                buffer.push(value);
            }
        }
        
        // Compute if ready
        if self.count >= self.period {
            self.value = self.engine.compute(&self.expression, &self.buffers);
            self.initialized = true;
        }
        
        self.count += 1;
    }
}
```

### 2. Expression Engine (`crates/factorexp/src/engine.rs`)

```rust
pub struct ComputationEngine {
    operators: HashMap<String, Box<dyn Operator>>,
    cache: LRUCache<String, f64>,
}

impl ComputationEngine {
    pub fn compute(&mut self, expr: &CompiledExpression, buffers: &HashMap<String, RollingBuffer>) -> f64 {
        match &expr.node {
            ExprNode::Constant(val) => *val,
            ExprNode::Feature(name) => {
                buffers.get(name)
                    .and_then(|b| b.last())
                    .unwrap_or(0.0)
            }
            ExprNode::Operator { name, args, params } => {
                let operator = self.operators.get(name)
                    .expect("Unknown operator");
                
                let arg_values: Vec<f64> = args.iter()
                    .map(|arg| self.compute(arg, buffers))
                    .collect();
                
                operator.compute(&arg_values, params, buffers)
            }
        }
    }
}
```

### 3. PyO3 Bindings (`crates/factorexp/src/python/`)

```rust
// crates/factorexp/src/python/indicator.rs
use pyo3::prelude::*;
use nautilus_model::data::{Bar, QuoteTick, TradeTick};

#[pyclass(name = "FactorExpIndicator")]
pub struct PyFactorExpIndicator {
    inner: ExpressionIndicator,
}

#[pymethods]
impl PyFactorExpIndicator {
    #[new]
    #[pyo3(signature = (expression, period=None, price_type=None))]
    fn py_new(expression: &str, period: Option<usize>, price_type: Option<PriceType>) -> PyResult<Self> {
        let parsed = parse_expression(expression)?;
        let compiled = compile_expression(parsed)?;
        let period = period.unwrap_or_else(|| estimate_period(&compiled));
        
        Ok(Self {
            inner: ExpressionIndicator::new(compiled, period, price_type),
        })
    }
    
    #[getter]
    fn value(&self) -> f64 {
        self.inner.value()
    }
    
    #[getter]
    fn initialized(&self) -> bool {
        self.inner.initialized
    }
    
    #[pyo3(name = "handle_quote_tick")]
    fn py_handle_quote_tick(&mut self, quote: &QuoteTick) {
        self.inner.handle_quote(quote);
    }
    
    #[pyo3(name = "handle_trade_tick")]
    fn py_handle_trade_tick(&mut self, trade: &TradeTick) {
        self.inner.handle_trade(trade);
    }
    
    #[pyo3(name = "handle_bar")]
    fn py_handle_bar(&mut self, bar: &Bar) {
        self.inner.handle_bar(bar);
    }
    
    #[pyo3(name = "reset")]
    fn py_reset(&mut self) {
        self.inner.reset();
    }
}
```

### 4. Cython Wrapper (`nautilus_trader/indicators/factorexp.pyx`)

```cython
# distutils: language = c++
# cython: language_level = 3

from nautilus_trader.core.rust.model cimport PriceType
from nautilus_trader.indicators.base.indicator cimport Indicator
from nautilus_trader.model.data cimport Bar, QuoteTick, TradeTick

# Import from Rust
from nautilus_trader.core.rust.indicators.factorexp cimport FactorExpIndicator as RustFactorExpIndicator


cdef class FactorExpIndicator(Indicator):
    """
    An indicator that evaluates FactorExp expressions using high-performance Rust backend.
    
    Parameters
    ----------
    expression : str
        The FactorExp expression to evaluate
    period : int, optional
        The lookback period (auto-detected if not provided)
    price_type : PriceType, default=PriceType.LAST
        The price type for quote tick data
    """
    cdef RustFactorExpIndicator _rust_indicator
    cdef str _expression
    cdef object _name
    
    def __init__(
        self,
        str expression not None,
        int period = 0,
        PriceType price_type = PriceType.LAST,
        str name = None,
    ):
        # Initialize Rust indicator
        if period == 0:
            self._rust_indicator = RustFactorExpIndicator(expression, price_type=price_type)
        else:
            self._rust_indicator = RustFactorExpIndicator(expression, period, price_type)
        
        # Extract period from Rust indicator
        actual_period = self._rust_indicator.period
        
        # Initialize base class
        super().__init__(params=[expression, actual_period])
        
        self._expression = expression
        self._name = name or f"FactorExp({expression[:20]}...)" if len(expression) > 20 else f"FactorExp({expression})"
    
    @property
    def expression(self) -> str:
        return self._expression
    
    @property
    def name(self) -> str:
        return self._name
    
    cpdef void handle_quote_tick(self, QuoteTick tick):
        """Handle quote tick update."""
        self._rust_indicator.handle_quote_tick(tick)
    
    cpdef void handle_trade_tick(self, TradeTick tick):
        """Handle trade tick update."""
        self._rust_indicator.handle_trade_tick(tick)
    
    cpdef void handle_bar(self, Bar bar):
        """Handle bar update."""
        self._rust_indicator.handle_bar(bar)
    
    cpdef void reset(self):
        """Reset the indicator state."""
        self._rust_indicator.reset()
    
    @property
    def value(self) -> float:
        """Get the current indicator value."""
        return self._rust_indicator.value
    
    @property
    def initialized(self) -> bool:
        """Check if the indicator is initialized."""
        return self._rust_indicator.initialized
```

## Expression Parser Integration

The expression parser remains in Python for flexibility but compiles to Rust structures:

```python
# nautilus_trader/indicators/factorexp/parser.py
from typing import Dict, Any
from nautilus_trader.core.rust.indicators.factorexp import compile_expression as rust_compile

class ExpressionCompiler:
    """Compiles parsed expressions to Rust representation."""
    
    def compile(self, ast: Expression) -> CompiledExpression:
        # Convert Python AST to Rust-compatible format
        rust_ast = self._convert_to_rust_ast(ast)
        
        # Compile using Rust
        return rust_compile(rust_ast)
```

## Migration Plan

### Phase 1: Core Infrastructure
1. Implement Rust core structures (`ExpressionIndicator`, `ComputationEngine`)
2. Create PyO3 bindings for the indicator
3. Write Cython wrapper following native pattern

### Phase 2: Operator Migration
1. Move all operators to Rust implementation
2. Create operator registry in Rust
3. Expose operators through PyO3

### Phase 3: Integration
1. Update Python code to use Cython wrapper
2. Remove unused adapter and bridge code
3. Update tests and examples

### Phase 4: Optimization
1. Implement caching strategies
2. Add SIMD optimizations where applicable
3. Profile and optimize hot paths

## Benefits

1. **Performance**: 10-100x speedup for computations
2. **Consistency**: Same interface as native indicators
3. **Type Safety**: Rust's type system prevents errors
4. **Memory Efficiency**: Rust's zero-cost abstractions
5. **Integration**: Seamless with existing Nautilus Trader strategies

## Example Usage

```python
# In a strategy
from nautilus_trader.indicators.factorexp import FactorExpIndicator

class MyStrategy(Strategy):
    def __init__(self):
        # Create factor indicator
        self.momentum = FactorExpIndicator(
            expression="TS_Mean($close, 20) / TS_Mean($close, 50)",
            name="MomentumRatio"
        )
        
        # Register with engine (same as native indicators)
        self.register_indicator_for_bars(
            self.momentum,
            bar_type=BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
        )
    
    def on_bar(self, bar: Bar):
        # Use like any native indicator
        if self.momentum.initialized:
            signal = self.momentum.value
            # Trading logic...
```

## Next Steps

1. Set up Rust indicator structure in `crates/factorexp/`
2. Implement core expression evaluation engine
3. Create PyO3 bindings
4. Write Cython wrapper
5. Migrate Python code to use new implementation
6. Remove obsolete files
7. Update documentation and tests