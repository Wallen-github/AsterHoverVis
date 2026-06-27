'''
@File        : smallbodyvis/ui/dialogs.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Small Qt dialogs used by the main window.
'''

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from smallbodyvis.core.models import SmallBodyProperties


def _format_optional(value: float | None, scale: float = 1.0) -> str:
    if value is None:
        return ""
    return f"{value / scale:.10g}"


def _parse_optional_float(text: str) -> float | None:
    stripped = text.strip()
    if not stripped:
        return None
    return float(stripped)


class ManualPhysicalPropertiesDialog(QDialog):
    """Collect missing size and mu when JPL lacks them."""

    def __init__(self, properties: SmallBodyProperties, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Manual Small-Body Parameters")
        self._input_properties = properties
        self._result: SmallBodyProperties | None = None

        intro = QLabel(
            "JPL SBDB did not provide enough physical parameters for dynamics. "
            "Enter radius/diameter and mu."
        )
        intro.setWordWrap(True)

        self.radius_edit = QLineEdit(_format_optional(properties.radius_m))
        self.diameter_edit = QLineEdit(_format_optional(properties.diameter_m))
        self.gm_edit = QLineEdit(_format_optional(properties.gm_m3_s2))

        form = QFormLayout()
        form.addRow("Radius [m]", self.radius_edit)
        form.addRow("Diameter [m]", self.diameter_edit)
        form.addRow("mu / GM [m^3/s^2]", self.gm_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept_with_validation)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    @property
    def properties(self) -> SmallBodyProperties:
        return self._result or self._input_properties

    def _accept_with_validation(self) -> None:
        try:
            radius_m = _parse_optional_float(self.radius_edit.text())
            diameter_m = _parse_optional_float(self.diameter_edit.text())
            gm_m3_s2 = _parse_optional_float(self.gm_edit.text())
            for name, value in (
                ("radius", radius_m),
                ("diameter", diameter_m),
                ("mu / GM", gm_m3_s2),
            ):
                if value is not None and value <= 0.0:
                    raise ValueError(f"{name} must be positive.")
            updated = self._input_properties.with_manual_overrides(
                radius_m=radius_m,
                diameter_m=diameter_m,
                gm_m3_s2=gm_m3_s2,
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Input", str(exc))
            return

        missing = updated.missing_required_fields
        if missing:
            QMessageBox.warning(
                self,
                "Missing Parameters",
                "Still missing: " + ", ".join(missing),
            )
            return

        self._result = updated
        self.accept()
