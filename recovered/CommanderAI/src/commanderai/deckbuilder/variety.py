"""Seeded randomness helpers for deck variety.

All variety is opt-in: callers pass ``variety > 0`` and/or a seed. When variety
is 0 the deterministic top-N behaviour is preserved exactly, so default builds
are unchanged and reproducible.
"""

import math
import random
from typing import Sequence, TypeVar

T = TypeVar("T")


def make_rng(seed: int | None) -> random.Random:
    """Create a deterministic RNG. ``None`` seeds from system entropy."""
    return random.Random(seed)


def resolve_seed(seed: int | None) -> int:
    """Return the seed to use, generating a random one when none is given."""
    if seed is not None:
        return seed
    return random.SystemRandom().randint(0, 2**31 - 1)


def weighted_sample_without_replacement(
    rng: random.Random,
    items: Sequence[T],
    weights: Sequence[float],
    k: int,
) -> list[T]:
    """Sample ``k`` distinct items with probability proportional to weight.

    Uses the Efraimidis-Spirakis A-Res algorithm: key = u**(1/w), keep the
    largest keys. Items with non-positive weight get a tiny floor so they can
    still appear (rarely) rather than crashing.
    """
    if k >= len(items):
        return list(items)
    keyed: list[tuple[float, int]] = []
    for i, w in enumerate(weights):
        w = w if w > 0 else 1e-12
        u = rng.random() or 1e-12
        keyed.append((u ** (1.0 / w), i))
    keyed.sort(reverse=True)
    return [items[i] for _, i in keyed[:k]]


def softmax_weights(scores: Sequence[float], variety: float) -> list[float]:
    """Turn scores into sampling weights controlled by ``variety`` (0..1].

    Lower variety sharpens the distribution toward the top scorers; higher
    variety flattens it so more of the (already strong) candidate pool can be
    chosen. Robust to negative scores and arbitrary score scales.
    """
    if not scores:
        return []
    hi = max(scores)
    lo = min(scores)
    spread = (hi - lo) or 1.0
    # temperature grows with variety; small floor keeps it well-defined.
    tau = spread * max(variety, 1e-6)
    return [math.exp((s - hi) / tau) for s in scores]
