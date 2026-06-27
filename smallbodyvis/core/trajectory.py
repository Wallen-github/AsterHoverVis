'''
@File        : smallbodyvis/core/trajectory.py
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com

Hyperbolic TH hovering trajectory and control computations.
'''

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import solve_continuous_are

from smallbodyvis.core.models import SimulationInputs, SimulationResult


@dataclass(frozen=True)
class HoveringModelConfig:
    central_mu_m3_s2: float
    small_body_mu_m3_s2: float
    small_body_radius_m: float
    orbit_q_m: float
    orbit_eccentricity: float


class HoveringModel3D:
    """Lean 3D TH model used by the v0 GUI."""

    def __init__(self, config: HoveringModelConfig) -> None:
        if config.central_mu_m3_s2 <= 0.0:
            raise ValueError("central_mu_m3_s2 must be positive.")
        if config.small_body_mu_m3_s2 <= 0.0:
            raise ValueError("small_body_mu_m3_s2 must be positive.")
        if config.small_body_radius_m <= 0.0:
            raise ValueError("small_body_radius_m must be positive.")
        if config.orbit_eccentricity <= 1.0:
            raise ValueError("orbit_eccentricity must be greater than 1.")
        if config.orbit_q_m <= 0.0:
            raise ValueError("orbit_q_m must be positive.")

        self.config = config
        self.f_inf = math.acos(-1.0 / config.orbit_eccentricity)
        self._lqr_gain: np.ndarray | None = None

    def th_scalars(self, f: float, position: np.ndarray) -> tuple[float, float, float, float]:
        e = self.config.orbit_eccentricity
        q = self.config.orbit_q_m
        mu_c = self.config.central_mu_m3_s2
        mu_s = self.config.small_body_mu_m3_s2

        eta = 1.0 + e * np.cos(f)
        if eta <= 0.0:
            raise ValueError("True anomaly is outside the physical hyperbola.")

        f_dot = np.sqrt(mu_c / (q**3 * (1.0 + e) ** 3)) * eta**2
        f_ddot = -2.0 * mu_c * e * np.sin(f) / (q**3 * (1.0 + e) ** 3)
        central_distance = q * (1.0 + e) / eta
        radius = float(np.linalg.norm(position))
        if radius <= 0.0:
            raise ValueError("Spacecraft position reached the small-body singularity.")

        F = f_ddot / f_dot**2
        C_A = mu_s / (f_dot**2 * radius**3)
        C_E = mu_c / (f_dot**2 * central_distance**3)
        return f_dot, F, C_A, C_E

    def natural_acceleration_f(self, f: float, state: np.ndarray) -> tuple[float, np.ndarray]:
        position = np.asarray(state[:3], dtype=float)
        x, y, z = position
        xp, yp, zp = state[3:6]
        f_dot, F, C_A, C_E = self.th_scalars(f, position)

        xpp = -F * xp + 2.0 * yp + F * y + (1.0 - C_A + 2.0 * C_E) * x
        ypp = -F * yp - 2.0 * xp - F * x + (1.0 - C_A - C_E) * y
        zpp = -F * zp - (C_A + C_E) * z
        return f_dot, np.array([xpp, ypp, zpp])

    def a_matrix(self, f: float, state: np.ndarray) -> np.ndarray:
        position = np.asarray(state[:3], dtype=float)
        x, y, z = position
        del x, y, z
        radius_squared = float(position @ position)
        _, F, C_A, C_E = self.th_scalars(f, position)

        A = np.zeros((6, 6))
        A[:3, 3:] = np.eye(3)
        asteroid_gradient = 3.0 * C_A * np.outer(position, position) / radius_squared
        A[3:, :3] = asteroid_gradient

        A[3, 0] += 1.0 - C_A + 2.0 * C_E
        A[3, 1] += F
        A[4, 0] += -F
        A[4, 1] += 1.0 - C_A - C_E
        A[5, 2] += -C_A - C_E

        A[3, 3] = -F
        A[3, 4] = 2.0
        A[4, 3] = -2.0
        A[4, 4] = -F
        A[5, 5] = -F
        return A

    def b_matrix(self, f: float, state: np.ndarray) -> np.ndarray:
        f_dot, _, _, _ = self.th_scalars(f, state[:3])
        B = np.zeros((6, 3))
        B[3:, :] = np.eye(3) / f_dot**2
        return B

    def lqr_gain(self, reference: np.ndarray) -> np.ndarray:
        if self._lqr_gain is None:
            Q = np.diag([1.0, 1.0, 1.0, 1.0e-2, 1.0e-2, 1.0e-2])
            R = np.diag([1.0e8, 1.0e8, 1.0e8])
            A = self.a_matrix(0.0, reference)
            B = self.b_matrix(0.0, reference)
            P = solve_continuous_are(A, B, Q, R)
            self._lqr_gain = np.linalg.solve(R, B.T @ P)
        return self._lqr_gain

    def feedforward_control(self, f: float, reference: np.ndarray) -> np.ndarray:
        f_dot, acceleration_f = self.natural_acceleration_f(f, reference)
        return -(f_dot**2) * acceleration_f

    def control_acceleration(
        self,
        f: float,
        state: np.ndarray,
        reference: np.ndarray,
        u_max_m_s2: float,
    ) -> np.ndarray:
        control = self.feedforward_control(f, reference) - self.lqr_gain(reference) @ (
            state - reference
        )
        magnitude = float(np.linalg.norm(control))
        if u_max_m_s2 > 0.0 and magnitude > u_max_m_s2:
            control = control * (u_max_m_s2 / magnitude)
        return control

    def rhs(
        self,
        f: float,
        state: np.ndarray,
        reference: np.ndarray,
        u_max_m_s2: float,
    ) -> np.ndarray:
        f_dot, acceleration_f = self.natural_acceleration_f(f, state)
        control = self.control_acceleration(f, state, reference, u_max_m_s2)
        acceleration_f = acceleration_f + control / f_dot**2
        return np.concatenate((state[3:6], acceleration_f))

    def integrate(self, inputs: SimulationInputs):
        if not (-self.f_inf < inputs.f_ini < self.f_inf):
            raise ValueError("f_ini is outside the physical hyperbola.")
        if not (-self.f_inf < inputs.f_end < self.f_inf):
            raise ValueError("f_end is outside the physical hyperbola.")

        reference = inputs.reference_state
        initial_position = inputs.reference_position_m + inputs.initial_position_error_m
        initial_f_dot, _, _, _ = self.th_scalars(inputs.f_ini, initial_position)
        initial_state = inputs.initial_state_for_f_dot(initial_f_dot)
        output_anomalies = np.linspace(inputs.f_ini, inputs.f_end, inputs.n_steps)
        sample_step = abs(inputs.f_end - inputs.f_ini) / max(inputs.n_steps - 1, 1)

        def crash_event(_f: float, state: np.ndarray) -> float:
            return float(np.linalg.norm(state[:3]) - self.config.small_body_radius_m)

        crash_event.terminal = True
        crash_event.direction = -1

        return solve_ivp(
            lambda f, state: self.rhs(f, state, reference, inputs.u_max_m_s2),
            (inputs.f_ini, inputs.f_end),
            initial_state,
            t_eval=output_anomalies,
            events=crash_event,
            method="DOP853",
            rtol=1.0e-9,
            atol=1.0e-11,
            first_step=sample_step,
            max_step=sample_step,
        )

    def compute_control_history(
        self,
        f_values: np.ndarray,
        states: np.ndarray,
        reference: np.ndarray,
        u_max_m_s2: float,
    ) -> np.ndarray:
        return np.column_stack(
            [
                self.control_acceleration(float(f), states[:, index], reference, u_max_m_s2)
                for index, f in enumerate(f_values)
            ]
        )

    def elapsed_time_hours(self, f_values: np.ndarray, states: np.ndarray) -> np.ndarray:
        f_dot = np.array(
            [self.th_scalars(float(f), states[:3, i])[0] for i, f in enumerate(f_values)]
        )
        dt_df = 1.0 / f_dot
        elapsed_seconds = np.zeros_like(f_values)
        elapsed_seconds[1:] = np.cumsum(
            0.5 * (dt_df[1:] + dt_df[:-1]) * np.diff(f_values)
        )
        return elapsed_seconds / 3600.0


def compute_hovering_trajectory(
    inputs: SimulationInputs,
    *,
    central_mu_m3_s2: float,
    small_body_mu_m3_s2: float,
    small_body_radius_m: float,
) -> tuple[HoveringModel3D, SimulationResult]:
    config = HoveringModelConfig(
        central_mu_m3_s2=central_mu_m3_s2,
        small_body_mu_m3_s2=small_body_mu_m3_s2,
        small_body_radius_m=small_body_radius_m,
        orbit_q_m=inputs.orbit_q_m,
        orbit_eccentricity=inputs.orbit_eccentricity,
    )
    model = HoveringModel3D(config)
    solution = model.integrate(inputs)
    if not solution.success:
        raise RuntimeError(solution.message)

    reference = inputs.reference_state
    control = model.compute_control_history(
        solution.t,
        solution.y,
        reference,
        inputs.u_max_m_s2,
    )
    time_hours = model.elapsed_time_hours(solution.t, solution.y)
    empty_visibility = np.zeros(0, dtype=float)
    return model, SimulationResult(
        f_values=solution.t,
        time_hours=time_hours,
        states=solution.y,
        reference_state=reference,
        control_m_s2=control,
        visibility_hours=empty_visibility,
        total_visibility_window_hours=float(time_hours[-1] - time_hours[0]),
        u_max_m_s2=inputs.u_max_m_s2,
    )
