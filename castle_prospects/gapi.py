"""Thin Google Maps Platform client (Places API (New) + Routes API) with a disk cache.

Every request body is hashed and its response cached under cache/google/, so a
re-run only pays for requests it has not made before. Pass refresh=True to
ignore the cache.
"""
import hashlib
import json
import math
import os
import time

import requests

from . import config

PLACES_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
ROUTE_MATRIX_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"


def load_api_key():
    """Read the key from .env first, then the environment. Never log it."""
    if config.ENV_FILE.exists():
        for line in config.ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(config.API_KEY_VAR + "="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    value = os.environ.get(config.API_KEY_VAR, "").strip()
    if value:
        return value
    raise SystemExit(
        f"No API key found. Put {config.API_KEY_VAR}=... in {config.ENV_FILE} "
        f"(see .env.example) or set the {config.API_KEY_VAR} environment variable."
    )


class ServiceBlocked(RuntimeError):
    """The API key is not allowed to call this Google API."""


def estimate_drive_minutes(origin, dest):
    """Straight-line distance x road factor at an average speed (see config)."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*origin, *dest))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    km = 12742 * math.asin(math.sqrt(h))
    return round(km * config.ROAD_FACTOR / config.AVG_SPEED_KMH * 60, 1)


class GoogleClient:
    def __init__(self, api_key=None, refresh=False):
        self.api_key = api_key or load_api_key()
        self.refresh = refresh
        self.cache_dir = config.CACHE_DIR / "google"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.calls = {"text_search": 0, "route_elements": 0, "cache_hits": 0}
        self.drive_source = "google"   # becomes "estimated" if the Routes API is blocked

    def _post(self, url, body, field_mask):
        key = hashlib.sha256(json.dumps([url, body, field_mask], sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists() and not self.refresh:
            self.calls["cache_hits"] += 1
            return json.loads(path.read_text())
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": field_mask,
        }
        for attempt in range(5):
            resp = self.session.post(url, json=body, headers=headers, timeout=60)
            if resp.status_code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            break
        if resp.status_code == 403 and "API_KEY_SERVICE_BLOCKED" in resp.text:
            raise ServiceBlocked(url)
        if resp.status_code != 200:
            # Error bodies from Google never echo the key, so they are safe to show.
            raise RuntimeError(f"Google API error {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        path.write_text(json.dumps(data))
        return data

    def text_search(self, query, center=None, radius=None, rectangle=None,
                    page_size=20, page_token=None, field_mask=config.TEXT_SEARCH_FIELDS):
        body = {"textQuery": query, "pageSize": page_size, "languageCode": "en", "regionCode": "US"}
        if rectangle:
            body["locationRestriction"] = {"rectangle": rectangle}
        elif center:
            body["locationBias"] = {"circle": {
                "center": {"latitude": center[0], "longitude": center[1]},
                "radius": float(min(radius or 50_000, 50_000)),
            }}
        if page_token:
            body["pageToken"] = page_token
        before = self.calls["cache_hits"]
        data = self._post(PLACES_TEXT_URL, body, field_mask)
        if self.calls["cache_hits"] == before:
            self.calls["text_search"] += 1
        return data

    def geocode_origin(self, address):
        data = self.text_search(address, page_size=1,
                                field_mask="places.formattedAddress,places.location")
        place = (data.get("places") or [None])[0]
        if not place:
            raise SystemExit(f"Could not locate clinic address: {address}")
        loc = place["location"]
        return (loc["latitude"], loc["longitude"]), place["formattedAddress"]

    def drive_minutes(self, origin, destinations, batch=100):
        """Drive time in minutes from origin to each (lat, lng); None if no route.

        Uses TRAFFIC_UNAWARE (typical free-flow time), which is stable between runs.
        If the key cannot use the Routes API, falls back to estimate_drive_minutes
        and sets self.drive_source to "estimated".
        """
        if self.drive_source == "estimated":
            return [estimate_drive_minutes(origin, d) for d in destinations]
        try:
            return self._route_matrix(origin, destinations, batch)
        except ServiceBlocked:
            print("  Routes API is blocked for this key; estimating drive time from distance instead")
            self.drive_source = "estimated"
            return [estimate_drive_minutes(origin, d) for d in destinations]

    def _route_matrix(self, origin, destinations, batch):
        results = [None] * len(destinations)
        for start in range(0, len(destinations), batch):
            chunk = destinations[start:start + batch]
            body = {
                "origins": [{"waypoint": {"location": {"latLng": {"latitude": origin[0], "longitude": origin[1]}}}}],
                "destinations": [
                    {"waypoint": {"location": {"latLng": {"latitude": lat, "longitude": lng}}}}
                    for lat, lng in chunk
                ],
                "travelMode": "DRIVE",
                "routingPreference": "TRAFFIC_UNAWARE",
            }
            before = self.calls["cache_hits"]
            data = self._post(ROUTE_MATRIX_URL, body,
                              "originIndex,destinationIndex,duration,distanceMeters,condition,status")
            if self.calls["cache_hits"] == before:
                self.calls["route_elements"] += len(chunk)
            for el in data:
                idx = el.get("destinationIndex", 0)
                if el.get("condition") == "ROUTE_EXISTS" and "duration" in el:
                    secs = float(el["duration"].rstrip("s"))
                    results[start + idx] = round(secs / 60.0, 1)
        return results
