# FactorExp Live Trading - 日志管理指南

## 📍 日志存储位置详解

### 🖥️ 控制台日志（实时显示）
```
位置: 终端输出
级别: INFO（可配置）
内容: 策略信号、交易执行、风险检查、错误信息
保存: 不自动保存到文件
```

**示例输出**：
```
2024-01-15 10:30:15 [INFO] FactorExpLiveStrategy: Factor values avg_raw=0.8420 effective=0.8420 factors=[vwap=0.9100, close=0.7740]
2024-01-15 10:30:15 [INFO] FactorExpLiveStrategy: Entering LONG position: size=0.0024, price=50000.0
2024-01-15 10:30:16 [INFO] FactorExpLiveStrategy: Position opened: BUY 0.0024 BTCUSDT-PERP.BINANCE
```

### 📄 系统日志文件
```
默认位置: ./nautilus_trader.log
配置位置: LoggingConfig参数控制
级别: DEBUG（可配置）
格式: JSON或文本格式
```

**实际存储路径**：
```bash
factorexp_live_trading/
├── nautilus_trader.log          # 主系统日志
├── logs/                        # 日志目录（如果创建）
│   ├── factorexp_YYYYMMDD.log  # 按日期分割的日志
│   ├── trading_YYYYMMDD.log    # 交易相关日志
│   └── errors_YYYYMMDD.log     # 错误日志
└── data/                        # 数据存储目录
    ├── catalog/                 # 数据目录
    ├── cache/                   # 缓存数据
    └── backups/                 # 备份文件
```

### 💾 交易数据存储

Nautilus Trader内置数据存储系统：

```
位置: ./data/ 目录
格式: 专有二进制格式 + JSON
内容: 订单、仓位、PnL、市场数据
```

**具体文件结构**：
```bash
data/
├── cache/
│   ├── instruments.json        # 合约信息缓存
│   ├── accounts.json          # 账户信息缓存  
│   └── orders.json            # 订单状态缓存
├── catalog/
│   ├── orders/                # 历史订单记录
│   ├── positions/             # 历史仓位记录
│   ├── account_events/        # 账户变化事件
│   └── trade_ticks/           # 成交数据
└── backups/                   # 每日自动备份
    ├── orders_20240115.json
    ├── positions_20240115.json
    └── pnl_20240115.json
```

## ⚙️ 日志配置详解

### 当前配置（trading_config.py）
```python
logging=LoggingConfig(
    log_level="INFO",              # 控制台日志级别
    log_level_file="DEBUG",        # 文件日志级别  
    log_file_format="json",        # JSON结构化格式
    log_colors=True,               # 彩色控制台输出
    log_component_levels={
        "Strategy": "DEBUG",       # 策略组件：详细日志
        "FactorExp": "DEBUG",      # FactorExp指标：详细日志
        "Portfolio": "INFO",       # 投组监控：标准日志
        "RiskEngine": "INFO",      # 风险引擎：标准日志
        "PortfolioMonitor": "DEBUG" # 投组监控：详细日志
    }
)
```

### 环境变量配置（.env）
```bash
# 基本日志设置
LOG_LEVEL=INFO                    # 控制台日志级别
LOG_LEVEL_FILE=DEBUG             # 文件日志级别
ENABLE_STRUCTURED_LOGGING=true   # 启用JSON格式

# 高级日志设置（可选）
LOG_DIRECTORY=./logs             # 自定义日志目录
LOG_MAX_SIZE=100MB              # 单个日志文件最大大小
LOG_BACKUP_COUNT=30             # 保留日志文件数量
```

## 📊 日志内容详解

### 1. 策略执行日志
```json
{
  "timestamp": "2024-01-15T10:30:15.123Z",
  "level": "INFO",
  "component": "FactorExpLiveStrategy",
  "message": "Generated LONG signal",
  "data": {
    "instrument": "BTCUSDT-PERP.BINANCE",
    "ema_ratio": 1.0078,
    "momentum": 0.0045,
    "volatility": 0.0156,
    "signal_type": "LONG"
  }
}
```

### 2. 交易执行日志
```json
{
  "timestamp": "2024-01-15T10:30:16.456Z",
  "level": "INFO", 
  "component": "Strategy",
  "message": "Position opened",
  "data": {
    "position_id": "P-20240115-001",
    "instrument": "BTCUSDT-PERP.BINANCE",
    "side": "BUY",
    "quantity": "0.0024",
    "entry_price": "50000.0",
    "notional_value": "120.0"
  }
}
```

### 3. 风险管理日志
```json
{
  "timestamp": "2024-01-15T10:30:14.789Z",
  "level": "DEBUG",
  "component": "RiskEngine", 
  "message": "Risk check passed",
  "data": {
    "account_balance": "200.0",
    "available_balance": "180.0", 
    "current_exposure": "0.0",
    "max_allowed_exposure": "120.0",
    "risk_utilization": "0.0%"
  }
}
```

### 4. 错误和异常日志
```json
{
  "timestamp": "2024-01-15T10:31:22.333Z",
  "level": "ERROR",
  "component": "BinanceExecClient",
  "message": "Order submission failed",
  "data": {
    "order_id": "O-20240115-001",
    "error_code": "INSUFFICIENT_BALANCE",
    "error_message": "Account has insufficient balance for requested action",
    "retry_count": 1
  }
}
```

## 🛠️ 日志管理操作

### 查看实时日志
```bash
# 运行系统并查看实时日志
python start_trading.py

# 或者后台运行并保存到文件
python start_trading.py > trading_$(date +%Y%m%d).log 2>&1 &
```

### 日志文件管理
```bash
# 1. 查看当前日志文件
ls -la *.log logs/*.log 2>/dev/null

# 2. 查看最近的交易日志
tail -f nautilus_trader.log

# 3. 搜索特定内容
grep "LONG signal" *.log
grep "Position opened" logs/*.log

# 4. 按日期查看日志
grep "2024-01-15" *.log | head -20
```

### JSON日志分析
```bash
# 提取交易信号
grep '"message": "Generated.*signal"' *.log | jq '.'

# 提取仓位变化
grep '"message": "Position.*"' *.log | jq '.data'

# 分析错误日志
grep '"level": "ERROR"' *.log | jq '.message'
```

## 📈 性能监控日志

### 系统性能指标
- **订单延迟**：提交到确认的时间
- **数据延迟**：市场数据接收延迟
- **策略延迟**：信号生成到执行时间
- **内存使用**：系统内存占用情况

### 交易统计日志
- **每日交易次数**：记录在`RiskMonitor`日志中
- **胜率统计**：盈利/亏损交易比例
- **平均持仓时间**：仓位开启到关闭的时间
- **滑点统计**：预期价格vs实际成交价格

## 🔧 自定义日志配置

### 创建日志目录
```python
# 在main.py中添加
import os
from pathlib import Path

# 创建日志目录
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 设置日志文件名
log_file = log_dir / f"factorexp_{datetime.now().strftime('%Y%m%d')}.log"
```

### 日志轮转配置
```python
# 添加到LoggingConfig（如果支持）
logging=LoggingConfig(
    log_level="INFO",
    log_level_file="DEBUG", 
    log_file_format="json",
    log_colors=True,
    # 自定义参数（取决于Nautilus版本）
    log_directory="./logs",
    log_max_size="100MB",
    log_backup_count=30
)
```

## ⚠️ 重要提醒

### 日志安全
- **🔒 不记录敏感信息**：API密钥、账户密码等
- **🔍 定期检查**：确认日志中没有泄露个人信息
- **📦 备份策略**：重要交易记录需要定期备份

### 存储管理
- **💽 磁盘空间**：日志文件会快速增长，需要定期清理
- **🔄 日志轮转**：建议设置自动轮转避免单个文件过大
- **📅 保留策略**：建议保留30-90天的详细日志

### 故障排除
- **📍 位置确认**：如果找不到日志文件，检查工作目录和权限
- **🔧 权限问题**：确保程序有写入日志目录的权限
- **💾 空间不足**：定期检查磁盘空间避免日志写入失败

---

## 💡 快速查找指南

**寻找交易记录**：
1. 实时日志：终端输出
2. 详细记录：`./nautilus_trader.log`
3. 历史数据：`./data/catalog/`

**日志级别说明**：
- **DEBUG**：最详细，包含所有调试信息
- **INFO**：标准信息，包含重要事件
- **WARNING**：警告信息，需要注意但不影响运行
- **ERROR**：错误信息，需要立即处理
