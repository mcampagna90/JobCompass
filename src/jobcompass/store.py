"""SQLite persistence and deduplication (Requirement 6). Includes excluded_companies (Req. 3.6)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from .models import Company, ExclusionResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id TEXT PRIMARY KEY,
    dedup_key TEXT UNIQUE,
    name TEXT,
    country TEXT,
    registry_ids TEXT,
    domains TEXT,
    sector_codes TEXT,
    it_class TEXT,
    it_signal TEXT,
    size_class TEXT,
    employees_approx TEXT,
    business_summary TEXT,
    tech_stack TEXT,
    ats_slug TEXT,
    source TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS locations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT REFERENCES companies(id),
    address TEXT,
    region TEXT,
    country TEXT,
    lat REAL,
    lon REAL
);
CREATE TABLE IF NOT EXISTS excluded_companies (
    id TEXT PRIMARY KEY,
    name TEXT,
    country TEXT,
    reason TEXT,
    rule TEXT,
    first_seen TEXT,
    last_seen TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT,
    sources_queried INTEGER,
    found INTEGER,
    excluded INTEGER,
    new INTEGER,
    updated INTEGER,
    duplicates INTEGER
);
CREATE TABLE IF NOT EXISTS company_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id TEXT,
    changed_at TEXT,
    field TEXT,
    old_value TEXT,
    new_value TEXT
);
"""


def dedup_key(company: Company) -> str:
    rid = company.registry_ids or {}
    stable = rid.get("vat") or rid.get("siren") or rid.get("uid") or \
        (company.domains[0] if company.domains else company.name)
    return f"{company.country}|{str(stable).strip().lower()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    _TRACKED = ("name", "size_class", "it_class", "employees_approx", "business_summary")

    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def upsert(self, company: Company) -> str:
        key = dedup_key(company)
        now = _now()
        existing = self.conn.execute(
            "SELECT * FROM companies WHERE dedup_key = ?", (key,)
        ).fetchone()

        new_values = {
            "name": company.name,
            "size_class": company.size_class.value,
            "it_class": company.it_class.value,
            "employees_approx": company.employees_approx,
            "business_summary": company.business_summary,
        }

        if existing is None:
            self._insert(company, key, now)
            state = "new"
        else:
            changed = self._record_changes(existing, new_values, now)
            company.id = existing["id"]
            self._update(company, now)
            state = "updated" if changed else "unchanged"
        self.conn.commit()
        return state

    def _record_changes(self, existing, new_values, now) -> bool:
        changed = False
        for f in self._TRACKED:
            old = existing[f]
            new = new_values[f]
            if (old or None) != (new or None):
                self.conn.execute(
                    "INSERT INTO company_changes (company_id, changed_at, field, old_value, new_value)"
                    " VALUES (?, ?, ?, ?, ?)", (existing["id"], now, f, old, new))
                changed = True
        return changed

    def _row(self, company: Company, key: str) -> dict:
        return {
            "id": company.id,
            "dedup_key": key,
            "name": company.name,
            "country": company.country,
            "registry_ids": json.dumps(company.registry_ids),
            "domains": json.dumps(company.domains),
            "sector_codes": json.dumps(company.sector_codes),
            "it_class": company.it_class.value,
            "it_signal": company.it_signal,
            "size_class": company.size_class.value,
            "employees_approx": company.employees_approx,
            "business_summary": company.business_summary,
            "tech_stack": json.dumps(company.tech_stack),
            "ats_slug": company.ats_slug,
            "source": company.source,
        }

    def _insert(self, company: Company, key: str, now: str) -> None:
        row = self._row(company, key)
        row["first_seen"] = now
        row["last_seen"] = now
        cols = ", ".join(row.keys())
        ph = ", ".join("?" for _ in row)
        self.conn.execute(f"INSERT INTO companies ({cols}) VALUES ({ph})", list(row.values()))
        self._write_locations(company)

    def _update(self, company: Company, now: str) -> None:
        row = self._row(company, dedup_key(company))
        row.pop("id")
        row["last_seen"] = now
        assign = ", ".join(f"{k} = ?" for k in row)
        self.conn.execute(f"UPDATE companies SET {assign} WHERE id = ?",
                          list(row.values()) + [company.id])
        self.conn.execute("DELETE FROM locations WHERE company_id = ?", (company.id,))
        self._write_locations(company)

    def _write_locations(self, company: Company) -> None:
        for loc in company.locations:
            self.conn.execute(
                "INSERT INTO locations (company_id, address, region, country, lat, lon)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (company.id, loc.address, loc.region, loc.country, loc.lat, loc.lon))

    def record_excluded(self, company: Company, result: ExclusionResult) -> None:
        now = _now()
        existing = self.conn.execute(
            "SELECT id FROM excluded_companies WHERE id = ?", (company.id,)).fetchone()
        if existing:
            self.conn.execute(
                "UPDATE excluded_companies SET last_seen = ?, reason = ?, rule = ? WHERE id = ?",
                (now, result.reason, result.rule, company.id))
        else:
            self.conn.execute(
                "INSERT INTO excluded_companies (id, name, country, reason, rule, first_seen, last_seen)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (company.id, company.name, company.country, result.reason, result.rule, now, now))
        self.conn.commit()

    def record_run(self, stats: dict) -> None:
        self.conn.execute(
            "INSERT INTO runs (started_at, sources_queried, found, excluded, new, updated, duplicates)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_now(), stats.get("sources_queried", 0), stats.get("found", 0),
             stats.get("excluded", 0), stats.get("new", 0), stats.get("updated", 0),
             stats.get("duplicates", 0)))
        self.conn.commit()
