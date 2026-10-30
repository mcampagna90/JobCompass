"""Output writers: GeoJSON, CSV, standalone HTML maps and interchange export.

Separate outputs for it_native and it_adjacent. Static map, no backend: Leaflet
served locally from output/vendor (no CDN), GeoJSON embedded inline so the map
works when opened directly (file://). Highlights changes since the last run.
"""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from .models import Company, DiscoveredCompany, ItClass

# Leaflet assets bundled in the package, copied to output/vendor so the map is
# self-contained (no CDN; works offline and inside IDE previews).
_VENDOR_DIR = Path(__file__).parent / "vendor"


def _copy_vendor(out: Path) -> None:
    dest = out / "vendor"
    dest.mkdir(parents=True, exist_ok=True)
    if _VENDOR_DIR.exists():
        for asset in _VENDOR_DIR.iterdir():
            if asset.is_file():
                shutil.copy2(asset, dest / asset.name)


_CSV_HEADERS = [
    "name", "country", "size_class", "employees_approx", "it_class",
    "it_signal", "sectors", "stack", "ats_slug", "locations", "state",
]


def write_outputs(discovered: list[DiscoveredCompany], output_dir: str) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    _copy_vendor(out)

    native = [d for d in discovered if d.company.it_class == ItClass.IT_NATIVE]
    adjacent = [d for d in discovered if d.company.it_class == ItClass.IT_ADJACENT]

    paths: dict[str, str] = {}
    for label, group in (("it_native", native), ("it_adjacent", adjacent)):
        geojson_path = out / f"{label}.geojson"
        csv_path = out / f"{label}.csv"
        html_path = out / f"{label}.html"
        geojson_data = _to_geojson(group)
        geojson_path.write_text(json.dumps(geojson_data, ensure_ascii=False, indent=2),
                                encoding="utf-8")
        _write_csv(csv_path, group)
        # GeoJSON is embedded inline in the HTML so the map works when opened with
        # a double click (file://), where fetch() of an external file is blocked.
        html_path.write_text(_html_map(label, geojson_data), encoding="utf-8")
        paths[f"{label}_geojson"] = str(geojson_path)
        paths[f"{label}_csv"] = str(csv_path)
        paths[f"{label}_html"] = str(html_path)
    return paths


def _in_liquidation(name: str | None) -> bool:
    n = (name or "").lower()
    return "liquidazione" in n or "liquidation" in n


def _to_geojson(group: list[DiscoveredCompany]) -> dict:
    features = []
    for d in group:
        c = d.company
        for loc in c.locations:
            if loc.lat is None or loc.lon is None:
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [loc.lon, loc.lat]},
                "properties": {
                    "name": c.name,
                    "size_class": c.size_class.value,
                    "employees": c.employees_approx,
                    "it_class": c.it_class.value,
                    "it_signal": c.it_signal,
                    "summary": c.business_summary,
                    "stack": ", ".join(c.tech_stack),
                    "address": loc.address,
                    "change_state": d.change_state,
                    "in_liquidation": _in_liquidation(c.name),
                    "website": c.domains[0] if c.domains else None,
                },
            })
    return {"type": "FeatureCollection", "features": features}


def _write_csv(path: Path, group: list[DiscoveredCompany]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(_CSV_HEADERS)
        for d in group:
            c = d.company
            w.writerow([
                c.name, c.country, c.size_class.value, c.employees_approx or "",
                c.it_class.value, c.it_signal or "", ", ".join(c.sector_codes),
                ", ".join(c.tech_stack), c.ats_slug or "",
                " | ".join(l.address for l in c.locations), d.change_state,
            ])


def _html_map(title: str, geojson_data: dict) -> str:
    # Standalone OFFLINE map: Leaflet (local), circle markers, GeoJSON inline.
    # Colored tags: liquidation=red, it_adjacent=purple, size=green, tech=blue,
    # new=orange. Includes a search box filtering the side list.
    geojson_inline = json.dumps(geojson_data, ensure_ascii=False)
    n = len(geojson_data.get("features", []))
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>JobCompass — {title}</title>
<link rel="stylesheet" href="vendor/leaflet.css"/>
<style>
  :root{{--blue:#2563eb;--green:#16a34a;--purple:#7c3aed;--red:#dc2626;--orange:#ea580c}}
  html,body{{height:100%;margin:0;font-family:'Segoe UI',Helvetica,Arial,sans-serif;color:#0f172a}}
  #wrap{{display:flex;height:100%}}
  #map{{flex:1;background:#eef1f4}}
  #side{{width:340px;display:flex;flex-direction:column;border-left:1px solid #e2e8f0}}
  #head{{padding:12px 14px;border-bottom:1px solid #e2e8f0}}
  #head h1{{font-size:16px;margin:0 0 2px}}
  #head .sub{{font-size:12px;color:#64748b}}
  #search{{width:100%;box-sizing:border-box;margin-top:8px;padding:7px 10px;
    border:1px solid #cbd5e1;border-radius:8px;font-size:13px}}
  #list{{overflow:auto;flex:1}}
  .item{{padding:9px 14px;border-bottom:1px solid #f1f5f9;cursor:pointer}}
  .item:hover{{background:#f8fafc}}
  .item b{{display:block;color:var(--blue);font-size:13px}}
  .item .addr{{display:block;font-size:11px;color:#94a3b8;margin:1px 0 4px}}
  .tag{{display:inline-block;border-radius:10px;padding:1px 8px;font-size:11px;
    margin:2px 4px 0 0;font-weight:600}}
  .t-tech{{background:#dbeafe;color:var(--blue)}}
  .t-size{{background:#dcfce7;color:var(--green)}}
  .t-adj{{background:#ede9fe;color:var(--purple)}}
  .t-liq{{background:#fee2e2;color:var(--red)}}
  .t-new{{background:#ffedd5;color:var(--orange)}}
  .leaflet-popup-content{{font-family:inherit}}
</style>
</head><body>
<div id="wrap">
  <div id="map"></div>
  <div id="side">
    <div id="head">
      <h1>JobCompass — {title}</h1>
      <div class="sub">{n} companies · click a marker or list item</div>
      <input id="search" placeholder="Filter by name, tag, city…"/>
    </div>
    <div id="list"></div>
  </div>
</div>
<script src="vendor/leaflet.js"></script>
<script>
const data = {geojson_inline};
const map = L.map('map').setView([46.8, 8.2], 8);
const bounds = [];
const entries = [];

function tagsHtml(p) {{
  let html = '';
  if (p.in_liquidation) html += '<span class="tag t-liq">in liquidation</span>';
  if (p.it_class === 'it_adjacent') html += '<span class="tag t-adj">IT-adjacent</span>';
  if (p.size_class && p.size_class !== 'sconosciuta')
    html += '<span class="tag t-size">' + p.size_class + '</span>';
  if (p.change_state === 'new') html += '<span class="tag t-new">new</span>';
  (p.stack||'').split(',').map(s=>s.trim()).filter(Boolean)
    .forEach(t => html += '<span class="tag t-tech">' + t + '</span>');
  return html || '<span style="color:#cbd5e1;font-size:11px">no tags</span>';
}}

data.features.forEach(f => {{
  const c = f.geometry.coordinates;        // [lon, lat]
  const latlng = [c[1], c[0]];
  const p = f.properties;
  const color = p.in_liquidation ? '#dc2626'
    : (p.it_class === 'it_adjacent' ? '#7c3aed' : '#2563eb');
  const m = L.circleMarker(latlng, {{radius:8, color:color, weight:2,
    fillColor:color, fillOpacity:0.55}}).addTo(map);
  const site = p.website ? '<br><a href="'+p.website+'" target="_blank">'+p.website+'</a>' : '';
  m.bindPopup('<b>'+(p.name||'')+'</b><br><span style="color:#64748b">'
    +(p.address||'')+'</span>'+site
    +(p.it_signal?'<br><i>'+p.it_signal+'</i>':'')+'<br>'+tagsHtml(p), {{maxWidth:280}});
  bounds.push(latlng);

  const div = document.createElement('div');
  div.className = 'item';
  div.innerHTML = '<b>'+(p.name||'')+'</b><span class="addr">'+(p.address||'')+'</span>'+tagsHtml(p);
  div.onclick = () => {{ map.setView(latlng, 15); m.openPopup(); }};
  document.getElementById('list').appendChild(div);
  entries.push({{el:div, text:((p.name||'')+' '+(p.address||'')+' '+(p.stack||'')
    +' '+(p.size_class||'')).toLowerCase()}});
}});

if (bounds.length) map.fitBounds(bounds, {{maxZoom:12, padding:[30,30]}});

document.getElementById('search').addEventListener('input', e => {{
  const q = e.target.value.toLowerCase();
  entries.forEach(en => en.el.style.display = en.text.includes(q) ? '' : 'none');
}});
</script>
</body></html>
"""


def export_interchange(discovered: list[DiscoveredCompany], output_dir: str) -> str:
    """Interchange file for the job-search side (Requirement 8.1): name, domains,
    locations, ATS slug."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "companies_interchange.json"
    payload = []
    for d in discovered:
        c = d.company
        payload.append({
            "name": c.name,
            "domains": c.domains,
            "ats_slug": c.ats_slug,
            "it_class": c.it_class.value,
            "locations": [{"address": l.address, "country": l.country,
                           "region": l.region} for l in c.locations],
        })
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
