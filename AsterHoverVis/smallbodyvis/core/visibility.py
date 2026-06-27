'''
@File        : smallbodyvis/core/visibility.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Camera visibility accumulation on a small-body triangle mesh.

The core visibility calculation intentionally mirrors
``figure_visibility_v3_standalone/figure_visibility_v3.py``:

1. interpolate the spacecraft position history onto JPL true-anomaly epochs,
2. test camera FOV, face-to-spacecraft orientation, and sunlight per epoch,
3. integrate the Boolean visibility matrix with JPL ``jd`` time weights.
'''

from __future__ import annotations

import numpy as np


DAY_TO_S = 86400.0


def sample_time_weights(jd: np.ndarray) -> np.ndarray:
    """Trapezoid-like integration weights in seconds for JPL sample epochs."""
    elapsed_seconds = (jd - jd[0]) * DAY_TO_S
    if elapsed_seconds.size < 2:
        return np.ones_like(elapsed_seconds)
    weights = np.zeros_like(elapsed_seconds)
    weights[0] = 0.5 * (elapsed_seconds[1] - elapsed_seconds[0])
    weights[-1] = 0.5 * (elapsed_seconds[-1] - elapsed_seconds[-2])
    weights[1:-1] = 0.5 * (elapsed_seconds[2:] - elapsed_seconds[:-2])
    return weights


def interpolate_positions_to_true_anomaly(
    f_values: np.ndarray,
    states: np.ndarray,
    query_true_anomaly: np.ndarray,
) -> np.ndarray:
    """Interpolate spacecraft position history onto JPL true-anomaly epochs."""
    return np.vstack(
        [np.interp(query_true_anomaly, f_values, states[index]) for index in range(3)]
    )


def accumulated_camera_visibility_hours(
    normals: np.ndarray,
    centers: np.ndarray,
    spacecraft_positions: np.ndarray,
    apophis_to_sun_rtn: np.ndarray,
    jd: np.ndarray,
    fov_deg: float,
) -> np.ndarray:
    """Compute per-facet time visible by center-pointing camera under sunlight."""
    if not (0.0 < fov_deg < 170.0):
        raise ValueError("FOV must be in (0, 170) deg.")

    n_faces = normals.shape[0]
    n_epochs = spacecraft_positions.shape[1]
    visible = np.zeros((n_faces, n_epochs), dtype=bool)
    cos_half_fov = np.cos(np.deg2rad(fov_deg) / 2.0)

    for index in range(n_epochs):
        spacecraft = spacecraft_positions[:, index]
        spacecraft_distance = np.linalg.norm(spacecraft)
        if spacecraft_distance <= 0.0:
            continue

        camera_boresight = -spacecraft / spacecraft_distance
        spacecraft_to_centers = centers - spacecraft
        center_distances = np.linalg.norm(spacecraft_to_centers, axis=1)
        valid = center_distances > 0.0
        center_directions = np.zeros_like(spacecraft_to_centers)
        center_directions[valid] = (
            spacecraft_to_centers[valid] / center_distances[valid, None]
        )

        in_fov = center_directions @ camera_boresight >= cos_half_fov
        faces_spacecraft = np.einsum("ij,ij->i", normals, spacecraft - centers) > 0.0
        sunlit = normals @ apophis_to_sun_rtn[index] > 0.0
        visible[:, index] = in_fov & faces_spacecraft & sunlit

    weights = sample_time_weights(jd)
    return (visible @ weights) / 3600.0
