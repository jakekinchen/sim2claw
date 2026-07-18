#!/usr/bin/env python3
"""Interactive Feetech follower calibration for an SO-101 on the Jetson.

Requires a LeRobot environment with Feetech motors support. Serial port and
robot id come from the environment (or defaults matching ports.env.example).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode

PORT = os.environ.get(
    "FOLLOWER_PORT",
    "/dev/serial/by-id/usb-1a86_USB_Single_Serial_5B3D040641-if00",
)
ROBOT_ID = os.environ.get("FOLLOWER_ID", "so101_follower")
CALIB_DIR = Path.home() / ".cache/huggingface/lerobot/calibration/robots/so_follower"
MIN_SPAN = {
    "shoulder_pan": 400,
    "shoulder_lift": 400,
    "elbow_flex": 400,
    "wrist_flex": 200,
    "gripper": 100,
}

MOTORS = {
    n: Motor(i, "sts3215", MotorNormMode.DEGREES)
    for i, n in enumerate(
        ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"],
        1,
    )
}


def main() -> None:
    bus = FeetechMotorsBus(port=PORT, motors=MOTORS)
    bus.connect(handshake=False)
    print("CONNECTED", flush=True)
    bus.disable_torque()
    for motor in bus.motors:
        bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)
        bus.write("Torque_Enable", motor, 0)

    print("PHASE1_WAIT_MID: put follower in middle pose, then reply mid ready", flush=True)
    while not Path("/tmp/cal_mid").exists():
        time.sleep(0.2)
    Path("/tmp/cal_mid").unlink(missing_ok=True)
    print("MID_OK", flush=True)
    homing_offsets = bus.set_half_turn_homings()
    print("homings", homing_offsets, flush=True)

    record = [m for m in bus.motors if m != "wrist_roll"]
    mins = {m: 10**9 for m in record}
    maxs = {m: -1 for m in record}
    print("PHASE2_MOVE: move ALL joints fully, especially wrist bend + gripper", flush=True)

    start = time.time()
    last = 0.0
    while True:
        for m in record:
            pos = int(bus.read("Present_Position", m, normalize=False))
            mins[m] = min(mins[m], pos)
            maxs[m] = max(maxs[m], pos)
        now = time.time()
        if now - last > 1.0:
            ok = True
            parts = []
            for m in record:
                span = maxs[m] - mins[m]
                need = MIN_SPAN[m]
                mark = "OK" if span >= need else "LOW"
                if span < need:
                    ok = False
                parts.append(f"{m}:{span}/{need}{mark}")
            print("SPANS", " ".join(parts), flush=True)
            last = now
            if ok and (now - start) > 5:
                print("ALL_SPANS_OK", flush=True)
                break
        if Path("/tmp/cal_force_save").exists():
            Path("/tmp/cal_force_save").unlink(missing_ok=True)
            print("FORCE_SAVE", flush=True)
            break
        time.sleep(0.05)

    range_mins = dict(mins)
    range_maxes = dict(maxs)
    range_mins["wrist_roll"] = 0
    range_maxes["wrist_roll"] = 4095

    calibration = {
        motor: MotorCalibration(
            id=m.id,
            drive_mode=0,
            homing_offset=int(homing_offsets[motor]),
            range_min=int(range_mins[motor]),
            range_max=int(range_maxes[motor]),
        )
        for motor, m in bus.motors.items()
    }

    bad = [m for m in record if range_maxes[m] <= range_mins[m]]
    if bad:
        print("BAD_ZERO_SPAN", bad, flush=True)
        bus.disconnect(disable_torque=True)
        raise SystemExit(2)

    bus.write_calibration(calibration)
    CALIB_DIR.mkdir(parents=True, exist_ok=True)
    fpath = CALIB_DIR / f"{ROBOT_ID}.json"
    payload = {
        motor: {
            "id": c.id,
            "drive_mode": c.drive_mode,
            "homing_offset": c.homing_offset,
            "range_min": c.range_min,
            "range_max": c.range_max,
        }
        for motor, c in calibration.items()
    }
    fpath.write_text(json.dumps(payload, indent=2) + "\n")
    print("SAVED", str(fpath), flush=True)
    print(json.dumps(payload, indent=2), flush=True)
    bus.disconnect(disable_torque=True)
    print("FOLLOWER_CALIB_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
