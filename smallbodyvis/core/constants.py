'''
@File        : smallbodyvis/core/constants.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Static catalog entries used by the v0 UI.
'''

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = PACKAGE_ROOT / "assets"
DATA_DIR = PACKAGE_ROOT / "data"
SBDB_CACHE_DIR = DATA_DIR / "sbdb_cache"
SUN_GEOMETRY_CACHE_DIR = DATA_DIR / "sun_geometry_cache"
DEFAULT_PERIAPSIS_UTC = "2029-04-13T21:46:00+00:00"
OFFLINE_APOPHIS_EARTH_SUN_FILE = ASSET_DIR / "jpl_apophis_earth_sun_2029_flyby_10min.npz"


@dataclass(frozen=True)
class SmallBodyPreset:
    label: str
    jpl_query: str
    obj_path: Path
    default_mu_m3_s2: float | None = None


@dataclass(frozen=True)
class CentralBody:
    name: str
    horizons_id: str
    mu_m3_s2: float
    radius_m: float
    color: str


SMALL_BODY_PRESETS: dict[str, SmallBodyPreset] = {
    "Apophis": SmallBodyPreset(
        label="Apophis",
        jpl_query="99942",
        obj_path=ASSET_DIR / "apophis_v233s7_vert2_new.obj",
        default_mu_m3_s2=2.6,
    ),
}


CENTRAL_BODIES: dict[str, CentralBody] = {
    "Mercury": CentralBody("Mercury", "199", 2.2032e13, 2_439_700.0, "#9c8c7c"),
    "Venus": CentralBody("Venus", "299", 3.24859e14, 6_051_800.0, "#d2a85f"),
    "Earth": CentralBody("Earth", "399", 3.986004418e14, 6_378_136.3, "#3d7edb"),
    "Mars": CentralBody("Mars", "499", 4.282837e13, 3_396_190.0, "#b95f3b"),
    "Jupiter": CentralBody("Jupiter", "599", 1.26686534e17, 71_492_000.0, "#d2b48c"),
    "Saturn": CentralBody("Saturn", "699", 3.7931187e16, 60_268_000.0, "#dbc07a"),
    "Uranus": CentralBody("Uranus", "799", 5.793939e15, 25_559_000.0, "#76c6d3"),
    "Neptune": CentralBody("Neptune", "899", 6.836529e15, 24_764_000.0, "#456bd8"),
}


GRAVITATIONAL_CONSTANT = 6.67430e-11
