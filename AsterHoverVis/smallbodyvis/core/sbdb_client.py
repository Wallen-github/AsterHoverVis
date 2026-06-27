'''
@File        : smallbodyvis/core/sbdb_client.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

JPL Small-Body Database physical-parameter client with local caching.
'''

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from smallbodyvis.core.constants import GRAVITATIONAL_CONSTANT, SBDB_CACHE_DIR
from smallbodyvis.core.models import SmallBodyProperties, spherical_volume_from_radius


SBDB_API_URL = "https://ssd-api.jpl.nasa.gov/sbdb.api"


class SBDBError(RuntimeError):
    """Raised when SBDB data cannot be downloaded or parsed."""


def safe_cache_stem(query: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", query.strip().lower()).strip("_")
    return stem or "small_body"


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"n.a.", "na", "nan", "null"}:
        return None
    match = re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", text)
    if not match:
        return None
    return float(match.group(0))


def _param_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in payload.get("phys_par") or []:
        name = item.get("name")
        if name:
            result[str(name).lower()] = item
    return result


def _physical_value(params: dict[str, dict[str, Any]], name: str) -> tuple[float | None, str]:
    item = params.get(name.lower())
    if not item:
        return None, ""
    return _parse_float(item.get("value")), str(item.get("units") or "")


def parse_sbdb_properties(
    payload_or_wrapper: dict[str, Any],
    *,
    query: str,
    cache_path: Path | None = None,
) -> SmallBodyProperties:
    """Convert raw SBDB JSON into normalized SI-unit physical properties."""
    payload = payload_or_wrapper.get("payload", payload_or_wrapper)
    if "object" not in payload:
        message = payload.get("message") or payload.get("error") or "missing object data"
        raise SBDBError(f"SBDB response did not contain an object: {message}")

    params = _param_map(payload)
    diameter, diameter_units = _physical_value(params, "diameter")
    gm, gm_units = _physical_value(params, "gm")
    density, density_units = _physical_value(params, "density")
    rot_per, rot_units = _physical_value(params, "rot_per")
    albedo, _ = _physical_value(params, "albedo")
    h_mag, _ = _physical_value(params, "h")

    diameter_m = None
    if diameter is not None:
        diameter_m = diameter * 1000.0 if "km" in diameter_units.lower() else diameter

    gm_m3_s2 = None
    if gm is not None:
        gm_m3_s2 = gm * 1.0e9 if "km" in gm_units.lower() else gm

    density_kg_m3 = None
    if density is not None:
        if "g/cm" in density_units.lower():
            density_kg_m3 = density * 1000.0
        else:
            density_kg_m3 = density

    rotation_period_s = None
    if rot_per is not None:
        rotation_period_s = rot_per * 3600.0 if rot_units.lower() == "h" else rot_per

    radius_m = 0.5 * diameter_m if diameter_m is not None else None
    mass_kg = gm_m3_s2 / GRAVITATIONAL_CONSTANT if gm_m3_s2 is not None else None
    if mass_kg is None and radius_m is not None and density_kg_m3 is not None:
        mass_kg = (4.0 / 3.0) * 3.141592653589793 * radius_m**3 * density_kg_m3
        gm_m3_s2 = GRAVITATIONAL_CONSTANT * mass_kg
    if density_kg_m3 is None and mass_kg is not None:
        volume = spherical_volume_from_radius(radius_m)
        if volume is not None:
            density_kg_m3 = mass_kg / volume

    obj = payload.get("object", {})
    return SmallBodyProperties(
        query=query,
        full_name=str(obj.get("fullname") or obj.get("des") or query),
        spkid=str(obj.get("spkid") or ""),
        source="JPL SBDB",
        cache_path=cache_path,
        diameter_m=diameter_m,
        radius_m=radius_m,
        gm_m3_s2=gm_m3_s2,
        mass_kg=mass_kg,
        density_kg_m3=density_kg_m3,
        rotation_period_s=rotation_period_s,
        albedo=albedo,
        h_magnitude=h_mag,
    )


class SBDBClient:
    """Download and cache SBDB object data."""

    def __init__(self, cache_dir: str | Path = SBDB_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def cache_path_for_query(self, query: str) -> Path:
        return self.cache_dir / f"{safe_cache_stem(query)}_sbdb.json"

    def load_cached(self, query: str) -> SmallBodyProperties:
        cache_path = self.cache_path_for_query(query)
        if not cache_path.exists():
            raise FileNotFoundError(cache_path)
        with cache_path.open("r", encoding="utf-8") as handle:
            wrapper = json.load(handle)
        return parse_sbdb_properties(wrapper, query=query, cache_path=cache_path)

    def fetch(self, query: str, *, force: bool = False, timeout: float = 30.0) -> SmallBodyProperties:
        cache_path = self.cache_path_for_query(query)
        if cache_path.exists() and not force:
            return self.load_cached(query)

        params = {
            "sstr": query,
            "phys-par": "1",
            "full-prec": "1",
            "alt-des": "1",
        }
        url = f"{SBDB_API_URL}?{urlencode(params)}"
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))

        if "list" in payload:
            raise SBDBError(
                "SBDB query matched multiple objects. Use a more specific designation."
            )
        if payload.get("code") and str(payload.get("code")) != "200":
            raise SBDBError(str(payload.get("message") or payload))

        wrapper = {
            "query": query,
            "url": url,
            "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "signature": payload.get("signature"),
            "payload": payload,
        }
        with cache_path.open("w", encoding="utf-8") as handle:
            json.dump(wrapper, handle, indent=2, sort_keys=True)

        return parse_sbdb_properties(wrapper, query=query, cache_path=cache_path)
