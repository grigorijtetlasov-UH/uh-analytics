"""🏪 Market & competitors sub-index — Google Trends + estimation."""

from .base import BaseCollector


class MarketCollector(BaseCollector):
    name = "market"
    weight = 0.05

    # Keywords to track in Google Trends
    KEYWORDS = [
        "купити матрац",
        "купити меблі",
        "матрац ціна",
        "диван купити",
        "меблі Київ",
    ]

    async def collect(self):
        signals = []
        score = 50

        # --- Google Trends via pytrends ---
        try:
            from pytrends.request import TrendReq

            pytrends = TrendReq(hl="uk-UA", tz=120, timeout=(10, 25))
            pytrends.build_payload(
                self.KEYWORDS[:3],  # max 5 keywords
                cat=0,
                timeframe="now 7-d",
                geo="UA",
            )
            df = pytrends.interest_over_time()

            if not df.empty:
                # Average interest across keywords
                avg_interest = df[self.KEYWORDS[:3]].mean().mean()

                if avg_interest > 70:
                    score += 20
                    signals.append(f"🔥 Високий пошуковий попит: {avg_interest:.0f}/100")
                elif avg_interest > 40:
                    score += 10
                    signals.append(f"📊 Помірний пошуковий попит: {avg_interest:.0f}/100")
                elif avg_interest > 20:
                    signals.append(f"📉 Знижений пошуковий попит: {avg_interest:.0f}/100")
                    score -= 5
                else:
                    score -= 15
                    signals.append(f"⬇️ Низький пошуковий попит: {avg_interest:.0f}/100")
            else:
                signals.append("📊 Google Trends: немає даних за тиждень")

        except ImportError:
            signals.append("📊 pytrends не встановлено — пошуковий попит не відстежується")
        except Exception as e:
            signals.append(f"📊 Google Trends помилка: {type(e).__name__}")
            # Use neutral score
            score = 50

        # --- NovaPoshta shipments estimation (seasonal) ---
        # This would need NP API key in production
        signals.append("📦 Нова Пошта: потрібен API-ключ для реальних даних")

        return self._result(score, signals)
