"""Per-country discoverers (Requirement 1, 3).

- France: SIRENE (official API), includes employee band.
- Switzerland: Zefix / LINDAS SPARQL (open data).
- Italy: free open data (partial); openapi.it preconfigured but disabled.

Disabled paid providers make NO calls (Requirement 1.8). JSON responses are mapped
to RawCompany; collectors are testable with a fake HTTP client (no real network
calls in tests).
"""

from __future__ import annotations

import json

from .http_client import HttpClient
from .models import RawCompany


class DiscovererError(Exception):
    pass


def discover(source: dict, client: HttpClient) -> list[RawCompany]:
    """Dispatch by source. Disabled sources -> no call, empty list."""
    if not source.get("enabled", False):
        return []
    country = source.get("country")
    if country == "FR":
        return _discover_sirene(source, client)
    if country == "CH":
        return _discover_zefix(source, client)
    if country == "IT":
        if source.get("type") == "commercial":
            return _discover_openapi_it(source, client)
        return _discover_it_opendata(source, client)
    raise DiscovererError(f"Unsupported country: {country}")


# INSEE employee bands (trancheEffectifs) -> indicative employee count.
# Official INSEE codes; we take the lower bound as a conservative estimate.
_INSEE_EFFECTIFS = {
    "00": 0, "01": 1, "02": 3, "03": 6, "11": 10, "12": 20, "21": 50,
    "22": 100, "31": 200, "32": 250, "41": 500, "42": 1000, "51": 2000,
    "52": 5000, "53": 10000,
}


def _build_sirene_query(source: dict) -> str:
    """Build the SIRENE `q` parameter: NAF (IT sector) + departments."""
    naf = source.get("naf_prefixes") or ["62", "63"]
    departments = source.get("departments") or []
    # activitePrincipaleUniteLegale starts with the NAF code (e.g. 62.01Z).
    naf_q = " OR ".join(f'periode(activitePrincipaleUniteLegale:{p}*)' for p in naf)
    q = f"({naf_q})"
    if departments:
        # codePostalEtablissement starts with the department number.
        dep_q = " OR ".join(f"codePostalEtablissement:{d}*" for d in departments)
        q += f" AND ({dep_q})"
    # active legal units only
    q += " AND etatAdministratifUniteLegale:A"
    return q


def _discover_sirene(source: dict, client: HttpClient) -> list[RawCompany]:
    # New INSEE scheme: a permanent API key in a header (no longer Bearer).
    # The header name is configurable because INSEE has changed it over time.
    api_key = source.get("credentials_env") or source.get("api_key")
    if not api_key:
        # Without a key we make no calls (source not activatable).
        return []
    auth_header = source.get("auth_header", "X-INSEE-Api-Key-Integration")
    headers = {auth_header: api_key, "Accept": "application/json"}

    params = dict(source.get("query") or {})
    params.setdefault("q", _build_sirene_query(source))
    params.setdefault("nombre", int(source.get("limit", 100)))

    text = client.get(source["endpoint"], params=params,
                      headers=headers, check_robots=False)
    data = json.loads(text)
    # The /siret endpoint returns "etablissements"; /siren returns "unitesLegales".
    units = (data.get("etablissements") or data.get("unitesLegales")
             or data.get("data") or [])
    out = []
    for u in units:
        ul = u.get("uniteLegale", u)  # on /siret the legal-unit fields are nested
        adr = u.get("adresseEtablissement", {})
        tranche = ul.get("trancheEffectifsUniteLegale")
        locations = []
        if adr:
            address = " ".join(str(x) for x in [
                adr.get("numeroVoieEtablissement", ""),
                adr.get("typeVoieEtablissement", ""),
                adr.get("libelleVoieEtablissement", ""),
                adr.get("codePostalEtablissement", ""),
                adr.get("libelleCommuneEtablissement", ""), "France",
            ] if x).strip()
            locations = [{"address": address, "country": "FR",
                          "region": adr.get("codePostalEtablissement", "")[:2]}]
        out.append(RawCompany(source=source["name"], country="FR", fields={
            "name": (ul.get("denominationUniteLegale")
                     or ul.get("denomination") or u.get("siren")),
            "registry_ids": {"siren": ul.get("siren") or u.get("siren")},
            "sector_codes": [ul.get("activitePrincipaleUniteLegale")]
                            if ul.get("activitePrincipaleUniteLegale") else [],
            "employees": _INSEE_EFFECTIFS.get(tranche) if tranche else None,
            "employees_approx": f"tranche {tranche}" if tranche else None,
            "locations": locations,
        }))
    return out


# STRICT IT keywords: only software development/product and concrete technologies.
# Deliberately NOT including vague terms like "IT services" or bare "data", which
# on Zefix catch fiduciaries and generic companies.
_CH_IT_KEYWORDS = [
    "sviluppo software", "sviluppo di software", "softwareentwicklung",
    "entwicklung von software", "développement de logiciels", "software development",
    "software house", "software as a service", "saas",
    "cloud computing", "cybersecurity", "cyber security", "cybersicurezza",
    "big data", "data engineering", "machine learning",
    "künstliche intelligenz", "intelligenza artificiale", "intelligence artificielle",
    "piattaforma software", "softwareplattform", "software platform",
    "applicazioni software", "software applicativi", "devops",
]
# Terms indicating a NON-IT sector or non-product firms: drop false positives
# (retail/repair/trade, fiduciaries, staffing, finance).
_CH_IT_NEGATIVE = [
    "foto", "photo", "copie", "copy shop", "druckerei", "stampa", "ristorante",
    "restaurant", "immobilien", "immobili", "coiffure", "parrucch",
    "riparazione", "reparatur", "réparation", "vendita al dettaglio",
    "commercio al dettaglio", "import-export", "import export", "noleggio",
    "turistic", "turismo", "alberghier", "logistica", "facchinaggio",
    # fiduciaries / accounting / staffing / recruitment
    "fiduciari", "fiduconsult", "fidupartners", "fiduciaire", "treuhand",
    "comptab", "contabil", "buchhaltung", "revisione contabile",
    "staffing", "personalvermittlung", "ressources humaines", "recruitment",
    "collocamento", "lavoro interinale", "gestione patrimoniale",
    "vermögensverwaltung", "asset management", "wealth management",
]


# Map: term (various languages in the Zefix legal purpose) -> EN technology tag.
# NOTE: Zefix does not contain the real stack (languages): only what the legal
# purpose explicitly mentions is extracted. Where nothing matches, it stays empty.
_TECH_TAG_MAP = {
    "AI": ["intelligenza artificiale", "künstliche intelligenz",
           "intelligence artificielle", "artificial intelligence", " ai ", " ia "],
    "Machine Learning": ["machine learning", "apprendimento automatico"],
    "Cloud": ["cloud computing", "cloud"],
    "Cybersecurity": ["cybersecurity", "cyber security", "sicurezza informatica",
                      "cybersicurezza"],
    "Data": ["big data", "data engineering", "banche dati", "datenbank",
             "database", "analisi dati", "elaborazione dati"],
    "Blockchain": ["blockchain", "crypto", "nft", "distributed ledger"],
    "IoT": ["internet of things", "iot", "internet delle cose"],
    "Web": ["piattaforme web", "web", "internet", "siti web"],
    "Mobile": ["app mobile", "applicazioni mobili", "mobile app"],
    "SaaS": ["saas", "software as a service"],
    "DevOps": ["devops"],
    "Robotics": ["robotica", "robotics", "automazione", "automation"],
    "Fintech": ["software in ambito finanziario", "financial software"],
    "E-commerce": ["e-commerce", "commercio elettronico", "negozio online"],
}


def _extract_tech_tags(descr: str | None) -> list[str]:
    """Extract English technology tags from the legal purpose (heuristic)."""
    if not descr:
        return []
    t = " " + descr.lower() + " "
    tags = []
    for tag, terms in _TECH_TAG_MAP.items():
        if any(term in t for term in terms):
            tags.append(tag)
    return tags
# Cantons of interest (Requirement 5.2).
_CH_REGIONS = ["VD", "ZH", "GE"]

# Real SPARQL query on the Zefix dataset (LINDAS). Configurable filters: canton,
# city, legal form, website presence, IT keywords. Verified live.
_ZEFIX_SPARQL = """PREFIX schema: <http://schema.org/>
SELECT ?org ?name ?url ?descr ?uid ?street ?plz ?city ?region WHERE {{
  ?org a <https://schema.ld.admin.ch/ZefixOrganisation> ;
       schema:legalName ?name ;
       schema:description ?descr ;
       schema:address ?addr .
  ?addr schema:addressRegion ?region ;
        schema:addressLocality ?city .
  {url_clause}
  OPTIONAL {{ ?addr schema:streetAddress ?street . }}
  OPTIONAL {{ ?addr schema:postalCode ?plz . }}
  FILTER(?region IN ({regions}))
{city_filter}{legalform_filter}
  FILTER({kw_filter})
}} LIMIT {limit}"""


def _build_zefix_query(source: dict, keywords: list[str], negatives: list[str]) -> str:
    regions = source.get("regions") or _CH_REGIONS
    cities = source.get("cities") or []
    legal_forms = source.get("legal_forms") or []
    require_website = bool(source.get("require_website", False))
    limit = int(source.get("limit", 200))

    kw_filter = " || ".join(
        f'CONTAINS(LCASE(STR(?descr)), "{k.lower()}")' for k in keywords
    )
    neg_filter = " && ".join(
        f'!CONTAINS(LCASE(STR(?descr)), "{n.lower()}")' for n in negatives
    )
    full_filter = f"({kw_filter})" + (f" && ({neg_filter})" if neg_filter else "")

    region_list = ", ".join(f'"{r}"' for r in regions)

    # City filter (optional): case-insensitive match on the locality.
    city_filter = ""
    if cities:
        conds = " || ".join(f'CONTAINS(LCASE(STR(?city)), "{c.lower()}")' for c in cities)
        city_filter = f"  FILTER({conds})\n"

    # Legal-form filter (optional): heuristic on the name (SA, AG, GmbH, Sagl).
    legalform_filter = ""
    if legal_forms:
        conds = " || ".join(
            f'REGEX(STR(?name), " {lf}$", "i") || CONTAINS(STR(?name), " {lf} ")'
            for lf in legal_forms
        )
        legalform_filter = f"  FILTER({conds})\n"

    # Website required (optional): proxy for "real company" vs micro-business.
    url_clause = ("?org schema:url ?url ."
                  if require_website else "OPTIONAL { ?org schema:url ?url . }")

    # Always exclude "in liquidation" companies by name.
    exclude_liquidation = (
        '  FILTER(!CONTAINS(LCASE(STR(?name)), "liquidazione") '
        '&& !CONTAINS(LCASE(STR(?name)), "liquidation"))\n'
    )

    return _ZEFIX_SPARQL.format(
        regions=region_list,
        city_filter=city_filter + exclude_liquidation,
        legalform_filter=legalform_filter, kw_filter=full_filter,
        url_clause=url_clause, limit=limit,
    )


def _discover_zefix(source: dict, client: HttpClient) -> list[RawCompany]:
    keywords = source.get("it_keywords") or _CH_IT_KEYWORDS
    negatives = source.get("it_negatives") or _CH_IT_NEGATIVE
    query = _build_zefix_query(source, keywords, negatives)

    text = client.get(source["endpoint"], params={"query": query},
                      headers={"Accept": "application/sparql-results+json"},
                      check_robots=False)
    data = json.loads(text)
    rows = data.get("results", {}).get("bindings", []) if isinstance(data, dict) else []
    out = []
    for r in rows:
        name = _sparql_val(r, "name")
        descr = _sparql_val(r, "descr")
        url = _sparql_val(r, "url")
        city = _sparql_val(r, "city")
        region = _sparql_val(r, "region")
        street = _sparql_val(r, "street")
        plz = _sparql_val(r, "plz")
        address = ", ".join(x for x in [street, f"{plz or ''} {city or ''}".strip(),
                                        "Switzerland"] if x)
        # Zefix exposes no NACE: we tag a synthetic IT code so they pass as
        # it_native (the query keyword filter guarantees the sector).
        out.append(RawCompany(source=source["name"], country="CH", fields={
            "name": name,
            "registry_ids": {"uid": _zefix_uid(_sparql_val(r, "uid"))},
            "sector_codes": ["62"],  # IT sector inferred from the keyword filter
            "domains": [url] if url else [],
            "business_summary": None,  # the long description is not shown
            "tech_stack": _extract_tech_tags(descr),  # EN technology tags
            "locations": [{"address": address, "country": "CH", "region": region}],
        }))
    return out


def _zefix_uid(identifier: str | None) -> str | None:
    if not identifier:
        return None
    # extract CHE... from the identifier URI, if present
    if "CHE" in identifier:
        return "CHE" + identifier.split("CHE", 1)[1]
    return identifier


def _sparql_val(row: dict, key: str):
    v = row.get(key)
    if isinstance(v, dict):
        return v.get("value")
    return v


def _discover_it_opendata(source: dict, client: HttpClient) -> list[RawCompany]:
    # Partial chamber open data: many fields (employees/locations) often missing.
    if not source.get("endpoint"):
        return []
    text = client.get(source["endpoint"], params=source.get("query"), check_robots=False)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    rows = data if isinstance(data, list) else data.get("data", [])
    out = []
    for r in rows:
        out.append(RawCompany(source=source["name"], country="IT", fields={
            "name": r.get("denominazione") or r.get("name"),
            "registry_ids": {"vat": r.get("partita_iva") or r.get("vat")},
            "sector_codes": [r.get("ateco")] if r.get("ateco") else [],
            "employees": r.get("dipendenti"),
            "locations": r.get("locations") or [],
        }))
    return out


def _discover_openapi_it(source: dict, client: HttpClient) -> list[RawCompany]:
    # Provider a pagamento: attivo solo se enabled True + token presente.
    token = source.get("credentials_env")
    if not token:
        return []
    endpoints = source.get("endpoints") or {}
    search_url = endpoints.get("search")
    if not search_url:
        return []
    headers = {"Authorization": f"Bearer {token}"}
    text = client.get(search_url, params=source.get("query"), headers=headers,
                      check_robots=False)
    data = json.loads(text)
    rows = data.get("data", []) if isinstance(data, dict) else data
    out = []
    for r in rows:
        out.append(RawCompany(source=source["name"], country="IT", fields={
            "name": r.get("companyName") or r.get("denominazione"),
            "registry_ids": {"vat": r.get("vatCode") or r.get("partita_iva")},
            "sector_codes": [r.get("atecoCode")] if r.get("atecoCode") else [],
            "employees": r.get("employees") or r.get("dipendenti"),
            "locations": r.get("locations") or [],
        }))
    return out
