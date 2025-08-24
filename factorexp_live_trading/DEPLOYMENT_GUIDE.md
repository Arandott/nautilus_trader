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

Edit `main.py` at the bottom to control:
- **Which contracts to trade** (instruments)
- **How much money to use** (account_size_usd)

```python
# Uncomment and customize these lines in main.py:
custom_instruments = ["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE"]
custom_account_size = 200.0  # USD

# Then change the last line to:
asyncio.run(main(instruments=custom_instruments, account_size_usd=custom_account_size))
```

## 💰 Account Size Settings

The system automatically optimizes based on your account size:

**Small Accounts (≤$500)**:
- Conservative settings: 60% max usage, 1.5% position risk
- Tighter stop losses: 1.2%
- Fewer daily trades: 10 max

**Standard Accounts (>$500)**:
- Standard settings: 80% max usage, 2% position risk  
- Normal stop losses: 1.5%
- More daily trades: 20 max

**Example Configurations**:
```python
# $200 small account trading BTC only
asyncio.run(main(
    instruments=["BTCUSDT-PERP.BINANCE"], 
    account_size_usd=200.0
))

# $1000 account trading BTC, ETH, SOL
asyncio.run(main(
    instruments=["BTCUSDT-PERP.BINANCE", "ETHUSDT-PERP.BINANCE", "SOLUSDT-PERP.BINANCE"],
    account_size_usd=1000.0  
))

# Default settings (uses environment variables if set)
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
ACCOUNT_SIZE_USD=500

# Email alerts (optional)
ENABLE_EMAIL_ALERTS=true
EMAIL_USERNAME=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

### Strategy Parameters

The strategy uses:
- **EMA signals**: Fast EMA (12) vs Slow EMA (26)
- **Risk management**: Dynamic based on account size
- **Stop losses**: 1.2-1.5% depending on account size
- **Position sizing**: 1.5-2% risk per trade

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

**Example 1: $200 Account, BTC Only**
```python
# Edit main.py bottom:
asyncio.run(main(
    instruments=["BTCUSDT-PERP.BINANCE"],
    account_size_usd=200.0
))
```

**Example 2: $1000 Account, Multiple Coins**  
```python
# Edit main.py bottom:
asyncio.run(main(
    instruments=[
        "BTCUSDT-PERP.BINANCE",
        "ETHUSDT-PERP.BINANCE", 
        "SOLUSDT-PERP.BINANCE"
    ],
    account_size_usd=1000.0
))
```

**Example 3: Use Environment Variables**
```bash
# Set in .env:
TRADING_INSTRUMENTS=BTCUSDT-PERP.BINANCE,ETHUSDT-PERP.BINANCE
ACCOUNT_SIZE_USD=500

# Run with defaults:
python main.py
```

---

**Ready to start?** Just copy your API keys to `.env` and run `python start_trading.py` 🚀