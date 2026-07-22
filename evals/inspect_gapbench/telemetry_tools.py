"""Inspect wrappers for hash-bound physical telemetry evidence."""

from __future__ import annotations

import base64
import json
from typing import Any

from inspect_ai._util.content import ContentImage, ContentText
from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import Tool, tool

from sim2claw.physical_telemetry import PhysicalTelemetryError, PhysicalTelemetrySession


def _session(
    sessions: dict[str, PhysicalTelemetrySession], recording_id: str
) -> PhysicalTelemetrySession:
    try:
        return sessions[recording_id]
    except KeyError as error:
        raise PhysicalTelemetryError("recording_id is not active in this task") from error


def telemetry_inspect_tools(
    sessions: dict[str, PhysicalTelemetrySession],
) -> list[Tool]:
    @tool(name="telemetry_status")
    def telemetry_status_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Return evidence availability, budgets, identity, and claim boundary.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).telemetry_status(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_joint_trace")
    def read_joint_trace_tool() -> Tool:
        async def execute(
            recording_id: str, start: int = 0, limit: int = 100
        ) -> str:
            """Read synchronized requested, commanded, measured, velocity, current, and timing rows.

            Args:
                recording_id: Exact active physical recording identifier.
                start: Zero-based sample offset.
                limit: Maximum rows to return, up to 200.
            """
            return json.dumps(
                _session(sessions, recording_id).read_joint_trace(
                    recording_id, start, limit
                ),
                sort_keys=True,
            )

        return execute

    @tool(name="read_camera_frame")
    def read_camera_frame_tool() -> Tool:
        async def execute(recording_id: str, phase: str) -> list[Any]:
            """Return one hash-bound qualitative endpoint frame and metadata.

            Args:
                recording_id: Exact active physical recording identifier.
                phase: Either initial or final.
            """
            metadata, path = _session(sessions, recording_id).read_camera_frame(
                recording_id, phase
            )
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return [
                ContentText(text=json.dumps(metadata, sort_keys=True)),
                ContentImage(image=f"data:image/png;base64,{encoded}", detail="high"),
            ]

        return execute

    @tool(name="read_object_trajectory")
    def read_object_trajectory_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Report whether a measured metric object trajectory exists.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_object_trajectory(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_contact_and_grasp_outcomes")
    def read_contact_and_grasp_outcomes_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Report recorded contact/grasp availability and episode-label context.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_contact_and_grasp_outcomes(
                    recording_id
                ),
                sort_keys=True,
            )

        return execute

    @tool(name="read_execution_timing")
    def read_execution_timing_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Read sample/control/video timing summaries and latency limitations.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_execution_timing(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_episode_outcome")
    def read_episode_outcome_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Read the human-teleoperation receipt outcome and its limitations.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_episode_outcome(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_trace_comparison")
    def read_trace_comparison_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Read deterministic command-versus-measured comparison statistics.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_trace_comparison(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="submit_telemetry_audit")
    def submit_telemetry_audit_tool() -> Tool:
        async def execute(
            recording_id: str,
            audit: dict[str, Any],
            claim_boundary: str,
        ) -> str:
            """Submit the exact observed/unavailable inventory and comparison digest.

            Args:
                recording_id: Exact active physical recording identifier.
                audit: Available list, unavailable list, and trace comparison SHA-256.
                claim_boundary: Must be retrospective_physical_observation_only.
            """
            return json.dumps(
                _session(sessions, recording_id).submit_telemetry_audit(
                    recording_id, audit, claim_boundary
                ),
                sort_keys=True,
            )

        return execute

    return [
        telemetry_status_tool(),
        read_joint_trace_tool(),
        read_camera_frame_tool(),
        read_object_trajectory_tool(),
        read_contact_and_grasp_outcomes_tool(),
        read_execution_timing_tool(),
        read_episode_outcome_tool(),
        read_trace_comparison_tool(),
        submit_telemetry_audit_tool(),
    ]


def physical_telemetry_bridge(
    sessions: dict[str, PhysicalTelemetrySession],
) -> BridgedToolsSpec:
    return BridgedToolsSpec(
        name="physical_telemetry", tools=telemetry_inspect_tools(sessions)
    )
