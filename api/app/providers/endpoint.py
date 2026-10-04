"""A model the adapters can call: everything a configured model resolves to,
the key in the clear included — so it lives only in memory, for one call."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.model_configs import Adapter, Dialect


@dataclass(frozen=True)
class Endpoint:
    adapter: Adapter
    model: str
    dialect: Dialect
    # None: the provider's own API.
    base_url: str | None
    api_key: str | None = field(repr=False)
    # Generous on purpose: hitting the cap cuts a reply mid-thought, and it is
    # only spent when used.
    max_tokens: int = 32_000

    @property
    def source(self) -> str:
        """Who produced a turn — the only model its raw record is replayed to."""
        return f"{self.adapter}:{self.model}"
