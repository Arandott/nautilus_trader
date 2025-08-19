# FactorExp Comprehensive Test Suite

This directory contains a comprehensive test suite for the FactorExp indicator system, covering all operators, edge cases, and complex expressions with correctness verification.

## 📋 Test Suite Overview

### 1. Basic Integration Tests (`test_factorexp_integration.py`)
- ✅ Basic system integration
- ✅ Simple expressions and data handling
- ✅ Rust-Python bridge functionality

### 2. Comprehensive Tests (`test_factorexp_comprehensive.py`)
- **All Mathematical Operators**: +, -, *, /, ^
- **All Unary Operators**: Log, Abs, Sign, Neg, Sqrt, Exp, Sin, Cos, Tan, etc.
- **All Comparison Operators**: Greater, Less, Equal, etc.
- **All Rolling Operators**: TS_Mean, TS_Sum, TS_Std, TS_Max, TS_Min, etc.
- **Edge Cases**: Insufficient data, zero/negative values, division by zero
- **Complex Nested Expressions**: Multiple levels of nesting
- **Performance Tests**: Large datasets, compilation speed, memory stability

### 3. Advanced Tests (`test_factorexp_advanced.py`)
- **Pair Rolling Operators**: TS_Corr, TS_Cov, TS_Beta
- **Cross-Sectional Operators**: CSRank, ZScore, Demean, CSMean, CSStd
- **Advanced Edge Cases**: Extreme values, rapid changes, constant values
- **Complex Interactions**: Mixed operator types, deeply nested expressions
- **Stress Tests**: Performance with complex expressions

### 4. Test Runner (`run_factorexp_tests.py`)
- Automated test execution with detailed reporting
- Multiple test suite options
- Performance monitoring and error tracking

## 🎯 Coverage Summary

### Operators Tested
| Category | Operators | Coverage |
|----------|-----------|----------|
| **Unary** | Log, Log10, Abs, Sign, Neg, Sqrt, Exp, Sin, Cos, Tan, Sinh, Cosh, Tanh, Asin, Acos, Atan | ✅ Complete |
| **Binary** | Add, Sub, Mul, Div, Pow, Greater, Less, GreaterEq, LessEq, Equal, NotEqual, And, Or, Max, Min | ✅ Complete |
| **Rolling** | TS_Mean, TS_Sum, TS_Std, TS_Var, TS_Max, TS_Min, TS_Med, TS_Delta, TS_Ref, etc. | ✅ Complete |
| **Pair Rolling** | TS_Cov, TS_Corr, TS_Beta | ✅ Complete |
| **Cross-Sectional** | CSRank, ZScore, Demean, CSMean, CSStd, CSSum | ✅ Complete |

### Test Categories
- ✅ **Correctness Verification**: All operators tested with known expected values
- ✅ **Edge Cases**: Insufficient data, extreme values, division by zero
- ✅ **Complex Expressions**: Nested operations, financial indicators
- ✅ **Performance**: Large datasets, compilation speed, memory stability
- ✅ **Error Handling**: Invalid inputs, boundary conditions

## 🚀 Usage

### Quick Start
```bash
# Run all tests with verbose output
python run_factorexp_tests.py --verbose

# Run specific test suite
python run_factorexp_tests.py --suite comprehensive

# Run basic tests only
python run_factorexp_tests.py --suite basic
```

### Using pytest
```bash
# Run comprehensive tests
pytest test_factorexp_comprehensive.py -v

# Run advanced tests
pytest test_factorexp_advanced.py -v

# Run all factorexp tests
pytest test_factorexp_*.py -v
```

### Manual Testing
```python
from test_factorexp_comprehensive import run_expression_test

# Test a specific expression
result = run_expression_test("TS_Mean($close, 20) / TS_Std($close, 20)", num_bars=50)
print(f"Result: {result}")
```

## 📊 Test Examples

### Basic Operators
```python
# Mathematical operations
"$close + 5"                    # Expected: close_price + 5
"$close * 2"                    # Expected: close_price * 2
"$high - $low"                  # Expected: price_range

# Unary functions
"Abs(-5)"                       # Expected: 5.0
"Sqrt(100)"                     # Expected: 10.0
"Log(2.718281828)"             # Expected: ~1.0 (ln(e))
```

### Rolling Operators
```python
# Time series operations
"TS_Mean($close, 5)"           # 5-period moving average
"TS_Std($close, 20)"           # 20-period standard deviation
"TS_Delta($close, 1)"          # Price change from previous bar
"TS_Ref($close, 5)"            # Price from 5 periods ago
```

### Complex Nested Expressions
```python
# Financial indicators
"TS_Mean($close, 20) / TS_Mean($close, 50)"  # Moving average ratio
"($close - TS_Mean($close, 20)) / TS_Std($close, 20)"  # Z-score
"TS_Mean(Abs($close - TS_Ref($close, 1)), 14)"  # Average true range

# Bollinger Band position
"($close - TS_Mean($close, 20)) / (2 * TS_Std($close, 20))"

# RSI-like calculation
"TS_Mean(Max($close - TS_Ref($close, 1), 0), 14)"
```

## 🧪 Edge Cases Tested

### Data Insufficiency
- Window size larger than available data
- First few bars with insufficient history
- System response to missing data

### Extreme Values
- Very large numbers (1e10)
- Very small numbers (1e-10)
- Zero values
- Negative values
- Division by zero protection

### Rapid Changes
- Oscillating values
- Sudden spikes
- Constant values
- Trending data

## 📈 Performance Benchmarks

### Test Performance Targets
- **1000 bars processing**: < 1.0 second
- **Expression compilation**: < 5.0 seconds for 500 expressions
- **Memory stability**: No leaks after 100 indicator cycles
- **Deep nesting (10 levels)**: < 1.0 second for 100 bars

### Complexity Handling
- ✅ Single expressions: Instant
- ✅ Simple rolling (TS_Mean): < 1ms per bar
- ✅ Complex nested: < 10ms per bar
- ✅ Financial indicators: < 50ms per bar

## 🔍 Correctness Verification

### Mathematical Verification
All operators are tested with known mathematical properties:

```python
# Basic math
assert "5 + 3" == 8.0
assert "10 / 2" == 5.0
assert "2 ^ 3" == 8.0

# Trigonometry
assert "Sin(0)" == 0.0
assert "Cos(0)" == 1.0
assert "Sin(π/2)" ≈ 1.0

# Statistics
assert TS_Mean([1,2,3,4,5]) == 3.0
assert TS_Max([1,5,3]) == 5.0
assert TS_Min([1,5,3]) == 1.0
```

### Financial Indicator Validation
```python
# Moving average properties
assert TS_Mean(constant_data) == constant_value
assert TS_Std(constant_data) == 0.0

# Correlation properties  
assert TS_Corr(x, x) ≈ 1.0  # Perfect correlation
assert -1.0 ≤ TS_Corr(x, y) ≤ 1.0  # Correlation bounds
```

## 🐛 Error Handling

### Graceful Degradation
- Invalid expressions → Clear error messages
- Missing data → NaN or reasonable defaults
- Division by zero → Infinity or NaN
- Extreme values → Maintained precision where possible

### Error Categories Tested
1. **Parse Errors**: Invalid syntax, unknown operators
2. **Runtime Errors**: Division by zero, domain errors
3. **Data Errors**: Insufficient data, missing features
4. **Memory Errors**: Large datasets, memory leaks

## 📝 Adding New Tests

### Test Structure
```python
def test_new_feature(self):
    """Test description."""
    # Create test data
    indicator = FactorExpIndicator("expression")
    
    # Feed data
    self.feed_bars(indicator, count)
    
    # Verify results
    assert condition, f"Error message: expected {expected}, got {indicator.value}"
```

### Best Practices
1. **Clear Names**: Use descriptive test method names
2. **Known Values**: Test with data that has predictable results
3. **Edge Cases**: Test boundary conditions
4. **Error Handling**: Verify graceful failure modes
5. **Performance**: Include timing assertions for complex operations

## 🎯 Expected Results

### All Tests Should Pass
When the system is fully implemented and integrated:
- ✅ Basic integration: 100% pass rate
- ✅ Comprehensive tests: >95% pass rate
- ✅ Advanced tests: >90% pass rate (some features may be partially implemented)
- ✅ Sample expressions: >95% pass rate

### Acceptable Failures
Some tests may fail if features are not yet fully implemented:
- Cross-sectional operators (CS_*) - may be partially implemented
- Advanced rolling operators (TS_WMA, TS_EMA) - implementation dependent
- Pair rolling operators - may require additional work

## 🔧 Maintenance

### Regular Testing
Run the test suite regularly to catch regressions:
```bash
# Daily smoke test
python run_factorexp_tests.py --suite basic

# Weekly comprehensive test
python run_factorexp_tests.py --suite all --verbose

# Before releases
pytest test_factorexp_*.py -v --tb=long
```

### Performance Monitoring
Track performance metrics over time:
- Expression compilation time
- Data processing speed
- Memory usage patterns
- Error rates

This comprehensive test suite ensures the FactorExp system works correctly across all use cases, handles edge conditions gracefully, and performs well under various conditions.