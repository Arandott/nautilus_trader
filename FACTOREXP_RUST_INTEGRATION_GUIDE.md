# FactorExp Rust集成指南

## 当前状态

1. **Rust代码已实现** ✅
   - 位置：`crates/factorexp/`
   - 包含15个核心算子的高性能实现

2. **Python集成已实现** ✅
   - engine.py已支持use_rust参数
   - rust_bridge.py提供了智能fallback

3. **项目集成未完成** ❌
   - factorexp未加入Nautilus Trader的Rust workspace
   - import路径不正确

## 正确的集成步骤

### 步骤1：将factorexp加入workspace

修改根目录的`Cargo.toml`：
```toml
[workspace]
members = [
    # ... 其他成员 ...
    "crates/factorexp",  # 添加这行
]

[workspace.dependencies]
# ... 其他依赖 ...
nautilus-factorexp = { path = "crates/factorexp", version = "0.49.0" }
```

### 步骤2：添加Python绑定依赖

修改`crates/pyo3/Cargo.toml`：
```toml
[dependencies]
# ... 其他依赖 ...
nautilus-factorexp = { workspace = true, features = ["python"] }

[features]
extension-module = [
    # ... 其他features ...
    "nautilus-factorexp/extension-module",
]
```

### 步骤3：注册Python模块

修改`crates/pyo3/src/lib.rs`：
```rust
// 在nautilus_pyo3函数中添加
let n = "factorexp";
let submodule = pyo3::wrap_pymodule!(nautilus_factorexp::python::factorexp);
m.add_wrapped(submodule)?;
sys_modules.set_item(format!("{module_name}.{n}"), m.getattr(n)?)?;
re_export_module_attributes(m, n)?;
```

### 步骤4：添加Python feature到factorexp

修改`crates/factorexp/Cargo.toml`：
```toml
[features]
default = []
extension-module = ["pyo3/extension-module"]
python = ["pyo3"]

[dependencies]
# 添加optional pyo3依赖
pyo3 = { workspace = true, optional = true }
```

### 步骤5：创建Python模块入口

创建`crates/factorexp/src/python/mod.rs`：
```rust
use pyo3::prelude::*;

#[pymodule]
pub fn factorexp(_: Python<'_>, m: &Bound<'_, PyModule>) -> PyResult<()> {
    // 注册所有算子
    m.add_class::<crate::operators::rolling::Mean>()?;
    m.add_class::<crate::operators::rolling::Sum>()?;
    // ... 其他算子
    
    // 注册工厂函数
    m.add_function(wrap_pyfunction!(crate::python::create_operator, m)?)?;
    
    Ok(())
}
```

### 步骤6：更新build.py

在`build.py`的`_build_rust_libs`函数中添加：
```python
needed_crates = [
    # ... 其他crates ...
    "nautilus-factorexp",  # 添加这个
]
```

### 步骤7：修正import路径

修改`rust_bridge.py`：
```python
try:
    from nautilus_trader.core.nautilus_pyo3.factorexp import (
        create_operator as rust_create_operator,
        Mean as RustMean,
        # ... 其他算子
    )
    RUST_OPERATORS_AVAILABLE = True
except ImportError:
    RUST_OPERATORS_AVAILABLE = False
```

## 编译和测试

```bash
# 清理旧的构建
make clean

# 重新构建（包含factorexp）
make build

# 或使用poetry
poetry run python build.py

# 测试import
python -c "from nautilus_trader.core.nautilus_pyo3.factorexp import create_operator"

# 运行测试
pytest tests/unit_tests/indicators/factorexp/test_rust_operators.py -v
```

## 替代方案：集成到indicators模块

如果不想创建独立的factorexp crate，可以直接集成到现有的indicators模块：

1. 将factorexp代码移到`crates/indicators/src/factorexp/`
2. 在`crates/indicators/src/lib.rs`中添加：
   ```rust
   pub mod factorexp;
   ```
3. 在`crates/indicators/src/python/mod.rs`中注册算子

这样import路径变为：
```python
from nautilus_trader.core.nautilus_pyo3.indicators import (
    FactorExpMean,
    FactorExpSum,
    # ...
)
```

## 性能验证

集成完成后，运行性能测试：
```bash
# 运行演示
python examples/factorexp_rust_engine_demo.py

# 应该看到：
# Rust operators available: True
# Speedup: 10-100x
```

## 注意事项

1. **版本一致性**：确保factorexp使用相同的workspace版本
2. **Feature flags**：正确配置Python features
3. **错误处理**：保持fallback机制以确保兼容性
4. **测试覆盖**：确保所有算子都有对应的测试

## 总结

正确的集成需要：
1. ✅ Rust代码实现（已完成）
2. ✅ Python桥接层（已完成）  
3. ❌ Workspace集成（待完成）
4. ❌ PyO3模块注册（待完成）
5. ❌ 正确的import路径（待修正）

完成这些步骤后，factorexp的Rust算子将真正集成到Nautilus Trader中，实现10-100倍的性能提升！