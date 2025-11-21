# Aurora Lattice – HF Dynamic Grid (HDG)

This module hosts the high-frequency dynamic grid (HDG) strategy described in `plans/hf_grid.md`.
All logic is built on top of **nautilus-trader** primitives (strategy lifecycle, order factory,
cache, portfolio APIs).  The package provides structured configs, shared math utilities, and the
strategy implementation itself so that HDG can be instantiated through the normal Nautilus
bootstrapping path (`ImportableStrategyConfig` / `StrategyFactory`).

## Layout

```
Aurora_Lattice/
  aurora_hdg/        # Strategy source code
  configs/           # Run configs (strategy + runtime, see `default.yaml`)
  run_live_trading.py  # TradingNode launcher for live/sandbox trading
  config_loader.py   # Central loader for runtime wiring + TradingNodeConfig
  tests/             # Smoke tests covering wiring + EV math
```

## Quick Use

```python
from Aurora_Lattice.aurora_hdg import AuroraHdgStrategy, load_config

cfg = load_config("Aurora_Lattice/configs/default.yaml")  # `strategy` section is read automatically
strategy = AuroraHdgStrategy(cfg)
# register the strategy with a Trader via StrategyFactory or tests/backtests
```

`load_config` returns an `AuroraHDGConfig` (`StrategyConfig`) so HDG can be launched through the
standard Nautilus boot pipeline (`ImportableStrategyConfig` → `StrategyFactory`).  The helper
`aurora_hdg.config.to_importable_config` wraps this into an importable payload when needed.
The strategy subclass wires in the feature/alpha/fill/risk modules described in `plans/hf_grid.md`.

每个 `configs/*.yaml` 现已划分为 `strategy` 与 `runtime` 两个部分：前者描述单标的参数，后者声明
本次运行要连接的 venue/account（例如 `runtime.clients.BINANCE_PERP`）、日志/目录配置以及
`trading_mode`（live/testnet）。因此“一份 YAML = 一次运行”，复制一份模板即可为新的标的/账户
创建完全隔离的配置。

## Live Trading

The repository now ships with first-party tooling to run Aurora HDG against Binance (spot or
USDT perpetual) using the exact `TradingNode` pattern showcased in the official Nautilus examples.

1. 在 `Aurora_Lattice/` 内复制 `.env.template` 为 `.env`，填入真实 API Key/Secret（默认读取
   `Aurora_Lattice/.env`，可用 `--env-file` / `AURORA_ENV_FILE` 覆盖），示例：
   ```
   BINANCE_API_KEY=xxxx
   BINANCE_API_SECRET=yyyy
   ```
   如果要并行连接其他交易所（如 OKX），也要在 `.env` 中增加 `OKX_API_KEY` / `OKX_API_SECRET`
   / `OKX_API_PASSPHRASE` 等对应字段。其它运行参数在 YAML 中控制，无需额外环境变量。

2. 调整 `Aurora_Lattice/configs/default.yaml`（或复制出新的 YAML），`runtime.clients` 部分现已支持
   多交易所：
   - `venue` 指定适配器（目前内置 `BINANCE` 和 `OKX`，默认会引用标准 `.env` 变量如
     `BINANCE_API_KEY` / `OKX_API_KEY`，无需在 YAML 中写凭证）；
   - 其余字段按 venue 特有参数填写（Binance 需要 `account_type`、`futures_leverage` 等；
     OKX 可设置 `instrument_types`, `contract_types`, `margin_mode` 等）。
   参见 `Aurora_Lattice/configs/sample_okx.yaml` 了解如何针对 OKX 单独跑一套配置。

3. Launch the live node（默认遵循配置里的 `runtime.trading_mode`；CLI 仅可覆盖日志等信息）:
   ```
   python -m Aurora_Lattice.run_live_trading \
       --config Aurora_Lattice/configs/default.yaml \
       --trader-id AURORA-HDG-001    # 可选，覆盖 YAML
   ```

The runner performs pre-flight checks (Python version, config path, required env vars), builds a
`TradingNodeConfig` through `Aurora_Lattice.config_loader.build_trading_node_config`, registers
each venue listed under `runtime.clients` as independent data/exec client（准确复刻官方多交易所示例），
instantiates `AuroraHdgStrategy`, and finally executes
`node.run()`/`node.dispose()` with graceful Ctrl+C handling。 启动脚本会在执行前自动加载 `.env`
（使用 python-dotenv 且 **覆盖** 当前进程已有的同名变量，缺失时退回手工解析），因此无需手动 `source`。Logging output 默认写到
`Aurora_Lattice/data/logs`（可用 `AURORA_LOG_DIR` 覆盖），parquet catalogs 写到
`AURORA_CATALOG_PATH`（默认 `Aurora_Lattice/data/catalog`）；目录都会在启动时自动创建。

### Selecting Live vs Testnet

- 交易模式完全由 YAML 中的 `runtime.trading_mode` 控制，取值仅 `live` 或 `testnet`。CLI 不会提供 `--live` 等参数，确保运行环境只能通过配置文件复现。
- 如果需要为不同 venue 指定不同环境，可在 `runtime.clients.<NAME>.testnet` 中写显式布尔值；缺省则继承 `runtime.trading_mode`。
- 修改 YAML 后重新运行 `python -m Aurora_Lattice.run_live_trading ...` 即可切换，不需要额外环境变量或命令行开关。

## Testing

仓库附带了一组 smoke/unit tests 覆盖配置加载、策略构造与填单/库存工具，可在仓库根目录直接运行：

```bash
python -m pytest Aurora_Lattice/tests
```

上述命令无需额外修改 `PYTHONPATH`，因为 `Aurora_Lattice` 目录本身就是 Python 包根目录。
