#!/usr/bin/env python3
"""
Trading Data Reader Script

正确读取Nautilus Trader生成的数据文件的脚本。
这些文件使用Apache Arrow IPC流格式，不能直接用pandas.read_feather()读取。
"""

import sys
from pathlib import Path
import pandas as pd
import pyarrow as pa
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def read_nautilus_data_file(file_path: str) -> Optional[pd.DataFrame]:
    """
    读取Nautilus Trader生成的数据文件
    
    Parameters
    ----------
    file_path : str
        数据文件路径
        
    Returns
    -------
    pd.DataFrame or None
        读取的数据，如果读取失败返回None
    """
    file_path = Path(file_path)
    
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return None
    
    file_size = file_path.stat().st_size
    print(f"📁 文件: {file_path.name}")
    print(f"💾 大小: {file_size:,} 字节")
    
    if file_size == 0:
        print("⚠️  文件为空")
        return None
    
    # 方法1: 使用PyArrow IPC流读取 (推荐)
    try:
        with open(file_path, 'rb') as f:
            reader = pa.ipc.open_stream(f)
            table = reader.read_all()
            
        print(f"✅ 成功读取Arrow IPC文件!")
        print(f"📊 数据形状: {table.num_rows:,} 行 x {table.num_columns} 列")
        
        # 转换为pandas DataFrame
        df = table.to_pandas()
        return df
        
    except Exception as e:
        print(f"❌ Arrow IPC读取失败: {e}")
    
    # 方法2: 尝试使用Arrow IPC文件读取
    try:
        with open(file_path, 'rb') as f:
            reader = pa.ipc.open_file(f)
            table = reader.read_all()
            
        print(f"✅ 成功读取Arrow IPC文件 (文件模式)!")
        df = table.to_pandas()
        return df
        
    except Exception as e:
        print(f"❌ Arrow IPC文件读取失败: {e}")
    
    # 方法3: 尝试标准feather读取（兼容性）
    try:
        df = pd.read_feather(file_path)
        print(f"✅ 成功读取Feather文件!")
        return df
        
    except Exception as e:
        print(f"❌ Feather读取失败: {e}")
    
    print("❌ 所有读取方法都失败了")
    return None

def read_nautilus_data_catalog(data_directory: str, instance_id: str) -> list:
    """
    使用Nautilus DataCatalog读取完整数据
    
    Parameters
    ---------- 
    data_directory : str
        数据目录路径 (如 ./data)
    instance_id : str
        实例ID (如 b73c3c19-9236-4036-aa45-93ecb604d81b)
    
    Returns
    -------
    list
        包含所有数据对象的列表
    """
    try:
        from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog
        
        catalog = ParquetDataCatalog(data_directory)
        
        # 使用正确的方法读取完整的实时运行数据
        data = catalog.read_live_run(instance_id)
        
        if data:
            print(f"✅ 成功读取实时数据: {len(data)} 条记录")
            
            # 按类型统计数据
            type_counts = {}
            for item in data:
                type_name = type(item).__name__
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            print("📊 数据类型统计:")
            for type_name, count in sorted(type_counts.items()):
                print(f"   {type_name}: {count:,} 条")
            
            return data
        else:
            print("⚠️ 未找到数据")
            return []
        
    except Exception as e:
        print(f"❌ DataCatalog读取失败: {e}")
        return []

def check_system_running() -> bool:
    """检查交易系统是否正在运行"""
    import psutil
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'main.py' in ' '.join(proc.info['cmdline'] or []):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def main():
    """主函数 - 读取交易数据示例"""
    print("🚀 Nautilus Trader 数据读取工具")
    print("=" * 50)
    
    # 检查系统状态
    if check_system_running():
        print("⚠️ 警告: 检测到交易系统可能正在运行")
        print("   这可能导致数据文件读取失败（文件正在写入中）")
        print("   建议停止交易系统后再读取数据\n")
    
    # 示例文件路径
    data_dir = Path("./data/live")
    
    # 查找最新的实例目录
    instance_dirs = [d for d in data_dir.iterdir() if d.is_dir()]
    if not instance_dirs:
        print("❌ 未找到数据目录")
        return
    
    # 使用最新的实例目录
    latest_instance = max(instance_dirs, key=lambda x: x.stat().st_mtime)
    instance_id = latest_instance.name
    print(f"📂 使用实例: {instance_id}")
    
    # 查找数据文件
    data_files = list(latest_instance.glob("*.feather"))
    print(f"📄 找到 {len(data_files)} 个数据文件")
    
    # 读取永续合约数据（通常是主要数据）
    crypto_perp_files = [f for f in data_files if "crypto_perpetual" in f.name]
    
    if crypto_perp_files:
        print(f"\n📊 读取永续合约数据...")
        df = read_nautilus_data_file(str(crypto_perp_files[0]))
        
        if df is not None:
            print(f"\n📈 数据摘要:")
            print(f"   形状: {df.shape[0]:,} 行 x {df.shape[1]} 列")
            if not df.empty:
                print(f"   列名: {list(df.columns)}")
                print(f"\n🔍 前3条记录:")
                print(df.head(3).to_string())
                
                # 如果有时间戳列，显示时间范围
                time_cols = [col for col in df.columns if 'time' in col.lower() or 'ts' in col.lower()]
                if time_cols:
                    print(f"\n⏰ 时间范围:")
                    for col in time_cols[:2]:  # 只显示前两个时间列
                        if pd.api.types.is_numeric_dtype(df[col]):
                            print(f"   {col}: {df[col].min()} - {df[col].max()}")
    
    # 方法2: 使用DataCatalog读取
    print(f"\n🗂️ 使用DataCatalog读取...")
    catalog_data = read_nautilus_data_catalog("./data", instance_id)
    
    if catalog_data:
        print(f"\n📚 DataCatalog成功读取了 {len(catalog_data)} 条数据记录")
        
        # 如果有工具数据，显示详细信息
        instruments = [item for item in catalog_data if hasattr(item, 'id')]
        if instruments:
            print(f"\n🏷️ 交易工具:")
            for inst in instruments[:5]:  # 只显示前5个
                print(f"   {inst.id}")
            if len(instruments) > 5:
                print(f"   ... 还有 {len(instruments) - 5} 个")
    else:
        print("⚠️ DataCatalog未能读取到数据")

if __name__ == "__main__":
    main()