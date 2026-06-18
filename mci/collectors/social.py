"""👥 Social sub-index — payment calendars, consumer sentiment."""

from datetime import datetime
from .base import BaseCollector


# Ukrainian public holidays and sales events
UA_EVENTS = {
    # (month, day): (name, score_impact)
    (1, 1):   ("Новий рік", +5),
    (1, 7):   ("Різдво", +3),
    (3, 8):   ("Міжнародний жіночий день", +8),
    (5, 1):   ("День праці", +3),
    (6, 1):   ("День захисту дітей", +5),
    (8, 24):  ("День Незалежності", +5),
    (9, 1):   ("Початок навчального року", +12),
    (10, 14): ("День захисника", +5),
    (11, 21): ("Чорна п'ятниця (приблизно)", +20),
    (12, 19): ("День Святого Миколая", +10),
    (12, 25): ("Католицьке Різдво", +5),
    (12, 31): ("Переддень Нового року", +8),
}

# Months with historically higher furniture demand
HIGH_DEMAND_MONTHS = {8, 9, 10, 11}  # back-to-school + pre-winter
LOW_DEMAND_MONTHS = {1, 2, 6, 7}     # post-holidays + summer


class SocialCollector(BaseCollector):
    name = "social"
    weight = 0.15

    async def collect(self):
        signals = []
        score = 50

        now = datetime.now()
        day = now.day
        month = now.month

        # --- Payment calendar ---
        # VPO payments: 15-20 of each month
        if 15 <= day <= 20:
            score += 12
            signals.append("💳 Дні виплат ВПО (15-20) — очікується сплеск заявок +15%")

        # Budget sector salaries: 5-10
        if 5 <= day <= 10:
            score += 8
            signals.append("💰 Виплати бюджетникам (5-10 число)")

        # End of month — private sector advances
        if 25 <= day <= 31:
            score += 5
            signals.append("💰 Аванси в приватному секторі")

        # --- Holidays and events ---
        key = (month, day)
        if key in UA_EVENTS:
            name, impact = UA_EVENTS[key]
            score += impact
            signals.append(f"🎉 {name} — вплив на попит: {'+' if impact > 0 else ''}{impact}")

        # Check proximity to events (3 days before)
        for (m, d), (name, impact) in UA_EVENTS.items():
            if m == month and 0 < d - day <= 3:
                pre_impact = impact // 2
                score += pre_impact
                signals.append(f"📅 Через {d - day} дн. — {name}")

        # --- Seasonal demand ---
        if month in HIGH_DEMAND_MONTHS:
            score += 10
            signals.append("📈 Сезон високого попиту на меблі")
        elif month in LOW_DEMAND_MONTHS:
            score -= 5
            signals.append("📉 Сезон зниженого попиту")

        # --- Day of week ---
        weekday = now.weekday()
        if weekday in (0, 1):  # Mon, Tue — peak online orders
            score += 5
            signals.append("📊 Понеділок-вівторок — пік онлайн-замовлень")
        elif weekday >= 5:  # Weekend
            score -= 3
            signals.append("🛋️ Вихідні — менше онлайн-замовлень, більше шоурум")

        return self._result(score, signals, {
            "day_of_month": day,
            "month": month,
            "weekday": weekday,
        })
