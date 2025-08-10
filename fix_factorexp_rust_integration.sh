#!/bin/bash
# FactorExp Rust集成修复脚本
# 修复模块路径不匹配问题，启用高性能Rust后端

echo "🔧 FactorExp Rust Integration Fix"
echo "=================================="

# Step 1: 修复Cython导入路径
echo "Step 1: 修复Cython导入路径..."
cat > /tmp/fix_cython_import.py << 'EOF'
import sys
import re

# 读取indicator.pyx
with open('nautilus_trader/indicators/factorexp/indicator.pyx', 'r') as f:
    content = f.read()

# 修复导入路径
old_import = "from nautilus_trader.core.nautilus_pyo3.indicators import FactorExpIndicator as RustFactorExpIndicator"
new_import = "from nautilus_trader.core.nautilus_pyo3.factorexp import FactorExpIndicator as RustFactorExpIndicator"

content = content.replace(old_import, new_import)

# 写回文件
with open('nautilus_trader/indicators/factorexp/indicator.pyx', 'w') as f:
    f.write(content)

print("✅ Cython导入路径已修复")
EOF

python3 /tmp/fix_cython_import.py

# Step 2: 修复Rust模块声明
echo "Step 2: 修复Rust模块声明..."
cat > /tmp/fix_rust_module.py << 'EOF'
import re

# 读取indicator.rs
with open('crates/factorexp/src/python/indicator.rs', 'r') as f:
    content = f.read()

# 修复模块路径
old_module = '#[pyclass(name = "FactorExpIndicator", module = "nautilus_trader.core.nautilus_pyo3.indicators")]'
new_module = '#[pyclass(name = "FactorExpIndicator", module = "nautilus_trader.core.nautilus_pyo3.factorexp")]'

content = content.replace(old_module, new_module)

# 写回文件
with open('crates/factorexp/src/python/indicator.rs', 'w') as f:
    f.write(content)

print("✅ Rust模块声明已修复")
EOF

python3 /tmp/fix_rust_module.py

# Step 3: 创建表达式桥接器
echo "Step 3: 创建Python-Rust表达式桥接..."
cat > nautilus_trader/indicators/factorexp/bridge.py << 'EOF'
"""
Python-Rust表达式桥接器
实现Python AST到Rust CompiledExpression的转换
"""

import json
from typing import Dict, Any
from nautilus_trader.indicators.factorexp.expressions.ast import Expression

def serialize_expression(expr: Expression) -> str:
    """
    将Python Expression AST序列化为JSON字符串
    供Rust端反序列化使用
    """
    def node_to_dict(node):
        if hasattr(node, 'op'):
            # 算子节点
            return {
                'type': 'operator',
                'name': node.op,
                'args': [node_to_dict(arg) for arg in node.args],
                'params': getattr(node, 'params', {})
            }
        elif hasattr(node, 'value'):
            # 常量节点
            return {
                'type': 'constant',
                'value': node.value
            }
        elif hasattr(node, 'name'):
            # 特征节点
            return {
                'type': 'feature',
                'name': node.name
            }
        else:
            raise ValueError(f"Unknown node type: {type(node)}")
    
    return json.dumps(node_to_dict(expr.root))

def compile_expression_for_rust(expression_str: str) -> Dict[str, Any]:
    """
    编译表达式字符串为Rust可用的格式
    """
    from nautilus_trader.indicators.factorexp.expressions.parser import ExpressionParser
    
    parser = ExpressionParser()
    ast = parser.parse(expression_str)
    
    # 提取元数据
    metadata = {
        'features': list(ast.get_features()),
        'operators': ast.get_operators(),
        'max_window': ast.get_max_window_size(),
    }
    
    return {
        'ast': serialize_expression(ast),
        'metadata': metadata,
        'original': expression_str
    }
EOF

echo "✅ 表达式桥接器已创建"

# Step 4: 更新Rust端反序列化
echo "Step 4: 增强Rust表达式解析..."
cat > /tmp/enhance_rust_parser.py << 'EOF'
# 这部分需要在Rust端实现JSON反序列化
# 由于需要修改Rust代码，这里只提供建议

print("""
📝 Rust端增强建议：

在 crates/factorexp/src/python/indicator.rs 中，修改 parse_simple_expression 函数：

```rust
use serde_json;

fn parse_expression_from_json(json_str: &str) -> Result<CompiledExpression, ExpressionError> {
    let data: serde_json::Value = serde_json::from_str(json_str)
        .map_err(|e| ExpressionError::ParseError(format!("JSON parse error: {}", e)))?;
    
    // 递归构建ExprNode
    fn build_node(value: &serde_json::Value) -> Result<ExprNode, ExpressionError> {
        match value["type"].as_str() {
            Some("constant") => {
                let val = value["value"].as_f64()
                    .ok_or_else(|| ExpressionError::ParseError("Invalid constant".to_string()))?;
                Ok(ExprNode::Constant(val))
            }
            Some("feature") => {
                let name = value["name"].as_str()
                    .ok_or_else(|| ExpressionError::ParseError("Invalid feature".to_string()))?;
                Ok(ExprNode::Feature(name.to_string()))
            }
            Some("operator") => {
                // 实现算子节点构建...
            }
            _ => Err(ExpressionError::ParseError("Unknown node type".to_string()))
        }
    }
    
    let node = build_node(&data)?;
    Ok(CompiledExpression::new(node))
}
```
""")
EOF

python3 /tmp/enhance_rust_parser.py

# Step 5: 创建集成测试
echo "Step 5: 创建集成测试..."
cat > test_factorexp_integration.py << 'EOF'
"""
FactorExp Rust集成测试
"""

def test_rust_integration():
    """测试Rust后端是否正常工作"""
    try:
        # 尝试导入
        from nautilus_trader.core.nautilus_pyo3.factorexp import FactorExpIndicator
        print("✅ Rust模块导入成功")
        
        # 测试创建指标
        indicator = FactorExpIndicator("TS_Mean($close, 20)")
        print(f"✅ 创建指标成功: {indicator}")
        
        # 测试算子
        from nautilus_trader.core.nautilus_pyo3.factorexp import create_operator
        mean_op = create_operator("TS_Mean", 20)
        print(f"✅ 创建算子成功: {mean_op}")
        
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("需要先编译: make build-debug")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

if __name__ == "__main__":
    print("\n=== FactorExp Rust集成测试 ===\n")
    if test_rust_integration():
        print("\n✅ 所有测试通过！Rust集成已修复。")
    else:
        print("\n⚠️ 测试未通过，请检查上述错误信息。")
EOF

echo ""
echo "=================================="
echo "✅ 修复脚本执行完成！"
echo ""
echo "下一步操作："
echo "1. 编译项目: make build-debug"
echo "2. 运行测试: python3 test_factorexp_integration.py"
echo "3. 如果测试失败，检查编译输出"
echo ""
echo "注意：完整的JSON反序列化需要在Rust端实现。"
echo "     当前修复主要解决了模块路径问题。"