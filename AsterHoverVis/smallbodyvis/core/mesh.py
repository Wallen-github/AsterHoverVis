'''
@File        : smallbodyvis/core/mesh.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

OBJ mesh loading and geometry helpers.
'''

from __future__ import annotations

from pathlib import Path

import numpy as np

from smallbodyvis.core.models import MeshData


def _parse_face_index(token: str, vertex_count: int) -> int:
    raw = token.split("/", 1)[0]
    if not raw:
        raise ValueError(f"Invalid OBJ face token {token!r}.")
    index = int(raw)
    if index < 0:
        return vertex_count + index
    return index - 1


def read_obj_triangles(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Read vertices and triangulated faces from a Wavefront OBJ file."""
    obj_path = Path(path)
    vertices: list[list[float]] = []
    faces: list[list[int]] = []

    with obj_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            fields = stripped.split()
            if fields[0] == "v":
                if len(fields) < 4:
                    raise ValueError(f"Invalid vertex at {obj_path}:{line_number}.")
                vertices.append([float(fields[1]), float(fields[2]), float(fields[3])])
            elif fields[0] == "f":
                if len(fields) < 4:
                    continue
                polygon = [_parse_face_index(token, len(vertices)) for token in fields[1:]]
                if any(index < 0 or index >= len(vertices) for index in polygon):
                    raise ValueError(f"Face index out of range at {obj_path}:{line_number}.")
                anchor = polygon[0]
                for i in range(1, len(polygon) - 1):
                    faces.append([anchor, polygon[i], polygon[i + 1]])

    if not vertices:
        raise ValueError(f"No vertices found in {obj_path}.")
    if not faces:
        raise ValueError(f"No faces found in {obj_path}.")
    return np.asarray(vertices, dtype=float), np.asarray(faces, dtype=np.int64)


def face_normals_and_centers(
    vertices: np.ndarray,
    faces: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    triangles = vertices[faces]
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    normals = np.cross(b - a, c - a)
    lengths = np.linalg.norm(normals, axis=1)
    valid = lengths > 0.0
    normals[valid] /= lengths[valid, None]
    centers = np.mean(triangles, axis=1)

    inward = np.einsum("ij,ij->i", normals, centers) < 0.0
    normals[inward] *= -1.0
    return normals, centers


def load_obj_mesh(
    path: str | Path,
    *,
    target_radius_m: float | None = None,
    center_mesh: bool = True,
) -> MeshData:
    """Load, optionally center, and optionally scale an OBJ mesh."""
    source_path = Path(path)
    vertices, faces = read_obj_triangles(source_path)

    if center_mesh:
        vertices = vertices - np.mean(vertices, axis=0)

    native_radius = float(np.max(np.linalg.norm(vertices, axis=1)))
    if native_radius <= 0.0:
        raise ValueError(f"OBJ mesh has zero radius: {source_path}.")

    scale_factor = 1.0
    if target_radius_m is not None:
        if target_radius_m <= 0.0:
            raise ValueError("target_radius_m must be positive.")
        scale_factor = float(target_radius_m) / native_radius
        vertices = vertices * scale_factor

    normals, centers = face_normals_and_centers(vertices, faces)
    return MeshData(
        vertices=vertices,
        faces=faces,
        normals=normals,
        centers=centers,
        source_path=source_path,
        native_radius=native_radius,
        scale_factor=scale_factor,
    )
