# FactorExp Engine集成Rust算子指南

## 修改engine.py以使用Rust算子

### 方案1：最小改动（推荐）

在`engine.py`的`ComputationEngine`类中，只需修改`_create_streaming_computation`方法：

```python
# nautilus_trader/indicators/factorexp/engine.py

from nautilus_trader.indicators.factorexp.core.rust_bridge import enhanced_bridge

class ComputationEngine:
    def __init__(self, use_rust: bool = True):
        """初始化计算引擎。
        
        Parameters
        ----------
        use_rust : bool, default=True
            是否使用Rust算子加速
        """
        self.use_rust = use_rust
        self._logger = logging.getLogger(__name__)
        
    def _create_streaming_computation(self, operator: str, window: int, **kwargs):
        """创建流式计算实例。"""
        if self.use_rust:
            try:
                # 尝试使用enhanced_bridge，自动选择最佳实现
                return enhanced_bridge.create_computation(operator, window, **kwargs)
            except Exception as e:
                self._logger.warning(f"Failed to create Rust operator {operator}: {e}")
        
        # 回退到原有实现
        return self._create_python_computation(operator, window, **kwargs)
    
    def _create_python_computation(self, operator: str, window: int, **kwargs):
        """创建Python实现的计算实例（原有代码）。"""
        # ... 原有的Python实现逻辑 ...
```

### 方案2：完整替换

如果想要更精细的控制，可以完全替换StreamingBridge：

```python
# nautilus_trader/indicators/factorexp/engine.py

from nautilus_trader.indicators.factorexp.core.rust_bridge import (
    enhanced_bridge,
    RustBridge,
)
from nautilus_trader.indicators.factorexp.core.bridge import StreamingBridge

class ComputationEngine:
    def __init__(self, use_rust: bool = True):
        self.use_rust = use_rust and RustBridge.is_available()
        
        # 根据配置选择bridge
        if self.use_rust:
            self._bridge = enhanced_bridge
            self._logger.info(f"Using Rust operators for: {RustBridge.RUST_OPERATOR_MAP.keys()}")
        else:
            self._bridge = StreamingBridge()
            self._logger.info("Using Python operators")
        
        # 统计信息
        self._operator_stats = {}
    
    def create_streaming_operator(self, node: RollingOp) -> StreamingComputation:
        """为滚动操作符创建流式计算实例。"""
        operator = node.operator
        window = node.window
        
        # 记录使用统计
        self._operator_stats[operator] = self._operator_stats.get(operator, 0) + 1
        
        # 使用选定的bridge创建
        return self._bridge.create_computation(operator, window)
    
    def get_performance_report(self) -> Dict[str, Any]:
        """获取性能报告。"""
        report = {
            "rust_enabled": self.use_rust,
            "operator_usage": self._operator_stats,
        }
        
        if self.use_rust:
            report["rust_stats"] = self._bridge.get_statistics()
        
        return report
```

## 在FactorExpIndicator中启用

修改`indicator.py`以支持Rust算子配置：

```python
# nautilus_trader/indicators/factorexp/core/indicator.py

class FactorExpIndicator(Indicator):
    def __init__(
        self,
        expression: str,
        buffer_size: int,
        price_type: PriceType = PriceType.LAST,
        use_rust: bool = True,  # 新增参数
    ):
        """初始化FactorExp指标。
        
        Parameters
        ----------
        use_rust : bool, default=True
            是否使用Rust算子加速
        """
        super().__init__(params=[expression, buffer_size])
        
        # 创建引擎时传递use_rust参数
        self._engine = ComputationEngine(use_rust=use_rust)
```

## 策略中的使用示例

```python
# 在策略中使用

class MyFactorStrategy(Strategy):
    def __init__(self, config):
        super().__init__(config)
        
        # 创建使用Rust加速的因子
        self.momentum_factor = FactorExpIndicator(
            expression="TS_Mean($close, 20) / TS_Mean($close, 50) - 1",
            buffer_size=50,
            use_rust=True,  # 启用Rust加速
        )
        
    def on_start(self):
        # 检查Rust使用情况
        engine = self.momentum_factor._engine
        if hasattr(engine, 'get_performance_report'):
            report = engine.get_performance_report()
            self.log.info(f"Factor engine report: {report}")
```

## 配置和环境变量

可以通过环境变量全局控制：

```python
# nautilus_trader/indicators/factorexp/config.py

import os

# 全局配置
FACTOREXP_USE_RUST = os.getenv("FACTOREXP_USE_RUST", "true").lower() == "true"

# 在engine.py中使用
class ComputationEngine:
    def __init__(self, use_rust: bool = None):
        if use_rust is None:
            use_rust = FACTOREXP_USE_RUST
        self.use_rust = use_rust
```

## 性能监控

添加性能监控功能：

```python
# nautilus_trader/indicators/factorexp/core/performance.py

class PerformanceMonitor:
    """监控Rust vs Python算子性能。"""
    
    def __init__(self):
        self.timings = {
            "rust": defaultdict(list),
            "python": defaultdict(list),
        }
    
    def record_timing(self, operator: str, is_rust: bool, duration: float):
        """记录操作耗时。"""
        key = "rust" if is_rust else "python"
        self.timings[key][operator].append(duration)
    
    def get_summary(self) -> Dict[str, Any]:
        """获取性能摘要。"""
        summary = {}
        
        for impl in ["rust", "python"]:
            for op, times in self.timings[impl].items():
                if times:
                    summary[f"{impl}_{op}"] = {
                        "count": len(times),
                        "mean_ms": np.mean(times) * 1000,
                        "std_ms": np.std(times) * 1000,
                    }
        
        return summary
```

## 部署检查清单

1. **构建Rust扩展**
   ```bash
   cd crates/factorexp
   maturin build --release
   pip install target/wheels/*.whl
   ```

2. **验证安装**
   ```python
   from nautilus_trader.indicators.factorexp.core.rust_bridge import RustBridge
   print(f"Rust operators available: {RustBridge.is_available()}")
   print(f"Supported operators: {list(RustBridge.RUST_OPERATOR_MAP.keys())}")
   ```

3. **运行测试**
   ```bash
   pytest tests/unit_tests/indicators/factorexp/test_rust_operators.py -v
   ```

4. **性能验证**
   ```bash
   python examples/factorexp_rust_demo.py
   ```

## 故障排除

### Rust算子不可用

```python
# 添加诊断代码
from nautilus_trader.indicators.factorexp.core.rust_bridge import RustBridge

if not RustBridge.is_available():
    print("Rust operators not available. Possible reasons:")
    print("1. Rust extension not built: cd crates/factorexp && maturin develop")
    print("2. Import error - check Python path")
    print("3. Architecture mismatch - rebuild for your platform")
```

### 性能未提升

1. 确认Rust算子被使用：
   ```python
   stats = enhanced_bridge.get_statistics()
   print(f"Rust attempts: {stats['stats']['attempts']}")
   print(f"Rust successes: {stats['stats']['successes']}")
   ```

2. 检查数据规模 - Rust在大数据量时优势更明显

3. 避免频繁的Python/Rust边界跨越

## 总结

集成Rust算子只需要最小的代码改动，就能获得10-100倍的性能提升。通过智能的fallback机制，即使Rust不可用也不会影响功能。建议在所有生产环境中启用Rust算子。