# Requirements — JobCompass

## Introduction

JobCompass is an open-source Python tool that **discovers and maps companies**
from official public business registries, so you can get a picture of who is out
there, where they are based, how big they are and what they do — without starting
from a list of companies you already know.

The output is meant to be browsed comfortably on desktop or phone: an interactive
**map** of companies and their locations, plus a **card** per company with a short
business summary and, when available, technology tags.

JobCompass is read-only toward its sources, uses only public/official data or
authorized APIs, and performs **no external actions** (no outreach, no messaging).
It can feed a separate job-search tool through a shared interchange file, but it
is a standalone project.

### Default geographic scope (configurable)
- **France**
- **Switzerland**
- Northern Italy border regions

The scope is fully configurable; the shipped examples target France and
Switzerland because those have free, official registry APIs.

### Ethical and legal constraints (cross-cutting, non-negotiable)
- Authorized sources only: business registries with API/open data, open
  geographic datasets (e.g. OpenStreetMap/Nominatim), public company websites
  within the limits of `robots.txt`, and commercial data providers **only**
  through their official APIs and terms.
- No aggressive scraping: respect `robots.txt`, conservative rate limits, an
  identifiable `User-Agent`.
- No bypassing of login, CAPTCHA, paywalls or terms of use.
- No automated outreach and no collection of personal data beyond public company
  data.
- Missing data is marked as missing, never fabricated.

## Requirements

### Requirement 1 — Discovery from authorized sources
**User story:** As a user, I want to discover companies in the target area without
knowing them in advance, starting from registries and public data.

#### Acceptance criteria
1. The system SHALL discover companies by querying authorized sources per country:
   business registries with API/open data (e.g. SIRENE for France, Zefix/LINDAS
   via SPARQL for Switzerland) and, where no complete free public API exists (e.g.
   Italy), open data or a commercial provider via its official API.
2. The system SHALL filter companies by **IT sector**. Where the source exposes
   activity codes (NACE/national, e.g. France) the filter uses them; where the
   source does NOT expose codes (e.g. Zefix/Switzerland) the filter is
   **heuristic** on the free-text description, via configurable positive IT
   keywords and negative exclusion terms. The heuristic may yield false
   positives/negatives and is documented as such.
3. The system SHALL limit discovery to the configured **geographic area**.
4. IF a source requires login/CAPTCHA or forbids automated use THEN the system
   SHALL skip it and record the reason.
5. The system SHALL apply rate limits and an identifiable `User-Agent`, with
   limited backoff retries, without aborting the whole discovery.
6. IF a rich data source is paid-only THEN its use SHALL be optional and
   configurable, with data marked missing when the source is inactive.
7. The default behaviour SHALL be fully **free** (France via SIRENE, Switzerland
   via Zefix/LINDAS). Fields unavailable without a paid source stay marked missing.
8. The system SHALL ship paid providers **preconfigured but disabled**
   (`enabled: false`): to activate them the user only sets `enabled: true` and
   provides credentials via an environment variable, without editing code. While
   disabled, the system SHALL make no paid calls.

### Requirement 2 — Size class and headcount (no revenue)
**User story:** As a user, I want to understand whether a company is medium, large
or multinational and roughly how many employees it has, without revenue data.

#### Acceptance criteria
1. The system SHALL assign each company a **size class** among `medium`, `large`,
   `multinational`, `unknown`.
2. The system SHALL report an **approximate employee count** (band), derived from
   registry bands when available.
3. The system SHALL NOT collect or display revenue data.
4. IF size data is unavailable THEN the system SHALL mark the class as `unknown`
   without inventing values.
5. Some free sources do NOT expose headcount (e.g. Zefix for Switzerland): for
   those the size class is typically `unknown` and the size threshold of
   Requirement 3.1 is NOT applicable.

### Requirement 3 — A-priori exclusions
**User story:** As a user, I want to exclude what I am not interested in, so the
map is not full of noise.

#### Acceptance criteria
1. The system SHALL exclude micro and small companies below a configurable
   employee threshold (indicative default: ~250).
2. The system SHALL exclude startups recognized via configurable signals (very
   young + small + "early stage/seed/Series A" language).
3. The system SHALL exclude consulting, body rental, staffing, outsourcing firms
   via configurable multilingual keyword/pattern lists.
4. The system SHALL exclude the **tobacco** and **gambling** sectors via a
   configurable NACE/national-code blocklist. **Defense** is NOT excluded.
5. WHEN a company is excluded THEN the system SHALL record the reason and the
   triggering rule in a readable form.
6. The system SHALL **persist excluded companies in SQLite** with the exclusion
   reason, so they can be reviewed later for missed opportunities; these companies
   do NOT appear in the main maps/outputs.

### Requirement 4 — Normalization and geocoding of locations
**User story:** As a user, I want geolocated offices and uniform cards so I can
explore them.

#### Acceptance criteria
1. WHEN a company is acquired THEN the system SHALL normalize it into: name,
   domains, sector/activity code, size class, approximate employees, business
   summary, technology tags (if available), locations, and optional ATS slug.
2. The system SHALL geocode each location (lat/lon) using an open geographic
   source (e.g. OpenStreetMap/Nominatim) respecting its terms.
3. IF a location cannot be geocoded THEN the system SHALL keep the textual address
   and mark the coordinates as missing.
4. A company MAY have multiple locations; each is a point on the map.

### Requirement 5 — Business summary and technology tags
**User story:** As a user, I want a short summary of what a company does and its
technology tags when available.

#### Acceptance criteria
1. The system SHALL derive technology tags from available text (e.g. the registry
   description): recognizable categories such as AI, Cloud, Data, Cybersecurity,
   Web, SaaS. Where a source does not expose a real tech stack (e.g. Zefix exposes
   only the legal purpose), only what is explicitly mentioned is extracted.
2. The system SHALL NOT invent descriptions or tags: absent a source, the field
   stays empty.

### Requirement 5b — IT-adjacent companies (non-IT with a relevant IT arm)
**User story:** As a user, I want to also discover companies that are not IT by
sector but have a significant technology arm (e.g. energy, large banks), kept on a
**separate map** from IT-native ones.

#### Acceptance criteria
1. The system SHALL classify each company as `it_native` (IT sector by NACE 62/63)
   or `it_adjacent` (other sector but with an IT arm of interest).
2. A company is `it_adjacent` ONLY given a **strong signal** of internal IT
   activity: an active ATS board (Greenhouse/Lever/Ashby) with tech roles, or a
   verifiable digital division/subsidiary.
3. The system SHALL NOT classify as `it_adjacent` based on generic marketing
   language ("digital transformation" and the like).
4. `it_adjacent` companies SHALL pass the Requirement 3 filters and SHALL be only
   **large or multinational** (`medium` is allowed only among `it_native`).
5. Large banks and multinationals with strong internal IT ARE allowed as
   `it_adjacent`; fintech and trading firms are excluded for now.
6. WHEN a company is `it_adjacent` THEN the system SHALL record the signal that
   justified inclusion.
7. `it_adjacent` companies SHALL be produced in a **separate map and outputs** from
   `it_native`, sharing the same data schema.

### Requirement 6 — Persistence and deduplication
**User story:** As a user, I want a history of companies without duplicates, so the
map grows over time.

#### Acceptance criteria
1. The system SHALL store companies and locations in a local SQLite database.
2. WHEN a company already exists THEN the system SHALL recognize it as a duplicate
   via stable identifiers (registry ID / VAT / domain).
3. WHEN a company's data changes THEN the system SHALL update it keeping history
   rather than duplicating.
4. The system SHALL record `first_seen` and `last_seen` per company.
5. WHEN the pipeline is re-run THEN the system SHALL work incrementally,
   classifying each company as **new**, **updated** or **unchanged**.
6. Data updates happen **only on a manual run**; the system SHALL NOT schedule
   automatic runs.

### Requirement 7 — Map and data outputs
**User story:** As a user, I want to browse companies on a map from desktop or
phone, even as the database grows.

#### Acceptance criteria
1. The system SHALL generate **GeoJSON** files as map data sources, separate for
   `it_native` and `it_adjacent`.
2. The system SHALL generate **CSV** exports (separate per class) with key fields.
3. The system SHALL generate **two separate static HTML maps** (it_native and
   it_adjacent) showing locations with a per-company card (name, class, employees,
   summary, tech tags, locations, link; for it_adjacent also the IT inclusion
   signal).
4. The map SHALL stay usable with many companies.
5. The map SHALL work with no backend, no paid services and **no API keys**,
   openable on desktop and phone **with a double click** (`file://`): the GeoJSON
   is **embedded inline** in the HTML, not loaded via external `fetch`. By default
   it uses a **neutral offline background** (no external tiles, no provider that
   could block access).
6. IF the user wants a street-map background THEN they MAY optionally provide
   their own tile key (e.g. MapTiler) in configuration; without a key the neutral
   offline background remains.
7. GeoJSON/CSV SHALL be UTF-8 with stable fields.
8. The output SHALL highlight **changes since the last run** (new and updated
   companies).

### Requirement 8 — Interchange with a job-search tool
**User story:** As a user, I want discovered companies to feed a job-search tool,
to follow their postings.

#### Acceptance criteria
1. The system SHALL export a companies file with at least: name, domains,
   locations and optional ATS slug, in a shared format.
2. The format SHALL be consumable as a list of career/ATS sources.
3. The projects stay separate: no mandatory runtime dependency, file exchange only.

### Requirement 9 — No automated external actions
**User story:** As a user, I want the tool to only map, without contacting anyone.

#### Acceptance criteria
1. The system SHALL NOT send emails, messages or applications.
2. The system SHALL NOT transmit data to third parties beyond the queries needed
   by authorized sources.

### Requirement 10 — Configuration and observability
**User story:** As a user, I want to configure area, thresholds and sources and
understand what happened on each run.

#### Acceptance criteria
1. Geographic area, IT sector codes, size threshold, startup signals,
   consulting/staffing exclusion lists and sources (credentials via env) SHALL be
   defined in versionable configuration.
2. The system SHALL produce a per-run log with sources queried, companies found,
   excluded (with reason), new, updated and duplicate.
3. The system SHALL be runnable from the CLI with a single command performing
   discovery, enrichment, persistence and output generation.
