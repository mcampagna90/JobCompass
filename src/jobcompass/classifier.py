"""IT classification: it_native vs it_adjacent (Requirement 5b) and size (Req. 2)."""

from __future__ import annotations

from .config import Config, ItAdjacentConfig
from .models import Company, ExclusionAction, ExclusionResult, ItClass, SizeClass


def is_it_native(company: Company, it_prefixes: list[str]) -> bool:
    """True if at least one sector code is IT (NACE 62/63)."""
    for code in company.sector_codes:
        for prefix in it_prefixes:
            if code.upper().startswith(prefix.upper()):
                return True
    return False


def has_strong_it_signal(company: Company) -> str | None:
    """Strong signal of internal IT (Requirement 5b.2): active ATS or division.

    Returns a description of the signal, or None. Generic language does not count.
    """
    if company.ats_slug:
        return f"active ATS board (slug: {company.ats_slug})"
    summary = (company.business_summary or "").lower()
    # Verifiable digital division/entity: requires an explicit reference.
    for marker in ("digital hub", "technology center", "it division",
                   "digital division", "tech subsidiary"):
        if marker in summary:
            return f"digital division: {marker}"
    return None


def classify_it(company: Company, cfg: Config) -> ExclusionResult:
    """Assign it_class. Returns an ExclusionResult if the company must be excluded.

    it_adjacent companies are allowed only if large/multinational and not
    fintech/trading.
    """
    if is_it_native(company, cfg.it_sector_prefixes):
        company.it_class = ItClass.IT_NATIVE
        company.it_signal = None
        return ExclusionResult(ExclusionAction.KEEP)

    # Not IT by sector -> it_adjacent candidate only with a strong signal.
    signal = has_strong_it_signal(company)
    if signal is None:
        return ExclusionResult(ExclusionAction.EXCLUDE,
                               "non-IT without a strong IT signal", "no_it_signal")

    # Finance excluded for now (fintech/trading).
    text = " ".join([company.name or "", company.business_summary or ""]).lower()
    fin = [k for k in cfg.it_adjacent.finance_exclude_keywords if k.lower() in text]
    if fin:
        return ExclusionResult(ExclusionAction.EXCLUDE,
                               "fintech/trading excluded: " + ", ".join(sorted(set(fin))),
                               "fintech_trading")

    # Large/multinational only.
    if company.size_class.value not in cfg.it_adjacent.allowed_size_classes:
        return ExclusionResult(
            ExclusionAction.EXCLUDE,
            f"it_adjacent not large/multinational ({company.size_class.value})",
            "it_adjacent_too_small",
        )

    company.it_class = ItClass.IT_ADJACENT
    company.it_signal = signal
    return ExclusionResult(ExclusionAction.KEEP)
