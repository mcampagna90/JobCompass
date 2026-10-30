"""Normalizer: RawCompany -> Company (Requirement 4) with size class (Req. 2)."""

from __future__ import annotations

import hashlib

from .models import Company, Location, RawCompany, SizeClass


def _size_class_from_employees(n: int | None) -> SizeClass:
    """Map an employee count to a size class (Requirement 2.1, 2.4).

    No revenue. Missing -> unknown.
    """
    if n is None:
        return SizeClass.UNKNOWN
    if n >= 5000:
        return SizeClass.MULTINATIONAL
    if n >= 1000:
        return SizeClass.LARGE
    if n >= 250:
        return SizeClass.MEDIUM
    return SizeClass.MEDIUM  # below 250 will be dropped by the filters


def _company_id(country: str, registry_ids: dict, name: str) -> str:
    key_src = registry_ids.get("vat") or registry_ids.get("siren") or \
        registry_ids.get("uid") or name
    return hashlib.sha1(f"{country}|{key_src}".encode("utf-8")).hexdigest()[:16]


def _parse_employees(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    digits = "".join(c for c in str(value) if c.isdigit())
    return int(digits) if digits else None


def normalize(raw: RawCompany) -> Company:
    f = raw.fields
    name = f.get("name") or "(unknown)"
    registry_ids = f.get("registry_ids") or {}
    employees = _parse_employees(f.get("employees"))
    size_class = _size_class_from_employees(employees)

    locations = []
    for loc in f.get("locations") or []:
        if isinstance(loc, dict):
            locations.append(Location(
                address=loc.get("address", ""),
                country=loc.get("country", raw.country),
                region=loc.get("region"),
                lat=loc.get("lat"),
                lon=loc.get("lon"),
            ))

    return Company(
        id=_company_id(raw.country, registry_ids, name),
        name=name,
        country=raw.country,
        registry_ids=registry_ids,
        domains=list(f.get("domains") or []),
        sector_codes=list(f.get("sector_codes") or []),
        size_class=size_class,
        employees_approx=f.get("employees_approx") or (str(employees) if employees else None),
        business_summary=f.get("business_summary"),
        tech_stack=list(f.get("tech_stack") or []),
        ats_slug=f.get("ats_slug"),
        locations=locations,
        source=raw.source,
    )
