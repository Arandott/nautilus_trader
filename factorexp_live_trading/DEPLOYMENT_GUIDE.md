# FactorExp Live Trading - Quick Start Guide

🎯 **Goal**: Copy API keys, run the strategy, control your money and trading contracts.

## 🚀 Quick Start (3 Steps)

### Step 1: Configure API Keys

1. **Copy environment template**:
   ```bash
   cd factorexp_live_trading/
   cp .env.template .env
   ```

2. **Add your Binance API keys** to `.env`:
   ```bash
   BINANCE_API_KEY=your_binance_api_key_here
   BINANCE_API_SECRET=your_binance_secret_key_here
   TRADING_MODE=testnet  # Use 'testnet' first, then 'live'
   ```

### Step 2: Start Trading

```bash
# Option A: Use startup script (recommended)
python start_trading.py

# Option B: Run directly with default settings
python main.py
```

### Step 3: Customize Your Trading (Optional)

Edit `main.py` at the bottom to control instruments, or use environment variables for capital settings.

```python
# Uncomment and customize these lines in main.py:
custom_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]

# Then change the last line to:
asyncio.run(main(instruments=custom_instruments))
```

## 💰 Capital Settings

- Set `FACTOREXP_CAPITAL_ALLOCATION_USD` for the desired margin budget (pre-leverage).
- Optionally set `FACTOREXP_TARGET_NOTIONAL_USD` if you want to cap the leveraged exposure.
- `FACTOREXP_MAX_LEVERAGE` overrides the venue leverage used for deriving notional targets.
- Leave them blank to rely on StrategyConfig defaults (margin budget defaults to 5,000 USD).
**Example Configurations**:
```python
# Custom instruments
asyncio.run(main(
    instruments=["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
))

# Default settings (uses environment variables / StrategyConfig defaults)
asyncio.run(main())
```

## 🔐 Binance API Setup

1. **Get API Keys**:
   - Go to [Binance API Management](https://www.binance.com/en/my/settings/api-management)
   - Create new API key with permissions:
     - ✅ Enable Reading
     - ✅ Enable Futures
     - ❌ Disable Withdrawals

2. **For Testnet** (recommended first):
   - Use [Binance Testnet](https://testnet.binancefuture.com/)
   - Set `TRADING_MODE=testnet` in `.env`

3. **For Live Trading**:
   - Set `TRADING_MODE=live` in `.env`
   - **Start with small amounts!**

## 📊 Available Trading Instruments

Common perpetual contracts you can trade:

```python
instruments = [
    "BTCUSDT-PERP.BINANCE",    # Bitcoin
    "ETHUSDT-PERP.BINANCE",    # Ethereum  
    "SOLUSDT-PERP.BINANCE",    # Solana
    "ADAUSDT-PERP.BINANCE",    # Cardano
    "DOGEUSDT-PERP.BINANCE",   # Dogecoin
    "AVAXUSDT-PERP.BINANCE",   # Avalanche
    "DOTUSDT-PERP.BINANCE",    # Polkadot
    "LINKUSDT-PERP.BINANCE",   # Chainlink
]
```

## ⚙️ Advanced Configuration

### Environment Variables (Optional)

You can still use environment variables for convenience:

```bash
# In .env file
TRADING_INSTRUMENTS=BTCUSDT-PERP.BINANCE,ETHUSDT-PERP.BINANCE
FACTOREXP_CAPITAL_ALLOCATION_USD=2500
FACTOREXP_TARGET_NOTIONAL_USD=7500
FACTOREXP_FACTOR_IDS=posvolume_vwap_ret_volatility_96,negvolume_vwap_ret_volatility_96,statenum1_close_ret_std_96
# Legacy fallback（单因子）:
# FACTOREXP_FACTOR_ID=vwap_return_std

# Email alerts (optional)
ENABLE_EMAIL_ALERTS=true
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

### Strategy Parameters

Key parameters:
- **FactorExp 指标平均**: 支持 1～N 个因子，信号为 Clip/ZScore 后的等权均值（范围 [-2, 2]）
- **Margin budget**: `capital_allocation_usd`（默认 5,000，可通过环境变量覆盖）
- **Target notional**: `target_notional_usd`（默认按杠杆推导，可显式配置）
- **Stop losses**: 1.5% 默认（无风险配置时 fallback）
- **Position sizing**: 2% risk per trade（可在 StrategyConfig 中调整）

## 🛠️ Troubleshooting

**"API credentials invalid"**:
- Check your API keys in `.env`
- Ensure correct trading mode (testnet vs live)

**"FactorExp not available"**:
- Install required dependencies: `pip install -r requirements.txt`

**Strategy not trading**:
- Check market hours and volatility
- Verify instruments are actively trading

## ⚠️ Important Safety Tips

1. **Always test on testnet first**
2. **Start with small amounts** 
3. **Monitor your trades closely**
4. **Never risk more than you can afford to lose**
5. **Keep your API keys secure**

## 🎯 Quick Examples

**Example 1: Override instruments in code**
```python
# Edit main.py bottom:
asyncio.run(main(
    instruments=["BTCUSDT-PERP.BINANCE", "SOLUSDT-PERP.BINANCE"]
))
```

**Example 2: Use environment overrides**
```bash
# Set in .env:
TRADING_INSTRUMENTS=BTCUSDT-PERP.BINANCE,ETHUSDT-PERP.BINANCE
FACTOREXP_CAPITAL_ALLOCATION_USD=2500
FACTOREXP_TARGET_NOTIONAL_USD=7500
FACTOREXP_MAX_LEVERAGE=3

# Run with defaults:
python main.py
```

---

**Ready to start?** Just copy your API keys to `.env` and run `python start_trading.py` 🚀
