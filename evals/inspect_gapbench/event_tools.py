"""Inspect wrappers for bounded interaction-event evidence and annotations."""

from __future__ import annotations

import base64
import json
from typing import Any

from inspect_ai._util.content import ContentImage, ContentText
from inspect_ai.agent import BridgedToolsSpec
from inspect_ai.tool import Tool, tool

from sim2claw.interaction_events import InteractionEventError, InteractionEventSession


def _session(
    sessions: dict[str, InteractionEventSession], recording_id: str
) -> InteractionEventSession:
    try:
        return sessions[recording_id]
    except KeyError as error:
        raise InteractionEventError("recording_id is not active in this task") from error


def interaction_event_tools(
    sessions: dict[str, InteractionEventSession],
) -> list[Tool]:
    @tool(name="event_status")
    def event_status_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Return event evidence identity, availability, budgets, and boundaries.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).event_status(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_event_proposals")
    def read_event_proposals_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Read ordered deterministic event candidates and phase intervals.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_event_proposals(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_event_metrics")
    def read_event_metrics_tool() -> Tool:
        async def execute(recording_id: str) -> str:
            """Read phase metrics, mechanical-load proxy, lag, and unavailable facts.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            return json.dumps(
                _session(sessions, recording_id).read_event_metrics(recording_id),
                sort_keys=True,
            )

        return execute

    @tool(name="read_interaction_strip")
    def read_interaction_strip_tool() -> Tool:
        async def execute(recording_id: str) -> list[Any]:
            """Return the synchronized nine-frame qualitative interaction strip.

            Args:
                recording_id: Exact active physical recording identifier.
            """
            metadata, path = _session(sessions, recording_id).read_interaction_strip(
                recording_id
            )
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            return [
                ContentText(text=json.dumps(metadata, sort_keys=True)),
                ContentImage(image=f"data:image/png;base64,{encoded}", detail="high"),
            ]

        return execute

    @tool(name="submit_visual_annotation")
    def submit_visual_annotation_tool() -> Tool:
        async def execute(
            recording_id: str,
            fields: dict[str, str],
            occlusion: str,
            confidence: str,
            rationale: str,
            annotator_system: str,
            model_identifier: str,
            prompt_sha256: str,
        ) -> str:
            """Submit one finite visual annotation without outcome or truth claims.

            Args:
                recording_id: Exact active physical recording identifier.
                fields: Frozen visibility fields using finite annotation enums.
                occlusion: One of none, partial, severe, or unknown.
                confidence: One of low, medium, or high.
                rationale: Short visible-evidence explanation.
                annotator_system: Harness/system identity.
                model_identifier: Exact model or system identifier.
                prompt_sha256: Digest returned by event_status.
            """
            return json.dumps(
                _session(sessions, recording_id).submit_visual_annotation(
                    recording_id,
                    {
                        "fields": fields,
                        "occlusion": occlusion,
                        "confidence": confidence,
                        "rationale": rationale,
                        "annotator_system": annotator_system,
                        "model_identifier": model_identifier,
                        "prompt_sha256": prompt_sha256,
                    },
                ),
                sort_keys=True,
            )

        return execute

    @tool(name="submit_event_audit")
    def submit_event_audit_tool() -> Tool:
        async def execute(
            recording_id: str,
            event_episode_sha256: str,
            annotation_sha256: str,
            claim_boundary: str,
        ) -> str:
            """Submit the exact event and annotation digests under the frozen boundary.

            Args:
                recording_id: Exact active physical recording identifier.
                event_episode_sha256: Digest returned by event_status.
                annotation_sha256: Digest returned after annotation submission.
                claim_boundary: Must be retrospective_multimodal_candidates_only.
            """
            return json.dumps(
                _session(sessions, recording_id).submit_event_audit(
                    recording_id,
                    event_episode_sha256,
                    annotation_sha256,
                    claim_boundary,
                ),
                sort_keys=True,
            )

        return execute

    return [
        event_status_tool(),
        read_event_proposals_tool(),
        read_event_metrics_tool(),
        read_interaction_strip_tool(),
        submit_visual_annotation_tool(),
        submit_event_audit_tool(),
    ]


def interaction_event_bridge(
    sessions: dict[str, InteractionEventSession],
) -> BridgedToolsSpec:
    return BridgedToolsSpec(
        name="interaction_events", tools=interaction_event_tools(sessions)
    )
