#!/usr/bin/env python3
"""
FactorExp集成问题诊断与修复脚本

这个脚本展示了当前的问题并提供修复方案。
"""

import os
import sys
from pathlib import Path

def diagnose_issues():
    """诊断当前集成问题"""
    print("=" * 60)
    print("FactorExp 集成诊断")
    print("=" * 60)
    
    issues = []
    
    # 1. 检查Python备份
    backup_path = Path("nautilus_trader/indicators/factorexp/_backup/indicator.py.backup")
    if backup_path.exists():
        print("✅ Python实现备份存在:", backup_path)
    else:
        print("❌ Python实现备份不存在")
        issues.append("missing_backup")
    
    # 2. 检查Cython wrapper
    cython_path = Path("nautilus_trader/indicators/factorexp/indicator.pyx")
    if cython_path.exists():
        print("✅ Cython包装器存在:", cython_path)
        
        # 检查导入路径
        with open(cython_path, 'r') as f:
            content = f.read()
            if "nautilus_trader.core.nautilus_pyo3.indicators" in content:
                print("⚠️  Cython导入路径: nautilus_pyo3.indicators (可能错误)")
                issues.append("wrong_import_path")
            elif "nautilus_trader.core.nautilus_pyo3.factorexp" in content:
                print("✅ Cython导入路径: nautilus_pyo3.factorexp (正确)")
    else:
        print("❌ Cython包装器不存在")
        issues.append("missing_cython")
    
    # 3. 检查Rust PyO3绑定
    pyo3_path = Path("crates/pyo3/src/lib.rs")
    if pyo3_path.exists():
        with open(pyo3_path, 'r') as f:
            content = f.read()
            if "factorexp" in content:
                print("✅ PyO3已注册factorexp模块")
            else:
                print("❌ PyO3未注册factorexp模块")
                issues.append("pyo3_not_registered")
    
    # 4. 检查Rust实现
    rust_indicator = Path("crates/factorexp/src/python/indicator.rs")
    if rust_indicator.exists():
        with open(rust_indicator, 'r') as f:
            content = f.read()
            if 'module = "nautilus_trader.core.nautilus_pyo3.indicators"' in content:
                print("⚠️  Rust模块路径: nautilus_pyo3.indicators")
                issues.append("rust_module_path_mismatch")
            elif 'module = "nautilus_trader.core.nautilus_pyo3.factorexp"' in content:
                print("✅ Rust模块路径: nautilus_pyo3.factorexp")
    
    return issues

def propose_fixes(issues):
    """根据诊断结果提出修复方案"""
    print("\n" + "=" * 60)
    print("修复方案")
    print("=" * 60)
    
    if not issues:
        print("✅ 没有检测到问题")
        return
    
    print(f"\n发现 {len(issues)} 个问题:\n")
    
    for issue in issues:
        if issue == "wrong_import_path":
            print("问题: Cython导入路径错误")
            print("修复方案A: 更改Cython导入为:")
            print("  from nautilus_trader.core.nautilus_pyo3.factorexp import FactorExpIndicator")
            print("修复方案B: 更改Rust模块声明为:")
            print('  #[pyclass(module = "nautilus_trader.core.nautilus_pyo3.indicators")]')
            print()
        
        elif issue == "rust_module_path_mismatch":
            print("问题: Rust模块路径与Cython导入不匹配")
            print("当前Rust声明了indicators路径，但PyO3注册在factorexp下")
            print("修复: 统一路径，建议都使用factorexp")
            print()
        
        elif issue == "missing_backup":
            print("问题: Python备份不存在")
            print("修复: 需要恢复Python实现或完成Rust集成")
            print()

def quick_fix_option():
    """快速修复选项：恢复Python实现"""
    print("\n" + "=" * 60)
    print("快速修复选项：恢复Python实现")
    print("=" * 60)
    
    print("""
执行以下命令恢复Python实现:

# 1. 恢复Python实现
mv nautilus_trader/indicators/factorexp/_backup/indicator.py.backup \\
   nautilus_trader/indicators/factorexp/indicator.py

# 2. 删除Cython wrapper（可选）
rm nautilus_trader/indicators/factorexp/indicator.pyx

# 3. 更新__init__.py
# 在__init__.py中添加: from .indicator import FactorExpIndicator
    """)

def rust_fix_option():
    """Rust集成修复选项"""
    print("\n" + "=" * 60)
    print("Rust集成修复选项")
    print("=" * 60)
    
    print("""
修复Rust集成需要:

1. 统一模块路径（选择一个）:
   选项A: 修改Cython导入
   - 编辑 indicator.pyx
   - 改为: from nautilus_trader.core.nautilus_pyo3.factorexp import FactorExpIndicator
   
   选项B: 修改Rust模块路径
   - 编辑 crates/factorexp/src/python/indicator.rs
   - 改为: #[pyclass(module = "nautilus_trader.core.nautilus_pyo3.factorexp")]

2. 实现表达式桥接:
   - 使用Python解析器解析表达式
   - 将解析结果传递给Rust
   - Rust执行计算

3. 编译和测试:
   make build-debug
   pytest tests/unit_tests/indicators/factorexp/
    """)

def main():
    """主函数"""
    print("\n🔍 开始FactorExp集成诊断...\n")
    
    # 诊断问题
    issues = diagnose_issues()
    
    # 提出修复方案
    propose_fixes(issues)
    
    # 显示快速修复选项
    quick_fix_option()
    
    # 显示Rust修复选项
    rust_fix_option()
    
    print("\n" + "=" * 60)
    print("建议")
    print("=" * 60)
    print("""
根据当前状况，建议采用渐进式方案:

1. 短期（立即）: 恢复Python实现，确保功能可用
2. 中期（1周）: 修复Rust集成路径问题，实现基础功能
3. 长期（1月）: 逐步将热点算子迁移到Rust，优化性能

这样可以避免"全有或全无"的风险，保证系统始终可用。
    """)

if __name__ == "__main__":
    main()