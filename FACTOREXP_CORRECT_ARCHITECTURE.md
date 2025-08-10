# FactorExp 正确架构方案

## 问题诊断

当前实现存在严重的架构问题：

1. **双重定义**：
   - `nautilus_trader/indicators/factorexp/core/indicator.py` - Python 实现 (应删除)
   - `nautilus_trader/indicators/factorexp.pyx` - Cython 实现 (位置错误)

2. **导入冲突**：策略中导入的类会产生歧义

## 正确的 Nautilus Trader 指标架构

```
nautilus_trader/
├── indicators/
│   ├── factorexp/
│   │   ├── __init__.py              # 空文件或简单导入
│   │   ├── indicator.pyx             # Cython 实现（主要接口）
│   │   ├── expressions/             # Python 解析器（保留）
│   │   │   ├── parser.py
│   │   │   ├── validator.py
│   │   │   └── ast.py
│   │   └── security/                # 安全配置（保留）
│   │       └── config.py
│   └── ...
└── core/
    └── nautilus_pyo3/
        └── indicators.pyi           # PyO3 类型存根
```

## 迁移方案

### 1. 移动 Cython 文件到正确位置
```bash
mv nautilus_trader/indicators/factorexp.pyx nautilus_trader/indicators/factorexp/indicator.pyx
```

### 2. 删除 Python 实现
```bash
rm nautilus_trader/indicators/factorexp/core/indicator.py
rm -rf nautilus_trader/indicators/factorexp/core/  # 如果没有其他文件
```

### 3. 清理 `__init__.py`
```python
# nautilus_trader/indicators/factorexp/__init__.py
"""FactorExp indicator with high-performance Rust backend."""

# 空文件，让 Python 识别为包即可
# 导入将直接使用: from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
```

### 4. 更新导入路径
```python
# 在策略中
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator

# 而不是
from nautilus_trader.indicators.factorexp import FactorExpIndicator
```

## 清理后的目录结构

```
nautilus_trader/indicators/factorexp/
├── __init__.py                      # 空文件
├── indicator.pyx                    # 主要的 Cython 实现
├── expressions/                     # 表达式解析（Python）
│   ├── __init__.py
│   ├── parser.py                   # 保留用于灵活的表达式解析
│   ├── validator.py
│   └── ast.py
└── security/                        # 安全配置
    ├── __init__.py
    └── config.py

# 删除的文件：
# - core/indicator.py                # Python 实现（删除）
# - core/engine.py                   # Python 引擎（删除）  
# - core/bridge.py                   # 桥接代码（删除）
# - core/rust_bridge.py              # Rust 桥接（删除）
# - adapters/                        # 适配器（整个目录删除）
# - operators/                       # Python 算子（删除，使用 Rust）
```

## 关键原则

1. **单一实现**：只有一个 `FactorExpIndicator` 类（Cython 版本）
2. **清晰路径**：导入路径明确无歧义
3. **遵循规范**：与其他 Nautilus Trader 指标保持一致

## 正确的使用方式

```python
# 导入
from nautilus_trader.indicators.factorexp.indicator import FactorExpIndicator
from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser

# 使用
class MyStrategy(Strategy):
    def on_start(self):
        # 创建指标（Rust 后端自动处理）
        self.indicator = FactorExpIndicator(
            expression="TS_Mean($close, 20)",
            name="MA20"
        )
        
        # 注册
        self.register_indicator_for_bars(self.indicator, self.bar_type)
```

## 性能保证

- **Cython 层**：类型安全和 Python 接口
- **Rust 后端**：通过 PyO3 实现高性能计算
- **零开销**：与原生指标相同的性能特征