"""Orchestration (Requirement 10): discovery -> filter -> it_class -> geocode ->
persistence -> output -> export. Logging with counters. No external actions."""

from __future__ import annotations

import logging

from . import classifier, discoverers, filters, normalizer, outputs
from .config import Config
from .geocoder import Geocoder
from .http_client import HttpClient, SourceSkipped
from .models import DiscoveredCompany, ExclusionAction
from .store import Store

logger = logging.getLogger("jobcompass")


def run(cfg: Config) -> dict:
    client = HttpClient(
        user_agent=cfg.user_agent,
        timeout=cfg.request_timeout,
        rate_limit_seconds=cfg.rate_limit_seconds,
        max_retries=cfg.max_retries,
    )
    geocoder = Geocoder(client)
    store = Store(cfg.db_path)
    stats = {"sources_queried": 0, "found": 0, "excluded": 0,
             "new": 0, "updated": 0, "duplicates": 0, "skipped": 0}
    discovered: list[DiscoveredCompany] = []

    try:
        for source in cfg.sources:
            if not source.get("enabled", False):
                continue
            stats["sources_queried"] += 1
            try:
                raws = discoverers.discover(source, client)
            except SourceSkipped as exc:
                stats["skipped"] += 1
                logger.warning("Skipped source '%s': %s", source.get("name"), exc)
                continue
            except Exception as exc:
                stats["skipped"] += 1
                logger.error("Error on source '%s': %s", source.get("name"), exc)
                continue

            for raw in raws:
                stats["found"] += 1
                company = normalizer.normalize(raw)

                excl = filters.classify_exclusion(company, cfg.filters)
                if excl.action == ExclusionAction.EXCLUDE:
                    store.record_excluded(company, excl)
                    stats["excluded"] += 1
                    continue

                it_res = classifier.classify_it(company, cfg)
                if it_res.action == ExclusionAction.EXCLUDE:
                    store.record_excluded(company, it_res)
                    stats["excluded"] += 1
                    continue

                for loc in company.locations:
                    geocoder.geocode(loc)

                state = store.upsert(company)
                if state == "new":
                    stats["new"] += 1
                elif state == "updated":
                    stats["updated"] += 1
                else:
                    stats["duplicates"] += 1
                discovered.append(DiscoveredCompany(company=company, change_state=state))

        store.record_run(stats)
        stats["outputs"] = outputs.write_outputs(discovered, cfg.output.output_dir)
        stats["interchange"] = outputs.export_interchange(discovered, cfg.output.output_dir)
    finally:
        store.close()

    logger.info("Run complete: %s",
                {k: v for k, v in stats.items() if k not in ("outputs", "interchange")})
    return stats
