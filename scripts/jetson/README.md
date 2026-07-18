# Jetson ↔ SO-101 arm connection (teleop)

Manual leader→follower teleoperation helpers for a Jetson host that is USB-
wired to the SO-101 arms. These scripts are **not** the sim2claw gateway, do
**not** serve policies, and do **not** grant physical-task authority inside
the clean-room runtime. They only start/stop LeRobot teleop over SSH and
support follower calibration.

## Layout

| Path | Runs on | Role |
| --- | --- | --- |
| `mac-teleop.sh` | Mac (USB-C gadget link to Jetson) | `start` / `stop` / `status` over SSH |
| `so101-teleop-toggle` | Jetson | Starts or stops `lerobot-teleoperate` |
| `guided_follower_cal.py` | Jetson (LeRobot venv) | Interactive follower Feetech calibration |
| `ports.env.example` | Jetson | Template for serial port + robot id paths |
| `local.env.example` | Mac | Template for SSH host/user (no secrets in Git) |

Optional Mac UI: build `SO101TeleopApp.swift` with `swiftc` and point it at
`mac-teleop.sh` via `SIM2CLAW_JETSON_TELEOP_SCRIPT`.

## Prerequisites

- Jetson with LeRobot installed at `~/lerobot` (or set `LEROBOT_HOME`)
- Leader and follower serial adapters visible under `/dev/serial/by-id/`
- Calibration files present for both arms (see `calibration/so101/README.md`)
- Mac can SSH to the Jetson (USB gadget IP is often `192.168.55.1`)

## Configure (Mac)

```bash
cp scripts/jetson/local.env.example scripts/jetson/local.env
# edit local.env — never commit it
export SIM2CLAW_JETSON_ENV="$PWD/scripts/jetson/local.env"
./scripts/jetson/mac-teleop.sh status
./scripts/jetson/mac-teleop.sh start
./scripts/jetson/mac-teleop.sh stop
```

`local.env` must supply `JETSON_USER`, `JETSON_HOST`, and either
`JETSON_PASSWORD` (password auth) or rely on your SSH key. Prefer keys.

## Configure (Jetson)

```bash
mkdir -p ~/so101_config ~/.local/bin
cp scripts/jetson/ports.env.example ~/so101_config/ports.env
# set LEADER_PORT / FOLLOWER_PORT / ids to your by-id paths
cp scripts/jetson/so101-teleop-toggle ~/.local/bin/
chmod +x ~/.local/bin/so101-teleop-toggle
```

## Proof boundary

- Teleop evidence is physical and outside the simulation evaluator.
- No camera, gateway protocol, policy-server, or motion-permit path is opened
  by importing these scripts into the repository.
- Credentials, ports.env with host-specific serial IDs, and `local.env` stay
  out of Git.
