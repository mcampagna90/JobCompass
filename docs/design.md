# Design — JobCompass

## Overview

JobCompass is a batch Python pipeline, runnable from the CLI, that discovers IT
companies in a target area (configurable; examples target France and
Switzerland), filters and enriches them, geocodes them and produces a browsable
map plus data exports. It can share a companies interchange file with a separate
job-search tool.

Pipeline order: discovery → exclusion filters → IT classification → geocoding →
persistence/dedup → outputs (GeoJSON + CSV + HTML maps) → interchange export.

### Guiding principles
- **Lawful by construction:** public/open-data registries, OSM/Nominatim, websites
  within `robots.txt`; paid providers only via official API, optional.
- **No revenue:** size class + employee band only.
- **Missing data marked, never invented.**
- **Data/view separation:** GeoJSON is the source of truth, HTML is a view.

## Architecture

```
          +-------------------+
 CLI ---> |   Orchestrator    |
          +-------------------+
             |    |    |    |
 Discoverers -> Filters -> ItClassifier -> Enricher -> Geocoder -> Store -> Outputs
 (registries/   (size,      (native vs      (summary,   (OSM/       (SQLite, (GeoJSON,
  open data)     startup,    adjacent)       tags,       Nominatim)  dedup,   CSV,
                 consulting,                 ATS slug)               history, 2 maps,
                 tobacco,                                            excluded)export)
                 gambling)
```

### Execution flow
1. The Orchestrator reads configuration (area, IT sectors, thresholds, sources,
   sector blocklist).
2. Discoverers query registries/open data per country and IT sector.
3. Filters exclude micro/small, startups, consulting/staffing/outsourcing and
   blocklisted sectors (tobacco, gambling); excluded companies are stored.
4. The ItClassifier assigns `it_native` or `it_adjacent` (only with a strong signal).
5. The Enricher adds size class, approximate employees, business summary, tech
   tags and optional ATS slug.
6. The Geocoder resolves locations to coordinates (OSM/Nominatim).
7. The Store persists to SQLite (companies, locations, excluded) with dedup/history.
8. Outputs generate GeoJSON, CSV and **separate** static HTML maps per class.
9. The interchange export produces the companies file for the job-search tool.

## Components

### Discoverers (one per source/country)
- Common interface: `discover(source, client) -> list[RawCompany]`.
- **France:** INSEE SIRENE (official API, portal `portail-api.insee.fr`, endpoint
  `api-sirene/3.11/siret`). Auth via an **API key in a header** (not OAuth/Bearer);
  the header name is configurable (`auth_header`) because INSEE has changed it over
  time. Query filters by **NAF** (IT sector 62/63) and departments. Exposes employee
  band (`trancheEffectifs`), activity and address. Requires a free user key; with
  no key, the source makes no calls.
- **Switzerland:** LINDAS open dataset via **SPARQL** (endpoint `ld.admin.ch/query`),
  class `ZefixOrganisation`. Exposes `legalName`, `description`, `url`, `identifier`
  (UID), `address`. Does **not** expose a NACE code or headcount. SPARQL query with
  configurable filters: canton, city, legal form (SA/AG via name heuristic), IT
  keywords in the description (positive) and non-IT exclusion terms (negative). No
  credentials. IT keywords are **strict** (software development/product, AI, cloud,
  cybersecurity…): on large cantons vague keywords catch fiduciaries and generic
  firms, so they are excluded. The "website required" filter exists but is
  **discouraged** since Zefix rarely populates the URL field (would zero results).
- **Italy:** free open data where available; otherwise a commercial provider via
  official API (optional, paid) — else partial data with fields marked missing.
- Cross-cutting: rate limit, identifiable `User-Agent`, backoff retries,
  skip+reason for forbidden/inaccessible sources.

### Filters (exclusions)
- Excludes below the size threshold (default ~250, configurable), startups,
  consulting/staffing/outsourcing (multilingual lists) and blocklisted sectors
  (tobacco, gambling). Defense is not excluded. Excluded companies are persisted
  to SQLite with reason.

### ItClassifier (it_native vs it_adjacent)
- `it_native` if the sector is IT by NACE 62/63.
- `it_adjacent` only with a **strong signal** of internal IT activity (active ATS
  board with tech roles, or a verifiable digital division). Generic marketing
  language is not enough. Large banks/multinationals with strong IT are allowed;
  fintech/trading excluded for now. `it_adjacent` requires large/multinational.

### Enricher
- Size class and employee band from registries. Technology tags from available
  text. ATS slug detection. No fabricated data.

### Geocoder
- OSM/Nominatim within terms (rate limit, local cache). Unresolvable → coordinates
  null, textual address kept.

### Store (SQLite)
- Dedup key: registry ID / VAT / normalized domain. `first_seen`/`last_seen`;
  in-place update with change tracking. Tables: `companies`, `locations`,
  `excluded_companies`, `runs`, `company_changes`.

### Outputs
- `GeoJSON` + `CSV` writers, separate per class.
- `HtmlMapWriter`: two separate static maps. The GeoJSON is **embedded inline**
  (not loaded via `fetch`), so the map works opened with a double click
  (`file://`). Leaflet assets are bundled locally under `output/vendor` (no CDN,
  works offline and in IDE previews). Default **neutral offline background** (no
  external tiles, no API key, no provider that could block). Colored tags:
  in-liquidation = red, it_adjacent = purple, size = green, tech = blue, new =
  orange. A search box filters the side list. A street-map background is available
  only as an option if the user provides a tile key.
- `InterchangeExporter`: companies file (name, domains, locations, ATS slug) for
  the job-search tool.
- Outputs highlight new/updated companies since the last run.

### Data updates
- Updates are **manual**: the user re-runs the pipeline; no scheduling.
- The run is **incremental**: comparison with the DB via dedup key, classifying
  new/updated/unchanged, history in `company_changes`.

## Data model

### `Company`
| Field | Type | Notes |
|---|---|---|
| id | str | stable internal id |
| registry_ids | dict | registry ID / VAT per country |
| name | str | legal name |
| domains | list[str] | web domains |
| country | str | FR/CH/IT |
| sector_codes | list[str] | NACE/activity codes |
| it_class | enum | it_native / it_adjacent |
| it_signal | str \| null | signal justifying it_adjacent |
| size_class | enum | medium/large/multinational/unknown |
| employees_approx | str \| null | employee band |
| business_summary | str \| null | short business summary |
| tech_stack | list[str] | technology tags if available |
| ats_slug | str \| null | Greenhouse/Lever/Ashby slug |
| locations | list[Location] | offices |

### `Location`
address, region, country, lat, lon (lat/lon null if not geocoded).

## Sector and size
- **IT sector:** selected via NACE/national codes for software development and IT
  services (configurable). Where a source lacks codes (Zefix), a keyword heuristic
  on the description is used.
- **Size:** derived from registry employee bands; exclusion threshold configurable
  (default ~250). `it_adjacent` allowed only for large/multinational.

## Known per-source limits (real status)
- **Switzerland (Zefix/LINDAS):** operational via SPARQL, free, no token. No NACE
  nor headcount → heuristic sector filter (possible false positives/negatives),
  size class typically `unknown`, hence no it_adjacent for CH and the size
  threshold is not applicable.
- **France (SIRENE):** requires a **free API key** from the INSEE portal, passed in
  a configurable header. Exposes NAF and employee band → size class and the ~250
  threshold ARE applicable here. Header name and endpoint version should be
  confirmed on the portal (INSEE has changed them). Not tested live without the
  user's key.
- **Italy:** no complete free endpoint ready to use. With open data only, output is
  typically empty/partial; real coverage needs a paid provider (optional, off by
  default).
- **Geocoding (Nominatim):** ~1 req/s rate limit; with many companies the run is
  slow and some partial addresses are not resolved (coordinates null).

## Error handling
- Forbidden/inaccessible source: skip + reason, no bypass.
- Network/timeout: backoff retries, then skip the single source.
- Geocoding failure: coordinates null, address kept.
- Missing data: field marked missing, never estimated arbitrarily.
- Disabled paid provider: related fields stay missing, pipeline continues.

## Testing strategy
- Unit: Discoverers (per-country mapping and query building), Filters (threshold,
  startup, consulting, blocklist), ItClassifier (strong signal, size gating),
  Enricher, Geocoder (cache, null coordinates).
- Dedup: same company not duplicated; field change → update with history.
- Outputs: valid GeoJSON, UTF-8 CSV, HTML openable without backend (local Leaflet,
  inline GeoJSON, no CDN), interchange export consumable.
- Compliance: restrictive-terms source → skipped and logged; Nominatim rate limit;
  no external actions.
- Fixtures: local sample registry responses, no real network calls in unit tests.
