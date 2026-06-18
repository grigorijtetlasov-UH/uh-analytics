"""☁️ Weather & calendar sub-index — Open-Meteo API (free, no key)."""

from .base import BaseCollector


# Major Ukrainian cities with coordinates
CITIES = {
    "Kyiv":         (50.45, 30.52),
    "Kharkiv":      (49.99, 36.23),
    "Odesa":        (46.48, 30.73),
    "Dnipro":       (48.46, 35.04),
    "Lviv":         (49.84, 24.03),
}


class WeatherCollector(BaseCollector):
    name = "weather"
    weight = 0.05

    async def collect(self):
        signals = []
        score = 50
        temps = {}

        # --- Get current weather for major cities ---
        for city, (lat, lon) in CITIES.items():
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current_weather=true"
                f"&timezone=Europe/Kyiv"
            )
            data = await self.fetch_json(url)

            if data and "current_weather" in data:
                temp = data["current_weather"]["temperature"]
                temps[city] = temp

        if temps:
            avg_temp = sum(temps.values()) / len(temps)
            kyiv_temp = temps.get("Kyiv", avg_temp)

            # --- Temperature impact on mattress/bedding demand ---
            if avg_temp < 0:
                score += 15
                signals.append(f"🥶 Мороз (сер. {avg_temp:.0f}°C) — підвищений попит на ковдри та наматрацники")
            elif avg_temp < 10:
                score += 10
                signals.append(f"🌡️ Прохолодно (сер. {avg_temp:.0f}°C) — зростає попит на постільне")
            elif avg_temp < 20:
                score += 3
                signals.append(f"🌤️ Комфортна температура (сер. {avg_temp:.0f}°C)")
            elif avg_temp < 30:
                signals.append(f"☀️ Тепло (сер. {avg_temp:.0f}°C) — попит на літнє постільне")
            else:
                score -= 5
                signals.append(f"🔥 Спека (сер. {avg_temp:.0f}°C) — знижена активність покупців")

            signals.append(f"🌡️ Київ: {kyiv_temp:.0f}°C")
        else:
            signals.append("🌡️ Не вдалося отримати погоду — використовуємо нейтральну оцінку")

        return self._result(score, signals, {"temperatures": temps})
