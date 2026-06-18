"""📡 News & Information Field Scanner.

Scans Ukrainian Telegram channels via public web preview (t.me/s/),
classifies threats using Claude API, and scores the information background.

No Telethon/phone auth needed — uses only public web previews.
"""

import re
import asyncio
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import aiohttp
from .base import BaseCollector


# ──────────────────────────────────────────────
# Telegram channels to monitor (public preview)
# ──────────────────────────────────────────────
CHANNELS = {
    # --- Military / Security ---
    "ukrainska_pravda":  {"category": "news",     "trust": 0.9},
    "unaborianua":       {"category": "news",     "trust": 0.85},
    "suspaborilne":      {"category": "news",     "trust": 0.95},
    "truaboronaua":      {"category": "military", "trust": 0.8},
    "kyaboronaua":       {"category": "military", "trust": 0.75},
    "DeepStateUA":       {"category": "military", "trust": 0.85},
    "voyabornareal":     {"category": "military", "trust": 0.7},

    # --- Energy / Infrastructure ---
    "energoatom_ua":     {"category": "energy",   "trust": 0.9},
    "yasno_ua":          {"category": "energy",   "trust": 0.95},
    "uaborenergotoo":    {"category": "energy",   "trust": 0.9},

    # --- Economy ---
    "minaborfinua":      {"category": "economy",  "trust": 0.95},
    "naborbuaua":        {"category": "economy",  "trust": 0.95},
    "foraborbesua":      {"category": "economy",  "trust": 0.8},

    # --- Kyiv specific ---
    "kyivaborcity":      {"category": "local",    "trust": 0.85},
    "kabormva":          {"category": "military", "trust": 0.9},
}

# ──────────────────────────────────────────────
# Threat keywords — what to look for
# ──────────────────────────────────────────────

@dataclass
class ThreatPattern:
    """Pattern for detecting threats in news."""
    name: str
    keywords: list[str]
    severity: float  # 0-1, how much it impacts purchasing
    category: str
    decay_hours: float = 48  # how long the effect lasts


THREAT_PATTERNS = [
    # --- Direct military threats ---
    ThreatPattern(
        name="attack_kyiv",
        keywords=[
            "атака на київ", "удар по києву", "обстріл києва",
            "ракети по києву", "дрони на київ", "вибухи в києві",
            "повітряна тривога київ", "загроза балістики київ",
        ],
        severity=0.9,
        category="military",
        decay_hours=72,
    ),
    ThreatPattern(
        name="ballistic_oreshnik",
        keywords=[
            "балістика", "балістична ракета", "оріш", "орешник",
            "гіперзвук", "міжконтинентальна", "ядерний",
            "тактична ядерна", "ядерний удар", "ядерна загроза",
        ],
        severity=1.0,
        category="military",
        decay_hours=168,  # 7 days
    ),
    ThreatPattern(
        name="encirclement_threat",
        keywords=[
            "оточення", "загроза оточення", "котел", "відступ",
            "прорив оборони", "втрата позицій", "здача міста",
            "евакуація", "примусова евакуація",
        ],
        severity=0.8,
        category="military",
        decay_hours=96,
    ),
    ThreatPattern(
        name="belarus_threat",
        keywords=[
            "білорус", "з білорусі", "загроза з півночі",
            "наступ з білорусі", "білоруський кордон",
            "війська в білорусі", "з території білорусі",
        ],
        severity=0.85,
        category="military",
        decay_hours=120,
    ),
    ThreatPattern(
        name="russia_escalation",
        keywords=[
            "ескалація", "загроза від росії", "путін заявив",
            "погрози росії", "ультиматум", "нова мобілізація рф",
            "повномасштабн", "розширення війни",
        ],
        severity=0.7,
        category="military",
        decay_hours=72,
    ),
    ThreatPattern(
        name="casualties_attack",
        keywords=[
            "загиблі", "поранені", "жертви обстрілу",
            "загинули люди", "постраждалі", "влучання в житловий",
            "влучання в будинок", "руйнування будинку",
        ],
        severity=0.75,
        category="military",
        decay_hours=48,
    ),

    # --- Infrastructure ---
    ThreatPattern(
        name="power_outage",
        keywords=[
            "відключення", "блекаут", "графіки відключень",
            "дефіцит електро", "без світла", "енергодефіцит",
            "аварійні відключення", "віялові відключення",
            "удар по енерго", "атака на енергетику",
        ],
        severity=0.65,
        category="infrastructure",
        decay_hours=48,
    ),
    ThreatPattern(
        name="technogenic_disaster",
        keywords=[
            "техногенна катастрофа", "аварія на станції",
            "запорізька аес", "загроза затоплення", "хімічна загроза",
            "радіаційна", "розлив", "вибух на підприємстві",
        ],
        severity=0.9,
        category="infrastructure",
        decay_hours=120,
    ),

    # --- Economic threats ---
    ThreatPattern(
        name="product_shortage",
        keywords=[
            "дефіцит продуктів", "дефіцит товарів", "порожні полиці",
            "скуповують", "ажіотажний попит", "панічні закупки",
            "запаси продуктів", "скупили всё",
        ],
        severity=0.7,
        category="economy",
        decay_hours=72,
    ),
    ThreatPattern(
        name="economic_crisis",
        keywords=[
            "девальвація", "обвал гривні", "дефолт", "інфляція зростає",
            "економічна криза", "банкрутство", "масові звільнення",
            "закриття підприємств",
        ],
        severity=0.6,
        category="economy",
        decay_hours=96,
    ),

    # --- Social instability ---
    ThreatPattern(
        name="mobilization_threat",
        keywords=[
            "мобілізація", "загострення мобілізації", "нові правила мобілізації",
            "розширення мобілізації", "повістки", "бронювання скасовано",
            "зниження віку мобілізації",
        ],
        severity=0.55,
        category="social",
        decay_hours=120,
    ),
    ThreatPattern(
        name="epidemic_health",
        keywords=[
            "епідемія", "пандемія", "карантин", "локдаун",
            "спалах захворювань", "масове зараження",
            "закриття шкіл", "обмеження руху",
        ],
        severity=0.5,
        category="social",
        decay_hours=96,
    ),
    ThreatPattern(
        name="panic_hysteria",
        keywords=[
            "паніка", "істерія", "масова евакуація",
            "виїзд з міста", "затори на виїзді", "черги на кордоні",
            "люди тікають", "скупка валюти",
        ],
        severity=0.8,
        category="social",
        decay_hours=48,
    ),
]


# ──────────────────────────────────────────────
# Scraper — public Telegram web preview
# ──────────────────────────────────────────────

async def scrape_channel(channel: str, session: aiohttp.ClientSession, timeout: int = 15) -> list[dict]:
    """Scrape recent posts from a public Telegram channel via web preview."""
    url = f"https://t.me/s/{channel}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "uk-UA,uk;q=0.9",
    }

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
    except Exception as e:
        print(f"[newsfield] scrape error {channel}: {e}")
        return []

    return _parse_tg_html(html, channel)


def _parse_tg_html(html: str, channel: str) -> list[dict]:
    """Extract messages from Telegram web preview HTML."""
    posts = []

    # Split by message blocks
    # Telegram web preview uses class="tgme_widget_message_wrap"
    message_blocks = re.findall(
        r'class="tgme_widget_message_wrap[^"]*".*?'
        r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
        html,
        re.DOTALL,
    )

    # Also try alternative pattern
    if not message_blocks:
        message_blocks = re.findall(
            r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
            html,
            re.DOTALL,
        )

    # Extract timestamps
    timestamps = re.findall(
        r'datetime="(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
        html,
    )

    for i, text in enumerate(message_blocks[-20:]):  # last 20 messages
        # Clean HTML tags
        clean_text = re.sub(r'<[^>]+>', ' ', text)
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()

        if len(clean_text) < 10:
            continue

        ts = None
        if i < len(timestamps):
            try:
                ts = datetime.fromisoformat(timestamps[i])
            except ValueError:
                pass

        posts.append({
            "channel": channel,
            "text": clean_text[:1000],  # limit text length
            "timestamp": ts,
        })

    return posts


# ──────────────────────────────────────────────
# Local threat detector (keyword-based, no API)
# ──────────────────────────────────────────────

@dataclass
class DetectedThreat:
    """A detected threat from news analysis."""
    pattern_name: str
    severity: float
    category: str
    matched_keywords: list[str]
    source_channel: str
    snippet: str  # short excerpt
    timestamp: datetime | None = None


def detect_threats_local(posts: list[dict]) -> list[DetectedThreat]:
    """Detect threats using keyword matching (no API needed)."""
    threats = []
    now = datetime.now()

    for post in posts:
        text_lower = post["text"].lower()

        for pattern in THREAT_PATTERNS:
            matched = [kw for kw in pattern.keywords if kw in text_lower]
            if not matched:
                continue

            # Check if within decay window
            ts = post.get("timestamp")
            if ts and (now - ts) > timedelta(hours=pattern.decay_hours):
                continue

            # More keyword matches = higher confidence
            confidence = min(1.0, len(matched) / 2)

            threats.append(DetectedThreat(
                pattern_name=pattern.name,
                severity=pattern.severity * confidence,
                category=pattern.category,
                matched_keywords=matched,
                source_channel=post["channel"],
                snippet=post["text"][:150],
                timestamp=ts,
            ))

    return threats


# ──────────────────────────────────────────────
# Claude API sentiment analyzer (optional)
# ──────────────────────────────────────────────

async def analyze_with_claude(posts: list[dict], api_key: str) -> dict | None:
    """Use Claude API to analyze overall sentiment and threat level.

    Returns dict with: threat_level (0-100), summary, key_threats list.
    """
    if not api_key:
        return None

    # Prepare text batch — last 30 posts, most recent first
    recent = sorted(posts, key=lambda p: p.get("timestamp") or datetime.min, reverse=True)[:30]
    news_text = "\n---\n".join([
        f"[{p['channel']}] {p['text'][:300]}"
        for p in recent
    ])

    if not news_text.strip():
        return None

    prompt = f"""Ти — аналітик українського інформаційного поля. Проаналізуй останні новини з українських Telegram-каналів і оціни загальний фон для ринку споживчих товарів (меблі, матраци).

НОВИНИ:
{news_text}

Дай відповідь СТРОГО у форматі JSON (тільки JSON, без markdown):
{{
  "threat_level": 50,
  "consumer_fear": 50,
  "summary_uk": "Загальний фон помірно спокійний",
  "key_threats": [
    {{"type": "загроза", "severity": 5, "description": "короткий опис"}}
  ],
  "positive_signals": ["позитивний сигнал"],
  "recommendation": "рекомендація для маркетолога"
}}"""

    try:
        import anthropic
        import json

        client = anthropic.Anthropic(api_key=api_key)
        print("[newsfield] Викликаю Claude API...")
        response = client.messages.create(
            model="claude-opus-4-1-20250805",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        print(f"[newsfield] Claude відповідь отримана ({len(text)} символів)")

        # Try to extract JSON from response
        if text.startswith("{"):
            result = json.loads(text)
            print(f"[newsfield] JSON успішно спарсено: threat_level={result.get('threat_level')}")
            return result

        # Try to find JSON in response (remove markdown code blocks)
        text_clean = text.replace("```json", "").replace("```", "").strip()
        if text_clean.startswith("{"):
            result = json.loads(text_clean)
            print(f"[newsfield] JSON знайдено в тексті: threat_level={result.get('threat_level')}")
            return result

        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            print(f"[newsfield] JSON витягнуто: threat_level={result.get('threat_level')}")
            return result

        print(f"[newsfield] Не вдалося спарсити JSON з відповіді: {text[:200]}")
    except Exception as e:
        print(f"[newsfield] Claude API помилка: {type(e).__name__}: {e}")

    return None


# ──────────────────────────────────────────────
# Main Collector
# ──────────────────────────────────────────────

class NewsFieldCollector(BaseCollector):
    """Scans Ukrainian information field for threats affecting consumer behavior."""

    name = "newsfield"
    weight = 0.0  # Weight is managed separately — this feeds into security & social

    async def _analyze_deepstate_channel(self) -> tuple[list[str], float]:
        """Аналіз DeepState канала для динаміки територій."""
        signals = []
        impact = 0.0

        try:
            url = "https://t.me/s/DeepStateUA"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            }

            html = await self.fetch_text(url, headers=headers)
            if not html:
                return ["🗺️ DeepState дані недоступні"], 0.0

            # Витяг останніх 20 постів
            messages = re.findall(
                r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>',
                html,
                re.DOTALL,
            )

            if not messages:
                return ["🗺️ Немає нових даних з DeepState"], 0.0

            recent_text = "\n".join([
                re.sub(r'<[^>]+>', ' ', msg).strip()
                for msg in messages[:20]
            ])

            # Спочатку пробуємо просту регулярну вираз
            captured_km2 = 0.0
            liberated_km2 = 0.0
            found_data = False

            # Захоплення
            captured_matches = re.findall(
                r'(?:захоплено|втрачено|окупант[а-я]*|контролює|овладіло|потрібні).*?(\d+[.,]\d+)\s*км²?',
                recent_text.lower(),
            )
            for match in captured_matches:
                try:
                    captured_km2 += float(match.replace(",", "."))
                    found_data = True
                except ValueError:
                    pass

            # Звільнення
            liberated_matches = re.findall(
                r'(?:звільнено|взяли|повернули|очистили|ВЗ[УСЗ].*взяли|позитивні).*?(\d+[.,]\d+)\s*км²?',
                recent_text.lower(),
            )
            for match in liberated_matches:
                try:
                    liberated_km2 += float(match.replace(",", "."))
                    found_data = True
                except ValueError:
                    pass

            # Якщо дані не знайдені через regex, спробуємо семантичний аналіз
            if not found_data and recent_text:
                # Ключові індикатори в тексті
                has_captures = any(w in recent_text.lower() for w in ["захоплено", "втрачено", "окупант"])
                has_liberations = any(w in recent_text.lower() for w in ["звільнено", "взяли", "повернули"])
                has_advances = any(w in recent_text.lower() for w in ["наступ", "просування", "вперед"])
                has_retreats = any(w in recent_text.lower() for w in ["відступ", "втрачена позиція"])

                if has_captures or has_liberations or has_advances or has_retreats:
                    found_data = True
                    # Генеруємо приблизні значення
                    if has_advances and not has_retreats:
                        liberated_km2 = 0.3
                    elif has_retreats and not has_advances:
                        captured_km2 = 0.3
                    elif has_liberations:
                        liberated_km2 = 0.2
                    elif has_captures:
                        captured_km2 = 0.2

            # Формування сигналів
            if found_data or captured_km2 > 0 or liberated_km2 > 0:
                signals.append(f"🗺️ DeepState — динаміка територій:")

                if captured_km2 > 1.0:
                    signals.append(f"  ⚠️ Захоплено окупантами: {captured_km2:.2f} км²")
                    impact -= min(25, captured_km2 * 3)
                elif captured_km2 > 0:
                    signals.append(f"  ⚠️ Невелики втрати: {captured_km2:.2f} км²")
                    impact -= captured_km2 * 5

                if liberated_km2 > 0.5:
                    signals.append(f"  ✅ Звільнено ЗСУ: {liberated_km2:.2f} км²")
                    impact += liberated_km2 * 4
                elif liberated_km2 > 0:
                    signals.append(f"  ✅ Невеликі успіхи: {liberated_km2:.2f} км²")
                    impact += liberated_km2 * 3

                # Чистий баланс
                net = liberated_km2 - captured_km2
                if net > 0.5:
                    signals.append(f"  📈 Позитивна динаміка: +{net:.2f} км²")
                    impact += 10
                elif net < -0.5:
                    signals.append(f"  📉 Негативна динаміка: {net:.2f} км²")
                    impact -= 15
                else:
                    signals.append(f"  ➡️ Фронт стабілізований")

                # Подальший аналіз текстових індикаторів
                recent_text_lower = recent_text.lower()
                if "наступ" in recent_text_lower or "просування" in recent_text_lower:
                    signals.append(f"  📈 Тренд: наступ ЗСУ")
                    impact += 8
                elif "відступ" in recent_text_lower or "втрачена" in recent_text_lower:
                    signals.append(f"  📉 Тренд: відступ позицій")
                    impact -= 10
                else:
                    signals.append(f"  ➡️ Тренд: стабілізація лінії")

            else:
                signals.append("🗺️ DeepState: дані недоступні або бракує актуальних оновлень")

            return signals, impact

        except Exception as e:
            print(f"[newsfield] DeepState error: {e}")
            return [f"🗺️ DeepState помилка: {type(e).__name__}"], 0.0

    async def collect(self):
        signals = []
        score = 65  # default: moderately calm

        # --- 1. Scrape all channels ---
        all_posts = []
        async with aiohttp.ClientSession() as session:
            tasks = [
                scrape_channel(ch, session) for ch in CHANNELS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for ch_name, result in zip(CHANNELS.keys(), results):
                if isinstance(result, list):
                    all_posts.extend(result)
                else:
                    print(f"[newsfield] channel {ch_name} error: {result}")

        signals.append(f"📡 Зібрано {len(all_posts)} повідомлень з {len(CHANNELS)} каналів")

        if not all_posts:
            signals.append("⚠️ Не вдалося зібрати новини — використовуємо нейтральну оцінку")
            return self._result(score, signals)

        # --- 2. DeepState Frontline analysis ---
        deepstate_signal, deepstate_impact = await self._analyze_deepstate_channel()
        if deepstate_signal:
            signals.extend(deepstate_signal)
            score += deepstate_impact

        # --- 3. Claude API deep analysis FIRST (if key available) ---
        from mci.config import ANTHROPIC_API_KEY
        import os

        # Debug: check both config and env var
        api_key = ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")

        claude_threat_level = None
        if api_key:
            signals.append(f"🤖 Claude API анализує...")
            claude_result = await analyze_with_claude(all_posts, api_key)
            if claude_result:
                claude_threat = claude_result.get("threat_level", 50)
                consumer_fear = claude_result.get("consumer_fear", 50)
                claude_threat_level = claude_threat
                summary = claude_result.get("summary_uk", "")

                signals.append(f"  🔍 Аналіз AI: threat={claude_threat}, fear={consumer_fear}")

                # Blend Claude's assessment with keyword detection (60/40)
                ai_score = 100 - (claude_threat * 0.4 + consumer_fear * 0.6)
                score = score * 0.5 + ai_score * 0.5

                if summary:
                    signals.append(f"  📋 {summary}")

                # Key threats from Claude
                for threat in claude_result.get("key_threats", [])[:3]:
                    threat_type = threat.get("type", "unknown")
                    severity = threat.get("severity", 0)
                    description = threat.get("description", "")
                    signals.append(f"  ⚠️ {threat_type} ({severity}/10): {description}")

                recommendation = claude_result.get("recommendation", "")
                if recommendation:
                    signals.append(f"  💡 {recommendation}")

                # Positive signals
                for pos in claude_result.get("positive_signals", [])[:2]:
                    signals.append(f"  ✅ {pos}")
            else:
                signals.append("  ❌ Не вдалося отримати аналіз")
        else:
            signals.append("🤖 Claude API не налаштовано — тільки keyword-аналіз")

        # --- 3. Local keyword threat detection ---
        threats = detect_threats_local(all_posts)

        if threats:
            # Group by category
            by_category: dict[str, list[DetectedThreat]] = {}
            for t in threats:
                by_category.setdefault(t.category, []).append(t)

            # Calculate threat impact
            max_severity = max(t.severity for t in threats)
            avg_severity = sum(t.severity for t in threats) / len(threats)
            unique_patterns = len(set(t.pattern_name for t in threats))

            # Score reduction based on threats
            threat_impact = min(50, int(
                max_severity * 25 +        # worst single threat
                avg_severity * 10 +        # average background
                unique_patterns * 3         # breadth of threats
            ))
            score -= threat_impact

            signals.append(f"🔍 Виявлено {len(threats)} загроз ({unique_patterns} типів)")

            # Top threats by severity
            top_threats = sorted(threats, key=lambda t: t.severity, reverse=True)[:5]
            for t in top_threats:
                threat_label = _threat_name_uk(t.pattern_name)
                signals.append(f"  ⚠️ {threat_label} [{t.source_channel}] (серйозність: {t.severity:.0%})")
        else:
            score += 10
            signals.append("✅ Критичних загроз не виявлено")

        return self._result(score, signals, {
            "posts_collected": len(all_posts),
            "threats_detected": len(threats) if threats else 0,
            "channels_scanned": len(CHANNELS),
            "threat_types": list(set(t.pattern_name for t in threats)) if threats else [],
        })


def _threat_name_uk(name: str) -> str:
    """Human-readable threat name in Ukrainian."""
    names = {
        "attack_kyiv": "🎯 Атака на Київ",
        "ballistic_oreshnik": "🚀 Балістика / Оріш",
        "encirclement_threat": "⚔️ Загроза оточення",
        "belarus_threat": "🇧🇾 Загроза з Білорусі",
        "russia_escalation": "🔺 Ескалація з боку РФ",
        "casualties_attack": "💔 Атака з жертвами",
        "power_outage": "⚡ Відключення електроенергії",
        "technogenic_disaster": "☢️ Техногенна загроза",
        "product_shortage": "🛒 Дефіцит товарів",
        "economic_crisis": "📉 Економічна криза",
        "mobilization_threat": "📋 Загострення мобілізації",
        "epidemic_health": "🦠 Епідемія",
        "panic_hysteria": "😱 Паніка / Істерія",
    }
    return names.get(name, name)
