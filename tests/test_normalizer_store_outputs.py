import json

from jobcompass.models import (
    Company,
    DiscoveredCompany,
    ExclusionAction,
    ExclusionResult,
    ItClass,
    Location,
    RawCompany,
    SizeClass,
)
from jobcompass.normalizer import normalize
from jobcompass.outputs import export_interchange, write_outputs
from jobcompass.store import Store, dedup_key


def test_normalize_size_class_mapping():
    raw = RawCompany(source="T", country="IT", fields={
        "name": "BigCo", "employees": 6000, "registry_ids": {"vat": "IT123"},
        "sector_codes": ["62"], "locations": [{"address": "Milano", "country": "IT"}]})
    c = normalize(raw)
    assert c.size_class == SizeClass.MULTINATIONAL
    assert c.name == "BigCo"
    assert c.locations[0].address == "Milano"


def test_normalize_missing_employees_is_unknown():
    raw = RawCompany(source="T", country="CH", fields={"name": "X"})
    c = normalize(raw)
    assert c.size_class == SizeClass.UNKNOWN
    assert c.employees_approx is None


def _company(**kw):
    base = dict(id="c1", name="Acme", country="IT",
                registry_ids={"vat": "IT1"}, size_class=SizeClass.LARGE,
                sector_codes=["62"])
    base.update(kw)
    return Company(**base)


def test_store_dedup_and_excluded(tmp_path):
    store = Store(str(tmp_path / "c.db"))
    c = _company()
    assert store.upsert(c) == "new"
    assert store.upsert(_company()) == "unchanged"
    changed = _company(employees_approx="3000")
    assert store.upsert(changed) == "updated"

    excl = _company(id="c2", name="Startup", registry_ids={"vat": "IT2"})
    store.record_excluded(excl, ExclusionResult(ExclusionAction.EXCLUDE, "startup", "startup"))
    rows = store.conn.execute("SELECT * FROM excluded_companies").fetchall()
    assert len(rows) == 1
    assert rows[0]["rule"] == "startup"
    store.close()


def test_dedup_key_stable():
    assert dedup_key(_company()) == dedup_key(_company(name="Acme Renamed"))


def test_outputs_separate_native_and_adjacent(tmp_path):
    native = DiscoveredCompany(company=_company(
        it_class=ItClass.IT_NATIVE,
        locations=[Location(address="Milano", country="IT", lat=45.46, lon=9.19)]))
    adjacent = DiscoveredCompany(company=_company(
        id="c3", name="ENI", registry_ids={"vat": "IT3"}, it_class=ItClass.IT_ADJACENT,
        it_signal="board ATS attivo",
        locations=[Location(address="Roma", country="IT", lat=41.9, lon=12.5)]))
    paths = write_outputs([native, adjacent], str(tmp_path / "out"))

    native_geo = json.loads(open(paths["it_native_geojson"], encoding="utf-8").read())
    adj_geo = json.loads(open(paths["it_adjacent_geojson"], encoding="utf-8").read())
    assert len(native_geo["features"]) == 1
    assert native_geo["features"][0]["properties"]["name"] == "Acme"
    assert adj_geo["features"][0]["properties"]["it_signal"] == "board ATS attivo"
    # HTML statico offline: Leaflet locale + circleMarker, geojson inline, no CDN.
    html = open(paths["it_native_html"], encoding="utf-8").read()
    assert "vendor/leaflet.js" in html
    assert "circleMarker" in html
    assert "https://unpkg.com" not in html  # nessun CDN esterno


def test_location_without_coords_skipped_in_geojson(tmp_path):
    d = DiscoveredCompany(company=_company(
        locations=[Location(address="Nowhere", country="IT")]))  # no lat/lon
    paths = write_outputs([d], str(tmp_path / "out"))
    geo = json.loads(open(paths["it_native_geojson"], encoding="utf-8").read())
    assert geo["features"] == []


def test_interchange_export(tmp_path):
    d = DiscoveredCompany(company=_company(domains=["acme.com"], ats_slug="acme"))
    path = export_interchange([d], str(tmp_path / "out"))
    data = json.loads(open(path, encoding="utf-8").read())
    assert data[0]["ats_slug"] == "acme"
    assert data[0]["domains"] == ["acme.com"]
