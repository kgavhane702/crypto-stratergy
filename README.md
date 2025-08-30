# MTF 5-Minute Breakout/Retest Strategy

A Python-based cryptocurrency trading strategy that implements a Multi-Timeframe (MTF) breakout/retest system using Binance Futures.

## Strategy Overview

The strategy is optimized for **intraday range-bound markets** using a top-down approach:
1. **Trend Analysis**: Monthly → Weekly → Daily → 1-Hour EMA alignment (for position sizing only)
2. **Zone Detection**: Consolidation zones on 5-minute charts with ≥3 touches
3. **Entry Logic**: **Immediate breakout entry** in both directions when dwell criteria met (18 bars)
4. **Position Sizing**: 5% for trend-aligned trades, 3% for counter-trend trades
5. **Risk Management**: Automatic stop losses, trailing stops, futures trading with isolated margin

## Quick Start

### 1. Environment Setup

Copy the environment template and configure your settings:

```bash
# Copy environment template
cp env.txt .env

# Edit with your Binance API credentials and preferences
nano .env
```

**Required Environment Variables:**
```bash
# Binance API (Live)
BINANCE_API_KEY=your_live_api_key_here
BINANCE_API_SECRET=your_live_secret_here

# Binance API (Testnet)
BINANCE_TESTNET_API_KEY=your_testnet_api_key_here
BINANCE_TESTNET_API_SECRET=your_testnet_secret_here

# Environment Settings
USE_TESTNET=true               # Set to false for live trading
DASHBOARD_PORT=8080            # Dashboard web interface port

# Trading Settings
LEVERAGE=10                    # Leverage for futures positions
POSITION_SIZE_PCT_TREND_ALIGNED=5.0    # % of balance for trend-aligned trades
POSITION_SIZE_PCT_COUNTER_TREND=3.0    # % of balance for counter-trend trades
DRY_RUN=true                   # Set to false for live trading
CLEAR_ORPHAN_POSITIONS=true    # Clean up existing positions on startup

# Universe & Monitoring
UNIVERSE_N=12                  # Top N symbols by volume
MAX_POSITIONS=3                # Maximum concurrent positions
MAX_MONITOR_POOL_SIZE=8        # Maximum symbols in monitor pool
```

### 2. Installation

#### Option A: Local Python Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .
```

#### Option B: Docker Installation

```bash
# Build the Docker image
docker build -t mtf-breakout .

# Or use Docker Compose
docker-compose build
```

## Usage

### Live Monitoring (Recommended)

Start the live monitoring system with automatic position management:

```bash
# Using Python directly
python runner.py

# Using Docker
docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports mtf-breakout

# Using Docker Compose
docker-compose up
```

**What happens during monitoring:**
1. **Global Scanner**: Scans all symbols every 30 seconds for potential candidates
2. **Priority Ranking**: Ranks candidates by touch count / zone width
3. **Monitor Pool**: Top 8 candidates get dedicated watchers
4. **Entry Execution**: Automatic entry with dynamic sizing (5%/3%) and stop losses
5. **Position Management**: One position per symbol, max 3 total
6. **Real-time Dashboard**: Web interface at http://localhost:8080 for monitoring

### Backtesting

Run historical backtests to validate strategy performance:

```bash
# Basic backtest with default settings
python -m mtf_breakout.cli backtest

# Custom backtest with parameters
python -m mtf_breakout.cli backtest \
    --universe-n 20 \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --export-dir ./backtest_results

# Using Docker for backtest
docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports \
    mtf-breakout python -m mtf_breakout.cli backtest --universe-n 20
```

**Backtest Output:**
- `trades.csv`: All trades with entry/exit details, MFE/MAE
- `metrics.txt`: Performance metrics (win rate, profit factor, CAGR, etc.)
- `equity_curve.png`: Equity curve visualization
- `drawdown.png`: Drawdown analysis

### Data Management

Download and cache historical data:

```bash
# Download data for default symbols
python -m mtf_breakout.cli fetch

# Download for specific symbols
python -m mtf_breakout.cli fetch --symbols BTCUSDT ETHUSDT BNBUSDT

# Download top N symbols by volume
python -m mtf_breakout.cli fetch --universe-n 50
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BINANCE_API_KEY` | - | Binance live API key |
| `BINANCE_API_SECRET` | - | Binance live API secret |
| `BINANCE_TESTNET_API_KEY` | - | Binance testnet API key |
| `BINANCE_TESTNET_API_SECRET` | - | Binance testnet API secret |
| `USE_TESTNET` | true | Use testnet (true) or live (false) |
| `DASHBOARD_PORT` | 8080 | Dashboard web interface port |
| `LEVERAGE` | 10 | Futures leverage |
| `POSITION_SIZE_PCT_TREND_ALIGNED` | 5.0 | % of balance for trend-aligned trades |
| `POSITION_SIZE_PCT_COUNTER_TREND` | 3.0 | % of balance for counter-trend trades |
| `DRY_RUN` | true | Enable/disable live trading |
| `CLEAR_ORPHAN_POSITIONS` | true | Clean existing positions on startup |
| `UNIVERSE_N` | 12 | Top N symbols to monitor |
| `MAX_POSITIONS` | 3 | Maximum concurrent positions |
| `MAX_MONITOR_POOL_SIZE` | 8 | Maximum symbols in monitor pool |
| `MONITOR_INTERVAL_SECONDS` | 15 | Symbol watcher scan interval |
| `GLOBAL_SCAN_INTERVAL_SECONDS` | 30 | Global scanner interval |
| `DWELL_BARS` | 18 | Minimum bars inside zone (90 minutes) |
| `TOUCH_SEPARATION_BARS` | 3 | Minimum bars between touches |
| `RETEST_WINDOW_BARS` | 8 | Bars to wait for retest |
| `TOUCH_BUFFER_FRAC` | 0.15 | ATR fraction for touch buffer |
| `BREAKOUT_BUFFER_FRAC` | 0.15 | ATR fraction for breakout buffer |
| `ATR_TIGHT_MULT` | 0.85 | Zone tightness threshold (looser for better entries) |
| `TAKER_FEE_BPS` | 10 | Taker fee in basis points |
| `SLIPPAGE_BPS` | 2 | Slippage in basis points |

### CLI Commands

```bash
# Monitor live trading
python -m mtf_breakout.cli monitor [--universe-n 20] [--max-positions 5] [--interval 15]

# Run backtest
python -m mtf_breakout.cli backtest [--universe-n 20] [--start 2024-01-01] [--end 2024-12-31] [--export-dir ./results]

# Download data
python -m mtf_breakout.cli fetch [--symbols BTCUSDT ETHUSDT] [--universe-n 50]
```

## Docker Commands

### Build and Run

```bash
# Build image
docker build -t mtf-breakout .

# Run with environment file
docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports mtf-breakout

# Run with custom command
docker run --env-file .env -v $(pwd)/data:/app/data -v $(pwd)/exports:/app/exports \
    mtf-breakout python -m mtf_breakout.cli backtest --universe-n 20
```

### Docker Compose

```bash
# Start monitoring
docker-compose up

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild and start
docker-compose up --build
```

## Strategy Logic

### 1. Trend Analysis (for Position Sizing)
- **Monthly, Weekly, Daily, 1-Hour** timeframes
- **Bullish**: Close > EMA-50 > EMA-200, both EMAs rising
- **Bearish**: Close < EMA-50 < EMA-200, both EMAs falling
- **Neutral**: Mixed conditions
- **Position Sizing**: 5% for trend-aligned trades, 3% for counter-trend trades

### 2. Zone Detection
- **Timeframe**: 5-minute charts
- **Dwell Time**: Minimum 18 bars (90 minutes) inside zone
- **Zone Width**: Must be tight relative to ATR (≤ 0.55 × ATR)
- **Touches**: Minimum 3 touches on relevant edge (top for LONG, bottom for SHORT)
- **Touch Separation**: Minimum 3 bars between touches

### 3. Entry Logic
- **Range Breakout**: Immediate entry in BOTH directions when close beyond zone edge + ATR buffer after ≥3 touches AND dwell criteria met (18 bars)
- **Dwell Requirement**: Zone must have sufficient dwell time (18 bars = 90 minutes)
- **Direction**: Takes LONG and SHORT entries regardless of higher timeframe trend
- **Retest Logic**: Only for no-dwell breakouts - wait for retest within 8 bars

### 4. Risk Management
- **Position Sizing**: 5% for trend-aligned trades, 3% for counter-trend trades
- **Stop Loss**: Breakout/confirmation candle extreme
- **Trailing Stop**: 5-minute swing-based trailing
- **Max Positions**: 3 concurrent positions maximum
- **One Per Symbol**: Maximum one position per symbol

## Monitoring Architecture

```
Global Scanner (1 thread)
├── Scans all symbols every 30s
├── Ranks by priority (touches/width)
└── Promotes top 8 to monitor pool

Monitor Pool (up to 8 threads)
├── 1 thread per candidate symbol
├── Scans every 15s for breakout
├── Executes trades with 2% sizing
└── Manages stop losses and exits
```

## Safety Features

- **Testnet Support**: Test with virtual money before going live
- **Dry Run Mode**: Test without real money (default: enabled)
- **Orphan Cleanup**: Automatically close existing positions on startup
- **Position Limits**: Maximum 3 positions, 1 per symbol
- **Error Handling**: Retry logic for API calls
- **Logging**: Comprehensive logging for transparency
- **Real-time Dashboard**: Monitor all trades and zones in web interface

## Performance Metrics

Backtests output comprehensive metrics:
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit / Gross loss
- **CAGR**: Compound Annual Growth Rate
- **Max Drawdown**: Maximum peak-to-trough decline
- **Average R**: Average risk-reward ratio
- **Expectancy**: Expected profit per trade
- **Sharpe Ratio**: Risk-adjusted returns
- **Trade Count**: Total number of trades
- **Average Holding Time**: Average trade duration

## Troubleshooting

### Common Issues

1. **API Errors**: Check Binance API credentials and permissions
2. **No Data**: Ensure symbols exist and have sufficient volume
3. **Permission Denied**: Verify API has futures trading permissions
4. **Docker Issues**: Check volume mounts and environment file

### Logs

Enable debug logging by setting `APP_LOG_LEVEL=DEBUG` in your `.env` file.

### Support

For issues or questions:
1. Check the logs for error messages
2. Verify environment configuration
3. Test with `DRY_RUN=true` first
4. Start with small universe size for testing

## Disclaimer

This software is for educational and research purposes. Trading cryptocurrencies involves substantial risk. Use at your own risk and never trade with money you cannot afford to lose.
