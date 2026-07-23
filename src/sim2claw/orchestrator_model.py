"""Exact, server-side OpenAI Responses adapter for bounded dry-run decisions."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


MODEL_TURN_SCHEMA = "sim2claw.orchestrator_model_turn.v1"
DECISIONS = {"observe", "ask_user", "run_skill", "pause", "complete"}


SYSTEM_PROMPT = """You are the bounded sim2claw Studio Task Orchestrator planner.

The named base case has B1, C2, D1, E2, F1, and G2 occupied by brown pawns and B2, C1, D2, E1, F2, and G1 empty. The named inverse base case flips every managed file: B2, C1, D2, E1, F2, and G1 are occupied and B1, C2, D1, E2, F1, and G2 are empty. Base case to inverse base case therefore consists of B1->B2, C2->C1, D1->D2, E2->E1, F1->F2, and G2->G1. The reverse direction uses B2->B1, C1->C2, D2->D1, E1->E2, F2->F1, and G1->G2. The named command "loop the base case" means: first restore or confirm the named base case, then transition one same-file move at a time to the named inverse base case, then transition one same-file move at a time back to the named base case, and repeat those inverse/base phases for the requested duration. Reacquire and verify a registered observation after every move; never queue or execute the next phase while a prior postcondition is unverified.

Only files B through G on ranks 1 and 2 are managed; every other square, piece, robot, prop, and workcell element is immutable context. You may request exactly one allowlisted skill per decision. For a run_skill decision, expected_postcondition must describe only that one move: occupied contains only the destination square and empty contains only the source square. Do not put the full target layout into a one-skill postcondition. You may propose an action, but executor validation owns whether it can run. Ask the user for help whenever occupancy, calibration, an obstruction, skill readiness, or postcondition confidence is insufficient. One exception is an explicit planning-only request that states a named starting layout and named target layout or requests the named base-case loop: you may use that stated layout as a non-visual planning assumption and propose the first same-file move in B-through-G order, even when perception is unregistered or the executor reports the skill unavailable. In that case, say clearly that the proposal is planning-only and that it grants no execution authority. A requested loop duration is a planning horizon, not permission to bypass per-move perception, skill-readiness, postcondition, hardware, or operator gates. You cannot declare success: only the deterministic state checker or separate evaluator owns completion. You cannot train or promote a policy, change a checkpoint or contract, call an arbitrary command, or emit raw joint or servo actions. Return only the required schema."""


class OrchestratorModelError(RuntimeError):
    def __init__(self, code: str, message: str, *, detail: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.detail = dict(detail or {})

    def receipt(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "detail": self.detail}


@dataclass(frozen=True)
class JSONResponse:
    status: int
    payload: dict[str, Any]


Transport = Callable[
    [str, str, Mapping[str, str], Mapping[str, Any] | None, float], JSONResponse
]


class _RejectProviderRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise OrchestratorModelError(
            "redirect_rejected",
            "OpenAI request redirected; provider redirects are not allowed.",
            detail={"status": int(code), "target_host": urlsplit(newurl).hostname},
        )


def _default_transport(
    method: str,
    url: str,
    headers: Mapping[str, str],
    payload: Mapping[str, Any] | None,
    timeout: float,
) -> JSONResponse:
    body = None
    request_headers = dict(headers)
    if payload is not None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method)
    opener = build_opener(_RejectProviderRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise OrchestratorModelError(
                    "oversized_provider_response",
                    "OpenAI response exceeded the bounded response size.",
                )
            parsed = json.loads(raw.decode("utf-8"))
            if not isinstance(parsed, dict):
                raise OrchestratorModelError(
                    "malformed_provider_response", "OpenAI response was not a JSON object."
                )
            return JSONResponse(int(response.status), parsed)
    except OrchestratorModelError:
        raise
    except HTTPError as error:
        try:
            error_payload = json.loads(error.read(256 * 1024).decode("utf-8"))
        except Exception:
            error_payload = {}
        provider_error = error_payload.get("error") if isinstance(error_payload, dict) else {}
        detail = {
            "status": int(error.code),
            "provider_error_type": (
                provider_error.get("type") if isinstance(provider_error, dict) else None
            ),
            "provider_error_code": (
                provider_error.get("code") if isinstance(provider_error, dict) else None
            ),
        }
        raise OrchestratorModelError(
            "provider_http_error",
            f"OpenAI returned HTTP {error.code}.",
            detail=detail,
        ) from error
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as error:
        raise OrchestratorModelError(
            "provider_unavailable",
            f"OpenAI request failed: {type(error).__name__}: {error}",
        ) from error


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_decision_schema(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("$id") != "sim2claw.orchestrator_decision.v1":
        raise ValueError("unexpected orchestrator decision schema")
    return payload


def validate_decision(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise OrchestratorModelError("invalid_model_output", "Model decision is not an object.")
    expected_keys = {
        "decision",
        "reason",
        "skill_id",
        "arguments",
        "expected_postcondition",
        "confidence",
    }
    if set(payload) != expected_keys:
        raise OrchestratorModelError(
            "invalid_model_output",
            "Model decision fields do not match the frozen schema.",
            detail={"observed_fields": sorted(payload)},
        )
    decision = payload["decision"]
    reason = payload["reason"]
    skill_id = payload["skill_id"]
    arguments = payload["arguments"]
    expected_postcondition = payload["expected_postcondition"]
    confidence = payload["confidence"]
    if decision not in DECISIONS:
        raise OrchestratorModelError("invalid_model_output", "Model decision enum is invalid.")
    if not isinstance(reason, str) or not 1 <= len(reason) <= 500:
        raise OrchestratorModelError("invalid_model_output", "Model reason is invalid.")
    if not isinstance(arguments, dict) or set(arguments) - {
        "source_square",
        "destination_square",
    }:
        raise OrchestratorModelError("invalid_model_output", "Model skill arguments are invalid.")
    if not isinstance(expected_postcondition, dict) or set(expected_postcondition) - {
        "occupied",
        "empty",
    }:
        raise OrchestratorModelError(
            "invalid_model_output", "Model expected postcondition is invalid."
        )
    for values in expected_postcondition.values():
        if not isinstance(values, list) or not all(
            isinstance(value, str) and len(value) == 2 and value[0] in "bcdefg" and value[1] in "12"
            for value in values
        ):
            raise OrchestratorModelError(
                "invalid_model_output", "Model postcondition squares are invalid."
            )
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise OrchestratorModelError("invalid_model_output", "Model confidence is invalid.")
    if not 0 <= float(confidence) <= 1:
        raise OrchestratorModelError("invalid_model_output", "Model confidence is out of range.")
    if decision == "run_skill":
        if not isinstance(skill_id, str) or not skill_id:
            raise OrchestratorModelError(
                "invalid_model_output", "run_skill requires a non-empty skill_id."
            )
        if set(arguments) != {"source_square", "destination_square"}:
            raise OrchestratorModelError(
                "invalid_model_output", "run_skill requires exact source/destination arguments."
            )
    elif skill_id is not None or arguments:
        raise OrchestratorModelError(
            "invalid_model_output", "Non-skill decisions cannot carry a skill request."
        )
    return {
        "decision": str(decision),
        "reason": reason,
        "skill_id": skill_id,
        "arguments": dict(arguments),
        "expected_postcondition": dict(expected_postcondition),
        "confidence": float(confidence),
    }


def _output_text(response: Mapping[str, Any]) -> str:
    texts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("type") == "output_text":
                text = content.get("text")
                if isinstance(text, str):
                    texts.append(text)
    if len(texts) != 1:
        raise OrchestratorModelError(
            "malformed_provider_response",
            "OpenAI response did not contain exactly one structured output text item.",
        )
    return texts[0]


class OpenAIOrchestratorModel:
    def __init__(
        self,
        config: Mapping[str, Any],
        decision_schema: Mapping[str, Any],
        *,
        api_key: str | None,
        transport: Transport = _default_transport,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = json.loads(json.dumps(config))
        self.decision_schema = json.loads(json.dumps(decision_schema))
        self.api_key = api_key
        self.transport = transport
        self.monotonic = monotonic
        self.preflight_result: dict[str, Any] | None = None
        self.closed = False
        if self.config.get("user_facing_label") != "5.6 luna":
            raise ValueError("model label is not the frozen 5.6 luna label")
        if self.config.get("provider_model_id") != "gpt-5.6-luna":
            raise ValueError("provider model is not the frozen gpt-5.6-luna identifier")
        if self.config.get("reasoning_effort") != "medium":
            raise ValueError("model reasoning effort is not medium")
        if self.config.get("endpoint") != "https://api.openai.com/v1/responses":
            raise ValueError("model endpoint is not the frozen OpenAI Responses endpoint")
        if self.config.get("model_preflight_endpoint") != (
            "https://api.openai.com/v1/models/gpt-5.6-luna"
        ):
            raise ValueError("model preflight endpoint is not the exact frozen model endpoint")
        if self.config.get("maximum_attempts") != 1:
            raise ValueError("model adapter must make exactly one attempt")
        if self.config.get("store") is not False:
            raise ValueError("model response storage must remain disabled")
        if self.config.get("allow_model_substitution") is not False:
            raise ValueError("model substitution must remain disabled")

    def close(self) -> None:
        self.closed = True
        self.api_key = None

    def preflight(self, *, refresh: bool = False) -> dict[str, Any]:
        if self.closed:
            return {
                "ready": False,
                "model": self.config["provider_model_id"],
                "reason": "model adapter is closed",
                "physical_authority": False,
            }
        if self.preflight_result is not None and not refresh:
            return dict(self.preflight_result)
        if not self.api_key:
            self.preflight_result = {
                "ready": False,
                "model": self.config["provider_model_id"],
                "reason": "OpenAI API key is absent",
                "physical_authority": False,
            }
            return dict(self.preflight_result)
        try:
            response = self.transport(
                "GET",
                self.config["model_preflight_endpoint"],
                {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
                None,
                float(self.config["timeout_seconds"]),
            )
            observed_model = response.payload.get("id")
            if response.status != 200 or observed_model != self.config["provider_model_id"]:
                raise OrchestratorModelError(
                    "model_identity_mismatch",
                    "OpenAI model preflight did not resolve the exact frozen identifier.",
                    detail={"status": response.status, "observed_model": observed_model},
                )
        except OrchestratorModelError as error:
            self.preflight_result = {
                "ready": False,
                "model": self.config["provider_model_id"],
                "reason": str(error),
                "error": error.receipt(),
                "physical_authority": False,
            }
            return dict(self.preflight_result)
        self.preflight_result = {
            "ready": True,
            "model": self.config["provider_model_id"],
            "user_facing_label": self.config["user_facing_label"],
            "reasoning_effort": self.config["reasoning_effort"],
            "substitution_allowed": False,
            "physical_authority": False,
        }
        return dict(self.preflight_result)

    def decide(
        self,
        *,
        context: Mapping[str, Any],
        accepted_frame_bytes: bytes,
        accepted_frame_encoding: str,
        reference_frame_bytes: bytes,
    ) -> dict[str, Any]:
        preflight = self.preflight()
        if not preflight["ready"]:
            raise OrchestratorModelError(
                "model_unavailable",
                str(preflight.get("reason") or "Exact configured model is unavailable."),
                detail={"model": self.config["provider_model_id"]},
            )
        safe_context = json.loads(json.dumps(context))
        request_identity = {
            "adapter_id": self.config["adapter_id"],
            "model": self.config["provider_model_id"],
            "reasoning_effort": self.config["reasoning_effort"],
            "context_sha256": _canonical_sha256(safe_context),
            "accepted_frame_sha256": hashlib.sha256(accepted_frame_bytes).hexdigest(),
            "reference_frame_sha256": hashlib.sha256(reference_frame_bytes).hexdigest(),
        }
        content = [
            {
                "type": "input_text",
                "text": json.dumps(safe_context, sort_keys=True, separators=(",", ":")),
            },
            {
                "type": "input_image",
                "image_url": (
                    f"data:image/{accepted_frame_encoding};base64,"
                    + base64.b64encode(accepted_frame_bytes).decode("ascii")
                ),
                "detail": "low",
            },
            {
                "type": "input_image",
                "image_url": "data:image/png;base64,"
                + base64.b64encode(reference_frame_bytes).decode("ascii"),
                "detail": "low",
            },
        ]
        provider_schema = {
            key: value
            for key, value in self.decision_schema.items()
            if key not in {"$schema", "$id"}
        }
        payload = {
            "model": self.config["provider_model_id"],
            "reasoning": {"effort": self.config["reasoning_effort"]},
            "instructions": SYSTEM_PROMPT,
            "input": [{"role": "user", "content": content}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "sim2claw_orchestrator_decision_v1",
                    "description": "One bounded sim2claw task-orchestrator decision.",
                    "strict": True,
                    "schema": provider_schema,
                }
            },
            "max_output_tokens": int(self.config["maximum_output_tokens"]),
            "store": bool(self.config["store"]),
        }
        started = self.monotonic()
        response = self.transport(
            "POST",
            self.config["endpoint"],
            {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
            payload,
            float(self.config["timeout_seconds"]),
        )
        latency_ms = round((self.monotonic() - started) * 1000.0, 3)
        if response.status != 200:
            raise OrchestratorModelError(
                "provider_http_error",
                f"OpenAI returned HTTP {response.status}.",
                detail={"status": response.status},
            )
        observed_model = response.payload.get("model")
        if observed_model != self.config["provider_model_id"]:
            raise OrchestratorModelError(
                "model_identity_mismatch",
                "OpenAI response model did not match the frozen provider identifier.",
                detail={"observed_model": observed_model},
            )
        try:
            raw_decision = json.loads(_output_text(response.payload))
        except json.JSONDecodeError as error:
            raise OrchestratorModelError(
                "invalid_model_output", "Structured model output was not valid JSON."
            ) from error
        decision = validate_decision(raw_decision)
        usage = response.payload.get("usage") or {}
        return {
            "schema_version": MODEL_TURN_SCHEMA,
            "request_id": response.payload.get("id"),
            "request_identity": request_identity,
            "request_identity_sha256": _canonical_sha256(request_identity),
            "model": observed_model,
            "user_facing_label": self.config["user_facing_label"],
            "reasoning_effort": self.config["reasoning_effort"],
            "response_status": response.payload.get("status"),
            "decision": decision,
            "validation": {"valid": True, "schema_id": self.decision_schema["$id"]},
            "latency_ms": latency_ms,
            "usage": {
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "reasoning_tokens": (usage.get("output_tokens_details") or {}).get(
                    "reasoning_tokens"
                ),
            },
            "cost": {"amount": None, "currency": None, "provider_reported": False},
            "store": False,
            "physical_authority": False,
        }
