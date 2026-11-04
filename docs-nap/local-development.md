# Running Locally

This guide covers supported local development workflows after you have checked
out this repository. They are intended for development, debugging, and replay;
they are not a substitute for the safety validation required before using a
vehicle.

There are three distinct ways to run software locally:

| Goal | Run | Hardware required |
| --- | --- | --- |
| Inspect UI and recorded messages | Replay a drive and start the UI | None |
| Inspect recorded messages with a tool | Replay a drive and attach PlotJuggler or another subscriber | None |
| Run the full process manager on a PC | Start manager with a webcam and panda | Camera, harness, panda, and vehicle |

The production device launcher, `./launch_openpilot.sh`, is for a comma
device. Do not use it as the normal PC development entry point: it performs
device initialization and invokes the manager after setting its device runtime
environment.

## One-time setup

Initialize the pinned submodules, then install the project dependencies. The
setup script installs system packages on Ubuntu and installs/uses UV for the
project virtual environment:

```bash
git submodule sync --recursive
git submodule update --init --recursive
./tools/setup_dependencies.sh
```

If system dependencies are already installed and UV is available, the
equivalent project dependency command is:

```bash
uv sync --frozen --all-extras
```

Activate the resulting environment before running Python tools:

```bash
source .venv/bin/activate
```

Build native tools, including `tools/replay/replay`, after a fresh checkout or
when changing native code:

```bash
scons -j"$(nproc)"
```

On macOS, use the available CPU count in place of `nproc`, for example
`scons -j"$(sysctl -n hw.ncpu)"`.

## Replay a route locally

Replay is the default no-hardware workflow. It republishes recorded route
messages so the UI and other subscribers behave as though the drive is live.
Run replay from the repository root in one terminal:

```bash
source .venv/bin/activate
tools/replay/replay --demo
```

In a second terminal, activate the same environment and start the UI:

```bash
source .venv/bin/activate
./selfdrive/ui/ui.py
```

Use a route from comma connect after authenticating once:

```bash
python3 tools/lib/auth.py
tools/replay/replay <route-name>
```

For route segments already stored on disk, pass their parent directory:

```bash
tools/replay/replay <route-name> --data_dir=/path/to/routes
```

Useful replay options:

```bash
# Stop when the route finishes instead of looping.
tools/replay/replay --demo --no-loop

# Start at a time offset and adjust playback speed.
tools/replay/replay <route-name> --start 60 --playback 2

# Include driver and wide camera streams for watch3.
tools/replay/replay --demo --dcam --ecam
./selfdrive/ui/watch3.py
```

`replay` uses the repository's default message transport. Set `ZMQ=1` only
when the subscriber being debugged explicitly needs ZMQ:

```bash
ZMQ=1 tools/replay/replay <route-name>
```

For the full option list, run `tools/replay/replay --help`. For stream
inspection with PlotJuggler, replay the route in one terminal and run
`tools/plotjuggler/juggle.py --stream` in another.

## Run the manager on a PC with a webcam

The manager can run on a development PC only with the webcam path enabled.
This is a hardware-in-the-loop workflow, not a replay workflow. It requires
Ubuntu 24.04 or macOS, a USB webcam (at least 720p with a suitable field of
view), a vehicle harness, a panda, and the appropriate USB cabling. WSL2 is
not supported.

Connect the road camera before the panda, activate the UV environment, then
start the process manager from the repository root:

```bash
source .venv/bin/activate
USE_WEBCAM=1 system/manager/manager.py
```

The road camera defaults to device index 0. Select a different camera or
optional driver/wide cameras with:

```bash
USE_WEBCAM=1 ROAD_CAM=1 DRIVER_CAM=2 WIDE_CAM=3 system/manager/manager.py
```

Use this workflow only when the hardware setup, calibration, and vehicle-port
safety requirements are understood. For pre-AP Tesla control changes, follow
the mandatory safety test and real-log replay requirements in
[`safety-model.md`](safety-model.md); do not use a PC manager launch as the
only validation.

## Test a single component

Most components can be run or tested independently once the virtual
environment is active. Prefer the smallest relevant command while developing:

```bash
# NAP engagement state-machine tests
python -m pytest opendbc_repo/opendbc/car/tesla/preap/tests/test_preap_engagement.py

# Panda safety tests for the pre-AP port
python -m pytest opendbc_repo/opendbc/safety/tests/test_tesla_preap.py -v
```

See `docs-nap/contributing.md` for CI-equivalent builds and the full
pre-push safety checklist.

## Troubleshoot UI test setup

UI collection requires an X11 display. On Ubuntu, install the headless display
server and its diagnostic utility if the setup helper reports that Xvfb is
missing:

```bash
sudo apt-get install xvfb x11-utils
```

Then authenticate before sourcing the helper; this prevents `sudo Xvfb` from
being suspended while reading a password in the background:

```bash
sudo -v
source selfdrive/test/setup_xvfb.sh
DISPLAY=:99 xdpyinfo >/dev/null && echo "Xvfb is ready"
```

If the helper reports a startup failure or timeout, inspect
`/tmp/openpilot-xvfb.log`. Without an active `:99` display, PyRay/Raylib UI
tests can segfault during import rather than reporting a normal Python error.

## Rebuild acados on hardened Linux systems

Some Linux environments reject the historical executable-stack request in the
prebuilt BLASFEO solver library. `third_party/acados/build.sh` builds the
shared libraries with a non-executable stack; rebuild it after checking out a
version that includes that change:

```bash
./third_party/acados/build.sh
scons -j"$(nproc)"
```

The acados build downloads its pinned source revision and requires CMake,
Make, a C/C++ compiler, and Cargo for its template renderer. The rebuilt
library is architecture-specific (`x86_64`, `larch64`, or `Darwin`).

### Updating acados

The MPC generators and the vendored `acados_template` Python package are a
single compatibility unit. Do not merge a generator API change by itself:
`scons` regenerates MPC code from the committed
`third_party/acados/acados_template`, so an integration/template mismatch
fails every CI job that builds openpilot.

After changing `third_party/acados/build.sh`, an acados pin, or MPC generator
code, run the **vendor acados** Actions workflow for the branch. It builds the
native `x86_64`, `larch64`, and `Darwin` artifacts and opens a separate vendor
pull request containing the matching headers, template, renderer, libraries,
and `lib/link_libs.json`. Merge that vendor pull request before relying on
ordinary build or test CI.

For a local update, rebuild the host artifacts and then build from the
generated vendor tree:

```bash
./third_party/acados/build.sh
scons -j"$(nproc)"
```

Before committing, confirm the vendor update includes the generated
`third_party/acados/include`, `acados_template`, `x86_64`, `larch64`,
`Darwin`, and `lib/link_libs.json` paths. A successful local build with
uncommitted generated files does not validate a clean CI checkout.
