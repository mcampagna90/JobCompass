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

## What is JobCompass?

JobCompass helps you **discover and map companies** from official public business
registries, so you can find employers you did not even know existed — then explore
them on an interactive map with your own filters.

It is built for job seekers who want to go beyond job boards: instead of waiting
for postings, you map the companies that match **your** criteria (sector, size,
location, technology) and decide where to aim.

Although the shipped examples target IT companies, JobCompass is **not IT-only**:
the sector keywords, size thresholds, exclusions and areas are all configurable,
so you can point it at any industry you like.

## Key features

- 🔎 **Discovery from official registries** — France (INSEE SIRENE) and
  Switzerland (Zefix via LINDAS/SPARQL), both free. No scraping of search engines
  or sites that forbid it.
- 🗺️ **Interactive map** — standalone HTML you can open with a double click, no
  server, no API key. Colored tags for size, technology, status and more.
- 🎯 **Your own filters** — sector codes, employee thresholds, cities/regions,
  legal forms, and exclusion lists (consulting, staffing, tobacco, gambling…).
- 🏷️ **Technology tags** — extracted from public descriptions (AI, Cloud, Data,
  Cybersecurity, Web, SaaS…).
- 🏢 **Two views** — IT-native companies and "IT-adjacent" ones (non-IT firms with
  a strong internal tech arm), on separate maps.
- 💾 **History & deduplication** — SQLite storage, incremental runs that show
  what's new or changed since last time.
- 🤝 **Interchange export** — hand off discovered companies to a job-search tool.

## Ethical by design

JobCompass is deliberately conservative:

- Only **authorized sources**: official registry APIs, open data, and public
  websites within `robots.txt`.
- **No** bypassing of logins, CAPTCHAs or terms of use.
- **No** aggressive scraping — rate limits and an identifiable User-Agent.
- **No** automated outreach, messaging or applications.
- Missing data is **marked as missing, never fabricated**.
- Paid providers are shipped **preconfigured but disabled** — free by default.

## Technologies

- **Python 3.11+**
- [requests](https://pypi.org/project/requests/) — HTTP client
- [PyYAML](https://pypi.org/project/PyYAML/) — configuration
- [Leaflet](https://leafletjs.com/) — maps (bundled locally, no CDN)
- **SPARQL** over [LINDAS](https://lindas.admin.ch/) for Swiss company data
- [INSEE SIRENE API](https://www.insee.fr/) for French company data
- [OpenStreetMap / Nominatim](https://nominatim.org/) for geocoding
- **SQLite** for storage

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
- `it_native.{geojson,csv,html}` — IT companies
- `it_adjacent.{geojson,csv,html}` — non-IT companies with a tech arm
- `companies_interchange.json` — export for a job-search tool

Open `output/it_native.html` in your browser (double click works).

### Enabling France (SIRENE)

1. Create a free account on the INSEE API portal and subscribe to the Sirene API.
2. Export your key and enable the source:
   ```bash
   export INSEE_API_KEY="your-key"
   ```
   Set `enabled: true` under the SIRENE source in `config.yaml`. Confirm the exact
   header name and endpoint version on your portal subscription.

## Configuration

All behaviour lives in `config.yaml` (copy from `config.example.yaml`).
Credentials come from environment variables — never commit them. See
[`docs/`](docs/) for the full requirements and design.

### Customizing filters

JobCompass is designed to be adapted to **your** search, not just the shipped IT
example. Every filter is configurable:

- **Sector** — `sectors.it_prefixes` lists the activity codes (NACE/national) that
  count as "in scope". The default targets software/IT (`62`, `63`), but you can
  point it at any industry by changing these codes. For sources without codes
  (e.g. Zefix), use the per-source `it_keywords` / `it_negatives` lists to match
  on the description text instead.
  ```yaml
  sectors:
    it_prefixes: ["62", "63"]        # e.g. swap for your industry's codes
  ```
- **Size** — `filters.size_threshold` excludes companies below a given employee
  count (default ~250). Only applies where the source exposes headcount.
- **Geography** — per-source `regions`, `cities`, `departments` narrow the area.
- **Legal form** — per-source `legal_forms` (e.g. `["SA", "AG"]`) keeps only
  certain company types.
- **Exclusions** — `filters.exclusion_keywords` (consulting/staffing),
  `filters.blocklist_sector_prefixes` (e.g. tobacco, gambling) and
  `filters.startup_signals`. All are plain lists you can extend or empty out.
- **IT-adjacent** — `it_adjacent.allowed_size_classes` and
  `finance_exclude_keywords` control which non-IT firms qualify.

Nothing is hard-coded: empty a list to disable a filter, or extend it to be
stricter. The tool is not limited to IT or to France/Switzerland — those are just
the examples that ship with it.

### Adding your own sources

You are not limited to the bundled sources. You can add your own under `sources:`
in `config.yaml`. JobCompass supports official registry APIs, SPARQL endpoints and
open-data feeds. Point it at any data source you are **authorized** to use:

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

Mapping a brand-new API shape may require a small adapter in
`src/jobcompass/discoverers.py` — contributions welcome.

## Limits and responsible use

JobCompass connects to **official APIs and open data**, not by scraping sites that
forbid it. When you add your own sources, the same rules apply — they are there to
keep you (and the data providers) safe:

- **Use authorized sources only.** Official/public APIs, open data, or services you
  have valid credentials for. Do not point JobCompass at endpoints whose terms
  forbid automated access.
- **Respect `robots.txt` and terms of use.** The HTTP client checks `robots.txt`
  and skips disallowed URLs; keep that behaviour on.
- **Respect rate limits.** `rate_limit_seconds` throttles requests and the client
  retries with backoff. Do not lower it to hammer a provider.
- **Identify yourself.** Requests send an honest `User-Agent`; keep it meaningful.
- **No bypassing.** JobCompass does not and should not circumvent logins, CAPTCHAs
  or paywalls. There is deliberately no headless-browser evasion.
- **Keep credentials out of git.** API keys go in environment variables; `.gitignore`
  excludes `config.yaml`, databases and outputs.

These are not arbitrary restrictions: they are what makes the tool lawful to run.
Adding a source is easy, but you remain responsible for using each provider within
its terms.

## Limitations (honest notes)

- **Switzerland (Zefix):** free and keyless, but exposes no NACE code or headcount.
  The IT-sector filter is a **keyword heuristic** on the legal purpose, so expect
  some false positives/negatives, and size class is usually `unknown`.
- **France (SIRENE):** needs a free API key; INSEE has changed header/endpoint over
  time, so confirm them on the portal.
- **Italy:** no complete free registry API — coverage needs a paid provider.
- **Map background:** neutral offline canvas by default; a street map requires your
  own tile key.

## License

[MIT](LICENSE) © JobCompass contributors.
