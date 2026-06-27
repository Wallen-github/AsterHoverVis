'''
@File        : smallbodyvis/core/models.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Shared dataclasses for AsterHoverVis core and UI layers.
'''

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from smallbodyvis.core.constants import GRAVITATIONAL_CONSTANT


def spherical_volume_from_radius(radius_m: float | None) -> float | None:
    """Return equivalent spherical volume from radius."""
    if radius_m is None or radius_m <= 0.0:
        return None
    return (4.0 / 3.0) * np.pi * radius_m**3


@dataclass(frozen=True)
class MeshData:
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    centers: np.ndarray
    source_path: Path
    native_radius: float
    scale_factor: float

    @property
    def triangles(self) -> np.ndarray:
        return self.vertices[self.faces]

    @property
    def face_count(self) -> int:
        return int(self.faces.shape[0])

    @property
    def vertex_count(self) -> int:
        return int(self.vertices.shape[0])


@dataclass(frozen=True)
class SmallBodyProperties:
    query: str
    full_name: str = ""
    spkid: str = ""
    source: str = "manual"
    cache_path: Path | None = None
    diameter_m: float | None = None
    radius_m: float | None = None
    gm_m3_s2: float | None = None
    mass_kg: float | None = None
    density_kg_m3: float | None = None
    rotation_period_s: float | None = None
    albedo: float | None = None
    h_magnitude: float | None = None

    @property
    def display_name(self) -> str:
        return self.full_name or self.query or "Unnamed small body"

    @property
    def has_size(self) -> bool:
        return self.radius_m is not None and self.radius_m > 0.0

    @property
    def has_gravity(self) -> bool:
        return self.gm_m3_s2 is not None and self.gm_m3_s2 > 0.0

    @property
    def missing_required_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.has_size:
            missing.append("radius or diameter")
        if not self.has_gravity:
            missing.append("mu / GM")
        return tuple(missing)

    def with_manual_overrides(
        self,
        *,
        diameter_m: float | None = None,
        radius_m: float | None = None,
        gm_m3_s2: float | None = None,
        mass_kg: float | None = None,
        density_kg_m3: float | None = None,
    ) -> "SmallBodyProperties":
        final_radius = radius_m if radius_m is not None else self.radius_m
        final_diameter = diameter_m if diameter_m is not None else self.diameter_m
        if final_radius is None and final_diameter is not None:
            final_radius = 0.5 * final_diameter
        if final_diameter is None and final_radius is not None:
            final_diameter = 2.0 * final_radius

        final_gm = gm_m3_s2 if gm_m3_s2 is not None else self.gm_m3_s2
        final_mass = mass_kg if mass_kg is not None else self.mass_kg
        final_density = (
            density_kg_m3 if density_kg_m3 is not None else self.density_kg_m3
        )
        if final_gm is None and final_mass is not None:
            final_gm = GRAVITATIONAL_CONSTANT * final_mass
        if final_mass is None and final_gm is not None:
            final_mass = final_gm / GRAVITATIONAL_CONSTANT
        if (
            final_gm is None
            and final_density is not None
            and final_radius is not None
            and final_radius > 0.0
        ):
            final_mass = (4.0 / 3.0) * np.pi * final_radius**3 * final_density
            final_gm = GRAVITATIONAL_CONSTANT * final_mass
        if final_density is None and final_mass is not None:
            volume = spherical_volume_from_radius(final_radius)
            if volume is not None:
                final_density = final_mass / volume

        return replace(
            self,
            source=f"{self.source}+manual",
            diameter_m=final_diameter,
            radius_m=final_radius,
            gm_m3_s2=final_gm,
            mass_kg=final_mass,
            density_kg_m3=final_density,
        )


@dataclass(frozen=True)
class SimulationInputs:
    reference_position_m: np.ndarray
    initial_position_error_m: np.ndarray
    initial_velocity_error_m_s: np.ndarray
    u_max_m_s2: float
    fov_deg: float
    f_ini: float = -np.pi / 2.0
    f_end: float = np.pi / 2.0
    n_steps: int = 800
    orbit_q_m: float = 3.72e7
    orbit_eccentricity: float = 4.229

    @property
    def reference_state(self) -> np.ndarray:
        return np.concatenate((self.reference_position_m, np.zeros(3)))

    def initial_state_for_f_dot(self, f_dot_rad_s: float) -> np.ndarray:
        if f_dot_rad_s <= 0.0:
            raise ValueError("Initial true-anomaly rate must be positive.")
        return self.reference_state + np.concatenate(
            (
                self.initial_position_error_m,
                self.initial_velocity_error_m_s / f_dot_rad_s,
            )
        )


@dataclass(frozen=True)
class SimulationResult:
    f_values: np.ndarray
    time_hours: np.ndarray
    states: np.ndarray
    reference_state: np.ndarray
    control_m_s2: np.ndarray
    visibility_hours: np.ndarray
    total_visibility_window_hours: float
    u_max_m_s2: float | None = None
    sun_to_body_directions_rtn: np.ndarray | None = None
    sun_direction_labels: tuple[str, ...] = ()
    sun_geometry_source: str = ""

    @property
    def trajectory_m(self) -> np.ndarray:
        return self.states[:3, :]

    @property
    def position_error_m(self) -> np.ndarray:
        return self.states[:3, :] - self.reference_state[:3, None]

    @property
    def max_control_m_s2(self) -> float:
        return float(np.max(np.linalg.norm(self.control_m_s2, axis=0)))

    @property
    def visible_surface_ratio(self) -> float:
        if self.visibility_hours.size == 0:
            return 0.0
        return float(np.mean(self.visibility_hours > 0.0))
