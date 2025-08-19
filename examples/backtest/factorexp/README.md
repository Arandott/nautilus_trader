# FactorExp Backtesting Examples

This directory contains examples demonstrating how to use FactorExp expressions within Nautilus Trader's backtesting framework.

## Overview

FactorExp is a high-performance expression language for quantitative finance that allows you to write complex mathematical expressions for technical analysis. These examples show how to integrate FactorExp with Nautilus Trader for backtesting trading strategies.

## Files

### `factorexp_ema_cross_strategy.py`
The main strategy implementation that demonstrates:
- **FactorExp Integration**: Using `FactorExpIndicator` instead of traditional indicators
- **Complex Expressions**: Multi-component mathematical expressions for analysis
- **Real-time Computation**: High-performance Rust backend for calculations
- **Strategy Logic**: EMA crossover with volatility filtering and momentum confirmation

### `factorexp_ema_cross_ethusdt.py`
The backtest runner that shows:
- **Data Loading**: Using Nautilus Trader's test data infrastructure
- **Strategy Configuration**: Setting up FactorExp parameters
- **Execution**: Running the backtest and generating reports
- **Analysis**: Extracting insights from FactorExp indicators

### `README.md`
This documentation file.

## FactorExp Expressions Used

The strategy demonstrates several powerful FactorExp expressions:

### 1. EMA Ratio
```
TS_Mean($close, 10) / TS_Mean($close, 20)
```
Calculates the ratio between fast and slow EMAs to detect crossovers.

### 2. Volatility Filter
```
TS_Std($close, 20) / TS_Mean($close, 20)
```
Normalized volatility to filter out low-volatility periods.

### 3. Momentum Analysis
```
($close - TS_Mean($close, 20)) / TS_Mean($close, 20)
```
Price deviation from moving average as a momentum indicator.

### 4. Trend Strength
```
(TS_Mean($close, 10) - TS_Mean($close, 20)) / TS_Mean($close, 20)
```
Difference between EMAs as a percentage of the slow EMA.

## Running the Example

### Prerequisites
1. **Build Requirements**: Ensure FactorExp is compiled with `make build`
2. **Test Data**: The example uses Nautilus Trader's built-in test data
3. **Dependencies**: All required packages are included with Nautilus Trader

### Execution
```bash
# From the nautilus_trader root directory
python examples/backtest/factorexp/factorexp_ema_cross_ethusdt.py
```

### Expected Output
The example will:
1. Load historical ETH/USDT trade data
2. Set up the backtesting environment
3. Run the FactorExp strategy
4. Display detailed reports including:
   - Account performance
   - Order fills
   - Position history
   - FactorExp indicator values

## Strategy Logic

### Entry Conditions
- **Long Entry**: Fast EMA crosses above slow EMA (ratio > 1.0) with positive momentum and sufficient volatility
- **Short Entry**: Fast EMA crosses below slow EMA (ratio < 1.0) with negative momentum and sufficient volatility

### Exit Conditions
- **Long Exit**: Trend strength weakens significantly (< -1%)
- **Short Exit**: Trend strength strengthens significantly (> 1%)

### Risk Management
- **Volatility Filter**: Only trades when market volatility exceeds 0.1% threshold
- **Position Sizing**: Fixed position size per trade
- **No Leverage**: Cash account with spot trading only

## Key Advantages of FactorExp

### 1. **Performance**
- All calculations performed in high-performance Rust
- O(1) complexity for rolling window operations
- Minimal memory allocation during computation

### 2. **Expressiveness**
- Complex mathematical expressions in a single line
- No need to manage multiple indicator objects
- Composable expressions for sophisticated analysis

### 3. **Integration**
- Drop-in replacement for traditional indicators
- Compatible with Nautilus Trader's indicator framework
- Automatic registration and bar updates

### 4. **Flexibility**
- Easy to modify expressions without code changes
- Support for multiple timeframes and price types
- Extensible with custom operators

## Comparison with Traditional Approach

### Traditional Indicators
```python
# Multiple indicator objects
self.fast_ema = ExponentialMovingAverage(10)
self.slow_ema = ExponentialMovingAverage(20)
self.volatility = StandardDeviation(20)

# Manual ratio calculation
ratio = self.fast_ema.value / self.slow_ema.value
normalized_vol = self.volatility.value / self.fast_ema.value
```

### FactorExp Approach
```python
# Single expression with automatic optimization
self.ema_ratio = FactorExpIndicator(
    "TS_Mean($close, 10) / TS_Mean($close, 20)"
)
self.volatility = FactorExpIndicator(
    "TS_Std($close, 20) / TS_Mean($close, 20)"
)
```

## Extending the Example

### Adding New Expressions
You can easily add more sophisticated expressions:

```python
# RSI approximation
self.rsi_approx = FactorExpIndicator(
    "100 - 100 / (1 + TS_Mean(Max($close - Delay($close, 1), 0), 14) / TS_Mean(Max(Delay($close, 1) - $close, 0), 14))"
)

# Bollinger Bands
self.bb_upper = FactorExpIndicator(
    "TS_Mean($close, 20) + 2 * TS_Std($close, 20)"
)

# Price momentum
self.price_momentum = FactorExpIndicator(
    "($close - Delay($close, 5)) / Delay($close, 5)"
)
```

### Parameter Optimization
The strategy configuration allows easy parameter tuning:

```python
config = FactorExpEMACrossConfig(
    fast_ema_period=5,           # Faster signals
    slow_ema_period=15,          # Shorter lookback
    volatility_threshold=0.0005,  # Lower volatility filter
    trade_size=Decimal("0.25"),  # Larger position size
)
```

## Performance Notes

### Computational Efficiency
- FactorExp uses O(1) rolling window algorithms
- Memory usage is constant regardless of data length
- Rust backend provides near-native performance

### Memory Management
- Minimal heap allocations during computation
- Efficient buffer management for rolling windows
- Automatic cleanup of intermediate calculations

## Troubleshooting

### Common Issues

1. **Import Error**: Ensure FactorExp is compiled with `make build`
2. **Expression Syntax**: Check FactorExp documentation for valid operators
3. **Data Requirements**: Ensure sufficient historical data for indicator warmup

### Debug Mode
Enable detailed logging by modifying the strategy:

```python
self.log.info(
    f"Indicator values: ratio={self.ema_ratio.value:.6f}, "
    f"vol={self.volatility.value:.6f}",
    color=LogColor.CYAN,
)
```

## Further Reading

- [FactorExp Documentation](../../indicators/factorexp/)
- [Nautilus Trader Backtesting Guide](https://docs.nautilustrader.io/concepts/backtesting)
- [Strategy Development Guide](https://docs.nautilustrader.io/concepts/strategies)

## License

This example is licensed under the same terms as Nautilus Trader (LGPL 3.0).