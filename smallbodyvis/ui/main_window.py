'''
@File        : smallbodyvis/ui/main_window.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Main AsterHoverVis v0 Qt window.
'''

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from smallbodyvis.core.constants import CENTRAL_BODIES, SMALL_BODY_PRESETS
from smallbodyvis.core.mesh import load_obj_mesh
from smallbodyvis.core.models import (
    MeshData,
    SimulationInputs,
    SimulationResult,
    SmallBodyProperties,
)
from smallbodyvis.core.sbdb_client import SBDBClient, SBDBError
from smallbodyvis.services.simulation_runner import run_visibility_simulation
from smallbodyvis.ui.dialogs import ManualPhysicalPropertiesDialog


BODY_TO_SUN_FALLBACK_RTN = np.array([1.0, -0.25, 0.10], dtype=float)
EARTH_DIRECTION_RTN = np.array([-1.0, 0.0, 0.0], dtype=float)
CUSTOM_ASTEROID_OPTION = "Custom Asteroid"
DEFAULT_FLYBY_Q_M = 3.72e7
DEFAULT_FLYBY_ECCENTRICITY = 4.229


class MainWindow(QMainWindow):
    """AsterHoverVis v0 main window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AsterHoverVis v0")

        self.sbdb_client = SBDBClient()
        self.small_body_properties = SmallBodyProperties(query="99942")
        self.current_obj_path = SMALL_BODY_PRESETS["Apophis"].obj_path
        self.mesh: MeshData | None = None
        self.current_result: SimulationResult | None = None

        self._build_ui()
        self._load_preset("Apophis")

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        splitter = QSplitter()
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_scene_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([390, 900, 390])

        self.status_label = QLabel("Ready")
        self.status_label.setFrameShape(QFrame.StyledPanel)
        self.status_label.setMinimumHeight(28)

        root.addWidget(splitter, stretch=1)
        root.addWidget(self.status_label)
        self.setCentralWidget(central)

    def _build_left_panel(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)

        shape_group = QGroupBox("Small Body")
        shape_form = QFormLayout(shape_group)
        self.shape_combo = QComboBox()
        self.shape_combo.addItems([*SMALL_BODY_PRESETS.keys(), CUSTOM_ASTEROID_OPTION])
        self.shape_combo.currentTextChanged.connect(self._on_shape_changed)
        self.jpl_query_edit = QLineEdit("99942")
        self.load_jpl_button = QPushButton("Load / Download JPL")
        self.refresh_jpl_button = QPushButton("Refresh JPL")
        self.import_obj_button = QPushButton("Import OBJ")
        self.load_jpl_button.clicked.connect(lambda: self._load_jpl_metadata(force=False))
        self.refresh_jpl_button.clicked.connect(lambda: self._load_jpl_metadata(force=True))
        self.import_obj_button.clicked.connect(self._import_obj)
        shape_form.addRow("Preset", self.shape_combo)
        shape_form.addRow("JPL ID / Name", self.jpl_query_edit)
        shape_form.addRow(self.load_jpl_button, self.refresh_jpl_button)
        shape_form.addRow("OBJ", self.import_obj_button)

        body_group = QGroupBox("Central Body")
        body_form = QFormLayout(body_group)
        self.central_body_combo = QComboBox()
        self.central_body_combo.addItems(list(CENTRAL_BODIES.keys()))
        self.central_body_combo.setCurrentText("Earth")
        body_form.addRow("Planet", self.central_body_combo)

        physical_group = QGroupBox("Physical Properties")
        physical_form = QGridLayout(physical_group)
        physical_form.setColumnStretch(0, 0)
        physical_form.setColumnStretch(1, 1)
        physical_form.setHorizontalSpacing(10)
        physical_form.setVerticalSpacing(7)
        self.name_value = QLabel("")
        self.diameter_value = QLabel("")
        self.radius_value = QLabel("")
        self.gm_value = QLabel("")
        self.rotation_value = QLabel("")
        self.cache_value = QLabel("")
        self.manual_button = QPushButton("Manual / Missing Params")
        self.manual_button.clicked.connect(self._open_manual_properties_dialog)
        for label in (
            self.name_value,
            self.diameter_value,
            self.radius_value,
            self.gm_value,
            self.rotation_value,
            self.cache_value,
        ):
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._add_property_row(physical_form, 0, "Name", self.name_value)
        self._add_property_row(physical_form, 1, "Diameter", self.diameter_value)
        self._add_property_row(physical_form, 2, "Radius", self.radius_value)
        self._add_property_row(physical_form, 3, "mu / GM", self.gm_value)
        self._add_property_row(physical_form, 4, "Rotation", self.rotation_value)
        self._add_property_row(physical_form, 5, "Cache", self.cache_value)
        physical_form.addWidget(self.manual_button, 6, 0, 1, 2)

        params_group = QGroupBox("Simulation Inputs")
        params_layout = QGridLayout(params_group)
        self.reference_edits = self._vector_edits(
            params_layout,
            0,
            "Reference [m]",
            ["500", "500", "500"],
        )
        self.pos_error_edits = self._vector_edits(
            params_layout,
            2,
            "Initial pos error [m]",
            ["0", "0", "0"],
        )
        self.vel_error_edits = self._vector_edits(
            params_layout,
            4,
            "Initial vel error [m/s]",
            ["0", "0", "0"],
        )
        params_layout.addWidget(QLabel("u_max [m/s^2]"), 6, 0)
        self.u_max_edit = QLineEdit("1e-4")
        params_layout.addWidget(self.u_max_edit, 6, 1, 1, 3)
        params_layout.addWidget(QLabel("FOV [deg]"), 7, 0)
        self.fov_edit = QLineEdit("40")
        params_layout.addWidget(self.fov_edit, 7, 1, 1, 3)
        params_layout.addWidget(QLabel("Flyby q [m]"), 8, 0)
        self.flyby_q_edit = QLineEdit(f"{DEFAULT_FLYBY_Q_M:.6g}")
        params_layout.addWidget(self.flyby_q_edit, 8, 1, 1, 3)
        params_layout.addWidget(QLabel("Flyby e [-]"), 9, 0)
        self.flyby_e_edit = QLineEdit(f"{DEFAULT_FLYBY_ECCENTRICITY:.6g}")
        params_layout.addWidget(self.flyby_e_edit, 9, 1, 1, 3)

        action_group = QGroupBox("Actions")
        action_layout = QHBoxLayout(action_group)
        self.run_button = QPushButton("Run / Update")
        self.reset_button = QPushButton("Reset Params")
        self.export_button = QPushButton("Export NPZ")
        self.run_button.clicked.connect(self._run_simulation)
        self.reset_button.clicked.connect(self._reset_parameters)
        self.export_button.clicked.connect(self._export_results)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.reset_button)
        action_layout.addWidget(self.export_button)

        layout.addWidget(shape_group)
        layout.addWidget(body_group)
        layout.addWidget(physical_group)
        layout.addWidget(params_group)
        layout.addWidget(action_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(container)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(360)
        scroll.setMaximumWidth(460)
        return scroll

    def _add_property_row(
        self,
        layout: QGridLayout,
        row: int,
        label_text: str,
        value_label: QLabel,
    ) -> None:
        label = QLabel(label_text)
        label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        label.setMinimumWidth(82)
        label.setMaximumWidth(92)
        layout.addWidget(label, row, 0)
        layout.addWidget(value_label, row, 1)

    def _build_scene_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(panel)
        self.plotter.set_background("white")
        self.plotter.add_text("AsterHoverVis v0", position="upper_left", font_size=10, color="black")
        layout.addWidget(self.plotter.interactor)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.graphs = pg.GraphicsLayoutWidget()
        layout.addWidget(self.graphs)
        self.control_plot = self.graphs.addPlot(row=0, col=0, title="Control Acceleration")
        self.x_plot = self.graphs.addPlot(row=1, col=0, title="Position Error X")
        self.y_plot = self.graphs.addPlot(row=2, col=0, title="Position Error Y")
        self.z_plot = self.graphs.addPlot(row=3, col=0, title="Position Error Z")
        for plot in (self.control_plot, self.x_plot, self.y_plot, self.z_plot):
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setLabel("bottom", "time", units="h")
        self.control_plot.setLabel("left", "u", units="m/s^2")
        self.x_plot.setLabel("left", "dx", units="m")
        self.y_plot.setLabel("left", "dy", units="m")
        self.z_plot.setLabel("left", "dz", units="m")
        panel.setMinimumWidth(340)
        return panel

    def _vector_edits(
        self,
        layout: QGridLayout,
        row: int,
        label: str,
        defaults: list[str],
    ) -> list[QLineEdit]:
        layout.addWidget(QLabel(label), row, 0, 1, 4)
        edits = [QLineEdit(default) for default in defaults]
        for col, edit in enumerate(edits):
            edit.setMinimumWidth(64)
            layout.addWidget(edit, row + 1, 2 * col + 1)
        layout.addWidget(QLabel("x"), row + 1, 0)
        layout.addWidget(QLabel("y"), row + 1, 2)
        layout.addWidget(QLabel("z"), row + 1, 4)
        return edits

    def _on_shape_changed(self, name: str) -> None:
        if name in SMALL_BODY_PRESETS:
            self._load_preset(name)
        else:
            self._set_flyby_fields_editable(True)

    def _load_preset(self, name: str) -> None:
        preset = SMALL_BODY_PRESETS[name]
        self.current_obj_path = preset.obj_path
        self.jpl_query_edit.setText(preset.jpl_query)
        self._reset_flyby_defaults()
        self._set_flyby_fields_editable(False)
        self._set_status(f"Loading {name} OBJ and JPL metadata...")
        self._load_jpl_metadata(force=False)
        self._reload_mesh()

    def _reset_flyby_defaults(self) -> None:
        self.flyby_q_edit.setText(f"{DEFAULT_FLYBY_Q_M:.6g}")
        self.flyby_e_edit.setText(f"{DEFAULT_FLYBY_ECCENTRICITY:.6g}")

    def _set_flyby_fields_editable(self, editable: bool) -> None:
        for edit in (self.flyby_q_edit, self.flyby_e_edit):
            edit.setReadOnly(not editable)
            edit.setEnabled(True)

    def _load_jpl_metadata(self, *, force: bool) -> None:
        query = self.jpl_query_edit.text().strip()
        if not query:
            QMessageBox.warning(self, "Missing JPL Query", "Enter a JPL designation or name.")
            return
        try:
            self.small_body_properties = self.sbdb_client.fetch(query, force=force)
            self._apply_default_small_body_mu(query)
            self._set_status(
                f"Loaded JPL SBDB data for {self.small_body_properties.display_name}."
            )
        except (OSError, SBDBError, ValueError) as exc:
            QMessageBox.warning(self, "JPL Load Failed", str(exc))
            self.small_body_properties = SmallBodyProperties(query=query)
            self._apply_default_small_body_mu(query)
            self._set_status("JPL metadata unavailable. Manual parameters are required.")
        self._update_properties_panel()
        self._reload_mesh()

    def _apply_default_small_body_mu(self, query: str) -> None:
        normalized_query = query.strip().lower()
        for preset in SMALL_BODY_PRESETS.values():
            if (
                preset.default_mu_m3_s2 is not None
                and normalized_query == preset.jpl_query.lower()
            ):
                self.small_body_properties = (
                    self.small_body_properties.with_manual_overrides(
                        gm_m3_s2=preset.default_mu_m3_s2
                    )
                )
                return

    def _import_obj(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import OBJ",
            str(Path.home()),
            "Wavefront OBJ (*.obj)",
        )
        if not path:
            return
        self.current_obj_path = Path(path)
        self.shape_combo.blockSignals(True)
        self.shape_combo.setCurrentText(CUSTOM_ASTEROID_OPTION)
        self.shape_combo.blockSignals(False)
        self._set_flyby_fields_editable(True)
        self._reload_mesh()

    def _reload_mesh(self) -> None:
        try:
            target_radius = self.small_body_properties.radius_m
            self.mesh = load_obj_mesh(
                self.current_obj_path,
                target_radius_m=target_radius,
                center_mesh=True,
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "OBJ Load Failed", str(exc))
            self.mesh = None
            return
        self.current_result = None
        self._draw_scene()
        self._set_status(
            f"Loaded mesh: {self.mesh.vertex_count} vertices, {self.mesh.face_count} faces."
        )

    def _update_properties_panel(self) -> None:
        p = self.small_body_properties
        self.name_value.setText(self._short_body_name(p.display_name))
        self.diameter_value.setText(self._fmt(p.diameter_m, "m"))
        self.radius_value.setText(self._fmt(p.radius_m, "m"))
        self.gm_value.setText(self._fmt(p.gm_m3_s2, "m^3/s^2"))
        self.rotation_value.setText(
            self._fmt(
                None if p.rotation_period_s is None else p.rotation_period_s / 3600.0,
                "h",
            )
        )
        self.cache_value.setText(self._short_cache_path(p.cache_path))
        if p.missing_required_fields:
            self.manual_button.setText("Manual Required")
        else:
            self.manual_button.setText("Manual / Override")

    def _open_manual_properties_dialog(self) -> bool:
        old_radius = self.small_body_properties.radius_m
        dialog = ManualPhysicalPropertiesDialog(self.small_body_properties, self)
        if dialog.exec() != QDialog.Accepted:
            return False
        self.small_body_properties = dialog.properties
        self._update_properties_panel()
        new_radius = self.small_body_properties.radius_m
        radius_changed = (
            old_radius is None
            or new_radius is None
            or abs(float(old_radius) - float(new_radius)) > 1.0e-9
        )
        self.current_result = None
        if self.mesh is None or radius_changed:
            self._reload_mesh()
        self._set_status("Manual physical parameters applied.")
        return True

    def _run_simulation(self) -> None:
        if self.mesh is None:
            QMessageBox.warning(self, "No Mesh", "Load or import an OBJ mesh first.")
            return
        if self.small_body_properties.missing_required_fields:
            QMessageBox.information(
                self,
                "Manual Parameters Required",
                "JPL SBDB is missing required size/gravity fields for this object. "
                "Please enter them manually.",
            )
            if not self._open_manual_properties_dialog():
                return
        try:
            inputs = self._read_simulation_inputs()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Simulation Input", str(exc))
            return

        self.run_button.setEnabled(False)
        self._set_status("Running trajectory and visibility simulation...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            result = run_visibility_simulation(
                mesh=self.mesh,
                small_body=self.small_body_properties,
                central_body=CENTRAL_BODIES[self.central_body_combo.currentText()],
                inputs=inputs,
            )
        except Exception as exc:  # noqa: BLE001 - show errors in the GUI.
            QApplication.restoreOverrideCursor()
            self._simulation_failed(str(exc))
            return

        QApplication.restoreOverrideCursor()
        self._simulation_finished(result)

    @Slot(object)
    def _simulation_finished(self, result: SimulationResult) -> None:
        self.current_result = result
        self._draw_scene(result)
        self._draw_plots(result)
        self.run_button.setEnabled(True)
        self._set_status(
            "Done. "
            f"max |u| = {result.max_control_m_s2:.3e} m/s^2, "
            f"visible face ratio = {100.0 * result.visible_surface_ratio:.1f}%."
        )

    @Slot(str)
    def _simulation_failed(self, message: str) -> None:
        self.run_button.setEnabled(True)
        QMessageBox.warning(self, "Simulation Failed", message)
        self._set_status("Simulation failed.")

    def _read_simulation_inputs(self) -> SimulationInputs:
        reference = np.array([float(edit.text()) for edit in self.reference_edits], dtype=float)
        pos_error = np.array([float(edit.text()) for edit in self.pos_error_edits], dtype=float)
        vel_error = np.array([float(edit.text()) for edit in self.vel_error_edits], dtype=float)
        u_max = float(self.u_max_edit.text())
        fov = float(self.fov_edit.text())
        orbit_q = float(self.flyby_q_edit.text())
        orbit_eccentricity = float(self.flyby_e_edit.text())
        if u_max <= 0.0:
            raise ValueError("u_max must be positive.")
        if not (0.0 < fov < 170.0):
            raise ValueError("FOV must be in (0, 170) deg.")
        if orbit_q <= 0.0:
            raise ValueError("Flyby q must be positive.")
        if orbit_eccentricity <= 1.0:
            raise ValueError("Flyby e must be greater than 1 for a hyperbolic flyby.")
        return SimulationInputs(
            reference_position_m=reference,
            initial_position_error_m=pos_error,
            initial_velocity_error_m_s=vel_error,
            u_max_m_s2=u_max,
            fov_deg=fov,
            orbit_q_m=orbit_q,
            orbit_eccentricity=orbit_eccentricity,
        )

    @staticmethod
    def _unit(vector: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            return np.array([1.0, 0.0, 0.0])
        return np.asarray(vector, dtype=float) / norm

    def _current_fov_deg(self) -> float:
        try:
            fov = float(self.fov_edit.text())
        except ValueError:
            return 40.0
        return float(np.clip(fov, 1.0, 169.0))

    def _current_reference_position(self) -> np.ndarray:
        try:
            return np.array([float(edit.text()) for edit in self.reference_edits], dtype=float)
        except ValueError:
            return np.array([500.0, 500.0, 500.0], dtype=float)

    def _point_visibility_scalars(self, face_scalars: np.ndarray) -> np.ndarray:
        """Average per-face visibility values onto vertices for smoother coloring."""
        assert self.mesh is not None
        point_values = np.zeros(self.mesh.vertex_count, dtype=float)
        counts = np.zeros(self.mesh.vertex_count, dtype=float)
        repeated_scalars = np.repeat(face_scalars, 3)
        vertex_indices = self.mesh.faces.ravel()
        np.add.at(point_values, vertex_indices, repeated_scalars)
        np.add.at(counts, vertex_indices, 1.0)
        valid = counts > 0.0
        point_values[valid] /= counts[valid]
        return point_values

    def _scene_bounds(self, radius: float, result: SimulationResult | None) -> tuple[float, ...]:
        assert self.mesh is not None
        points = [self.mesh.vertices]
        if result is not None:
            points.append(result.trajectory_m.T)
            points.append(result.reference_state[:3][None, :])
        else:
            points.append(self._current_reference_position()[None, :])
        cloud = np.vstack(points)
        mins = np.min(cloud, axis=0)
        maxs = np.max(cloud, axis=0)
        span = np.maximum(maxs - mins, 2.0 * radius)
        padding = np.maximum(0.18 * span, 0.75 * radius)
        mins -= padding
        maxs += padding
        return (
            float(mins[0]),
            float(maxs[0]),
            float(mins[1]),
            float(maxs[1]),
            float(mins[2]),
            float(maxs[2]),
        )

    def _add_coordinate_box(self, bounds: tuple[float, ...]) -> None:
        self.plotter.show_bounds(
            bounds=bounds,
            grid="back",
            location="outer",
            all_edges=True,
            xtitle="x [m]",
            ytitle="y [m]",
            ztitle="z [m]",
            n_xlabels=4,
            n_ylabels=4,
            n_zlabels=4,
            fmt="%.0f",
            color="black",
            font_size=10,
        )

    def _add_direction_arrow(
        self,
        *,
        start: np.ndarray,
        direction: np.ndarray,
        length: float,
        color: str,
        label: str,
        label_offset: float = 0.10,
    ) -> None:
        unit_direction = self._unit(direction)
        arrow = pv.Arrow(
            start=start,
            direction=unit_direction,
            scale=length,
            tip_length=0.28,
            tip_radius=0.07,
            shaft_radius=0.025,
        )
        self.plotter.add_mesh(arrow, color=color, ambient=0.35, diffuse=0.65)
        label_point = start + unit_direction * length * (1.0 + label_offset)
        self.plotter.add_point_labels(
            label_point[None, :],
            [label],
            font_size=12,
            text_color="black",
            shape_color="white",
            shape_opacity=0.45,
            show_points=False,
            always_visible=True,
        )

    def _add_sunlight_arrows(
        self,
        radius: float,
        result: SimulationResult | None,
    ) -> None:
        if result is not None and result.sun_to_body_directions_rtn is not None:
            directions = np.asarray(result.sun_to_body_directions_rtn, dtype=float)
            labels = result.sun_direction_labels or (
                "Sun initial",
                "Sun perigee",
                "Sun final",
            )
        else:
            directions = np.tile(-self._unit(BODY_TO_SUN_FALLBACK_RTN), (3, 1))
            labels = ("Sun initial", "Sun perigee", "Sun final")

        for index, (direction, label) in enumerate(zip(directions, labels)):
            unit_direction = self._unit(direction)
            tangent = self._unit(np.cross(unit_direction, np.array([0.0, 0.0, 1.0])))
            if np.linalg.norm(tangent) <= 0.0:
                tangent = np.array([0.0, 1.0, 0.0])
            offset = (index - 1) * 0.55 * radius * tangent
            start = -3.25 * radius * unit_direction + offset
            self._add_direction_arrow(
                start=start,
                direction=unit_direction,
                length=1.35 * radius,
                color="gold",
                label=label,
                label_offset=0.03,
            )

    def _add_earth_arrow(self, radius: float) -> None:
        central_name = self.central_body_combo.currentText()
        direction = self._unit(EARTH_DIRECTION_RTN)
        self._add_direction_arrow(
            start=1.22 * radius * direction,
            direction=direction,
            length=1.55 * radius,
            color="#2b6fdb",
            label=f"to {central_name}",
            label_offset=0.05,
        )

    def _make_fov_cone(
        self,
        apex: np.ndarray,
        fov_deg: float,
        radius: float,
    ) -> pv.PolyData:
        axis = self._unit(-apex)
        distance_to_origin = float(np.linalg.norm(apex))
        height = max(min(distance_to_origin - 1.20 * radius, 3.2 * radius), 0.60 * radius)
        base_center = apex + axis * height
        base_radius = height * np.tan(np.deg2rad(fov_deg) / 2.0)

        u = self._unit(np.cross(axis, np.array([0.0, 0.0, 1.0])))
        if np.linalg.norm(u) <= 0.0:
            u = np.array([0.0, 1.0, 0.0])
        v = self._unit(np.cross(axis, u))

        resolution = 64
        angles = np.linspace(0.0, 2.0 * np.pi, resolution, endpoint=False)
        circle = np.array(
            [base_center + base_radius * (np.cos(a) * u + np.sin(a) * v) for a in angles]
        )
        points = np.vstack((apex[None, :], circle))
        faces: list[int] = []
        for i in range(resolution):
            j = 1 + i
            k = 1 + ((i + 1) % resolution)
            faces.extend([3, 0, j, k])
        return pv.PolyData(points, np.asarray(faces))

    def _add_fov_cone(self, radius: float, result: SimulationResult | None) -> None:
        if result is not None:
            apex = result.trajectory_m[:, 0]
        else:
            apex = self._current_reference_position()
        distance_to_origin = float(np.linalg.norm(apex))
        if distance_to_origin <= 1.25 * radius:
            return
        cone = self._make_fov_cone(apex, self._current_fov_deg(), radius)
        self.plotter.add_mesh(
            cone,
            color="#00a9e0",
            opacity=0.18,
            show_edges=True,
            edge_color="#0078a8",
            line_width=1,
            label="FOV cone",
        )
        self._add_direction_arrow(
            start=apex,
            direction=-apex,
            length=max(min(distance_to_origin - 1.25 * radius, 3.2 * radius), 0.60 * radius),
            color="#00a9e0",
            label=f"FOV {self._current_fov_deg():.0f} deg",
            label_offset=0.04,
        )

    def _draw_scene(self, result: SimulationResult | None = None) -> None:
        self.plotter.clear()
        self.plotter.set_background("white")
        if self.mesh is None:
            self.plotter.add_text("No mesh loaded", color="black")
            return

        faces = np.column_stack(
            (np.full(self.mesh.faces.shape[0], 3, dtype=np.int64), self.mesh.faces)
        ).ravel()
        poly = pv.PolyData(self.mesh.vertices, faces)
        if result is None or result.visibility_hours.size != self.mesh.face_count:
            scalars = np.zeros(self.mesh.face_count)
            scalar_label = "visibility_h"
            clim = [0.0, 1.0]
        else:
            scalars = result.visibility_hours
            scalar_label = "visibility_h"
            vmax = max(float(np.max(scalars)), 1.0e-12)
            clim = [0.0, vmax]
        poly.point_data[scalar_label] = self._point_visibility_scalars(scalars)
        self.plotter.add_mesh(
            poly,
            scalars=scalar_label,
            cmap="inferno",
            clim=clim,
            show_edges=False,
            smooth_shading=True,
            preference="point",
            n_colors=256,
            interpolate_before_map=True,
            scalar_bar_args={
                "title": "visible h",
                "vertical": True,
                "position_x": 0.88,
                "position_y": 0.18,
                "width": 0.08,
                "height": 0.62,
                "fmt": "%.2f",
                "color": "black",
                "title_font_size": 12,
                "label_font_size": 10,
            },
        )

        radius = max(float(np.max(np.linalg.norm(self.mesh.vertices, axis=1))), 1.0)
        bounds = self._scene_bounds(radius, result)
        self._add_coordinate_box(bounds)
        self.plotter.add_axes(
            xlabel="x",
            ylabel="y",
            zlabel="z",
            line_width=3,
            color="black",
        )
        self._add_sunlight_arrows(radius, result)
        self._add_earth_arrow(radius)
        self._add_fov_cone(radius, result)

        if result is not None:
            trajectory = result.trajectory_m.T
            if trajectory.shape[0] >= 2:
                self.plotter.add_mesh(
                    pv.lines_from_points(trajectory),
                    color="black",
                    line_width=3,
                    label="trajectory",
                )
            self.plotter.add_points(
                trajectory[[0]],
                color="limegreen",
                point_size=13,
                render_points_as_spheres=True,
            )
            sc_direction = self._unit(trajectory[0])
            sc_label_point = trajectory[0] + 0.20 * radius * sc_direction
            self.plotter.add_point_labels(
                sc_label_point[None, :],
                ["S/C"],
                font_size=13,
                text_color="black",
                shape_color="white",
                shape_opacity=0.55,
                show_points=False,
                always_visible=True,
            )
            self.plotter.add_points(
                result.reference_state[:3][None, :],
                color="deepskyblue",
                point_size=15,
                render_points_as_spheres=True,
            )

        self.plotter.add_text(
            f"{self.small_body_properties.display_name}\n"
            f"{self.central_body_combo.currentText()} centered TH model\n"
            f"Sun directions: {result.sun_geometry_source if result else 'not computed'}",
            position="upper_left",
            color="black",
            font_size=9,
        )
        self.plotter.reset_camera()
        self.plotter.render()

    def _draw_plots(self, result: SimulationResult) -> None:
        time = result.time_hours
        control = result.control_m_s2
        error = result.position_error_m

        for plot in (self.control_plot, self.x_plot, self.y_plot, self.z_plot):
            plot.clear()
        pens = [
            pg.mkPen("#1f77b4", width=1.7),
            pg.mkPen("#d62728", width=1.7),
            pg.mkPen("#2ca02c", width=1.7),
            pg.mkPen("#ffffff", width=2.8),
        ]
        control_norm = np.linalg.norm(control, axis=0)
        self.control_plot.plot(time, control_norm, pen=pens[3], name="|u|")
        self.control_plot.plot(time, control[0], pen=pens[0], name="u_x")
        self.control_plot.plot(time, control[1], pen=pens[1], name="u_y")
        self.control_plot.plot(time, control[2], pen=pens[2], name="u_z")
        if result.u_max_m_s2 is not None and time.size > 0:
            saturation_pen = pg.mkPen("#666666", width=1.4, style=Qt.DashLine)
            self.control_plot.plot(
                time,
                np.full_like(time, result.u_max_m_s2, dtype=float),
                pen=saturation_pen,
                name="u_max",
            )
        self.x_plot.plot(time, error[0], pen=pens[0])
        self.y_plot.plot(time, error[1], pen=pens[1])
        self.z_plot.plot(time, error[2], pen=pens[2])

    def _reset_parameters(self) -> None:
        for edits, defaults in (
            (self.reference_edits, ["500", "500", "500"]),
            (self.pos_error_edits, ["0", "0", "0"]),
            (self.vel_error_edits, ["0", "0", "0"]),
        ):
            for edit, value in zip(edits, defaults):
                edit.setText(value)
        self.u_max_edit.setText("1e-4")
        self.fov_edit.setText("40")
        self._reset_flyby_defaults()
        self._set_flyby_fields_editable(
            self.shape_combo.currentText() == CUSTOM_ASTEROID_OPTION
        )
        self._set_status("Simulation inputs reset.")

    def _export_results(self) -> None:
        if self.current_result is None:
            QMessageBox.information(self, "No Results", "Run a simulation before exporting.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Results",
            "asterhovervis_result.npz",
            "NumPy archive (*.npz)",
        )
        if not path:
            return
        result = self.current_result
        np.savez_compressed(
            path,
            f_values=result.f_values,
            time_hours=result.time_hours,
            states=result.states,
            reference_state=result.reference_state,
            control_m_s2=result.control_m_s2,
            u_max_m_s2=np.array(result.u_max_m_s2 if result.u_max_m_s2 is not None else np.nan),
            visibility_hours=result.visibility_hours,
            mesh_vertices=self.mesh.vertices if self.mesh else np.zeros((0, 3)),
            mesh_faces=self.mesh.faces if self.mesh else np.zeros((0, 3), dtype=int),
        )
        self._set_status(f"Exported results to {path}.")

    @staticmethod
    def _fmt(value: float | None, unit: str) -> str:
        if value is None:
            return "missing"
        return f"{value:.6g} {unit}"

    @staticmethod
    def _short_body_name(name: str) -> str:
        return name.replace(" (", "\n(")

    @staticmethod
    def _short_cache_path(path) -> str:
        if path is None:
            return "manual / none"
        return f".../{path.parent.name}/{path.name}"

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)
