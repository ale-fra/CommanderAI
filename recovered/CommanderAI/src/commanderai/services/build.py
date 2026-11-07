"""Deck building use-case: ``build_deck(ctx, BuildRequest) -> BuildResult``.

The pipeline (each step a small function operating on ``_BuildState``):

 1. resolve options      theme / colors / variety / role quotas
 2. load collection      file check → catalog → parse → match
 3. choose commanders    explicit, or auto-pick by theme/colors (+ partner)
 4. candidates           color-identity filter, role classification, scoring
 5. budget filter        drop cards priced above the whole budget
 6. bracket filter       Commander Spellbook exclusions / prioritisation
 7. feasibility          warn (or fail) when the pool is too thin
 8. pick non-lands       heuristic, or Claude with heuristic fallback
 9. backfill             top up short picks; pad with extra lands if needed
10. upgrade swaps        swap in owned cards the LLM recommended
11. mana base            nonbasic priority + basics by pip ratio
12. budget enforcement   greedy swaps down to the budget
13. validation           deck-construction rules

Every user-facing message goes through ``ctx.reporter`` (see
:mod:`commanderai.reporting`); structured details are also returned on the
``BuildResult``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from commanderai.config import DEFAULT_LAND_COUNT, SLOT_QUOTAS
from commanderai.deckbuilder.budget import (
    commanders_price,
    enforce_budget,
    filter_candidates_by_budget,
)
from commanderai.deckbuilder.candidates import build_candidates, heuristic_pick
from commanderai.deckbuilder.colors import color_name, format_colors, wubrg_sort
from commanderai.deckbuilder.llm_picker import llm_build
from commanderai.deckbuilder.mana_base import build_mana_base
from commanderai.deckbuilder.partner import can_partner, combined_identity, partner_ability
from commanderai.deckbuilder.rules import is_legal_commander, validate_deck
from commanderai.deckbuilder.slots import classify_card
from commanderai.deckbuilder.themes import apply_theme_quotas
from commanderai.errors import (
    CardNotFoundError,
    CollectionTooSmallError,
    IllegalCommanderError,
    IllegalPartnerError,
    InsufficientCardsError,
    InvalidRequestError,
    NoMatchingCommanderError,
)
from commanderai.models import Card, Deck, DeckPick, DeckSlot, PublicModel, ScoredCard
from commanderai.reporting import Notice
from commanderai.services.collection import (
    LoadedCollection,
    MatchReport,
    load_collection,
    resolve_collection_source,
)
from commanderai.services.commanders import auto_select_commander, auto_select_partner
from commanderai.services.common import (
    VarietySetup,
    resolve_colors_or_raise,
    resolve_theme_or_raise,
    setup_variety,
)
from commanderai.services.context import ServiceContext
from commanderai.services.library import prior_card_lists

# A collection smaller than this can't produce anything resembling a deck.
MIN_COLLECTION_CARDS = 20
# Below this many candidates the build is aborted rather than padded.
MIN_VIABLE_CANDIDATES = 30


# ---------------------------------------------------------------------------
# Request / result models
# ---------------------------------------------------------------------------

class BuildRequest(BaseModel):
    """Everything that drives a build. Mirrors the CLI ``build`` options."""

    collection: Path | None = None          # collection file (None → settings default)
    collection_text: str | None = None      # …or the raw text of a collection
    collection_id: int | None = None        # …or a collection stored in the database
    collection_label: str | None = None     # how to name the collection in reports
    commander: str | None = None            # omit to auto-pick from theme/colors
    partner: str | None = None
    theme: str | None = None
    colors: str | None = None
    lands: int = Field(DEFAULT_LAND_COUNT, ge=0, le=99)
    variety: float = Field(0.0, ge=0.0, le=1.0)
    seed: int | None = None
    budget: float | None = Field(None, ge=0)
    bracket: int | None = Field(None, ge=1, le=5)
    use_llm: bool = False
    verbose: bool = False                   # report per-card unmatched details


class AutoPickInfo(PublicModel):
    commander_auto: bool = False
    support: int | None = None              # on-theme / supporting cards for the auto-pick
    theme_fit: int | None = None
    partner_auto: bool = False


class BudgetReport(PublicModel):
    budget: float
    commanders_price: float = 0.0           # part of the budget taken by the commander(s)
    removed_over_budget: int = 0            # candidates dropped up front
    swaps: int = 0                          # greedy swaps after assembly
    final_price: float = 0.0
    met: bool = True


class ExcludedCard(PublicModel):
    name: str
    reason: str


class ExcludedCombo(PublicModel):
    cards: list[str]
    reason: str


class BracketReport(PublicModel):
    bracket: int
    mode: str = "online"                    # online (Commander Spellbook) | offline (local rules)
    offline_reason: str | None = None
    excluded_cards: list[ExcludedCard] = Field(default_factory=list)
    excluded_combos: list[ExcludedCombo] = Field(default_factory=list)
    prioritized: list[str] = Field(default_factory=list)
    remaining_candidates: int = 0


class BuildResult(BaseModel):
    request: BuildRequest
    deck: Deck
    theme: str | None = None                 # canonical theme key
    color_filter: list[str] | None = None    # WUBRG-ordered letters
    variety: float = 0.0                     # effective variety
    seed: int | None = None                  # seed actually used (None = deterministic)
    lands: int                               # final land count (may exceed the request)
    quotas: dict[str, int]
    quota_changes: dict[str, tuple[int, int]] = Field(default_factory=dict)
    autopick: AutoPickInfo = Field(default_factory=AutoPickInfo)
    match: MatchReport
    candidate_count: int = 0
    budget: BudgetReport | None = None
    bracket: BracketReport | None = None
    llm_used: bool = False
    llm_error: str | None = None
    backfilled: int = 0
    shortfall: int = 0
    upgrade_swaps: int = 0
    validation_errors: list[str] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

@dataclass
class _BuildState:
    req: BuildRequest
    theme: str | None = None
    color_filter: set[str] | None = None
    var: VarietySetup | None = None
    synergy_emphasis: float = 1.0
    rank_emphasis: float = 1.0
    quotas: dict[str, int] = field(default_factory=dict)
    lands: int = DEFAULT_LAND_COUNT

    loaded: LoadedCollection | None = None
    collection_cards: list[Card] = field(default_factory=list)
    owned_names: set[str] = field(default_factory=set)

    commander: Card | None = None
    partner: Card | None = None
    autopick: AutoPickInfo = field(default_factory=AutoPickInfo)

    candidates: dict[DeckSlot, list[ScoredCard]] = field(default_factory=dict)
    total_candidates: int = 0
    budget_report: BudgetReport | None = None
    bracket_report: BracketReport | None = None
    bracket_excluded_names: set[str] = field(default_factory=set)
    extra_instructions: str = ""

    deck_picks: list[DeckPick] = field(default_factory=list)
    strategy: str = ""
    upgrades: list[str] = field(default_factory=list)
    llm_used: bool = False
    llm_error: str | None = None
    backfilled: int = 0
    shortfall: int = 0
    upgrade_swaps: int = 0
    all_picks: list[DeckPick] = field(default_factory=list)

    @property
    def rng(self) -> random.Random | None:
        return self.var.rng if self.var else None

    @property
    def variety(self) -> float:
        return self.var.variety if self.var else 0.0

    @property
    def others(self) -> int:
        """Non-commander cards in the deck: 99, or 98 with a partner."""
        return 99 if self.partner is None else 98

    @property
    def num_commanders(self) -> int:
        return 100 - self.others


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_deck(ctx: ServiceContext, req: BuildRequest) -> BuildResult:
    """Build a Commander deck from a collection. See module docstring."""
    st = _BuildState(req=req, lands=req.lands)
    _resolve_options(ctx, st)
    _load_owned_cards(ctx, st)
    _choose_commanders(ctx, st)
    _build_candidate_pool(ctx, st)
    _apply_budget_filter(ctx, st)
    _apply_bracket(ctx, st)
    _check_feasibility(ctx, st)
    _pick_nonlands(ctx, st)
    _backfill(ctx, st)
    _swap_in_owned_upgrades(ctx, st)
    _add_mana_base(ctx, st)
    _enforce_budget(ctx, st)
    deck, errors = _assemble_and_validate(ctx, st)

    return BuildResult(
        request=req,
        deck=deck,
        theme=st.theme,
        color_filter=wubrg_sort(st.color_filter) if st.color_filter is not None else None,
        variety=st.variety,
        seed=st.var.seed if st.var else None,
        lands=st.lands,
        quotas=st.quotas,
        quota_changes={
            s: (SLOT_QUOTAS[s], st.quotas[s])
            for s in SLOT_QUOTAS
            if s != "LAND" and st.quotas.get(s) != SLOT_QUOTAS.get(s)
        },
        autopick=st.autopick,
        match=st.loaded.report,
        candidate_count=st.total_candidates,
        budget=st.budget_report,
        bracket=st.bracket_report,
        llm_used=st.llm_used,
        llm_error=st.llm_error,
        backfilled=st.backfilled,
        shortfall=st.shortfall,
        upgrade_swaps=st.upgrade_swaps,
        validation_errors=errors,
        notices=list(ctx.reporter.notices),
    )


# ---------------------------------------------------------------------------
# Steps
# ---------------------------------------------------------------------------

def _resolve_options(ctx: ServiceContext, st: _BuildState) -> None:
    req = st.req
    st.theme = resolve_theme_or_raise(req.theme)
    st.color_filter = resolve_colors_or_raise(req.colors)

    if not req.commander and not st.theme and st.color_filter is None:
        raise InvalidRequestError(
            "Specify --commander, or --theme/--colors to auto-pick a commander."
        )
    if req.partner and not req.commander:
        raise InvalidRequestError("--partner requires --commander.")

    st.var = setup_variety(req.variety, req.seed, ctx.reporter)
    if st.variety > 0:
        st.synergy_emphasis = 1.0 + st.variety
        st.rank_emphasis = 1.0 - 0.4 * st.variety
    st.quotas = apply_theme_quotas(SLOT_QUOTAS, st.theme)


def _load_owned_cards(ctx: ServiceContext, st: _BuildState) -> None:
    req = st.req
    source, label = resolve_collection_source(ctx, req.collection, req.collection_text, req.collection_id)
    label = req.collection_label or label
    loaded = load_collection(
        ctx, source, empty_message="Error: No cards found in collection file", label=label
    )
    st.loaded = loaded
    match = loaded.match
    rep = ctx.reporter

    skipped = len(match.skipped_tokens)
    unmatched = len(match.unmatched)
    parts = [f"Matched {len(match.matched)} cards"]
    if skipped:
        parts.append(f"{skipped} tokens/special skipped")
    if unmatched:
        parts.append(f"{unmatched} unmatched")
    rep.success(
        "collection.matched", " | ".join(parts),
        matched=len(match.matched), skipped=skipped, unmatched=unmatched,
    )

    for original, corrected in match.fuzzy_matched[:5]:
        rep.warning(
            "collection.fuzzy", f"'{original}' → '{corrected}'",
            original=original, corrected=corrected,
        )
    if match.unmatched and req.verbose:
        for name in match.unmatched[:10]:
            rep.error("collection.unmatched", f"'{name}' not found", name=name)

    st.collection_cards = loaded.cards
    st.owned_names = {c.name for c in st.collection_cards}

    if len(st.collection_cards) < MIN_COLLECTION_CARDS:
        raise CollectionTooSmallError(
            f"Collection too small ({len(st.collection_cards)} cards). "
            f"Need at least ~60+ cards in commander's colors to build a playable deck.",
            cards=len(st.collection_cards),
        )


def _choose_commanders(ctx: ServiceContext, st: _BuildState) -> None:
    req = st.req
    rep = ctx.reporter
    index = ctx.catalog()

    if req.commander:
        commander = index.get(req.commander)
        if not commander:
            raise CardNotFoundError(f"Commander '{req.commander}' not found", name=req.commander)
        if not is_legal_commander(commander):
            raise IllegalCommanderError(
                f"'{commander.name}' is not a legal commander", name=commander.name
            )
    else:
        picked = auto_select_commander(
            st.collection_cards, st.theme, st.color_filter, st.rng, st.variety
        )
        if not picked:
            criteria = []
            if st.theme:
                criteria.append(f"theme '{st.theme}'")
            if st.color_filter is not None:
                criteria.append(f"colors {color_name(st.color_filter)}")
            raise NoMatchingCommanderError(
                f"No legal commander in your collection matches "
                f"{' + '.join(criteria) or 'the given filters'}."
            )
        commander, support, fit = picked
        reason = []
        if st.theme:
            reason.append(f"{support} on-theme cards in colors")
            if fit:
                reason.append(f"commander matches theme ({fit})")
        else:
            reason.append(f"{support} supporting cards")
        st.autopick = AutoPickInfo(commander_auto=True, support=support, theme_fit=fit)
        rep.success(
            "commander.auto_selected",
            f"Auto-selected commander: {commander.name} "
            f"[{format_colors(commander.color_identity)}] — {', '.join(reason)}",
            name=commander.name, colors=format_colors(commander.color_identity),
            support=support, theme_fit=fit, reasons=reason,
        )
    st.commander = commander

    # Resolve / auto-pick a partner (second commander).
    partner = None
    if req.partner:
        partner = index.get(req.partner)
        if not partner:
            raise CardNotFoundError(f"Partner '{req.partner}' not found", name=req.partner)
        if not can_partner(commander, partner):
            raise IllegalPartnerError(
                f"'{commander.name}' and '{partner.name}' can't be partners. "
                f"They need matching Partner, Partner with, Friends forever, "
                f"Choose a Background + Background, or Doctor's companion + Doctor.",
                commander=commander.name, partner=partner.name,
            )
    elif not req.commander:
        # Auto-pick mode: if the chosen commander wants a partner, find the best one owned.
        partner = auto_select_partner(
            commander, st.collection_cards, st.theme, st.color_filter, st.rng, st.variety
        )
        if partner:
            st.autopick.partner_auto = True
            rep.success(
                "partner.auto_selected",
                f"Auto-selected partner: {partner.name} [{format_colors(partner.color_identity)}]",
                name=partner.name, colors=format_colors(partner.color_identity),
            )
    else:
        # Explicit commander with no partner: hint if it wants one.
        if partner_ability(commander).can_take_partner:
            rep.detail(
                "partner.tip",
                "Tip: this commander can have a partner — pass --partner "
                "\"Name\" to build a two-commander deck.",
            )
    st.partner = partner

    if partner:
        identity = format_colors(combined_identity(commander, partner))
        rep.info(
            "commander.selected",
            f"Commanders: {commander.name} + {partner.name} [{identity}]",
            commanders=[
                {"name": c.name, "type_line": c.type_line, "oracle_text": c.oracle_text}
                for c in (commander, partner)
            ],
            colors=identity,
        )
    else:
        rep.info(
            "commander.selected",
            f"Commander: {commander.name} — {commander.type_line}",
            commanders=[
                {"name": commander.name, "type_line": commander.type_line,
                 "oracle_text": commander.oracle_text}
            ],
            colors=format_colors(commander.color_identity),
        )


def _build_candidate_pool(ctx: ServiceContext, st: _BuildState) -> None:
    rep = ctx.reporter
    with rep.progress("Analyzing candidates..."):
        st.candidates = build_candidates(
            st.collection_cards, st.commander,
            theme=st.theme, synergy_emphasis=st.synergy_emphasis,
            rank_emphasis=st.rank_emphasis, partner=st.partner, quotas=st.quotas,
        )

    if st.theme:
        rep.detail("theme.active", f"Theme: leaning into '{st.theme}'", theme=st.theme)
        changed = {
            s: f"{SLOT_QUOTAS[s]}→{st.quotas[s]}"
            for s in SLOT_QUOTAS
            if s != "LAND" and st.quotas.get(s) != SLOT_QUOTAS.get(s)
        }
        if changed:
            rep.detail(
                "theme.quotas_adjusted",
                "Role mix adjusted: " + ", ".join(f"{s} {v}" for s, v in changed.items()),
                changes={s: [SLOT_QUOTAS[s], st.quotas[s]] for s in changed},
            )

    st.total_candidates = _count(st.candidates)
    rep.detail(
        "candidates.found",
        f"Found {st.total_candidates} candidate cards across all slots",
        count=st.total_candidates,
    )


def _apply_budget_filter(ctx: ServiceContext, st: _BuildState) -> None:
    """Drop candidates that can never fit: priced above the budget left after the commanders."""
    budget = st.req.budget
    if budget is None:
        return
    fixed = commanders_price(st.commander, st.partner)
    st.budget_report = BudgetReport(budget=budget, commanders_price=round(fixed, 2))
    if fixed > budget:
        ctx.reporter.warning(
            "budget.commanders_exceed",
            f"Budget ${budget:.2f}: the commander(s) alone cost ${fixed:.2f}.",
            budget=budget, commanders_price=fixed,
        )
    st.candidates, removed = filter_candidates_by_budget(st.candidates, max(budget - fixed, 0.0))
    st.budget_report.removed_over_budget = removed
    if removed:
        ctx.reporter.detail(
            "budget.filtered",
            f"Budget ${budget:.2f}: dropped {removed} cards priced above budget",
            budget=budget, removed=removed,
        )
    st.total_candidates = _count(st.candidates)


def _apply_bracket(ctx: ServiceContext, st: _BuildState) -> None:
    bracket = st.req.bracket
    if not (bracket and bracket < 5):
        return
    from commanderai.deckbuilder.bracket import check_bracket

    rep = ctx.reporter
    offline = ctx.settings.offline
    all_candidate_cards = [sc.card for scored in st.candidates.values() for sc in scored]
    source = "offline rules" if offline else "Commander Spellbook"
    with rep.progress(f"Checking bracket {bracket} constraints ({source})..."):
        result = check_bracket(
            st.commander, all_candidate_cards, bracket, partner=st.partner, offline=offline
        )

    if result.mode == "offline":
        rep.warning(
            "bracket.offline",
            f"Bracket {bracket}: {result.offline_reason} — applied offline rules "
            f"(game changers, extra turns, mass land denial); combos not checked.",
            bracket=bracket, reason=result.offline_reason,
        )

    report = BracketReport(
        bracket=bracket,
        mode=result.mode,
        offline_reason=result.offline_reason,
        excluded_cards=[ExcludedCard(name=n, reason=r) for n, r in result.excluded_cards],
        excluded_combos=[ExcludedCombo(cards=c, reason=r) for c, r in result.excluded_combos],
        prioritized=sorted(result.prioritized_names),
    )

    if result.excluded_cards:
        rep.warning(
            "bracket.excluded_cards",
            f"Bracket {bracket} — excluded {len(result.excluded_cards)} cards",
            bracket=bracket,
            cards=[{"name": n, "reason": r} for n, r in result.excluded_cards],
        )
    if result.excluded_combos:
        rep.warning(
            "bracket.excluded_combos",
            f"Excluded {len(result.excluded_combos)} combos",
            combos=[{"cards": c, "reason": r} for c, r in result.excluded_combos],
        )

    for slot in st.candidates:
        st.candidates[slot] = [
            sc for sc in st.candidates[slot] if sc.card.name in result.allowed_names
        ]

    if result.prioritized_names:
        for slot in st.candidates:
            for sc in st.candidates[slot]:
                if sc.card.name in result.prioritized_names:
                    sc.score += 50
            st.candidates[slot].sort(key=lambda sc: sc.score, reverse=True)
        rep.success(
            "bracket.prioritized",
            f"Prioritized {len(result.prioritized_names)} high-value cards within bracket limits",
            count=len(result.prioritized_names),
        )

    # NB: total_candidates intentionally keeps its pre-bracket value (historical
    # behaviour); the post-filter count is reported separately.
    report.remaining_candidates = _count(st.candidates)
    rep.detail(
        "bracket.remaining",
        f"{report.remaining_candidates} candidates remaining after bracket filter",
        count=report.remaining_candidates,
    )
    st.bracket_report = report
    st.bracket_excluded_names = {name for name, _ in result.excluded_cards}

    if bracket <= 2:
        st.extra_instructions = (
            f"IMPORTANT: This deck must be bracket {bracket} (1=most casual, 5=cEDH). "
            f"Do NOT include infinite combos or two-card win conditions. "
            f"No extra turns, no mass land denial. "
            f"Prioritize fun, interactive gameplay over efficiency."
        )
    elif bracket == 3:
        st.extra_instructions = (
            "IMPORTANT: This deck targets bracket 3 (Upgraded). "
            "Up to 3 game changers allowed. One late-game two-card combo OK (mana value 6+). "
            "No chaining extra turns, no mass land denial. "
            "Prioritize strong synergy and high card quality."
        )


def _check_feasibility(ctx: ServiceContext, st: _BuildState) -> None:
    rep = ctx.reporter
    target_nonland = st.others - st.lands
    if st.total_candidates < target_nonland:
        rep.warning(
            "candidates.insufficient",
            f"Warning: Only {st.total_candidates} eligible cards found "
            f"(need {target_nonland} nonland + {st.lands} lands).",
            candidates=st.total_candidates, needed_nonland=target_nonland, lands=st.lands,
        )
        if st.total_candidates < MIN_VIABLE_CANDIDATES:
            colors = "/".join(wubrg_sort(st.commander.color_identity)) or "colorless"
            raise InsufficientCardsError(
                f"Not enough cards in {colors} "
                f"to build a viable deck. Try a commander with more color overlap.",
                candidates=st.total_candidates,
            )
        rep.warning("candidates.underpowered", "Building best possible deck — will be underpowered.")

    if st.req.budget is not None:
        budget_note = (
            f"BUDGET: Keep the total deck price at or under ${st.req.budget:.2f} USD. "
            f"Prefer cheaper cards (prices shown in parentheses) when synergy is similar. "
            f"Lands are added separately, so leave some headroom."
        )
        st.extra_instructions = f"{st.extra_instructions} {budget_note}".strip()


def _heuristic_picks(st: _BuildState, reason: str | None = None) -> list[DeckPick]:
    picked = heuristic_pick(
        st.candidates, st.lands, rng=st.rng, variety=st.variety,
        others=st.others, quotas=st.quotas,
    )
    return [
        DeckPick(card=sc.card, slot=sc.slot, reason=reason if reason is not None else ", ".join(sc.reasons))
        for scored in picked.values()
        for sc in scored
    ]


def _pick_nonlands(ctx: ServiceContext, st: _BuildState) -> None:
    rep = ctx.reporter
    if not st.req.use_llm:
        rep.detail("picks.heuristic", "Using heuristic selection (--no-llm)")
        st.deck_picks = _heuristic_picks(st)
        return

    prior_decks = prior_card_lists(ctx, st.commander.name) if st.variety > 0 else None
    if prior_decks:
        rep.detail(
            "llm.prior_decks",
            f"Found {len(prior_decks)} prior deck(s) — asking Claude to differ",
            count=len(prior_decks),
        )
    with rep.progress("Asking Claude for deck picks..."):
        try:
            if ctx.settings.offline and ctx.settings.has_llm_key:
                raise RuntimeError("offline mode (COMMANDERAI_OFFLINE=1)")
            st.deck_picks, st.strategy, st.upgrades = llm_build(
                st.commander, st.candidates, st.lands,
                extra_instructions=st.extra_instructions, owned_names=st.owned_names,
                rng=st.rng, variety=st.variety, prior_decks=prior_decks,
                partner=st.partner, quotas=st.quotas,
            )
            st.llm_used = True
        except Exception as e:  # noqa: BLE001 — any LLM failure falls back to heuristics
            st.llm_error = str(e)
            rep.warning(
                "llm.failed", f"LLM failed ({e}), falling back to heuristic", error=str(e)
            )
            st.deck_picks = _heuristic_picks(st)
            st.strategy = ""
            st.upgrades = []


def _backfill(ctx: ServiceContext, st: _BuildState) -> None:
    """Top up when the LLM returned fewer picks than needed; pad lands if the pool is short."""
    rep = ctx.reporter
    target_nonland = st.others - st.lands
    if len(st.deck_picks) >= target_nonland:
        return

    deficit = target_nonland - len(st.deck_picks)
    picked_names = {p.card.name for p in st.deck_picks}
    fallback = heuristic_pick(
        st.candidates, st.lands, rng=st.rng, variety=st.variety,
        others=st.others, quotas=st.quotas,
    )
    backfill: list[DeckPick] = []
    for scored in fallback.values():
        for sc in scored:
            if sc.card.name not in picked_names:
                backfill.append(DeckPick(card=sc.card, slot=sc.slot, reason="backfill"))
                picked_names.add(sc.card.name)
    backfill.sort(key=lambda p: p.card.edhrec_rank or 99999)
    st.deck_picks.extend(backfill[:deficit])
    st.backfilled = min(deficit, len(backfill))
    if st.backfilled > 0:
        rep.detail("picks.backfilled", f"Backfilled {st.backfilled} cards", count=st.backfilled)

    if len(st.deck_picks) < target_nonland:
        shortfall = target_nonland - len(st.deck_picks)
        colors = "/".join(wubrg_sort(st.commander.color_identity)) or "colorless"
        rep.warning(
            "deck.shortfall",
            f"Warning: Collection short by {shortfall} cards. "
            f"Deck will have {len(st.deck_picks) + st.num_commanders + st.lands} cards instead of 100. "
            f"Adding {shortfall} extra lands to fill. "
            f"Consider acquiring more cards in {colors}.",
            shortfall=shortfall,
            deck_size=len(st.deck_picks) + st.num_commanders + st.lands,
            colors=colors,
        )
        st.shortfall = shortfall
        st.lands += shortfall


def _swap_in_owned_upgrades(ctx: ServiceContext, st: _BuildState) -> None:
    """If the LLM suggested upgrades we actually own, swap them in.

    Only replaces backfill cards or cards with a strictly worse EDHREC rank.
    """
    if st.upgrades:
        picked_names = {p.card.name.lower() for p in st.deck_picks}
        by_name: dict[str, ScoredCard] = {}
        for slot_list in st.candidates.values():
            for sc in slot_list:
                by_name[sc.card.name.lower()] = sc

        swapped = 0
        for upgrade_name in st.upgrades[:]:
            sc = by_name.get(upgrade_name.lower())
            if not sc or upgrade_name.lower() in picked_names:
                continue

            upgrade_rank = sc.card.edhrec_rank or 99999

            # Prefer replacing backfill cards first
            same_slot = [(i, p) for i, p in enumerate(st.deck_picks) if p.slot == sc.slot]
            backfill_picks = [(i, p) for i, p in same_slot if "backfill" in p.reason]

            if backfill_picks:
                target_idx, target = backfill_picks[0]
            elif same_slot:
                # Only replace if upgrade is strictly better (lower EDHREC rank)
                target_idx, target = max(same_slot, key=lambda x: x[1].card.edhrec_rank or 99999)
                if upgrade_rank >= (target.card.edhrec_rank or 99999):
                    continue
            else:
                continue

            st.deck_picks[target_idx] = DeckPick(
                card=sc.card, slot=sc.slot, reason=f"upgrade swap (replaced {target.card.name})"
            )
            picked_names.add(upgrade_name.lower())
            st.upgrades.remove(upgrade_name)
            swapped += 1

        st.upgrade_swaps = swapped
        if swapped:
            ctx.reporter.success(
                "upgrades.swapped", f"Swapped in {swapped} owned upgrade cards", count=swapped
            )

    # Never suggest buying cards the user already owns.
    owned_lower = {n.lower() for n in st.owned_names}
    st.upgrades = [u for u in st.upgrades if u.lower() not in owned_lower]


def _add_mana_base(ctx: ServiceContext, st: _BuildState) -> None:
    land_cards = [c for c in st.collection_cards if classify_card(c) == DeckSlot.LAND]
    if st.bracket_excluded_names:
        land_cards = [c for c in land_cards if c.name not in st.bracket_excluded_names]
    land_picks = build_mana_base(
        [p.card for p in st.deck_picks], land_cards, st.commander, st.lands,
        rng=st.rng, variety=st.variety, partner=st.partner,
    )
    st.all_picks = st.deck_picks + land_picks


def _enforce_budget(ctx: ServiceContext, st: _BuildState) -> None:
    budget = st.req.budget
    if budget is None:
        return
    rep = ctx.reporter
    st.all_picks, swaps, final_price = enforce_budget(
        st.all_picks, st.candidates, st.commander, budget, partner=st.partner
    )
    report = st.budget_report or BudgetReport(budget=budget)
    report.swaps = swaps
    report.final_price = final_price
    report.met = final_price <= budget
    st.budget_report = report

    if swaps:
        rep.success(
            "budget.swapped", f"Budget: swapped {swaps} cards to fit ${budget:.2f}",
            swaps=swaps, budget=budget,
        )
    if final_price > budget:
        rep.warning(
            "budget.unmet",
            f"Budget: could not reach ${budget:.2f} — best is "
            f"${final_price:.2f} with the available pool. Add cheaper cards "
            f"to your collection or raise --budget.",
            budget=budget, final_price=final_price,
        )
    else:
        rep.success(
            "budget.met", f"Budget: deck fits at ${final_price:.2f} / ${budget:.2f}",
            budget=budget, final_price=final_price,
        )


def _assemble_and_validate(ctx: ServiceContext, st: _BuildState) -> tuple[Deck, list[str]]:
    deck = Deck(
        commander=st.commander,
        partner=st.partner,
        cards=st.all_picks,
        strategy_summary=st.strategy,
        upgrade_suggestions=st.upgrades,
    )
    errors = validate_deck(st.commander, st.all_picks, partner=st.partner)
    if errors:
        ctx.reporter.warning(
            "deck.validation", f"Validation warnings: {len(errors)}", errors=errors
        )
    return deck, errors


def _count(candidates: dict[DeckSlot, list[ScoredCard]]) -> int:
    return sum(len(v) for v in candidates.values() if v)
