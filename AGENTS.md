# NotAutopilot AI Reference

This repository is NotAutopilot (NAP), a vehicle-specific fork of
[openpilot](https://github.com/commaai/openpilot). It provides driver
assistance for 2012-2014 pre-Autopilot Tesla Model S vehicles: lateral
steering through EPAS, optional Comma Pedal longitudinal control, optional
Bosch radar with gateway emulation, driver monitoring, on-device settings,
logging, and remote connectivity.

Read this file before locating implementation code. For behavior specific to
the pre-AP port, `docs-nap/` is authoritative:

- `docs-nap/architecture.md` describes the port's components and constraints.
- `docs-nap/engagement.md` specifies pedal and no-pedal engagement behavior.
- `docs-nap/safety-model.md` explains panda safety invariants.
- `docs-nap/contributing.md` specifies branches, submodules, builds, and
  safety validation.
- `docs-nap/local-development.md` specifies UV setup plus replay, UI, webcam,
  and focused local test workflows.

## System topology

`system/manager/manager.py` supervises the processes declared in
`system/manager/process_config.py`. The process registry gates services by
on-road state, hardware (PC versus comma/TICI device), camera mode, and car
capabilities.

Processes exchange typed Cap'n Proto messages over `cereal.messaging`.
`cereal/` owns schemas and messaging bindings; `common/params.py` provides
persistent cross-process settings and learned values. Do not replace a
message-channel interaction with shared process state.

The on-road control path is:

```text
camera/sensors/CAN
  -> camerad, sensord, pandad
  -> modeld, dmonitoringmodeld, locationd, radard
  -> plannerd
  -> controlsd (carControl)
  -> card (brand interface and CAN construction)
  -> pandad / panda firmware
  -> vehicle CAN
```

`selfdrived` owns engagement and event state; `controlsd` gates and computes
actuators from vehicle state, plans, perception, localization, and driver
monitoring. `card` creates the selected car interface, publishes vehicle
state/capabilities, and turns `carControl` into `sendcan`. Panda safety is an
independent lower layer: application code must not be treated as the final
actuator safety boundary.

Supporting services include `loggerd` and uploader (drive recording and
upload), `ui` and `soundd` (driver feedback), `paramsd` (parameter learning),
`updated` (software updates), `hardwared`, GPS services, and Athena/WebRTC
remote connectivity.

## Directory responsibilities

| Path | Responsibility | Relationship |
| --- | --- | --- |
| `selfdrive/` | Driving stack: controls, planners, vehicle bridge, models, localization, monitoring, UI, and replay tests. | Uses `cereal` messages, `common` helpers, and vehicle interfaces in `opendbc_repo`. |
| `system/` | Device services: process manager, cameras/sensors, logging, hardware abstraction, GPS, updater, telemetry, and WebRTC. | Starts and supports the driving stack. |
| `opendbc_repo/opendbc/` | Car ports, DBCs, vehicle models, CAN helpers, and panda safety definitions. | A NAP forked submodule; contains the pre-AP Tesla implementation. |
| `panda/` | Panda firmware, protocol, and hardware tooling. | Enforces safety and interfaces with CAN hardware; `selfdrive/pandad/` is its host-side bridge. |
| `cereal/` | Cap'n Proto schemas and pub/sub bindings. | Contract between independently supervised processes. |
| `common/` | Shared primitives such as Params, realtime, conversions, logging, and utilities. | Shared by system and driving processes. |
| `rednose/`, `tinygrad/`, `msgq/`, `teleoprtc/` | Checked-out dependency links to corresponding `*_repo` submodules. | Provide estimation, model/runtime, messaging, and real-time communication support. |
| `docs/` | General upstream-style user, safety, car-porting, and contributor documentation. | Complemented by NAP-specific docs in `docs-nap/`. |

Tests are normally colocated with their component. Cross-process replay tests
are under `selfdrive/test/`; test discovery and isolated test prefixes are
configured in `pyproject.toml` and `conftest.py`.

## Pre-AP Tesla port

The NAP-specific port lives in `opendbc_repo`, not `selfdrive`:

```text
opendbc_repo/opendbc/
├── car/tesla/preap/
│   ├── interface.py       # CarParams, capabilities, safety flags
│   ├── carstate.py        # CAN to CarState and button events
│   ├── carcontroller.py   # CarControl to steering, pedal, and stalk CAN
│   ├── engagement.py      # Stalk and engagement finite-state machine
│   ├── pedal_feedback.py  # Pedal parsing and health tracking
│   └── nap_conf.py        # Params-backed NAP configuration
├── dbc/tesla_preap.dbc    # CAN message definitions
└── safety/modes/tesla_preap.h
```

Pre-AP cars have no Autopilot ECU or harness relay. The standalone
`SAFETY_TESLA_PREAP` mode is intentionally separate from upstream Tesla modes.
Every transmitted CAN address must be explicitly whitelisted and configured
for the direct-CAN topology. Preserve the documented relay/static-blocking
exceptions when changing the safety mode.

The port has two mutually exclusive longitudinal paths:

| Configuration | Steering | Longitudinal | Relevant interface flags |
| --- | --- | --- | --- |
| Comma Pedal installed | NAP lateral control | NAP sends `GAS_COMMAND` (0x551) from the longitudinal planner. Brake drops longitudinal while lateral remains engaged. | `openpilotLongitudinalControl=True`, `pcmCruise=False` |
| No pedal | NAP lateral control | Stock Tesla cruise control; NAP spoofs stalk requests over 0x45 to engage/cancel it. | `openpilotLongitudinalControl=False`, `pcmCruise=True` |

Both paths use the stalk FSM. Echo-suppression windows prevent NAP's spoofed
stalk CAN messages from being interpreted as driver input. Do not change
stalk, brake, steering-disengage, or pedal logic without tracing the FSM,
`carstate.py`, `carcontroller.py`, and their tests together.

Optional Bosch radar support is implemented with GTW emulation. Its panda
forwarding logic must use the `rx_all` path because it has to observe frames
outside normal RX checks.

## Safety-critical invariants

`opendbc_repo/opendbc/safety/modes/tesla_preap.h` is the executable source of
truth. Read `docs-nap/safety-model.md` before modifying it.

- Panda's `controls_allowed` must gate every applicable transmission.
- Steering angle/rate limits, hands-on override, EPAS faults, door/gear state,
  stalk cancel, and AEB blocking are safety-layer responsibilities.
- Pedal transmission requires both the `ENABLE_PEDAL` safety flag and
  longitudinal permission.
- Pedal and no-pedal configurations require distinct RX-check sets; a
  zero-frequency check can invalidate safety timing.
- Brake behavior is intentionally non-generic: real brake state drops pedal
  longitudinal control but preserves lateral engagement. Panda reports
  `brakePressed=false` so generic openpilot brake handling does not also
  disengage lateral.
- Python and panda vehicle-model/steering parameters must stay aligned. A
  mismatch creates different command limits in the two layers.

Never weaken an invariant merely to make a test, replay, or unsupported
hardware configuration pass. Any safety change needs corresponding coverage in
`opendbc_repo/opendbc/safety/tests/test_tesla_preap.py`.

## Build, test, and repository workflow

Python 3.12 dependencies and development tools are declared in
`pyproject.toml`; native/Cython components build with SCons. The target
hardware is a comma 3/3X (TICI/Linux ARM64), while Linux x86_64 and macOS
support development workflows.

```bash
# Initialize NAP-pinned submodules after checkout
git submodule sync --recursive
git submodule update --init --recursive

# Build native components
scons -j"$(nproc)"

# Run a focused pre-AP safety suite
python -m pytest opendbc_repo/opendbc/safety/tests/test_tesla_preap.py -v
```

Run the smallest relevant test suite for the changed component. Use a recorded
drive replay when changing process interactions, controls, CAN behavior, or RX
rate expectations. Safety changes additionally require building the safety
library and running the pre-AP safety tests; see `docs-nap/safety-model.md`.

Development targets `nap-dev`. Keep sunnypilot-specific code out of
`nap-dev`/`nap-alpha`; `naponsp-dev` is the dedicated branch. When changing
`opendbc_repo`, push its commit before updating the main repository's
submodule pointer. Update the leading release-notes section in `RELEASES.md`
for user-visible NAP changes.

## Change-navigation guide

| If changing... | Start with... |
| --- | --- |
| Core process lifecycle or service gating | `system/manager/manager.py`, `system/manager/process_config.py` |
| Message contract or a new pub/sub service | `cereal/` schemas and adjacent process publishers/subscribers |
| Vehicle state, CAN decoding, actuation, or NAP settings | `opendbc_repo/opendbc/car/tesla/preap/` |
| Safety behavior or CAN transmit allowlists | `opendbc_repo/opendbc/safety/modes/tesla_preap.h` and safety tests |
| Engagement, driver override, brake, or stalk behavior | `docs-nap/engagement.md`, then `engagement.py`, `carstate.py`, and `carcontroller.py` |
| On-road control algorithm | `selfdrive/controls/` plus messages consumed by `controlsd.py` |
| UI or device settings | `selfdrive/ui/` and the relevant Params-backed configuration |
| Build, test, lint, or dependency settings | `pyproject.toml`, `SConstruct`, `conftest.py`, and `docs-nap/contributing.md` |
