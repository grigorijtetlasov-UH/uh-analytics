"""MCI calculation engine — collects all sub-indexes and computes composite score.

NewsField collector has weight=0 because it's a "meta-collector":
its score modifies security and social sub-indexes rather than
being a standalone component.
"""

import asyncio
from datetime import datetime

from mci.config import get_mci_label
from mci.models import MCIResult, SubIndexResult
from mci.collectors import ALL_COLLECTORS


# How much newsfield affects other sub-indexes (0-1)
NEWSFIELD_BLEND = 0.35


async def calculate_mci() -> MCIResult:
    """Run all collectors in parallel and compute weighted MCI score."""

    collectors = [cls() for cls in ALL_COLLECTORS]

    # Run all collectors concurrently
    tasks = [collector.collect() for collector in collectors]
    results: list[SubIndexResult] = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out errors
    valid_results = []
    newsfield_result = None

    for r in results:
        if isinstance(r, SubIndexResult):
            if r.name == "newsfield":
                newsfield_result = r
            valid_results.append(r)
        else:
            print(f"[engine] collector error: {r}")

    # --- Blend newsfield into security & social ---
    if newsfield_result:
        nf_score = newsfield_result.score
        for r in valid_results:
            if r.name in ("security", "social"):
                old = r.score
                r.score = r.score * (1 - NEWSFIELD_BLEND) + nf_score * NEWSFIELD_BLEND
                r.score = max(0.0, min(100.0, r.score))
                if abs(old - r.score) > 2:
                    direction = "↓" if r.score < old else "↑"
                    r.signals.append(
                        f"📡 Інфополе {direction} скориговано: {old:.0f} → {r.score:.0f}"
                    )

    # Compute weighted score (only collectors with weight > 0)
    weighted_results = [r for r in valid_results if r.weight > 0]
    if weighted_results:
        total_weight = sum(r.weight for r in weighted_results)
        if total_weight > 0:
            raw_score = sum(r.weighted_score for r in weighted_results) / total_weight
        else:
            raw_score = 50.0
    else:
        raw_score = 50.0

    # Clamp to 0-100
    score = max(0.0, min(100.0, raw_score))

    label, advice = get_mci_label(score)

    return MCIResult(
        score=score,
        label=label,
        advice=advice,
        sub_indexes=valid_results,
        timestamp=datetime.now(),
    )
