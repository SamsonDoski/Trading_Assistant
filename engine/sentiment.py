import os
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

MULTIPLIER_MIN = 0.5
MULTIPLIER_MAX = 1.5


class SentimentVerdict(BaseModel):
    """The LLM's structured output — schema for the parse call only."""
    sentiment_multiplier: float
    veto: bool
    rationale: str


class SentimentReport(BaseModel):
    """What callers receive: the verdict PLUS the evidence behind it, so no
    caller ever needs to reach back into this module for context."""
    sentiment_multiplier: float
    veto: bool
    rationale: str
    headlines: list[str] = []


def _neutral(headlines=None):
    """Baseline report — trade proceeds at normal size."""
    return SentimentReport(
        sentiment_multiplier=1.0,
        veto=False,
        rationale="No recent news or sentiment unavailable; trading at baseline size.",
        headlines=headlines or [],
    )


SYSTEM_PROMPT = """You are a financial news analyst for an automated trend-following trading bot.
You will receive recent news items (each a headline, plus a short summary when available) for a stock the bot is about to BUY on a technical signal.
Score the news impact on that purchase:

- sentiment_multiplier: position-size multiplier from 0.5 to 1.5.
  0.5-0.8 = clearly negative news (weak earnings, downgrades, guidance cuts).
  0.9-1.1 = neutral, mixed, routine, or ambiguous news.
  1.2-1.5 = clearly positive news (strong earnings, upgrades, major wins).
  Judge financial impact, not word tone: "slashes prices" can be bullish for volume.
- veto: true ONLY for disqualifying events — fraud, bankruptcy risk, SEC/DOJ investigation,
  delisting, going-concern doubt, auditor resignation. Ordinary bad news is NOT a veto;
  express it through a low multiplier instead.
- rationale: one short sentence explaining your call.

News items are prefixed with their age, e.g. "[3h ago]". Weight fresher news more
heavily; older news within the window may already be priced in."""


class SentimentAnalyzer:
    """Scores recent news for a buy candidate with Claude Haiku.

    Advisory only: every failure path (no news, news API down, Anthropic down,
    malformed response) returns a neutral report so the trade proceeds at
    baseline size. This module must never raise into the trade loop.
    """

    def __init__(self):
        # Lazy clients: importing this module can never fail — a missing
        # anthropic package or API key degrades the scoring call to neutral,
        # not the pipeline.
        self._news_client = None
        self._llm = None

    def _get_news_client(self):
        if self._news_client is None:
            from alpaca.data.historical.news import NewsClient
            self._news_client = NewsClient(
                os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_SECRET_KEY")
            )
        return self._news_client

    def _get_llm(self):
        if self._llm is None:
            import anthropic
            # Short timeout + 1 retry: a hung sentiment call must not eat the
            # Lambda time budget. Past this, we fall back to neutral.
            self._llm = anthropic.Anthropic(timeout=15.0, max_retries=1)
        return self._llm

    def fetch_headlines(self, ticker, hours=24, limit=10, summary_chars=300):
        """Recent news for the ticker as age-prefixed strings, e.g.
        "[3h ago] Headline — short summary...". Including Alpaca's article
        summary (free in the same response) gives the model a sentence of
        context instead of just the title, cutting misleading-headline and
        wrong-ticker-contamination errors. Empty list on any failure.

        Single seam for news sourcing: additional providers plug in here
        (fetch, merge, dedupe) without any caller changing.
        """
        try:
            from alpaca.data.requests import NewsRequest
            now = datetime.now(timezone.utc)
            req = NewsRequest(
                symbols=ticker,
                start=now - timedelta(hours=hours),
                limit=limit,
            )
            news = self._get_news_client().get_news(req)
            items = news.data.get("news", []) if hasattr(news, "data") else []
            headlines = []
            for item in items:
                headline = (getattr(item, "headline", "") or "").strip()
                if not headline:
                    continue

                # Alpaca returns a short summary in the same payload — free extra
                # context. Collapse whitespace, cap the length so a long body
                # can't blow up the prompt, and drop it if it just echoes the
                # headline (Benzinga sometimes duplicates).
                summary = (getattr(item, "summary", "") or "").strip()
                if summary:
                    summary = " ".join(summary.split())
                    if len(summary) > summary_chars:
                        summary = summary[:summary_chars].rstrip() + "…"
                    if summary.lower() == headline.lower():
                        summary = ""
                text = f"{headline} — {summary}" if summary else headline

                try:
                    created = getattr(item, "created_at", None)
                    age_h = (now - created).total_seconds() / 3600.0
                    if age_h > hours:
                        continue     # skip any news that slipped past the filter
                    headlines.append(f"[{max(age_h, 0):.0f}h ago] {text}")
                except Exception:
                    headlines.append(text)   # keep the item even if its timestamp is unusable
            return headlines
        except Exception as e:
            print(f"⚠️ News fetch failed for {ticker}: {e}")
            return []

    def get_verdict(self, ticker):
        """SentimentReport for a buy candidate. Neutral on any failure."""
        headlines = self.fetch_headlines(ticker)
        if not headlines:
            print(f"📰 {ticker}: no recent news — neutral sentiment.")
            return _neutral()

        try:
            response = self._get_llm().messages.parse(
                model="claude-haiku-4-5",
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{
                    "role": "user",
                    "content": f"Ticker: {ticker}\nHeadlines from the last 24 hours:\n"
                               + "\n".join(f"- {h}" for h in headlines),
                }],
                output_format=SentimentVerdict,
            )
            verdict = response.parsed_output
            report = SentimentReport(
                # Clamp defensively — the schema asks for 0.5-1.5 but we enforce it.
                sentiment_multiplier=max(
                    MULTIPLIER_MIN, min(MULTIPLIER_MAX, verdict.sentiment_multiplier)
                ),
                veto=verdict.veto,
                rationale=verdict.rationale,
                headlines=headlines,
            )
            print(f"📰 {ticker}: x{report.sentiment_multiplier:.2f} "
                  f"veto={report.veto} — {report.rationale}")
            return report
        except Exception as e:
            print(f"⚠️ Sentiment scoring failed for {ticker}: {e}")
            return _neutral(headlines)


if __name__ == "__main__":
    # Terminal tool: news + sentiment for any ticker.
    #   python -m engine.sentiment NVDA
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    ticker = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    report = SentimentAnalyzer().get_verdict(ticker)
    print(f"\n=== {ticker} sentiment ===")
    if report.headlines:
        print(f"Headlines considered ({len(report.headlines)}):")
        for h in report.headlines:
            print(f"  • {h}")
    else:
        print("No headlines in the last 24 hours.")
    print(f"\nMultiplier: x{report.sentiment_multiplier:.2f}")
    print(f"Veto:       {report.veto}")
    print(f"Rationale:  {report.rationale}")