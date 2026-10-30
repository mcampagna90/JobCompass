"""Discoverers e pipeline senza rete: client HTTP fake / collector monkeypatched."""

import json

from jobcompass import pipeline
from jobcompass.config import Config
from jobcompass.discoverers import discover
from jobcompass.models import RawCompany


class FakeClient:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, params=None, headers=None, check_robots=True):
        for key, text in self.responses.items():
            if key in url:
                return text
        raise AssertionError(f"URL inatteso: {url}")


def test_disabled_source_no_call():
    # Fonte spenta → nessuna chiamata, lista vuota (anche senza client).
    assert discover({"country": "IT", "enabled": False}, FakeClient({})) == []


def test_commercial_source_without_token_no_call():
    # Provider a pagamento abilitato ma senza token → nessuna chiamata.
    src = {"country": "IT", "type": "commercial", "enabled": True,
           "endpoints": {"search": "https://company.openapi.com/IT-search"},
           "credentials_env": ""}
    assert discover(src, FakeClient({})) == []


# NB: il parsing SIRENE è coperto in test_sirene_discoverer.py (nuovo schema a chiave API).


def test_full_pipeline(tmp_path, monkeypatch):
    cfg = Config()
    cfg.db_path = str(tmp_path / "p.db")
    cfg.output.output_dir = str(tmp_path / "out")
    cfg.sources = [{"name": "Fake", "country": "FR", "enabled": True}]

    def fake_discover(source, client):
        return [
            # IT-native grande → tenuta.
            RawCompany(source="Fake", country="FR", fields={
                "name": "TechNative", "registry_ids": {"siren": "1"},
                "sector_codes": ["62"], "employees": 3000,
                "locations": [{"address": "Paris", "country": "FR",
                               "lat": 48.85, "lon": 2.35}]}),
            # Piccola → esclusa.
            RawCompany(source="Fake", country="FR", fields={
                "name": "SmallCo", "registry_ids": {"siren": "2"},
                "sector_codes": ["62"], "employees": 10}),
            # Non-IT grande con ATS → it_adjacent tenuta.
            RawCompany(source="Fake", country="FR", fields={
                "name": "EnergyCorp", "registry_ids": {"siren": "3"},
                "sector_codes": ["35"], "employees": 8000, "ats_slug": "energycorp",
                "locations": [{"address": "Lyon", "country": "FR",
                               "lat": 45.76, "lon": 4.83}]}),
        ]

    monkeypatch.setattr(pipeline.discoverers, "discover", fake_discover)
    # Disattiva il geocoding reale.
    monkeypatch.setattr(pipeline.Geocoder, "geocode", lambda self, loc: loc)

    stats = pipeline.run(cfg)
    assert stats["found"] == 3
    assert stats["excluded"] == 1   # SmallCo
    assert stats["new"] == 2        # TechNative + EnergyCorp

    native = json.loads(open(stats["outputs"]["it_native_geojson"], encoding="utf-8").read())
    adjacent = json.loads(open(stats["outputs"]["it_adjacent_geojson"], encoding="utf-8").read())
    assert native["features"][0]["properties"]["name"] == "TechNative"
    assert adjacent["features"][0]["properties"]["name"] == "EnergyCorp"
