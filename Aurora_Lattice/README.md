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
  configs/           # YAML configs (see `default.yaml`)
  run_live_trading.py  # TradingNode launcher for live/sandbox trading
  live_trading_config.py  # Runtime helpers for TradingNodeConfig wiring
  tests/             # Smoke tests covering wiring + EV math
```

## Quick Use

```python
from aurora_hdg import AuroraHdgStrategy, load_config

cfg = load_config("Aurora_Lattice/configs/default.yaml")
strategy = AuroraHdgStrategy(cfg)
# register the strategy with a Trader via StrategyFactory or tests/backtests
```

`load_config` returns an `AuroraHDGConfig` (`StrategyConfig`) so HDG can be launched through the
standard Nautilus boot pipeline (`ImportableStrategyConfig` → `StrategyFactory`).  The helper
`aurora_hdg.config.to_importable_config` wraps this into an importable payload when needed.
The strategy subclass wires in the feature/alpha/fill/risk modules described in `plans/hf_grid.md`.

## Live Trading

The repository now ships with first-party tooling to run Aurora HDG against Binance (spot or
USDT perpetual) using the exact `TradingNode` pattern showcased in the official Nautilus examples.

1. 在 `Aurora_Lattice/` 内复制 `.env.template` 为 `.env`，填入真实 API Key/Secret（默认读取
   `Aurora_Lattice/.env`，可用 `--env-file` / `AURORA_ENV_FILE` 覆盖），示例：
   ```
   BINANCE_API_KEY=xxxx
   BINANCE_API_SECRET=yyyy
   ```
   可补充可选项：
   - `AURORA_TRADING_MODE=live|testnet` (默认 testnet，脚本仅依据 `.env` 这个字段判定实盘/沙盒)
   - `AURORA_TRADER_ID`, `AURORA_LOG_LEVEL`, `AURORA_LOG_DIR`, `AURORA_CATALOG_PATH`
   - `AURORA_FUTURES_LEVERAGE` to set an account-wide default leverage

2. Adjust `Aurora_Lattice/configs/default.yaml` (or provide your own YAML/JSON config).

3. Launch the live node (defaults to testnet unless `--live` or `AURORA_TRADING_MODE=live`):
   ```
   python -m Aurora_Lattice.run_live_trading \
       --config Aurora_Lattice/configs/default.yaml \
       --trader-id AURORA-HDG-001 \
       --live              # omit for testnet
   ```

The runner performs pre-flight checks (Python version, config path, required env vars), builds a
`TradingNodeConfig` through `Aurora_Lattice.live_trading_config.build_trading_node_config`, registers
Binance live data/exec client factories, instantiates `AuroraHdgStrategy`, and finally executes
`node.run()`/`node.dispose()` with graceful Ctrl+C handling。 启动脚本会在执行前自动加载 `.env`
（使用 python-dotenv 且 **覆盖** 当前进程已有的同名变量，缺失时退回手工解析），因此无需手动 `source`。Logging output 默认写到
`Aurora_Lattice/data/logs`（可用 `AURORA_LOG_DIR` 覆盖），parquet catalogs 写到
`AURORA_CATALOG_PATH`（默认 `Aurora_Lattice/data/catalog`）；目录都会在启动时自动创建。
