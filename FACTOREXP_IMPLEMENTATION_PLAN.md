# FactorExp Implementation Plan

## Phase 1: Rust Core Implementation

### 1.1 Expression Data Structures (`crates/factorexp/src/expression.rs`)

```rust
use std::collections::HashMap;
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ExprNode {
    Constant(f64),
    Feature(String),
    Operator {
        name: String,
        args: Vec<CompiledExpression>,
        params: HashMap<String, f64>,
    },
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompiledExpression {
    pub node: ExprNode,
    pub metadata: ExpressionMetadata,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExpressionMetadata {
    pub features: Vec<String>,
    pub max_window: usize,
    pub has_cross_sectional: bool,
    pub operators: Vec<String>,
}
```

### 1.2 Indicator Implementation (`crates/factorexp/src/indicator.rs`)

```rust
use std::collections::HashMap;
use nautilus_model::{
    data::{Bar, QuoteTick, TradeTick},
    enums::PriceType,
};
use crate::buffer::RollingBuffer;
use crate::expression::CompiledExpression;
use crate::engine::ComputationEngine;

pub struct FactorExpIndicator {
    expression: CompiledExpression,
    engine: ComputationEngine,
    buffers: HashMap<String, RollingBuffer>,
    period: usize,
    price_type: PriceType,
    value: f64,
    count: usize,
    initialized: bool,
}

impl FactorExpIndicator {
    pub fn new(expression: CompiledExpression, period: usize, price_type: PriceType) -> Self {
        // Initialize buffers for each feature
        let mut buffers = HashMap::new();
        for feature in &expression.metadata.features {
            buffers.insert(feature.clone(), RollingBuffer::new(period));
        }
        
        Self {
            expression,
            engine: ComputationEngine::new(),
            buffers,
            period,
            price_type,
            value: 0.0,
            count: 0,
            initialized: false,
        }
    }
    
    pub fn handle_bar(&mut self, bar: &Bar) {
        // Extract bar data
        let data = HashMap::from([
            ("open".to_string(), bar.open.as_f64()),
            ("high".to_string(), bar.high.as_f64()),
            ("low".to_string(), bar.low.as_f64()),
            ("close".to_string(), bar.close.as_f64()),
            ("volume".to_string(), bar.volume.as_f64()),
        ]);
        
        self.update_with_data(data);
    }
    
    fn update_with_data(&mut self, data: HashMap<String, f64>) {
        // Update buffers
        for (feature, value) in data {
            if let Some(buffer) = self.buffers.get_mut(&feature) {
                buffer.push(value);
            }
        }
        
        self.count += 1;
        
        // Compute if we have enough data
        if self.count >= self.period {
            self.value = self.engine.compute(&self.expression, &self.buffers);
            if !self.initialized && self.count >= self.period {
                self.initialized = true;
            }
        }
    }
}
```

### 1.3 Computation Engine (`crates/factorexp/src/engine.rs`)

```rust
use std::collections::HashMap;
use crate::expression::{CompiledExpression, ExprNode};
use crate::buffer::RollingBuffer;
use crate::operators::{get_operator, Operator};

pub struct ComputationEngine {
    cache: HashMap<String, f64>,
}

impl ComputationEngine {
    pub fn new() -> Self {
        Self {
            cache: HashMap::new(),
        }
    }
    
    pub fn compute(&mut self, expr: &CompiledExpression, buffers: &HashMap<String, RollingBuffer>) -> f64 {
        self.compute_node(&expr.node, buffers)
    }
    
    fn compute_node(&mut self, node: &ExprNode, buffers: &HashMap<String, RollingBuffer>) -> f64 {
        match node {
            ExprNode::Constant(val) => *val,
            
            ExprNode::Feature(name) => {
                // Handle feature references (e.g., $close, $volume)
                let feature_name = name.trim_start_matches('$');
                buffers.get(feature_name)
                    .and_then(|b| b.last())
                    .unwrap_or(0.0)
            }
            
            ExprNode::Operator { name, args, params } => {
                // Get operator implementation
                let operator = get_operator(name)
                    .expect(&format!("Unknown operator: {}", name));
                
                // Compute arguments
                let arg_values: Vec<f64> = args.iter()
                    .map(|arg| self.compute_node(&arg.node, buffers))
                    .collect();
                
                // Execute operator
                operator.compute(&arg_values, params, buffers)
            }
        }
    }
}
```

## Phase 2: PyO3 Bindings

### 2.1 Indicator Python Bindings (`crates/factorexp/src/python/indicator.rs`)

```rust
use pyo3::prelude::*;
use pyo3::types::PyDict;
use nautilus_model::data::{Bar, QuoteTick, TradeTick};
use nautilus_model::enums::PriceType;
use crate::indicator::FactorExpIndicator;
use crate::parser::parse_and_compile;

#[pyclass(name = "FactorExpIndicator", module = "nautilus_trader.core.nautilus_pyo3.indicators")]
pub struct PyFactorExpIndicator {
    inner: FactorExpIndicator,
    expression_str: String,
}

#[pymethods]
impl PyFactorExpIndicator {
    #[new]
    #[pyo3(signature = (expression, period=None, price_type=None))]
    fn py_new(expression: &str, period: Option<usize>, price_type: Option<PriceType>) -> PyResult<Self> {
        // Parse and compile expression
        let compiled = parse_and_compile(expression)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(
                format!("Failed to compile expression: {}", e)
            ))?;
        
        // Auto-detect period if not provided
        let period = period.unwrap_or(compiled.metadata.max_window);
        let price_type = price_type.unwrap_or(PriceType::Last);
        
        Ok(Self {
            inner: FactorExpIndicator::new(compiled, period, price_type),
            expression_str: expression.to_string(),
        })
    }
    
    #[getter]
    fn expression(&self) -> &str {
        &self.expression_str
    }
    
    #[getter]
    fn period(&self) -> usize {
        self.inner.period
    }
    
    #[getter]
    fn value(&self) -> f64 {
        self.inner.value
    }
    
    #[getter]
    fn count(&self) -> usize {
        self.inner.count
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

### 2.2 Module Registration (`crates/factorexp/src/python/mod.rs`)

```rust
use pyo3::prelude::*;

mod indicator;
use indicator::PyFactorExpIndicator;

// Re-export existing operator bindings
mod operators;

#[pymodule]
pub fn factorexp(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Register indicator
    m.add_class::<PyFactorExpIndicator>()?;
    
    // Register operators (existing)
    operators::register_operators(m)?;
    
    Ok(())
}
```

## Phase 3: Cython Wrapper

### 3.1 Main Indicator Wrapper (`nautilus_trader/indicators/factorexp.pyx`)

```cython
# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2025 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

from typing import Optional

from nautilus_trader.core.correctness cimport Condition
from nautilus_trader.core.rust.model cimport PriceType
from nautilus_trader.indicators.base.indicator cimport Indicator
from nautilus_trader.model.data cimport Bar
from nautilus_trader.model.data cimport QuoteTick
from nautilus_trader.model.data cimport TradeTick

# Import Rust implementation
from nautilus_trader.core.nautilus_pyo3.indicators import FactorExpIndicator as RustFactorExpIndicator


cdef class FactorExpIndicator(Indicator):
    """
    An indicator that evaluates FactorExp expressions on streaming market data.
    
    This indicator provides a high-performance bridge between FactorExp's expression
    language and Nautilus Trader's indicator framework, with all computations
    performed in Rust.
    
    Parameters
    ----------
    expression : str
        The FactorExp expression to evaluate (e.g., "TS_Mean($close, 20)")
    period : int, optional
        The maximum lookback period required by the expression (auto-detected if not provided)
    price_type : PriceType, default=PriceType.LAST
        The price type to use for quote tick data
    name : str, optional
        Custom name for the indicator (defaults to the expression)
    
    Raises
    ------
    ValueError
        If the expression cannot be parsed or compiled
    
    Examples
    --------
    >>> # Simple moving average ratio
    >>> indicator = FactorExpIndicator("TS_Mean($close, 20) / TS_Mean($close, 50)")
    
    >>> # Bollinger Band width
    >>> indicator = FactorExpIndicator(
    ...     "(TS_Mean($close, 20) + 2 * TS_Std($close, 20)) - (TS_Mean($close, 20) - 2 * TS_Std($close, 20))",
    ...     name="BBWidth"
    ... )
    """
    cdef object _rust_indicator
    cdef str _expression
    cdef str _name
    cdef readonly int period
    
    def __init__(
        self,
        str expression not None,
        int period = 0,
        PriceType price_type = PriceType.LAST,
        str name = None,
    ):
        Condition.not_none(expression, "expression")
        Condition.not_empty(expression.strip(), "expression")
        
        # Create Rust indicator
        if period > 0:
            self._rust_indicator = RustFactorExpIndicator(expression, period, price_type)
        else:
            self._rust_indicator = RustFactorExpIndicator(expression, price_type=price_type)
        
        # Get actual period from Rust
        self.period = self._rust_indicator.period
        
        # Initialize base class
        super().__init__(params=[expression, self.period])
        
        # Store properties
        self._expression = expression
        self._name = name or self._generate_name(expression)
    
    cdef str _generate_name(self, str expression):
        """Generate a readable name from the expression."""
        if len(expression) > 30:
            return f"FactorExp({expression[:27]}...)"
        return f"FactorExp({expression})"
    
    @property
    def expression(self) -> str:
        """Return the expression string."""
        return self._expression
    
    @property
    def name(self) -> str:
        """Return the indicator name."""
        return self._name
    
    @property
    def value(self) -> float:
        """Return the current indicator value."""
        return self._rust_indicator.value
    
    @property
    def count(self) -> int:
        """Return the count of updates."""
        return self._rust_indicator.count
    
    @property
    def initialized(self) -> bool:
        """Return whether the indicator is initialized."""
        return self._rust_indicator.initialized
    
    cpdef void handle_quote_tick(self, QuoteTick tick):
        """
        Update the indicator with the given quote tick.
        
        Parameters
        ----------
        tick : QuoteTick
            The quote tick to handle
        """
        Condition.not_none(tick, "tick")
        self._rust_indicator.handle_quote_tick(tick)
    
    cpdef void handle_trade_tick(self, TradeTick tick):
        """
        Update the indicator with the given trade tick.
        
        Parameters
        ----------
        tick : TradeTick
            The trade tick to handle
        """
        Condition.not_none(tick, "tick")
        self._rust_indicator.handle_trade_tick(tick)
    
    cpdef void handle_bar(self, Bar bar):
        """
        Update the indicator with the given bar.
        
        Parameters
        ----------
        bar : Bar
            The bar to handle
        """
        Condition.not_none(bar, "bar")
        self._rust_indicator.handle_bar(bar)
    
    cpdef void reset(self):
        """Reset the indicator state."""
        self._rust_indicator.reset()
        self._set_has_inputs(False)
        self._set_initialized(False)
    
    def __repr__(self) -> str:
        return f"{self._name}(period={self.period})"
```

## Phase 4: Python Integration

### 4.1 Updated `__init__.py`

```python
# nautilus_trader/indicators/factorexp/__init__.py
"""
FactorExp indicator integration for Nautilus Trader.

High-performance expression-based indicators with Rust backend.
"""

# Import Cython indicator
from nautilus_trader.indicators.factorexp import FactorExpIndicator

# Import expression parser (remains in Python for flexibility)
from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
from nautilus_trader.indicators.factorexp.expressions.validator import ExpressionValidator

__all__ = [
    "FactorExpIndicator",
    "ExpressionParser", 
    "ExpressionValidator",
]
```

### 4.2 Example Usage

```python
# examples/indicators/factorexp_native_example.py
from nautilus_trader.indicators.factorexp import FactorExpIndicator
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.trading import Strategy

class FactorExpStrategy(Strategy):
    """Example strategy using native FactorExp indicators."""
    
    def __init__(self):
        super().__init__()
        
        # Create indicators with expressions
        self.momentum = FactorExpIndicator(
            expression="TS_Mean($close, 20) / TS_Mean($close, 50)",
            name="Momentum"
        )
        
        self.volatility = FactorExpIndicator(
            expression="TS_Std($close, 20) / TS_Mean($close, 20)",
            name="Volatility"
        )
        
        self.rsi_approx = FactorExpIndicator(
            expression="100 - 100 / (1 + TS_Mean(Max($close - Delay($close, 1), 0), 14) / TS_Mean(Max(Delay($close, 1) - $close, 0), 14))",
            name="RSI_Approx"
        )
    
    def on_start(self):
        # Register indicators for bars
        bar_type = BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
        
        self.register_indicator_for_bars(self.momentum, bar_type)
        self.register_indicator_for_bars(self.volatility, bar_type)
        self.register_indicator_for_bars(self.rsi_approx, bar_type)
    
    def on_bar(self, bar: Bar):
        # Use indicators like native ones
        if not self.momentum.initialized:
            return
        
        momentum_signal = self.momentum.value
        volatility = self.volatility.value
        rsi = self.rsi_approx.value
        
        # Trading logic based on factors
        if momentum_signal > 1.05 and volatility < 0.02 and rsi < 70:
            # Bullish signal
            pass
```

## Migration Steps

### Step 1: Set up Rust structures
1. Create expression data structures
2. Implement indicator core logic
3. Build computation engine

### Step 2: Create PyO3 bindings
1. Wrap indicator in PyO3
2. Add to pyo3 crate exports
3. Test Python imports

### Step 3: Implement Cython wrapper
1. Create factorexp.pyx
2. Add to setup.py/build.py
3. Test integration

### Step 4: Clean up
1. Remove unused files:
   - `nautilus_trader/indicators/factorexp/adapters/`
   - `nautilus_trader/indicators/factorexp/core/bridge.py`
   - Old `indicator.py` implementation
2. Update imports in remaining Python files
3. Update tests

### Step 5: Documentation
1. Update API documentation
2. Create migration guide
3. Add performance benchmarks

## Performance Expectations

Based on native indicator performance:
- 10-100x faster than Python implementation
- Sub-microsecond update times for simple expressions
- Efficient memory usage with zero-copy where possible
- Parallel computation support for complex expressions

## Testing Strategy

1. **Unit Tests**: Test each Rust component
2. **Integration Tests**: Test PyO3 bindings
3. **System Tests**: Test Cython integration
4. **Performance Tests**: Benchmark against Python implementation
5. **Compatibility Tests**: Ensure existing strategies work

## Risks and Mitigations

1. **Expression Parsing**: Keep parser in Python for flexibility, compile to Rust
2. **Backward Compatibility**: Maintain same Python API
3. **Complex Expressions**: Implement incremental optimization
4. **Cross-sectional Operations**: Design for future multi-instrument support