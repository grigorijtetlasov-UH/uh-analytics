"""Telegram notifications for MCI."""

import aiohttp
from mci.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from mci.models import MCIResult
from mci.storage import get_trend


def format_report(result: MCIResult) -> str:
    """Format MCI result as Telegram message."""

    lines = [
        f"📊 *MCI — Market Conditions Index*",
        f"🗓 {result.timestamp.strftime('%d.%m.%Y %H:%M')}",
        "",
        f"*Індекс: {result.score:.0f}/100 {result.label}*",
        f"💡 _{result.advice}_",
        "",
        get_trend(),
        "",
        "─── Суб-індекси ───",
    ]

    emoji_map = {
        "security": "🛡️",
        "economy": "📈",
        "infrastructure": "⚡",
        "social": "👥",
        "realestate": "🏠",
        "market": "🏪",
        "weather": "☁️",
        "newsfield": "📡",
    }

    for si in result.sub_indexes:
        emoji = emoji_map.get(si.name, "📊")
        bar = _score_bar(si.score)
        lines.append(f"{emoji} *{si.name}*: {si.score:.0f} {bar}")

        # More signals for newsfield (AI analysis)
        limit = 8 if si.name == "newsfield" else 3
        for signal in si.signals[:limit]:
            lines.append(f"    {signal}")

    lines.extend([
        "",
        "─── Рекомендація ───",
        f"💡 {result.advice}",
    ])

    return "\n".join(lines)


def _score_bar(score: float) -> str:
    """Visual score bar."""
    filled = int(score / 10)
    return "█" * filled + "░" * (10 - filled)


async def send_telegram(result: MCIResult) -> bool:
    """Send MCI report to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[notifier] Telegram not configured — skipping")
        return False

    text = format_report(result)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    print("[notifier] Telegram message sent ✅")
                    return True
                else:
                    body = await resp.text()
                    print(f"[notifier] Telegram error {resp.status}: {body}")
                    return False
    except Exception as e:
        print(f"[notifier] Telegram send failed: {e}")
        return False
