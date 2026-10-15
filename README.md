# Daily Market Report Bot

Automated end-of-day portfolio analysis powered by yfinance + Claude AI, delivered by email and run entirely on GitHub Actions.

## What it does

Every weekday afternoon this bot pulls live price data and top news headlines for a three-ETF portfolio (VOO, VXUS, XLB), sends them to Claude, and emails a structured market analysis as a formatted HTML digest. No server to maintain — runs entirely on GitHub's free infrastructure.

**Pipeline:** yfinance (price + news) → Python (prompt builder) → Claude API (analysis) → Gmail SMTP (HTML email)

## Report structure

Each report opens with an executive summary table showing portfolio P&L and allocation drift, followed by seven sections:

1. **Regime label** — one-line market environment (e.g. "risk-on / dollar-soft / international outperformance")
2. **Portfolio scorecard** — weighted return, contribution per holding, drift vs. target weights
3. **Daily moves & drivers** — what moved, by how much, and why — tied to that day's headlines
4. **Cross-portfolio theme** — the macro narrative linking all three positions
5. **Concept of the day** — one finance concept illustrated by something that actually happened today
6. **Watchpoints & considerations** — risks and questions to track, framed as prompts, never buy/sell calls
7. **What would change my mind** — specific, falsifiable triggers that would invalidate the day's narrative

## Tech stack

- Python 3.11
- yfinance — price data and headlines
- anthropic SDK — Claude claude-sonnet-4-5
- smtplib / MIME — Gmail delivery
- GitHub Actions — scheduling and execution

## Setup

**1. Clone and install**
```bash
git clone https://github.com/mfheathcote/market-report.git
cd market-report
pip install yfinance anthropic
```

**2. Get your credentials**

| Secret | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `GMAIL_ADDRESS` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | Google Account → Security → 2-Step Verification → App Passwords |

**3. Set environment variables (local runs)**
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="abcdefghijklmnop"  # no spaces
```

Then run: `python daily_market_report.py`

**4. Add secrets to GitHub (automated runs)**

Settings → Secrets and variables → Actions → New repository secret. Add all three keys above. They never appear in logs.

**5. Customise the portfolio**

Edit the `CONFIG` block at the top of `daily_market_report.py`:

```python
TICKERS = ["VOO", "VXUS", "XLB"]
PORTFOLIO_WEIGHTS = {"VOO": 0.6095, "VXUS": 0.2457, "XLB": 0.1391}
TARGET_WEIGHTS    = {"VOO": 0.60,   "VXUS": 0.25,   "XLB": 0.15}
HOLDINGS = {
    "VOO":  {"shares": 10, "cost_basis": 6063.20},
    "VXUS": {"shares": 32, "cost_basis": 2461.44},
    "XLB":  {"shares": 30, "cost_basis": 1473.94},
}
```

## Running costs

Each report uses roughly 2,500 input tokens and 800 output tokens — about $0.02 per report at claude-sonnet-4-5 pricing. A $5 Anthropic credit covers approximately a full trading year. GitHub Actions is free for public repos.

## What this project covers

Built from scratch as a first Python project:

- Python scripting and functions
- REST API integration (Anthropic, yfinance)
- Secrets and environment variable management
- SMTP email delivery with HTML templates
- Git and GitHub version control
- GitHub Actions for automated scheduling
- Portfolio math (weighted returns, allocation drift, P&L)
- LLM prompt engineering

## Disclaimer

This project is for educational purposes only. Nothing in the generated reports constitutes financial advice or a recommendation to buy, sell, or hold any security.
