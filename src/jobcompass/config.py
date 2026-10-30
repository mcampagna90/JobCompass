"""Configuration (Requirement 10.1). Free by default; paid providers disabled."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# NACE/national codes for the native IT sector (Requirement 1.2): 62 software
# development/IT consulting, 63 information services.
DEFAULT_IT_SECTOR_PREFIXES: list[str] = ["62", "63", "J62", "J63"]

# Blocklisted sectors (Requirement 3.4): tobacco (C12) and gambling (R92/92).
DEFAULT_BLOCKLIST_SECTOR_PREFIXES: list[str] = ["12", "C12", "92", "R92", "920"]

# Consulting/staffing exclusions, multilingual (Requirement 3.3).
DEFAULT_EXCLUSION_KEYWORDS: list[str] = [
    "consulting", "consultancy", "consulenza", "conseil", "beratung",
    "body rental", "staff augmentation", "staffing", "somministrazione",
    "interim", "outsourcing", "recruitment agency", "agenzia per il lavoro",
]

# Finance excluded from it_adjacent for now (fintech/trading) (Requirement 5b.5).
DEFAULT_FINANCE_EXCLUDE_KEYWORDS: list[str] = [
    "fintech", "trading", "proprietary trading", "crypto exchange",
    "hedge fund", "market maker",
]

# Startup signals to exclude (Requirement 3.2).
DEFAULT_STARTUP_SIGNALS: list[str] = [
    "early stage", "seed", "series a", "pre-seed", "startup", "newly founded",
]


@dataclass
class FiltersConfig:
    size_threshold: int = 250  # exclude below threshold (Requirement 3.1)
    exclusion_keywords: list[str] = field(
        default_factory=lambda: list(DEFAULT_EXCLUSION_KEYWORDS)
    )
    startup_signals: list[str] = field(
        default_factory=lambda: list(DEFAULT_STARTUP_SIGNALS)
    )
    blocklist_sector_prefixes: list[str] = field(
        default_factory=lambda: list(DEFAULT_BLOCKLIST_SECTOR_PREFIXES)
    )


@dataclass
class ItAdjacentConfig:
    # it_adjacent allowed only for large/multinational firms (Requirement 5b.4).
    allowed_size_classes: list[str] = field(
        default_factory=lambda: ["large", "multinational"]
    )
    finance_exclude_keywords: list[str] = field(
        default_factory=lambda: list(DEFAULT_FINANCE_EXCLUDE_KEYWORDS)
    )


@dataclass
class OutputConfig:
    output_dir: str = "output"
    cluster: bool = True


@dataclass
class Config:
    sources: list[dict[str, Any]] = field(default_factory=list)
    it_sector_prefixes: list[str] = field(
        default_factory=lambda: list(DEFAULT_IT_SECTOR_PREFIXES)
    )
    filters: FiltersConfig = field(default_factory=FiltersConfig)
    it_adjacent: ItAdjacentConfig = field(default_factory=ItAdjacentConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    db_path: str = "companies.db"
    user_agent: str = "jobcompass/0.1 (+personal-use; respects robots.txt)"
    request_timeout: int = 20
    rate_limit_seconds: float = 1.0
    max_retries: int = 3


def _env_expand(value: Any) -> Any:
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def load_config(path: str | os.PathLike | None = None) -> Config:
    cfg = Config()
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        return cfg
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    if "sources" in data:
        cfg.sources = [
            {k: _env_expand(v) for k, v in src.items()} for src in data["sources"]
        ]
    if "sectors" in data and "it_prefixes" in data["sectors"]:
        cfg.it_sector_prefixes = list(data["sectors"]["it_prefixes"])
    if "filters" in data:
        f = data["filters"]
        cfg.filters.size_threshold = int(f.get("size_threshold", 250))
        if "exclusion_keywords" in f:
            cfg.filters.exclusion_keywords = list(f["exclusion_keywords"])
        if "startup_signals" in f:
            cfg.filters.startup_signals = list(f["startup_signals"])
        if "blocklist_sector_prefixes" in f:
            cfg.filters.blocklist_sector_prefixes = list(f["blocklist_sector_prefixes"])
    if "it_adjacent" in data:
        a = data["it_adjacent"]
        if "allowed_size_classes" in a:
            cfg.it_adjacent.allowed_size_classes = list(a["allowed_size_classes"])
        if "finance_exclude_keywords" in a:
            cfg.it_adjacent.finance_exclude_keywords = list(a["finance_exclude_keywords"])
    if "output" in data:
        o = data["output"]
        cfg.output.output_dir = o.get("output_dir", cfg.output.output_dir)
        cfg.output.cluster = bool(o.get("cluster", True))
    if "db_path" in data:
        cfg.db_path = data["db_path"]
    for key in ("user_agent", "request_timeout", "rate_limit_seconds", "max_retries"):
        if key in data:
            setattr(cfg, key, data[key])

    return cfg
