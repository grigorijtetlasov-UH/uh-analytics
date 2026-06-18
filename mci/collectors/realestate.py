"""🏠 Real estate sub-index — new housing, rental activity."""

from datetime import datetime
from .base import BaseCollector


class RealEstateCollector(BaseCollector):
    name = "realestate"
    weight = 0.05

    # LUN.ua new buildings API (public listing page)
    LUN_URL = "https://www.lun.ua/api/realties/count?city=kyiv"

    async def collect(self):
        signals = []
        score = 50

        now = datetime.now()
        month = now.month

        # --- Seasonal patterns for new housing ---
        # Q2-Q3: most new buildings are commissioned
        if month in (4, 5, 6, 9, 10):
            score += 15
            signals.append("🏗️ Сезон здачі нових ЖК — очікується попит на меблі через 18-22 дні")
        elif month in (7, 8):
            score += 8
            signals.append("🏗️ Літній сезон будівництва — помірна активність")
        elif month in (12, 1, 2):
            score -= 5
            signals.append("❄️ Зимовий застій у будівництві")

        # --- єОселя program estimation ---
        # Program is active, ~2000 mortgages/month → each = buyer in 1-3 months
        score += 5
        signals.append("🏠 Програма єОселя активна — ~2000 іпотек/міс → покупці через 1-3 міс")

        # --- Rental activity peaks ---
        if month in (8, 9):
            score += 10
            signals.append("📦 Пік оренди (серпень-вересень) — переїзди = попит на меблі")
        elif month == 1:
            score += 5
            signals.append("📦 Січневий пік оренди — зміна житла після свят")

        # --- Try LUN data (may be blocked) ---
        lun_data = await self.fetch_text("https://lun.ua/")
        if lun_data and "новобуд" in lun_data.lower():
            signals.append("🔗 LUN.ua доступний для моніторингу")

        return self._result(score, signals, {"month": month})
