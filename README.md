Daily ETF market report

A Python script that sends me a short market report every weekday morning on the ETFs I hold. It pulls the latest prices with yfinance, has Claude write up what moved and why, and emails the result to me. GitHub Actions runs it on a schedule, so I don't have to do anything once it's set up.

I built it because I hold a small long-term portfolio and wanted a quick, consistent way to see how each position did and to connect the moves to what was actually happening in markets (earnings, oil, geopolitics) instead of just looking at a number on an app.

What it tracks
Ticker -	Fund	- Why I hold it

VOO	- Vanguard S&P 500 ETF	- US large caps, the core of the portfolio

VXUS	- Vanguard Total International Stock ETF -	Exposure outside the US

XLB	- Materials Select Sector SPDR	- Materials and commodity-linked companies

How it works
Get the data. daily_market_report.py downloads recent price history for each ticker with yfinance and calculates the daily change for each holding.
Write the report. The numbers go to the Claude API with a prompt asking for a short summary: what each fund did, what drove it, and anything in the news that matters for the portfolio.
Send it. The report is emailed to me through Gmail SMTP.
Run it automatically. A GitHub Actions workflow runs the script on a schedule (triggered by an external cron job), so the report arrives each day without my laptop being on.
