'''
@File        : smallbodyvis/core/sun_geometry.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

JPL/Horizons Sun direction helpers for scene annotations.
'''

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np

from smallbodyvis.core.constants import (
    DEFAULT_PERIAPSIS_UTC,
    OFFLINE_APOPHIS_EARTH_SUN_FILE,
    SUN_GEOMETRY_CACHE_DIR,
    CentralBody,
)
from smallbodyvis.core.models import SimulationInputs, SmallBodyProperties


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
DAY_TO_S = 86400.0
KM_TO_M = 1000.0

FALLBACK_BODY_TO_SUN_RTN = np.array([1.0, -0.25, 0.10], dtype=float)


@dataclass(frozen=True)
class SunGeometry:
    sample_f: np.ndarray
    labels: tuple[str, str, str]
    body_to_sun_rtn: np.ndarray
    sun_to_body_rtn: np.ndarray
    jd: np.ndarray
    true_anomaly: np.ndarray
    body_to_sun_epochs_rtn: np.ndarray
    source: str


def normalize_rows(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    norms = np.linalg.norm(array, axis=1)
    output = np.zeros_like(array)
    valid = norms > 0.0
    output[valid] = array[valid] / norms[valid, None]
    return output


def parse_utc(value: str) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def datetime_to_jd(value: datetime) -> float:
    return value.timestamp() / DAY_TO_S + 2440587.5


def jd_to_datetime(jd: float) -> datetime:
    timestamp = (float(jd) - 2440587.5) * DAY_TO_S
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def true_anomaly_to_seconds(
    f: float | np.ndarray,
    *,
    central_mu_m3_s2: float,
    orbit_q_m: float,
    orbit_eccentricity: float,
) -> np.ndarray:
    f_array = np.asarray(f, dtype=float)
    argument = np.sqrt(
        (orbit_eccentricity - 1.0) / (orbit_eccentricity + 1.0)
    ) * np.tan(f_array / 2.0)
    if np.any(np.abs(argument) >= 1.0):
        raise ValueError("True anomaly is outside the finite hyperbola.")
    H = 2.0 * np.arctanh(argument)
    semi_major_magnitude = orbit_q_m / (orbit_eccentricity - 1.0)
    mean_motion = np.sqrt(central_mu_m3_s2 / semi_major_magnitude**3)
    return (orbit_eccentricity * np.sinh(H) - H) / mean_motion


def horizons_command_for_small_body(properties: SmallBodyProperties) -> str:
    query = properties.query.strip()
    if query.isdigit():
        return f"{query};"
    return query


def is_default_apophis_earth(
    small_body: SmallBodyProperties,
    central_body: CentralBody,
) -> bool:
    query = small_body.query.strip().lower()
    return central_body.name == "Earth" and query in {"99942", "apophis"}


def _horizons_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_vectors(payload: str) -> tuple[np.ndarray, np.ndarray]:
    try:
        text = json.loads(payload)["result"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError("Unexpected response from JPL Horizons.") from exc

    if "$$SOE" not in text or "$$EOE" not in text:
        message = text.strip().splitlines()[-1] if text.strip() else "empty response"
        raise RuntimeError(f"Horizons did not return vector data: {message}")

    table = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]
    epochs, states = [], []
    for row in csv.reader(io.StringIO(table)):
        fields = [item.strip() for item in row if item.strip()]
        if len(fields) < 8:
            continue
        try:
            epochs.append(float(fields[0]))
            states.append([float(value) for value in fields[2:8]])
        except ValueError:
            continue
    if len(epochs) < 2:
        raise RuntimeError("Could not parse enough Horizons vector samples.")

    state = np.asarray(states, dtype=float)
    state[:, :3] *= KM_TO_M
    state[:, 3:] *= KM_TO_M
    return np.asarray(epochs, dtype=float), state


def download_vectors(
    command: str,
    *,
    start: datetime,
    stop: datetime,
    step_size: str = "10 min",
    timeout: float = 30.0,
) -> tuple[np.ndarray, np.ndarray]:
    params = {
        "format": "json",
        "COMMAND": f"'{command}'",
        "OBJ_DATA": "'NO'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
        "CENTER": "'@0'",
        "START_TIME": f"'{_horizons_time(start)}'",
        "STOP_TIME": f"'{_horizons_time(stop)}'",
        "STEP_SIZE": f"'{step_size}'",
        "TIME_TYPE": "'TDB'",
        "REF_SYSTEM": "'ICRF'",
        "REF_PLANE": "'FRAME'",
        "OUT_UNITS": "'KM-S'",
        "VEC_TABLE": "'2'",
        "VEC_CORR": "'NONE'",
        "CSV_FORMAT": "'YES'",
        "VEC_LABELS": "'NO'",
    }
    url = f"{HORIZONS_API_URL}?{urlencode(params)}"
    with urlopen(url, timeout=timeout) as response:
        payload = response.read().decode("utf-8")
    return _parse_vectors(payload)


def interpolate_state(jd: np.ndarray, states: np.ndarray, query_jd: np.ndarray) -> np.ndarray:
    return np.column_stack(
        [np.interp(query_jd, jd, states[:, column]) for column in range(states.shape[1])]
    )


def cache_key(data: dict[str, Any]) -> str:
    encoded = json.dumps(data, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def fallback_sun_geometry(sample_f: np.ndarray, source: str) -> SunGeometry:
    body_to_sun = normalize_rows(np.tile(FALLBACK_BODY_TO_SUN_RTN, (3, 1)))
    return SunGeometry(
        sample_f=sample_f,
        labels=("Sun initial", "Sun perigee", "Sun final"),
        body_to_sun_rtn=body_to_sun,
        sun_to_body_rtn=-body_to_sun,
        jd=np.arange(sample_f.size, dtype=float),
        true_anomaly=sample_f,
        body_to_sun_epochs_rtn=body_to_sun,
        source=source,
    )


def geometry_from_states(
    *,
    jd: np.ndarray,
    target: np.ndarray,
    central: np.ndarray,
    sun: np.ndarray,
    central_mu_m3_s2: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute body-to-Sun RTN directions and true anomaly like standalone."""
    n_epochs = jd.size
    body_to_sun_rtn = np.zeros((n_epochs, 3))
    true_anomaly = np.zeros(n_epochs)

    for index in range(n_epochs):
        radial = target[index, :3] - central[index, :3]
        relative_velocity = target[index, 3:] - central[index, 3:]
        e_r = radial / np.linalg.norm(radial)
        e_n = np.cross(radial, relative_velocity)
        e_n /= np.linalg.norm(e_n)
        e_t = np.cross(e_n, e_r)
        rtn_to_icrf = np.column_stack((e_r, e_t, e_n))

        body_to_sun_icrf = sun[index, :3] - target[index, :3]
        body_to_sun_icrf /= np.linalg.norm(body_to_sun_icrf)
        body_to_sun_rtn[index] = rtn_to_icrf.T @ body_to_sun_icrf

        h_vec = np.cross(radial, relative_velocity)
        h_norm = np.linalg.norm(h_vec)
        r_norm = np.linalg.norm(radial)
        e_vec = np.cross(relative_velocity, h_vec) / central_mu_m3_s2 - radial / r_norm
        eccentricity = np.linalg.norm(e_vec)
        cos_nu = np.dot(e_vec, radial) / (eccentricity * r_norm)
        sin_nu = np.dot(radial, relative_velocity) * h_norm / (
            central_mu_m3_s2 * eccentricity * r_norm
        )
        true_anomaly[index] = np.arctan2(sin_nu, np.clip(cos_nu, -1.0, 1.0))

    return true_anomaly, body_to_sun_rtn


def sun_arrow_indices(true_anomaly: np.ndarray) -> np.ndarray:
    return np.array(
        [0, int(np.argmin(np.abs(true_anomaly))), true_anomaly.size - 1],
        dtype=int,
    )


def build_sun_geometry(
    *,
    jd: np.ndarray,
    target: np.ndarray,
    central: np.ndarray,
    sun: np.ndarray,
    central_mu_m3_s2: float,
    source: str,
) -> SunGeometry:
    true_anomaly, body_to_sun_epochs = geometry_from_states(
        jd=jd,
        target=target,
        central=central,
        sun=sun,
        central_mu_m3_s2=central_mu_m3_s2,
    )
    indices = sun_arrow_indices(true_anomaly)
    body_to_sun = normalize_rows(body_to_sun_epochs[indices])
    return SunGeometry(
        sample_f=true_anomaly[indices],
        labels=("Sun initial", "Sun perigee", "Sun final"),
        body_to_sun_rtn=body_to_sun,
        sun_to_body_rtn=-body_to_sun,
        jd=np.asarray(jd, dtype=float),
        true_anomaly=true_anomaly,
        body_to_sun_epochs_rtn=body_to_sun_epochs,
        source=source,
    )


def load_offline_apophis_earth_geometry(central_body: CentralBody) -> SunGeometry:
    with np.load(OFFLINE_APOPHIS_EARTH_SUN_FILE) as data:
        return build_sun_geometry(
            jd=data["jd"],
            target=data["apophis"],
            central=data["earth"],
            sun=data["sun"],
            central_mu_m3_s2=central_body.mu_m3_s2,
            source=f"offline:{OFFLINE_APOPHIS_EARTH_SUN_FILE.name}",
        )


def load_sun_geometry(
    *,
    small_body: SmallBodyProperties,
    central_body: CentralBody,
    inputs: SimulationInputs,
    timeout: float = 30.0,
) -> SunGeometry:
    """Return full standalone-style Sun geometry and three arrow directions."""
    if is_default_apophis_earth(small_body, central_body) and OFFLINE_APOPHIS_EARTH_SUN_FILE.exists():
        return load_offline_apophis_earth_geometry(central_body)

    sample_f = np.array([inputs.f_ini, 0.0, inputs.f_end], dtype=float)
    perigee = parse_utc(DEFAULT_PERIAPSIS_UTC)
    offsets = true_anomaly_to_seconds(
        sample_f,
        central_mu_m3_s2=central_body.mu_m3_s2,
        orbit_q_m=inputs.orbit_q_m,
        orbit_eccentricity=inputs.orbit_eccentricity,
    )
    sample_datetimes = np.array(
        [perigee + timedelta(seconds=float(offset)) for offset in offsets],
        dtype=object,
    )
    sample_jd = np.array([datetime_to_jd(value) for value in sample_datetimes])

    request = {
        "mode": "full-visibility-geometry-v1",
        "small_body": horizons_command_for_small_body(small_body),
        "central": central_body.horizons_id,
        "perigee": DEFAULT_PERIAPSIS_UTC,
        "f": [float(value) for value in sample_f],
        "q": inputs.orbit_q_m,
        "e": inputs.orbit_eccentricity,
    }
    SUN_GEOMETRY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = SUN_GEOMETRY_CACHE_DIR / f"{cache_key(request)}.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            cached = json.load(handle)
        jd = np.asarray(cached["jd"], dtype=float)
        true_anomaly = np.asarray(cached["true_anomaly"], dtype=float)
        body_to_sun_epochs = normalize_rows(
            np.asarray(cached["body_to_sun_epochs_rtn"], dtype=float)
        )
        indices = sun_arrow_indices(true_anomaly)
        body_to_sun = normalize_rows(body_to_sun_epochs[indices])
        return SunGeometry(
            sample_f=true_anomaly[indices],
            labels=("Sun initial", "Sun perigee", "Sun final"),
            body_to_sun_rtn=body_to_sun,
            sun_to_body_rtn=-body_to_sun,
            jd=jd,
            true_anomaly=true_anomaly,
            body_to_sun_epochs_rtn=body_to_sun_epochs,
            source=f"cache:{path.name}",
        )

    try:
        start = jd_to_datetime(float(np.min(sample_jd))) - timedelta(minutes=20)
        stop = jd_to_datetime(float(np.max(sample_jd))) + timedelta(minutes=20)
        target_jd, target_state = download_vectors(
            request["small_body"],
            start=start,
            stop=stop,
            timeout=timeout,
        )
        central_jd, central_state = download_vectors(
            central_body.horizons_id,
            start=start,
            stop=stop,
            timeout=timeout,
        )
        sun_jd, sun_state = download_vectors("10", start=start, stop=stop, timeout=timeout)
        if not (
            np.allclose(target_jd, central_jd, atol=1.0e-11)
            and np.allclose(target_jd, sun_jd, atol=1.0e-11)
        ):
            raise RuntimeError("Horizons returned inconsistent vector epochs.")

        true_anomaly, body_to_sun_epochs = geometry_from_states(
            jd=target_jd,
            target=target_state,
            central=central_state,
            sun=sun_state,
            central_mu_m3_s2=central_body.mu_m3_s2,
        )

        with path.open("w", encoding="utf-8") as handle:
            json.dump(
                {
                    "request": request,
                    "sample_utc": [value.isoformat() for value in sample_datetimes],
                    "jd": target_jd.tolist(),
                    "true_anomaly": true_anomaly.tolist(),
                    "body_to_sun_epochs_rtn": body_to_sun_epochs.tolist(),
                },
                handle,
                indent=2,
                sort_keys=True,
            )
        return build_sun_geometry(
            jd=target_jd,
            target=target_state,
            central=central_state,
            sun=sun_state,
            central_mu_m3_s2=central_body.mu_m3_s2,
            source=f"JPL Horizons:{path.name}",
        )
    except Exception as exc:  # noqa: BLE001 - visualization should still run.
        return fallback_sun_geometry(sample_f, f"fallback:{exc}")


def interpolate_body_to_sun(
    sample_f: np.ndarray,
    body_to_sun_rtn: np.ndarray,
    query_f: np.ndarray,
) -> np.ndarray:
    values = np.column_stack(
        [
            np.interp(query_f, sample_f, body_to_sun_rtn[:, column])
            for column in range(3)
        ]
    )
    return normalize_rows(values)
