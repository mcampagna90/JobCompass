"""Test del discoverer Francia (SIRENE) con client HTTP fake: nessuna rete reale."""

import json

from jobcompass.discoverers import _build_sirene_query, discover


class FakeClient:
    def __init__(self, response, capture=None):
        self.response = response
        self.capture = capture

    def get(self, url, params=None, headers=None, check_robots=True):
        if self.capture is not None:
            self.capture["params"] = params
            self.capture["headers"] = headers
        return self.response


def test_sirene_query_naf_and_departments():
    q = _build_sirene_query({"naf_prefixes": ["62", "63"], "departments": ["06", "74"]})
    assert "62*" in q and "63*" in q
    assert "06*" in q and "74*" in q
    assert "etatAdministratifUniteLegale:A" in q


def test_sirene_without_key_makes_no_call():
    # Senza chiave API → nessuna chiamata, lista vuota (fonte non attivabile).
    src = {"country": "FR", "enabled": True, "endpoint": "https://api.insee.fr/x"}
    assert discover(src, FakeClient("{}")) == []


def test_sirene_sends_api_key_header():
    payload = json.dumps({"etablissements": [
        {
            "siren": "123456789",
            "uniteLegale": {
                "denominationUniteLegale": "TechFR SAS",
                "siren": "123456789",
                "activitePrincipaleUniteLegale": "62.01Z",
                "trancheEffectifsUniteLegale": "32",
            },
            "adresseEtablissement": {
                "numeroVoieEtablissement": "10",
                "typeVoieEtablissement": "RUE",
                "libelleVoieEtablissement": "DE LA PAIX",
                "codePostalEtablissement": "06000",
                "libelleCommuneEtablissement": "NICE",
            },
        }
    ]})
    capture = {}
    client = FakeClient(payload, capture)
    src = {
        "name": "SIRENE", "country": "FR", "enabled": True,
        "endpoint": "https://api.insee.fr/api-sirene/3.11/siret",
        "auth_header": "X-INSEE-Api-Key-Integration",
        "credentials_env": "secret-key-123",
        "naf_prefixes": ["62"], "departments": ["06"],
    }
    raws = discover(src, client)

    assert len(raws) == 1
    r = raws[0]
    assert r.fields["name"] == "TechFR SAS"
    assert r.fields["registry_ids"]["siren"] == "123456789"
    assert r.fields["sector_codes"] == ["62.01Z"]
    assert r.fields["employees"] == 250  # tranche 32 -> estremo inferiore 250
    assert "NICE" in r.fields["locations"][0]["address"]
    # La chiave API viene inviata nell'header configurato (non Bearer).
    assert capture["headers"]["X-INSEE-Api-Key-Integration"] == "secret-key-123"
    assert "Authorization" not in capture["headers"]
