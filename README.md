<p align="center">
  <img src="assets/jobcompass-logo.svg" alt="JobCompass" width="420"/>
</p>

<p align="center">
  <b>Find your direction to the right job.</b><br>
  Open-source company discovery for smarter job hunting.
</p>

<p align="center">
  <a href="#license"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"/></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-brightgreen.svg" alt="Python 3.11+"/>
</p>

---

## Table of contents

- [Purpose](#purpose)
- [How it works (design)](#how-it-works-design)
- [What data is stored, and where](#what-data-is-stored-and-where)
- [Customizing filters](#customizing-filters)
- [Adding your own sources](#adding-your-own-sources)
- [Map: how it renders and its limits](#map-how-it-renders-and-its-limits)
- [API limits you should know](#api-limits-you-should-know)
- [Limits and responsible use](#limits-and-responsible-use)
- [Installation](#installation)
- [Usage](#usage)
- [Technologies](#technologies)
- [License](#license)

---

## Purpose

JobCompass helps you **discover and map companies** from official public business
registries, so you can find employers you did not even know existed — then explore
them on an interactive map with your own filters.

It is built for job seekers who want to go beyond job boards: instead of waiting
for postings, you map the companies that match **your** criteria (sector, size,
location, technology) and decide where to aim.

Although the shipped examples target IT companies, JobCompass is **not IT-only**:
sector keywords, size thresholds, exclusions and areas are all configurable, so you
can point it at any industry.

What it is **not**: it does not apply to jobs, send messages, or scrape sites that
forbid automated access. It is a read-only discovery and mapping tool.

---

## How it works (design)

JobCompass is a batch pipeline run from the CLI. Each stage has one job:

1. **Discoverers** — query one authorized source per country and return raw
   records. France uses the INSEE SIRENE API; Switzerland uses the Zefix dataset on
   LINDAS via SPARQL; Italy uses open data or an optional paid provider.
2. **Normalizer** — convert each raw record into a uniform `Company` object; map
   employee bands to a size class (`medium` / `large` / `multinational` /
   `unknown`). Missing fields stay empty, never invented.
3. **Filters** — drop companies below the size threshold, startups,
   consulting/staffing, and blocklisted sectors (e.g. tobacco, gambling). Excluded
   companies are recorded (not silently dropped).
4. **IT classifier** — label each company `it_native` (IT by sector code) or
   `it_adjacent` (non-IT but with a strong internal tech signal, e.g. an active ATS
   board). IT-adjacent is kept on a separate map.
5. **Geocoder** — resolve each office address to coordinates via OpenStreetMap
   Nominatim, with a local cache; unresolved addresses keep text, coordinates null.
6. **Store** — persist to a local SQLite database with deduplication and history.
7. **Outputs** — write GeoJSON + CSV + a standalone HTML map per class, plus an
   interchange file for a job-search tool.

```
Discoverers → Normalizer → Filters → IT classifier → Geocoder → Store(SQLite) → Outputs
(SIRENE,       (uniform    (size,     (native vs       (OSM/       (dedup,         (GeoJSON,
 Zefix/LINDAS)  schema)     startup,   adjacent)        Nominatim)  history)        CSV, HTML)
                            blocklist)
```

Runs are **manual and incremental**: re-running compares against the database and
labels each company new / updated / unchanged. There is no scheduler and no
automatic background activity.

Full requirements and design live in [`docs/`](docs/).

---

## What data is stored, and where

Everything is **local**. JobCompass creates a single SQLite file (default
`companies.db`, configurable via `db_path`) in your working directory. Nothing is
uploaded anywhere; the only outbound traffic is the read-only queries to the
sources you enable.

The database has five tables:

| Table | What it holds |
|---|---|
| `companies` | Normalized companies: name, country, `registry_ids`, domains, `sector_codes`, `it_class`, `it_signal`, `size_class`, `employees_approx`, `business_summary`, `tech_stack`, `ats_slug`, plus `first_seen` / `last_seen`. Keyed by a stable `dedup_key`. |
| `locations` | One row per office: address, region, country, `lat`, `lon` (null if not geocoded), linked to a company. |
| `excluded_companies` | Companies filtered out, with the `reason` and the `rule` that triggered it — so you can review missed opportunities later. |
| `runs` | One row per run: timestamp and counters (sources queried, found, excluded, new, updated, duplicates). |
| `company_changes` | History of changed fields over time (field, old value, new value, timestamp). |

**Deduplication key:** `country` + a stable identifier (VAT → SIREN → UID →
domain → name). Re-runs update existing rows in place and append to
`company_changes`, so the database grows without duplicating.

**Generated files** (in `output/`, git-ignored): `*.geojson` (map data),
`*.csv` (spreadsheet export), `*.html` (the maps), `companies_interchange.json`,
and a local copy of the Leaflet assets under `output/vendor/`.

**Credentials are never stored in the database or the repo.** API keys are read
from environment variables referenced in `config.yaml` (e.g. `${INSEE_API_KEY}`).
`config.yaml`, `*.db` and `output/` are all git-ignored.

---

## Customizing filters

Every filter lives in `config.yaml` (copy from `config.example.yaml`). Nothing is
hard-coded — empty a list to disable a filter, or extend it to be stricter.

- **Sector** — `sectors.it_prefixes` lists the activity codes (NACE/national) in
  scope. Default targets software/IT (`62`, `63`); change it for your industry.
  For sources without codes (Zefix), use per-source `it_keywords` / `it_negatives`
  to match on the description text.
  ```yaml
  sectors:
    it_prefixes: ["62", "63"]
  ```
- **Size** — `filters.size_threshold` excludes companies below an employee count
  (default ~250). Applies only where the source exposes headcount.
- **Geography** — per-source `regions`, `cities`, `departments`.
- **Legal form** — per-source `legal_forms` (e.g. `["SA", "AG"]`).
- **Exclusions** — `filters.exclusion_keywords` (consulting/staffing),
  `filters.blocklist_sector_prefixes` (e.g. tobacco, gambling),
  `filters.startup_signals`.
- **IT-adjacent** — `it_adjacent.allowed_size_classes` and
  `finance_exclude_keywords`.

---

## Adding your own sources

You are not limited to the bundled sources. Add your own under `sources:`:

```yaml
sources:
  - name: "My registry API"
    country: XX
    type: registry
    transport: api
    endpoint: "https://api.example.org/companies"
    auth_header: "X-API-Key"            # if the provider uses a key
    credentials_env: "${MY_API_KEY}"    # key read from an env var
    enabled: true
```

Mapping a brand-new API response shape may require a small adapter in
`src/jobcompass/discoverers.py`. Only connect to sources you are **authorized** to
use (see below).

---

## Map: how it renders and its limits

The maps are **standalone HTML files** you can open with a double click — no
server, no API key, no internet required to view them:

- **GeoJSON is embedded inline** in the HTML, so it works over `file://` (where a
  normal `fetch` of an external file would be blocked by the browser).
- **Leaflet is bundled locally** under `output/vendor/` — no CDN, works offline and
  inside IDE previews.
- **Neutral offline background** by default (no map tiles). A real street-map
  background is optional and requires your own tile key (e.g. MapTiler).
- **Colored tags** make scanning fast: `in-liquidation` (red), `IT-adjacent`
  (purple), size class (green), `new since last run` (orange), technology (blue).
  A search box filters the side list.

**Rendering limits (be realistic):**

- Markers are drawn as lightweight circle markers. A few hundred to a couple of
  thousand points render smoothly on desktop and phone.
- Because the GeoJSON is embedded **inline**, the HTML file size grows with the
  number of companies. With **many thousands** of points the file gets heavy to
  load and pan. If you reach that scale, narrow your filters (region/city/sector)
  or split the map — JobCompass does not yet do marker clustering or tiling.
- Only companies with resolved coordinates appear as markers; the rest are still in
  the CSV/GeoJSON with a textual address.

---

## API limits you should know

JobCompass respects provider limits, and so should you when adding sources. The
ones that matter in practice:

- **OpenStreetMap Nominatim (geocoding)** — the usage policy allows an **absolute
  maximum of 1 request per second for the whole application** (not per user). The
  client throttles to `rate_limit_seconds` (default 1.0) and caches results, but
  this makes geocoding the slow part: ~N seconds for N new addresses. For large
  batches you should run your own Nominatim instance or use a paid geocoder.
  Source: [Nominatim Usage Policy](https://operations.osmfoundation.org/policies/nominatim/).
- **INSEE SIRENE (France)** — requires a free API key and enforces a per-key
  request quota (historically on the order of tens of requests per minute for the
  open API; confirm the exact figure on your portal subscription). The pipeline
  retries with backoff on transient errors and paginates via the `limit` setting.
- **Zefix / LINDAS (Switzerland)** — a public SPARQL endpoint, no key. Very large
  or unbounded queries can time out; keep a `limit` and filter by canton/city.
- **Paid providers (e.g. openapi.it)** — billed per request and **disabled by
  default**. While disabled, no calls and no cost. You control when to enable them.

General behaviour on limits: requests are throttled (`rate_limit_seconds`), retried
with exponential backoff, and a source that returns 401/403 or is disallowed by
`robots.txt` is skipped and logged rather than retried aggressively.

---

## Limits and responsible use

JobCompass connects to **official APIs and open data**, not by scraping sites that
forbid it. The same rules apply to any source you add:

- **Authorized sources only** — official/public APIs, open data, or services you
  have valid credentials for. Do not target endpoints whose terms forbid automated
  access.
- **Respect `robots.txt` and terms of use** — the client checks `robots.txt` and
  skips disallowed URLs; keep that on.
- **Respect rate limits** — do not lower `rate_limit_seconds` to hammer a provider.
- **Identify yourself** — requests send an honest `User-Agent`.
- **No bypassing** — no circumventing logins, CAPTCHAs or paywalls; there is
  deliberately no headless-browser evasion.
- **No external actions** — JobCompass never sends emails, messages or applications.
- **Keep credentials out of git** — keys live in environment variables.

These are what make the tool lawful to run. Adding a source is easy, but you remain
responsible for using each provider within its terms.

---

## Installation

```bash
git clone https://github.com/<your-user>/JobCompass.git
cd JobCompass
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```bash
cp config.example.yaml config.yaml   # then edit sources and filters
jobcompass run                       # discover, enrich, map
jobcompass sources                   # list configured sources
```

Outputs land in `output/`:
- `it_native.{geojson,csv,html}` — companies in your target sector
- `it_adjacent.{geojson,csv,html}` — adjacent companies with a tech arm
- `companies_interchange.json` — export for a job-search tool

Open `output/it_native.html` in your browser (double click works). Re-run anytime;
the database updates incrementally and the output highlights what's new.

### Enabling France (SIRENE)

1. Create a free account on the INSEE API portal and subscribe to the Sirene API.
2. Export your key and enable the source:
   ```bash
   export INSEE_API_KEY="your-key"
   ```
   Set `enabled: true` under the SIRENE source in `config.yaml`. Confirm the exact
   header name and endpoint version on your portal subscription.

---

## Technologies

- **Python 3.11+**
- [requests](https://pypi.org/project/requests/) — HTTP client
- [PyYAML](https://pypi.org/project/PyYAML/) — configuration
- [Leaflet](https://leafletjs.com/) — maps (bundled locally, no CDN)
- **SPARQL** over [LINDAS](https://lindas.admin.ch/) for Swiss company data
- [INSEE SIRENE API](https://www.insee.fr/) for French company data
- [OpenStreetMap / Nominatim](https://nominatim.org/) for geocoding
- **SQLite** for local storage

---

## License

[MIT](LICENSE) © JobCompass contributors.
