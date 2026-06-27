# AsterHoverVis

AsterHoverVis v0 is an interactive asteroid-flyby hovering-orbit and
surface-visibility tool based on the `figure_visibility_v3_standalone`
workflow. It loads a polyhedral OBJ shape, propagates a spacecraft in a
hovering orbit relative to the asteroid during a major-planet flyby, and
visualizes accumulated facet visibility on the 3D mesh.

## Quick Start

On macOS, double-click the app launcher:

```text
Run_AsterHoverVis.app
```

This starts the UI without opening a Terminal window. Launcher output is written
to:

```text
data/asterhovervis_launcher.log
```

The app launcher searches for a Python environment with the required packages.
It checks the local `.venv` first, then common Anaconda/Homebrew/system Python
paths.

For debugging, you can run the terminal launcher:

```text
Run_AsterHoverVis.command
```

To force a specific interpreter from the terminal:

```bash
ASTERHOVERVIS_PYTHON=/path/to/python ./Run_AsterHoverVis.command
```

Install dependencies once if the launcher reports missing packages:

```bash
python3 -m pip install -r requirements.txt
```

You can also start from the `AsterHoverVis` directory with:

```bash
python3 -m smallbodyvis.app
```

After editable installation, the command-line entry point is:

```bash
asterhovervis
```

## Platform Support

The AsterHoverVis source code is designed to be cross-platform. The core UI and
simulation stack uses Python, PySide6, PyVista, PyVistaQt, PyQtGraph, NumPy, and
SciPy, which are available on macOS, Linux, and Windows.

The current double-click launcher is macOS-only:

```text
Run_AsterHoverVis.app
Run_AsterHoverVis.applescript
Run_AsterHoverVis.command
```

The `.app` bundle, AppleScript wrapper, macOS app icon, and macOS-style error
dialog do not run directly on Linux or Windows.

On Linux, run from the `AsterHoverVis` directory with:

```bash
python3 -m pip install -r requirements.txt
PYTHONPATH=. python3 -m smallbodyvis.app
```

On Windows PowerShell, run from the `AsterHoverVis` directory with:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH="."
python -m smallbodyvis.app
```

Linux and Windows need a working desktop OpenGL/Qt environment for the PyVista
3D view. For a true double-click distribution on those platforms, add a Linux
`.desktop` launcher or a Windows `.bat`/PowerShell launcher, or package the app
with a tool such as PyInstaller.

## UI Workflow

1. Select `Apophis` or choose `Custom Asteroid` and click `Import OBJ`.
2. Enter a JPL small-body ID or name, then click `Load / Download JPL`.
3. Select the central major planet.
4. Set simulation inputs:
   - `Reference [m]`: spacecraft reference position in the small-body/central-body frame.
   - `Initial pos error [m]`: initial spacecraft position offset from the reference.
   - `Initial vel error [m/s]`: initial velocity error in time-domain SI units.
   - `u_max [m/s^2]`: saturated control acceleration magnitude.
   - `FOV [deg]`: camera field of view.
   - `Flyby q [m]`: hyperbolic flyby periapsis distance parameter.
   - `Flyby e [-]`: hyperbolic flyby eccentricity.
5. Click `Run / Update`.

For the built-in `Apophis` preset, `q` and `e` are displayed with the v0
default flyby values and kept read-only. For `Custom Asteroid`, both fields are
editable.

The main 3D view shows the small-body mesh, accumulated visibility color map,
coordinate box, FOV cone, spacecraft start point, `S/C` label, reference point,
trajectory, Sun illumination arrows, and the arrow toward the selected central
planet. The right panel shows control acceleration and x/y/z position error.
The control plot includes `u_x`, `u_y`, `u_z`, white `|u|`, and the dashed
`u_max` saturation line.

## Default Data

The only built-in selectable small-body preset is:

```text
Apophis
```

The default Apophis OBJ file is:

```text
assets/apophis_v233s7_vert2_new.obj
```

The app can still import user-provided OBJ files through `Custom Asteroid`.

Apophis currently has a JPL diameter but no GM in SBDB, so AsterHoverVis applies
the v0 default:

```text
mu = 2.6 m^3/s^2
```

Mass and density are not required inputs. If needed later, mass and density can
be derived from `mu` and volume, but they are not used by the current dynamics
or visibility calculation.

## JPL Metadata and Cache

Small-body physical parameters are loaded from the JPL SBDB API:

```text
https://ssd-api.jpl.nasa.gov/sbdb.api
```

Raw SBDB responses are cached locally under:

```text
data/sbdb_cache/
```

Sun illumination directions for the initial, perigee, and final flyby epochs
are downloaded from JPL Horizons when available and cached locally under:

```text
data/sun_geometry_cache/
```

For the Apophis/Earth 2029 flyby, an offline JPL ephemeris asset is included:

```text
assets/jpl_apophis_earth_sun_2029_flyby_10min.npz
```

If JPL does not provide the required size or gravity parameter for a custom
small body, the UI prompts for manual input. The required fields are:

```text
radius or diameter
mu / GM
```

## Calculation Notes

- The trajectory model is the 3D hyperbolic TH hovering model.
- The central body selection changes the central gravitational parameter.
- The built-in Apophis preset uses the default hyperbolic parameters
  `q = 3.72e7 m` and `e = 4.229`. Custom asteroids can override both values
  from the UI.
- `u_max` is a vector-norm saturation on control acceleration:
  `|u| <= u_max`.
- Initial velocity error is entered in `m/s`. Internally it is converted to the
  true-anomaly-domain state with `r' = v / f_dot(f_ini)`.
- The visibility accumulation follows the same time-weighted facet/FOV/Sun
  logic as `figure_visibility_v3_standalone`.
- The Sun arrows show sunlight directions from Sun to small body at initial,
  perigee, and final epochs.
- Full ray-cast self-occlusion is not included in v0.

## Output

After a successful run, the status bar reports:

```text
max |u|
visible face ratio
```

Use `Export NPZ` to save the current result, including:

```text
f_values
time_hours
states
reference_state
control_m_s2
u_max_m_s2
visibility_hours
mesh_vertices
mesh_faces
```
