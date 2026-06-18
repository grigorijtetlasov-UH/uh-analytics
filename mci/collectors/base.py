"""Base collector interface."""

from abc import ABC, abstractmethod
import aiohttp
import sys
from pathlib import Path

# Handle imports both when running as package and standalone
try:
    from mci.models import SubIndexResult
except ModuleNotFoundError:
    # If mci package not found, try relative import
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from models import SubIndexResult
    except ModuleNotFoundError:
        # Fallback: create a dummy SubIndexResult
        from dataclasses import dataclass

        @dataclass
        class SubIndexResult:
            """Dummy SubIndexResult for standalone mode."""
            score: float
            weight: float
            signals: list[str] = None
            extra_data: dict = None

            def __post_init__(self):
                if self.signals is None:
                    self.signals = []
                if self.extra_data is None:
                    self.extra_data = {}


class BaseCollector(ABC):
    """All collectors inherit from this."""

    name: str = "base"
    weight: float = 0.0

    async def fetch_json(self, url: str, **kwargs) -> dict | list | None:
        """Helper: async GET → JSON."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
        except Exception as e:
            print(f"[{self.name}] fetch error {url}: {e}")
        return None

    async def fetch_text(self, url: str, **kwargs) -> str | None:
        """Helper: async GET → text."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            print(f"[{self.name}] fetch error {url}: {e}")
        return None

    @abstractmethod
    async def collect(self) -> SubIndexResult:
        """Collect data and return a scored SubIndexResult (0-100)."""
        ...

    def _result(self, score: float, signals: list[str], details: dict | None = None) -> SubIndexResult:
        score = max(0.0, min(100.0, score))
        return SubIndexResult(
            name=self.name,
            score=score,
            weight=self.weight,
            signals=signals,
            details=details or {},
        )
