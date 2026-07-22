"""Six bounded tools shared by native and Inspect GapBench harnesses."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .gapbench_contracts import (
    ATTEMPT_SCHEMA,
    CLAIM_BOUNDARY,
    GapBenchContractError,
    load_candidate,
    load_public_case,
    validate_hypotheses,
    validate_prediction,
)
from .gapbench_evaluator import SealedEvaluator, public_evaluate
from .learning_factory_artifacts import atomic_write_json, canonical_digest, load_json_object


TOOL_NAMES = (
    "case_status",
    "read_evidence",
    "submit_hypotheses",
    "request_probe",
    "run_public_evaluation",
    "submit_candidate",
)


class GapBenchSession:
    """Stateful host-side implementation of the six-tool contract."""

    def __init__(
        self,
        packet_root: Path,
        sealed_evaluator: SealedEvaluator,
        state_root: Path,
        *,
        reset: bool = False,
    ):
        self.packet_root = packet_root.resolve()
        self.case = load_public_case(self.packet_root)
        if self.case["case_id"] != sealed_evaluator.case_id:
            raise GapBenchContractError("public and sealed case identities differ")
        self.sealed_evaluator = sealed_evaluator
        self.state_root = state_root.resolve()
        self.state_root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_root / "session_state.json"
        if reset:
            for generated in (self.state_path, self.state_root / "attempt.json", self.state_root / "score_receipt.json"):
                generated.unlink(missing_ok=True)
        if not self.state_path.exists():
            self._write_state({
                "case_id": self.case["case_id"],
                "used": {"probes": 0, "public_evaluations": 0, "terminal_submissions": 0},
                "hypotheses": [],
                "events": [],
                "forbidden_attempts": 0,
                "terminal_receipt": None,
            })
        self._state()

    def terminal_receipt(self) -> dict[str, Any] | None:
        receipt = self._state().get("terminal_receipt")
        return copy.deepcopy(receipt) if isinstance(receipt, dict) else None

    def _state(self) -> dict[str, Any]:
        state = load_json_object(self.state_path, label="GapBench session state")
        if state.get("case_id") != self.case["case_id"]:
            raise GapBenchContractError("session state case identity mismatch")
        return state

    def _write_state(self, state: dict[str, Any]) -> None:
        atomic_write_json(self.state_path, state)

    def _event(self, state: dict[str, Any], tool: str, payload: dict[str, Any]) -> None:
        state["events"].append({"sequence": len(state["events"]) + 1, "tool": tool, "payload": payload})

    def _require_case(self, case_id: str) -> None:
        if case_id != self.case["case_id"]:
            raise GapBenchContractError("case_id does not match the active frozen case")

    def _charge(self, state: dict[str, Any], budget: str) -> None:
        limit = int(self.case["budgets"][budget])
        if int(state["used"][budget]) >= limit:
            raise GapBenchContractError(f"{budget} budget exhausted")
        state["used"][budget] += 1

    def case_status(self, case_id: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        remaining = {name: int(self.case["budgets"][name]) - int(state["used"][name]) for name in state["used"]}
        result = {
            "case_id": case_id,
            "case_sha256": self.case["case_sha256"],
            "proof_class": self.case["proof_class"],
            "fault_families": self.case["allowed_fault_families"],
            "parameter_envelopes": self.case["parameter_envelopes"],
            "evidence": [{"artifact_id": row["artifact_id"], "media_type": row["media_type"]} for row in self.case["evidence_manifest"]],
            "probe_menu": copy.deepcopy(self.case["probe_menu"]),
            "remaining_budgets": remaining,
            "hypotheses_submitted": bool(state["hypotheses"]),
            "terminal": state["terminal_receipt"] is not None,
            "allowed_next_actions": [] if state["terminal_receipt"] is not None else list(TOOL_NAMES[1:]),
        }
        return result

    def read_evidence(self, case_id: str, artifact_id: str, start: int = 0, limit: int = 100) -> dict[str, Any]:
        self._require_case(case_id)
        if start < 0 or limit <= 0 or limit > 200:
            raise GapBenchContractError("evidence slice is outside bounds")
        row = next((item for item in self.case["evidence_manifest"] if item["artifact_id"] == artifact_id), None)
        if row is None:
            raise GapBenchContractError("artifact_id is not in the public manifest")
        path = (self.packet_root / row["path"]).resolve()
        if self.packet_root not in path.parents:
            raise GapBenchContractError("evidence path escaped the packet")
        artifact = load_json_object(path, label="public evidence")
        rows = artifact.get("rows")
        if isinstance(rows, list):
            artifact = {**artifact, "rows": rows[start : start + limit], "slice": {"start": start, "limit": limit, "total": len(rows)}}
        return artifact

    def submit_hypotheses(self, case_id: str, hypotheses: list[dict[str, Any]]) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        if state["terminal_receipt"] is not None:
            raise GapBenchContractError("attempt is terminal")
        normalized = validate_hypotheses(hypotheses)
        state["hypotheses"] = normalized
        self._event(state, "submit_hypotheses", {"hypotheses_sha256": canonical_digest(normalized)})
        self._write_state(state)
        return {"accepted": True, "hypotheses_sha256": canonical_digest(normalized), "count": len(normalized)}

    def request_probe(self, case_id: str, probe_id: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        if state["terminal_receipt"] is not None:
            raise GapBenchContractError("attempt is terminal")
        declared = next((item for item in self.case["probe_menu"] if item["probe_id"] == probe_id), None)
        if declared is None:
            state["forbidden_attempts"] += 1
            self._event(state, "forbidden_probe", {"probe_id": probe_id})
            self._write_state(state)
            raise GapBenchContractError("probe is undeclared or forbidden")
        if declared["mode"] not in {"simulated", "read_only"}:
            raise GapBenchContractError("physical probes are disabled")
        self._charge(state, "probes")
        receipt = self.sealed_evaluator.probe(probe_id)
        self._event(state, "request_probe", {"probe_id": probe_id, "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        return receipt

    def run_public_evaluation(self, case_id: str, candidate_ref: str) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        if state["terminal_receipt"] is not None:
            raise GapBenchContractError("attempt is terminal")
        self._charge(state, "public_evaluations")
        candidate = load_candidate(self.packet_root, candidate_ref, self.case)
        evidence = self.read_evidence(case_id, "development_rollouts", 0, 200)
        rows = evidence.get("rows")
        if not isinstance(rows, list):
            raise GapBenchContractError("development_rollouts evidence has no rows")
        receipt = public_evaluate(self.case, {"parameters": candidate["parameters"]}, rows)
        receipt["candidate_sha256"] = candidate["candidate_sha256"]
        receipt["receipt_sha256"] = canonical_digest({key: value for key, value in receipt.items() if key != "receipt_sha256"})
        self._event(state, "run_public_evaluation", {"candidate_sha256": candidate["candidate_sha256"], "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        return receipt

    def submit_candidate(
        self,
        case_id: str,
        candidate_ref: str,
        prediction: dict[str, Any],
        claim_boundary: str,
    ) -> dict[str, Any]:
        self._require_case(case_id)
        state = self._state()
        if state["terminal_receipt"] is not None:
            raise GapBenchContractError("terminal submission already exists")
        if not state["hypotheses"]:
            raise GapBenchContractError("hypotheses must be submitted before the terminal candidate")
        if claim_boundary != CLAIM_BOUNDARY:
            raise GapBenchContractError("claim_boundary must be synthetic_only")
        normalized_prediction = validate_prediction(prediction)
        candidate = load_candidate(self.packet_root, candidate_ref, self.case)
        self._charge(state, "terminal_submissions")
        attempt = {
            "schema_version": ATTEMPT_SCHEMA,
            "case_id": case_id,
            "case_sha256": self.case["case_sha256"],
            "candidate_ref": candidate["candidate_ref"],
            "candidate_sha256": candidate["candidate_sha256"],
            "hypotheses": state["hypotheses"],
            "prediction": normalized_prediction,
            "claim_boundary": claim_boundary,
            "budgets_used": copy.deepcopy(state["used"]),
            "forbidden_attempts": int(state["forbidden_attempts"]),
            "promotion_authority": False,
        }
        attempt_sha256 = canonical_digest(attempt)
        attempt["attempt_sha256"] = attempt_sha256
        receipt = self.sealed_evaluator.score(
            case=self.case,
            candidate={"parameters": candidate["parameters"]},
            hypotheses=state["hypotheses"],
            prediction=normalized_prediction,
            claim_boundary=claim_boundary,
            probes_used=int(state["used"]["probes"]),
            forbidden_attempts=int(state["forbidden_attempts"]),
            candidate_sha256=candidate["candidate_sha256"],
            attempt_sha256=attempt_sha256,
        )
        atomic_write_json(self.state_root / "attempt.json", attempt)
        atomic_write_json(self.state_root / "score_receipt.json", receipt)
        state["terminal_receipt"] = receipt
        self._event(state, "submit_candidate", {"attempt_sha256": attempt_sha256, "receipt_sha256": receipt["receipt_sha256"]})
        self._write_state(state)
        return receipt
