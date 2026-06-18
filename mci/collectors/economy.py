"""📈 Economy sub-index — NBU exchange rates + interbank."""

from datetime import datetime
from .base import BaseCollector


class EconomyCollector(BaseCollector):
    name = "economy"
    weight = 0.25

    # NBU official API — free, no key needed
    NBU_RATE_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=USD&json"
    NBU_RATE_EUR_URL = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json"

    # Thresholds for USD/UAH
    USD_CALM = 41.0       # below = stable
    USD_WORRY = 43.0      # above = people start panic-buying
    USD_PANIC = 45.0      # above = serious devaluation fears

    async def collect(self):
        signals = []
        score = 50  # neutral default

        # --- USD rate ---
        usd_data = await self.fetch_json(self.NBU_RATE_URL)
        usd_rate = None
        if usd_data and isinstance(usd_data, list) and len(usd_data) > 0:
            usd_rate = usd_data[0].get("rate")

        if usd_rate:
            if usd_rate < self.USD_CALM:
                score += 20
                signals.append(f"✅ Курс USD стабільний: {usd_rate:.2f} грн")
            elif usd_rate < self.USD_WORRY:
                score += 5
                signals.append(f"➡️ Курс USD помірний: {usd_rate:.2f} грн")
            elif usd_rate < self.USD_PANIC:
                score -= 10
                signals.append(f"⚠️ Курс USD зростає: {usd_rate:.2f} грн — частина покупців прискорює покупки")
            else:
                score -= 20
                signals.append(f"🔴 Курс USD високий: {usd_rate:.2f} грн — паніка на ринку")
                # Paradox: some people rush to buy goods to "save" money
                score += 5
                signals.append("💡 Парадокс: частина покупців вкладає в товар щоб зберегти кошти")
        else:
            signals.append("❓ Не вдалося отримати курс НБУ")

        # --- EUR rate ---
        eur_data = await self.fetch_json(self.NBU_RATE_EUR_URL)
        eur_rate = None
        if eur_data and isinstance(eur_data, list) and len(eur_data) > 0:
            eur_rate = eur_data[0].get("rate")

        if eur_rate:
            signals.append(f"💶 Курс EUR: {eur_rate:.2f} грн")

        # --- Day of month: salary/payment cycles ---
        day = datetime.now().day
        if 5 <= day <= 10:
            score += 10
            signals.append("💰 Дні виплати зарплат бюджетникам (5-10 число)")
        elif 15 <= day <= 20:
            score += 8
            signals.append("💰 Дні виплат ВПО та соціальних (15-20 число)")
        elif 25 <= day <= 31:
            score += 5
            signals.append("💰 Кінець місяця — аванси в приватному секторі")

        return self._result(score, signals, {
            "usd_rate": usd_rate,
            "eur_rate": eur_rate,
        })
