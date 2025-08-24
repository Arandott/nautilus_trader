# FactorExp 日志文件位置分析

## 当前状况
用户发现日志文件直接保存在 `factorexp_live_trading/` 目录下，如：
```
factorexp_live_trading/FACTOREXP-LIVE-001_2025-08-21_6a44a180-1cfd-425b-b893-68f5d6be948a.json
```

## 原因分析

### Nautilus Trader 默认行为
根据源码分析，Nautilus Trader的日志和数据文件保存位置由以下因素决定：

1. **工作目录**: 默认情况下，文件保存在当前工作目录
2. **catalog_path**: 在BacktestConfig中有此配置，但TradingNodeConfig中未直接暴露
3. **环境变量**: 可能通过环境变量控制(需要进一步验证)

### 文件类型说明
- **JSON文件**: 包含交易数据、订单记录、仓位快照等结构化数据
- **日志文件**: 程序运行日志(如果启用文件日志)
- **数据库文件**: SQLite数据库文件(如果使用)

## 当前配置检查

### LoggingConfig 设置
```python
logging=LoggingConfig(
    log_level="INFO",
    log_level_file="DEBUG", 
    log_file_format="json",  # 结构化日志格式
    log_colors=True,
)
```

### 潜在解决方案

#### 方案1: 创建data目录并调整工作目录
```bash
mkdir -p factorexp_live_trading/data
cd factorexp_live_trading/data
python ../main.py
```

#### 方案2: 添加环境变量控制(需验证)
```bash
export NAUTILUS_DATA_DIR="./data"
export NAUTILUS_LOG_DIR="./logs"
```

#### 方案3: 修改启动脚本
在main.py中添加工作目录设置：
```python
import os
data_dir = os.path.join(os.getcwd(), "data")
os.makedirs(data_dir, exist_ok=True)
os.chdir(data_dir)
```

## 推荐配置

### 建议的目录结构
```
factorexp_live_trading/
├── main.py
├── config/
├── strategies/
├── data/              # 所有数据文件
│   ├── logs/          # 日志文件
│   ├── orders/        # 订单数据
│   ├── positions/     # 仓位数据  
│   └── trades/        # 交易记录
└── .env
```

### 具体实现
1. 在main.py的初始化阶段创建data目录
2. 设置工作目录到data目录
3. 确保所有数据文件保存在指定位置

## 是否合理?

### 当前方案的问题
- **混乱的目录结构**: 数据文件与代码文件混在一起
- **不便于管理**: 难以区分哪些是数据文件，哪些是代码文件
- **版本控制问题**: 数据文件不应该提交到git

### 推荐改进
1. ✅ **分离关注点**: 代码和数据分开存储
2. ✅ **便于备份**: data目录可以单独备份
3. ✅ **便于清理**: 可以安全删除data目录进行重置
4. ✅ **符合惯例**: 大部分项目都将数据文件放在专门的data目录

## 结论
**不合理，建议调整为data目录结构**，这样更符合项目管理的最佳实践。