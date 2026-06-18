"""⚡ Infrastructure sub-index — power/internet availability."""

from datetime import datetime
from .base import BaseCollector


class InfrastructureCollector(BaseCollector):
    name = "infrastructure"
    weight = 0.20

    # Cloudflare Radar — public internet traffic data for UA
    RADAR_URL = "https://api.cloudflare.com/client/v4/radar/http/timeseries?dateRange=1d&location=UA&format=json"

    async def collect(self):
        signals = []
        score = 60  # default: mostly OK

        now = datetime.now()
        month = now.month
        hour = now.hour

        # --- Season-based power estimation ---
        # Winter months = higher risk of outages due to energy attacks
        if month in (12, 1, 2):
            score -= 15
            signals.append("❄️ Зимовий період — підвищений ризик відключень")
        elif month in (11, 3):
            score -= 8
            signals.append("🍂 Опалювальний сезон — помірний ризик відключень")
        else:
            score += 10
            signals.append("☀️ Теплий сезон — мінімальний ризик відключень")

        # --- Time-based internet traffic estimation ---
        # Peak online shopping: 10-14 and 19-22
        if 10 <= hour <= 14:
            score += 10
            signals.append("📈 Пік онлайн-активності (10:00-14:00)")
        elif 19 <= hour <= 22:
            score += 8
            signals.append("📈 Вечірній пік онлайн-активності")
        elif 0 <= hour <= 6:
            score -= 5
            signals.append("🌙 Нічні години — мінімальний трафік")

        # --- Try to get real Cloudflare data (often blocked without key) ---
        radar = await self.fetch_json(self.RADAR_URL)
        if radar and "result" in radar:
            signals.append("📡 Дані Cloudflare Radar отримано")
        else:
            signals.append("📡 Cloudflare Radar: використовуємо оцінку")

        return self._result(score, signals, {"month": month, "hour": hour})
