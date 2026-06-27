'''
@File        : smallbodyvis/services/simulation_runner.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

High-level simulation workflow used by the UI.
'''

from __future__ import annotations

from dataclasses import replace

from smallbodyvis.core.constants import CentralBody
from smallbodyvis.core.models import (
    MeshData,
    SimulationInputs,
    SimulationResult,
    SmallBodyProperties,
)
from smallbodyvis.core.sun_geometry import load_sun_geometry
from smallbodyvis.core.trajectory import compute_hovering_trajectory
from smallbodyvis.core.visibility import (
    accumulated_camera_visibility_hours,
    interpolate_positions_to_true_anomaly,
)


class MissingPhysicalPropertyError(ValueError):
    """Raised when JPL did not provide enough data and manual input is needed."""


def run_visibility_simulation(
    *,
    mesh: MeshData,
    small_body: SmallBodyProperties,
    central_body: CentralBody,
    inputs: SimulationInputs,
) -> SimulationResult:
    missing = small_body.missing_required_fields
    if missing:
        raise MissingPhysicalPropertyError(
            "Missing small-body physical parameters: " + ", ".join(missing)
        )

    assert small_body.gm_m3_s2 is not None
    assert small_body.radius_m is not None
    _, trajectory_result = compute_hovering_trajectory(
        inputs,
        central_mu_m3_s2=central_body.mu_m3_s2,
        small_body_mu_m3_s2=small_body.gm_m3_s2,
        small_body_radius_m=small_body.radius_m,
    )
    sun_geometry = load_sun_geometry(
        small_body=small_body,
        central_body=central_body,
        inputs=inputs,
    )
    spacecraft_positions_at_jpl = interpolate_positions_to_true_anomaly(
        trajectory_result.f_values,
        trajectory_result.states,
        sun_geometry.true_anomaly,
    )
    visibility_hours = accumulated_camera_visibility_hours(
        mesh.normals,
        mesh.centers,
        spacecraft_positions_at_jpl,
        sun_geometry.body_to_sun_epochs_rtn,
        sun_geometry.jd,
        inputs.fov_deg,
    )
    return replace(
        trajectory_result,
        visibility_hours=visibility_hours,
        total_visibility_window_hours=float(
            trajectory_result.time_hours[-1] - trajectory_result.time_hours[0]
        ),
        sun_to_body_directions_rtn=sun_geometry.sun_to_body_rtn,
        sun_direction_labels=sun_geometry.labels,
        sun_geometry_source=sun_geometry.source,
    )
