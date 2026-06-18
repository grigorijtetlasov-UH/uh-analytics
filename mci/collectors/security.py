"""🛡️ Security sub-index — air alerts via alerts.in.ua API."""

from datetime import datetime, timedelta
from .base import BaseCollector


class SecurityCollector(BaseCollector):
    name = "security"
    weight = 0.25

    # alerts.in.ua — free public API
    ALERTS_URL = "https://api.alerts.in.ua/v1/alerts/active.json"
    HISTORY_URL = "https://api.alerts.in.ua/v1/alerts/regionHistory.json?regionId=31"

    async def collect(self):
        signals = []
        score = 70  # default: moderately safe

        # --- Active alerts right now ---
        data = await self.fetch_json(
            self.ALERTS_URL,
            headers={"X-API-Key": "not_required_for_active"}
        )

        active_count = 0
        if data and isinstance(data, list):
            active_count = len(data)
        elif data and isinstance(data, dict) and "alerts" in data:
            active_count = len(data["alerts"])

        if active_count == 0:
            score += 15
            signals.append("✅ Немає активних тривог")
        elif active_count <= 3:
            score -= 10
            signals.append(f"⚠️ Активних тривог: {active_count}")
        elif active_count <= 10:
            score -= 25
            signals.append(f"🔴 Масова тривога: {active_count} регіонів")
        else:
            score -= 40
            signals.append(f"🚨 Тривога майже по всій країні: {active_count} регіонів")

        # --- Fallback: estimate from time of day / day of week ---
        now = datetime.now()
        hour = now.hour

        # Night attacks are more common 2-6 AM
        if 2 <= hour <= 6:
            score -= 5
            signals.append("🌙 Нічний час — підвищений ризик атак")

        # Weekends slightly calmer for online orders anyway
        if now.weekday() >= 5:
            signals.append("📅 Вихідний — знижений онлайн-трафік")

        return self._result(score, signals, {"active_alerts": active_count})
