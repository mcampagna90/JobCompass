"""Normalized data model (Requirement 4) and derived entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SizeClass(str, Enum):
    """Size class (Requirement 2.1). No revenue."""

    MEDIUM = "medium"
    LARGE = "large"
    MULTINATIONAL = "multinational"
    UNKNOWN = "unknown"


class ItClass(str, Enum):
    """IT-native vs IT-adjacent (Requirement 5b.1)."""

    IT_NATIVE = "it_native"
    IT_ADJACENT = "it_adjacent"


class ExclusionAction(str, Enum):
    KEEP = "keep"
    EXCLUDE = "exclude"


@dataclass
class Location:
    """A company office (Requirement 4)."""

    address: str
    country: str
    region: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None


@dataclass
class RawCompany:
    """Raw company produced by a Discoverer, before normalization."""

    source: str
    country: str
    fields: dict = field(default_factory=dict)


@dataclass
class Company:
    """Normalized company (Requirement 4.1)."""

    id: str
    name: str
    country: str
    registry_ids: dict = field(default_factory=dict)
    domains: list[str] = field(default_factory=list)
    sector_codes: list[str] = field(default_factory=list)
    it_class: ItClass = ItClass.IT_NATIVE
    it_signal: Optional[str] = None
    size_class: SizeClass = SizeClass.UNKNOWN
    employees_approx: Optional[str] = None
    business_summary: Optional[str] = None
    tech_stack: list[str] = field(default_factory=list)
    ats_slug: Optional[str] = None
    locations: list[Location] = field(default_factory=list)
    source: str = ""


@dataclass
class ExclusionResult:
    """Result of the exclusion filter (Requirement 3)."""

    action: ExclusionAction
    reason: str = ""
    rule: str = ""


@dataclass
class DiscoveredCompany:
    """Fully processed company, ready for persistence/output."""

    company: Company
    change_state: str = "new"  # new | updated | unchanged
