"""Test del discoverer svizzero (SPARQL) con client HTTP fake: nessuna rete reale."""

import json

from jobcompass.discoverers import _build_zefix_query, discover


class FakeClient:
    def __init__(self, response, capture=None):
        self.response = response
        self.capture = capture

    def get(self, url, params=None, headers=None, check_robots=True):
        if self.capture is not None:
            self.capture["params"] = params
            self.capture["headers"] = headers
        return self.response


def test_build_query_includes_regions_positive_and_negative():
    src = {"regions": ["TI", "ZH"], "limit": 50}
    q = _build_zefix_query(src, ["software", "cloud computing"], ["foto"])
    assert "software" in q.lower()
    assert '"TI"' in q and '"ZH"' in q
    assert "LIMIT 50" in q
    assert "!contains" in q.lower()  # filtro negativo presente


def test_build_query_optional_filters():
    # Filtri città / forma giuridica / sito solo se richiesti.
    src = {"regions": ["TI"], "cities": ["Lugano"], "legal_forms": ["SA"],
           "require_website": True, "limit": 10}
    q = _build_zefix_query(src, ["software"], [])
    assert "lugano" in q.lower()
    assert " SA$" in q
    # require_website → url NON opzionale (clausola obbligatoria)
    assert "OPTIONAL { ?org schema:url" not in q


def test_build_query_website_optional_by_default():
    src = {"regions": ["TI"], "limit": 10}
    q = _build_zefix_query(src, ["software"], [])
    assert "OPTIONAL { ?org schema:url" in q


def test_zefix_parsing_from_sparql_json():
    payload = json.dumps({"results": {"bindings": [
        {
            "name": {"value": "Coding 83 SA"},
            "descr": {"value": "Sviluppo software e servizi informatici"},
            "url": {"value": "https://coding83.ch"},
            "uid": {"value": "https://register.ld.admin.ch/zefix/company/1/UID/CHE123456789"},
            "street": {"value": "Via Test 1"},
            "plz": {"value": "6900"},
            "city": {"value": "Lugano"},
            "region": {"value": "TI"},
        }
    ]}})
    capture = {}
    client = FakeClient(payload, capture)
    src = {"name": "Zefix", "country": "CH", "endpoint": "https://ld.admin.ch/query",
           "regions": ["TI"], "limit": 10, "enabled": True}
    raws = discover(src, client)

    assert len(raws) == 1
    r = raws[0]
    assert r.fields["name"] == "Coding 83 SA"
    assert r.fields["registry_ids"]["uid"] == "CHE123456789"
    assert r.fields["sector_codes"] == ["62"]  # settore IT dedotto
    assert "Lugano" in r.fields["locations"][0]["address"]
    assert r.fields["locations"][0]["region"] == "TI"
    # La query SPARQL viene inviata come parametro con header Accept corretto.
    assert "query" in capture["params"]
    assert "sparql-results+json" in capture["headers"]["Accept"]
