"""MCI — Market Conditions Index — entry point.

Usage:
    python -m mci.main              # Single run — calculate and print
    python -m mci.main --notify     # Calculate + send to Telegram
    python -m mci.main --schedule   # Run daily at 08:00
    python -m mci.main --json       # Output raw JSON
"""

import asyncio
import argparse
import json
import sys

from mci.engine import calculate_mci
from mci.storage import save_result
from mci.notifier import format_report, send_telegram


async def run_once(notify: bool = False, as_json: bool = False) -> None:
    """Single MCI calculation."""

    print("=" * 50)
    print("  MCI — Market Conditions Index")
    print("  Розрахунок...")
    print("=" * 50)

    result = await calculate_mci()

    if as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_report(result))

    # Save to history
    save_result(result)
    print(f"\n💾 Збережено в історію ({result.timestamp.strftime('%d.%m.%Y %H:%M')})")

    # Send to Telegram if requested
    if notify:
        await send_telegram(result)


def run_scheduled():
    """Run MCI on a daily schedule at 08:00."""
    from apscheduler.schedulers.blocking import BlockingScheduler

    scheduler = BlockingScheduler()

    async def job():
        await run_once(notify=True)

    def sync_job():
        asyncio.run(job())

    scheduler.add_job(sync_job, "cron", hour=8, minute=0)
    print("⏰ Планувальник запущено — MCI щодня о 08:00")
    print("   Ctrl+C для зупинки")

    # Run once immediately
    asyncio.run(run_once(notify=True))

    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("\n🛑 Планувальник зупинено")


def main():
    parser = argparse.ArgumentParser(description="MCI — Market Conditions Index")
    parser.add_argument("--notify", action="store_true", help="Send result to Telegram")
    parser.add_argument("--schedule", action="store_true", help="Run daily at 08:00")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.schedule:
        run_scheduled()
    else:
        asyncio.run(run_once(notify=args.notify, as_json=args.json))


if __name__ == "__main__":
    main()
