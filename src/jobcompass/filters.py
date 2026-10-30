"""Exclusion filters (Requirement 3): threshold, startup, consulting, blocklist."""

from __future__ import annotations

from .config import FiltersConfig
from .models import Company, ExclusionAction, ExclusionResult, SizeClass


def _text(company: Company) -> str:
    parts = [company.name or "", company.business_summary or "",
             " ".join(company.sector_codes)]
    return " ".join(parts).lower()


def _employees_count(company: Company) -> int | None:
    """Extract an indicative employee count from the band, if present."""
    if not company.employees_approx:
        return None
    digits = "".join(c for c in company.employees_approx if c.isdigit())
    return int(digits) if digits else None


def classify_exclusion(company: Company, cfg: FiltersConfig) -> ExclusionResult:
    """Decide whether to exclude the company and why (Requirement 3.1-3.5)."""
    text = _text(company)

    # Sector blocklist (tobacco, gambling) via NACE/national prefixes.
    for code in company.sector_codes:
        for prefix in cfg.blocklist_sector_prefixes:
            if code.upper().startswith(prefix.upper()):
                return ExclusionResult(ExclusionAction.EXCLUDE,
                                       f"blocklisted sector ({code})", "blocklist_sector")

    # Consulting/body rental/staffing/outsourcing.
    kw = [k for k in cfg.exclusion_keywords if k.lower() in text]
    if kw:
        return ExclusionResult(ExclusionAction.EXCLUDE,
                               "consulting/staffing: " + ", ".join(sorted(set(kw))),
                               "consulting_staffing")

    # Startup.
    startup = [s for s in cfg.startup_signals if s.lower() in text]
    count = _employees_count(company)
    if startup and (count is None or count < cfg.size_threshold):
        return ExclusionResult(ExclusionAction.EXCLUDE,
                               "startup: " + ", ".join(sorted(set(startup))), "startup")

    # Size threshold: exclude micro/small below threshold.
    if count is not None and count < cfg.size_threshold:
        return ExclusionResult(ExclusionAction.EXCLUDE,
                               f"below size threshold ({count} < {cfg.size_threshold})",
                               "below_threshold")
    if company.size_class == SizeClass.MEDIUM and count is None:
        # medium without a precise headcount: allowed (it_native only, decided later).
        pass

    return ExclusionResult(ExclusionAction.KEEP)
