"""Location geocoder via OSM/Nominatim (Requirement 4.2, 4.3), with local cache.

Unresolvable -> coordinates None, address kept. Respects Nominatim terms (rate
limit, identifiable User-Agent).
"""

from __future__ import annotations

import json

from .http_client import HttpClient
from .models import Location

_NOMINATIM = "https://nominatim.openstreetmap.org/search"


class Geocoder:
    def __init__(self, client: HttpClient, enabled: bool = True):
        self.client = client
        self.enabled = enabled
        self._cache: dict[str, tuple[float, float] | None] = {}

    def geocode(self, location: Location) -> Location:
        if location.lat is not None and location.lon is not None:
            return location
        if not self.enabled or not location.address:
            return location
        coords = self._lookup(location.address)
        if coords:
            location.lat, location.lon = coords
        return location

    def _lookup(self, address: str) -> tuple[float, float] | None:
        if address in self._cache:
            return self._cache[address]
        result = None
        try:
            text = self.client.get(
                _NOMINATIM,
                params={"q": address, "format": "json", "limit": 1},
                check_robots=False,
            )
            data = json.loads(text)
            if data:
                result = (float(data[0]["lat"]), float(data[0]["lon"]))
        except Exception:
            result = None
        self._cache[address] = result
        return result
