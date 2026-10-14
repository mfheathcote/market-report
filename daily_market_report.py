"""
Daily Market Report Generator
=============================
Fetches end-of-day price action and headlines for a portfolio,
sends them to Claude, and produces a narrative market report
with watchpoints framed as questions, not trade recommendations.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 daily_market_report.py

Required packages:
    pip3 install yfinance anthropic
"""

import os
import sys
from datetime import datetime

import yfinance as yf
import anthropic

# === CONFIG =================================================================
TICKERS = ["VOO", "VXUS", "XLB", "VO"]          # Edit to match your portfolio

# Your CURRENT portfolio weights as decimals (must sum to ~1.0).
# Update these periodically as your allocation drifts with market moves.
PORTFOLIO_WEIGHTS = {
    "VOO":  0.5826,
    "VXUS": 0.2205,
    "XLB":  0.1214,
    "VO":   0.0723,
}

# Your TARGET weights (what you originally intended to hold).
# Used to flag drift. Set equal to PORTFOLIO_WEIGHTS to disable drift commentary.
TARGET_WEIGHTS = {
    "VOO":  0.55,
    "VXUS": 0.25,
    "XLB":  0.08,
    "VO":   0.12,
}

# Your actual holdings. Update these when you buy more shares.
# cost_basis = total amount you paid (not per share, total $)
HOLDINGS = {
    "VOO":  {"shares": 10, "cost_basis": 6063.20},
    "VXUS": {"shares": 32, "cost_basis": 2461.44},
    "XLB":  {"shares": 30, "cost_basis": 1473.94},
    "VO":   {"shares": 11, "cost_basis": 887.96},
}

LOOKBACK_DAYS = 5                          # Trading days of history to pull
MODEL = "claude-sonnet-4-5"                # Or "claude-opus-4-7" for deeper analysis
MAX_NEWS_PER_TICKER = 7
OUTPUT_DIR = "."                           # Where the .md report gets saved
MAX_TOKENS = 3000                          # Higher for the longer v2 reports
# ============================================================================

def fetch_price_data(tickers: list[str], days_back: int = LOOKBACK_DAYS) -> dict:
    """
    Pull recent OHLCV data for each ticker via yfinance.
    Returns the most recent trading day plus calculated daily change.
    """
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=f"{days_back}d")
            if hist.empty:
                print(f"  WARNING: No price data returned for {ticker}")
                continue

            latest = hist.iloc[-1]
            previous = hist.iloc[-2] if len(hist) >= 2 else None

            info = {
                "ticker": ticker,
                "name": t.info.get("longName", ticker),
                "date": latest.name.strftime("%Y-%m-%d"),
                "close": round(float(latest["Close"]), 2),
                "open": round(float(latest["Open"]), 2),
                "high": round(float(latest["High"]), 2),
                "low": round(float(latest["Low"]), 2),
                "volume": int(latest["Volume"]),
            }
            if previous is not None:
                change = float(latest["Close"]) - float(previous["Close"])
                pct = (change / float(previous["Close"])) * 100
                info["change"] = round(change, 2)
                info["pct_change"] = round(pct, 2)
                info["prev_close"] = round(float(previous["Close"]), 2)
            data[ticker] = info
        except Exception as e:
            print(f"  WARNING: Error fetching {ticker}: {e}")
    return data

def compute_portfolio_return(price_data: dict, weights: dict) -> float | None:
    """
    Compute the weighted portfolio % return for the day.
    Example: if VOO is 60% of portfolio and gained 1%, it contributes 0.6pp
    to the total portfolio return.
    """
    total = 0.0
    weight_used = 0.0
    for ticker, info in price_data.items():
        if "pct_change" in info and ticker in weights:
            total += weights[ticker] * info["pct_change"]
            weight_used += weights[ticker]
    if weight_used == 0:
        return None
    return total / weight_used

def fetch_news(tickers: list[str], max_per: int = MAX_NEWS_PER_TICKER) -> dict:
    """
    Pull recent headlines per ticker via yfinance (free, no API key needed).
    For better/more relevant news, swap this for NewsAPI or Alpaca News later.
    """
    news = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            items = (t.news or [])[:max_per]
            cleaned = []
            for item in items:
                # yfinance schema changed in 2024 - content is now nested
                content = item.get("content", item)
                cleaned.append({
                    "title": content.get("title", "Untitled"),
                    "publisher": (
                        content.get("provider", {}).get("displayName")
                        if isinstance(content.get("provider"), dict)
                        else content.get("publisher", "Unknown")
                    ),
                    "summary": (content.get("summary") or "")[:400],
                })
            news[ticker] = cleaned
        except Exception as e:
            print(f"  WARNING: Error fetching news for {ticker}: {e}")
            news[ticker] = []
    return news

def build_summary_table(price_data: dict) -> str:
    """
    Build an HTML summary table showing real portfolio P&L for the day.
    Uses HOLDINGS (shares + cost basis) + live prices from yfinance.
    """
    rows = ""
    total_market_value = 0
    total_day_change = 0
    total_cost_basis = 0
    total_gain_loss = 0

    for ticker, info in price_data.items():
        holding = HOLDINGS.get(ticker)
        if not holding:
            continue

        shares = holding["shares"]
        cost_basis = holding["cost_basis"]
        price = info["close"]
        market_value = shares * price
        day_change_dollar = shares * info.get("change", 0)
        day_change_pct = info.get("pct_change", 0)
        gain_loss = market_value - cost_basis
        gain_loss_pct = (gain_loss / cost_basis) * 100

        total_market_value += market_value
        total_day_change += day_change_dollar
        total_cost_basis += cost_basis
        total_gain_loss += gain_loss

        # Color code: green for positive, red for negative
        day_color = "#1a7f4b" if day_change_dollar >= 0 else "#c0392b"
        gl_color = "#1a7f4b" if gain_loss >= 0 else "#c0392b"
        day_sign = "+" if day_change_dollar >= 0 else ""
        gl_sign = "+" if gain_loss >= 0 else ""

        rows += f"""
        <tr>
            <td><strong>{ticker}</strong></td>
            <td>{shares}</td>
            <td>${price:,.2f}</td>
            <td>${market_value:,.2f}</td>
            <td style="color:{day_color}">
                {day_sign}${day_change_dollar:,.2f}<br>
                <small>{day_sign}{day_change_pct:.2f}%</small>
            </td>
            <td>${cost_basis:,.2f}</td>
            <td style="color:{gl_color}">
                {gl_sign}${gain_loss:,.2f}<br>
                <small>{gl_sign}{gain_loss_pct:.2f}%</small>
            </td>
        </tr>
        """

    # Totals row
    total_gain_loss_pct = (total_gain_loss / total_cost_basis) * 100
    total_day_pct = (total_day_change / (total_market_value - total_day_change)) * 100
    day_color = "#1a7f4b" if total_day_change >= 0 else "#c0392b"
    gl_color = "#1a7f4b" if total_gain_loss >= 0 else "#c0392b"
    day_sign = "+" if total_day_change >= 0 else ""
    gl_sign = "+" if total_gain_loss >= 0 else ""

    rows += f"""
    <tr style="border-top: 2px solid #0a2342; font-weight: bold; background-color: #f0f4f8;">
        <td><strong>TOTAL</strong></td>
        <td>—</td>
        <td>—</td>
        <td>${total_market_value:,.2f}</td>
        <td style="color:{day_color}">
            {day_sign}${total_day_change:,.2f}<br>
            <small>{day_sign}{total_day_pct:.2f}%</small>
        </td>
        <td>${total_cost_basis:,.2f}</td>
        <td style="color:{gl_color}">
            {gl_sign}${total_gain_loss:,.2f}<br>
            <small>{gl_sign}{total_gain_loss_pct:.2f}%</small>
        </td>
    </tr>
    """

    return f"""
    <table style="width:100%; border-collapse:collapse; font-size:14px; margin-bottom:24px;">
        <thead>
            <tr style="background-color:#0a2342; color:#ffffff;">
                <th style="padding:10px 8px; text-align:left;">Ticker</th>
                <th style="padding:10px 8px; text-align:left;">Shares</th>
                <th style="padding:10px 8px; text-align:left;">Price</th>
                <th style="padding:10px 8px; text-align:left;">Market Value</th>
                <th style="padding:10px 8px; text-align:left;">Day Change</th>
                <th style="padding:10px 8px; text-align:left;">Cost Basis</th>
                <th style="padding:10px 8px; text-align:left;">Gain / Loss</th>
            </tr>
        </thead>
        <tbody style="font-family: monospace;">
            {rows}
        </tbody>
    </table>
    """

def build_prompt(price_data: dict, news_data: dict) -> str:
    """Format price + news data + weights into a structured prompt for Claude."""

    portfolio_return = compute_portfolio_return(price_data, PORTFOLIO_WEIGHTS)

    lines = [
        "You are a financial analyst writing an end-of-day market report for a "
        "first-year business school student studying finance with an interest in "
        "commodities trading. Your goal is to make today's market action legible "
        "AND to teach finance concepts through it. The reader is intellectually "
        "curious and wants depth, not hand-holding. The reader also wants you to "
        "look at the day before's market session activity and compare it to what "
        "happened today, you should comment on evolution and why",
        "",
        "Write a structured report (~800 words) with these sections IN ORDER:",
        "",
        "  ## 1. Regime label (1 line)",
        "     A single line naming today's macro regime in plain English.",
        "     Examples: 'Oil-down / risk-on / dollar-soft'",
        "     'Growth scare / yields lower / defensives lead'",
        "     This is a tag the reader can compare across days to spot when",
        "     regimes persist vs. break.",
        "",
        "  ## 2. Portfolio scorecard (~80 words)",
        "     Report the weighted portfolio return for the day (provided below).",
        "     State which holding contributed most and least in percentage points.",
        "     Comment on whether current weights have drifted from target weights",
        "     (also provided below). Drift over 2 percentage points is worth",
        "     flagging. Drift under that is noise, don't mention it.",
        "",
        "  ## 3. Daily moves and likely drivers (~250 words)",
        "     For each holding: state the % move, then connect it to specific",
        "     news from the headlines provided. Be honest when a move cannot be",
        "     cleanly explained by the available headlines.",
        "     Do NOT invent causation that is not supported by the headlines.",
        "",
        "  ## 4. Cross-portfolio theme (~80 words)",
        "     The macro pattern across all three holdings today. What regime",
        "     mechanic explains why they moved the way they did relative to",
        "     each other?",
        "",
        "  ## 5. Concept of the day (~150 words)",
        "     Pick ONE finance concept that today's action illustrates well.",
        "     Explain it in genuine depth: the mechanism, why it matters, and",
        "     exactly how it showed up today. Go beyond a surface definition.",
        "     Good candidates: sector beta, currency translation effect, breadth,",
        "     carry trade, contango, basis risk, multiple expansion, duration.",
        "     Treat this as a mini-lesson the reader will remember because it is",
        "     anchored to something real that happened today.",
        "",
        "  ## 6. Watchpoints and considerations (~150 words)",
        "     RULES - strictly follow these:",
        "       - You are NOT a financial advisor.",
        "       - NO buy/sell/hold recommendations on specific tickers.",
        "       - Frame as: things to monitor, questions to ask, scenarios.",
        "       - Always include at least one downside/risk scenario.",
        "       - Remind the reader that single-day moves are noise and",
        "         long-term plans should not change based on one day.",
        "",
        "  ## 7. What would change my mind (~80 words)",
        "     For the dominant narrative from today, list 2-3 specific things",
        "     that would invalidate it. Be precise with levels and triggers.",
        "     Examples: 'WTI back above $107', 'a 10y yield close above 4.8%',",
        "     'a Fed speaker explicitly walking back rate-cut expectations'.",
        "     This trains the reader to hold views provisionally.",
        "",
        "GLOSSARY RULE (applies to the whole report):",
        "  The first time you use a technical finance term, define it briefly",
        "  in parentheses. Examples:",
        "    'breadth (the share of stocks participating in a move)'",
        "    'basis points (one basis point = 0.01%)'",
        "    'beta (sensitivity to broad market moves)'",
        "  Aim for 3-5 inline definitions per report. After defining a term",
        "  once, use it freely without re-defining.",
        "",
        "TONE: Direct, analytical, intellectually honest. Treat the reader as",
        "smart and curious. No filler phrases like 'It is important to note'.",
        "",
        "=== PORTFOLIO ALLOCATION ===",
        "",
        "Current weights vs. target weights:",
    ]

    for ticker in TICKERS:
        current = PORTFOLIO_WEIGHTS.get(ticker, 0) * 100
        target = TARGET_WEIGHTS.get(ticker, 0) * 100
        drift = current - target
        lines.append(
            f"  {ticker}: current {current:.2f}%  |  "
            f"target {target:.2f}%  |  drift {drift:+.2f}pp"
        )

    if portfolio_return is not None:
        lines.append(
            f"\nWeighted portfolio return today: {portfolio_return:+.3f}%"
        )

    lines.append("\n=== PORTFOLIO PRICE ACTION ===")

    for ticker, info in price_data.items():
        lines.append(f"\n{ticker} - {info.get('name')}")
        lines.append(f"  Date: {info['date']}")
        if "pct_change" in info:
            contribution = PORTFOLIO_WEIGHTS.get(ticker, 0) * info["pct_change"]
            lines.append(
                f"  Close: ${info['close']}  |  "
                f"Change {info['change']:+} ({info['pct_change']:+.2f}%)  |  "
                f"Prev close: ${info['prev_close']}"
            )
            lines.append(
                f"  Portfolio contribution: {contribution:+.3f}pp"
            )
        else:
            lines.append(f"  Close: ${info['close']}")
        lines.append(
            f"  Open: ${info['open']}  |  "
            f"High: ${info['high']}  |  "
            f"Low: ${info['low']}"
        )
        lines.append(f"  Volume: {info['volume']:,}")

    lines.append("\n=== RECENT HEADLINES ===")
    for ticker, items in news_data.items():
        lines.append(f"\n--- {ticker} ---")
        if not items:
            lines.append("  (no headlines returned)")
            continue
        for item in items:
            lines.append(f"- [{item['publisher']}] {item['title']}")
            if item["summary"]:
                lines.append(f"    {item['summary']}")
    return "\n".join(lines)

def generate_report(prompt: str) -> str:
    """Send the prompt to Claude and return the generated report text."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set.\n"
            "Get a key at https://console.anthropic.com and run:\n"
            '  export ANTHROPIC_API_KEY="sk-ant-..."'
        )
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

def send_email(report_text: str, date_str: str, price_data: dict) -> None:
    """
    Convert Claude's markdown-style report to HTML and email it
    to yourself via Gmail SMTP using an App Password.
    """
    import smtplib
    import re
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    gmail_address = os.environ.get("GMAIL_ADDRESS")
    app_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not app_password:
        print("  WARNING: GMAIL_ADDRESS or GMAIL_APP_PASSWORD not set. Skipping email.")
        return

    # === Convert report text to HTML ========================================
    def md_to_html(text: str) -> str:
        """
        Lightweight markdown-to-HTML converter for the report.
        Handles: ## headings, **bold**, bullet points, blank lines.
        """
        lines = text.split("\n")
        html_lines = []
        for line in lines:
            # Section headings (## Heading)
            if line.startswith("## "):
                content = line[3:].strip()
                html_lines.append(f"<h2>{content}</h2>")
            # Bold text (**text**)
            elif "**" in line:
                line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(f"<p>{line}</p>")
            # Bullet points
            elif line.startswith("- ") or line.startswith("• "):
                content = line[2:].strip()
                content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", content)
                html_lines.append(f"<li>{content}</li>")
            # Blank line
            elif line.strip() == "":
                html_lines.append("<br>")
            # Regular paragraph
            else:
                line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
                html_lines.append(f"<p>{line}</p>")
        return "\n".join(html_lines)

    body_html = md_to_html(report_text)

    # === Full HTML email template ============================================
    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Georgia, 'Times New Roman', serif;
                background-color: #f4f4f4;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 680px;
                margin: 0 auto;
                background: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            .header {{
                background-color: #0a2342;
                color: #ffffff;
                padding: 28px 32px;
            }}
            .header h1 {{
                margin: 0;
                font-size: 22px;
                font-weight: 700;
                letter-spacing: 0.5px;
            }}
            .header p {{
                margin: 6px 0 0;
                font-size: 13px;
                color: #a0b4c8;
            }}
            .body {{
                padding: 28px 32px;
                color: #1a1a1a;
                line-height: 1.7;
                font-size: 15px;
            }}
            h2 {{
                font-size: 16px;
                font-weight: 700;
                color: #0a2342;
                border-bottom: 2px solid #e8edf2;
                padding-bottom: 6px;
                margin-top: 28px;
                margin-bottom: 12px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            p {{
                margin: 0 0 12px;
            }}
            li {{
                margin-bottom: 8px;
            }}
            ul {{
                padding-left: 20px;
            }}
            strong {{
                color: #0a2342;
            }}
            .positive {{
                color: #1a7f4b;
                font-weight: bold;
            }}
            .negative {{
                color: #c0392b;
                font-weight: bold;
            }}
            .footer {{
                background-color: #f4f4f4;
                padding: 16px 32px;
                font-size: 12px;
                color: #888888;
                text-align: center;
                border-top: 1px solid #e0e0e0;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Daily Market Report</h1>
                <p>{date_str} &nbsp;|&nbsp; VOO · VXUS · XLB</p>
            </div>
            <div class="body">
                {build_summary_table(price_data)}
                {body_html}
            </div>
            <div class="footer">
                Generated by your market report script via Claude API.
                This is not financial advice.
            </div>
        </div>
    </body>
    </html>
    """

    # === Send via Gmail SMTP =================================================
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Market Report — {date_str}"
    msg["From"] = gmail_address
    msg["To"] = gmail_address
    msg.attach(MIMEText(report_text, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, app_password)
            server.sendmail(gmail_address, gmail_address, msg.as_string())
        print(f"  Email sent to {gmail_address}")
    except Exception as e:
        print(f"  WARNING: Failed to send email: {e}")

def save_report(report: str, prompt: str = None) -> str:
    """Save the report (and optionally the raw prompt) to a dated markdown file."""
    today = datetime.now().strftime("%Y-%m-%d")
    fname = os.path.join(OUTPUT_DIR, f"market_report_{today}.md")
    with open(fname, "w") as f:
        f.write(f"# Market Report - {today}\n\n")
        f.write(report)
        f.write("\n")
        if prompt:
            f.write("\n\n---\n\n## Raw data sent to Claude\n\n```\n")
            f.write(prompt)
            f.write("\n```\n")
    return fname


def main():
    print(f"Daily Market Report - {datetime.now():%Y-%m-%d %H:%M}")
    print("-" * 60)

    print("Fetching prices...")
    prices = fetch_price_data(TICKERS)
    if not prices:
        print("ERROR: No price data fetched. Exiting.")
        sys.exit(1)

    print("Fetching news...")
    news = fetch_news(TICKERS)

    print("Building prompt...")
    prompt = build_prompt(prices, news)

    print("\n========== PROMPT (what gets sent to Claude) ==========\n")
    print(prompt)

    print("\n========== CLAUDE'S REPORT ==========\n")
    try:
        report = generate_report(prompt)
        print(report)
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"ERROR: Claude API error: {e}")
        sys.exit(1)

    fname = save_report(report, prompt=prompt)
    print(f"\nSaved to {fname}")

    print("\nSending email...")
    date_str = datetime.now().strftime("%B %d, %Y")
    send_email(report, date_str, prices)


if __name__ == "__main__":
    main()
