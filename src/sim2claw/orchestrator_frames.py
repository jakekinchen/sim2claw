"""Protected Silicon snapshot intake and frozen frame-comparison primitives."""

from __future__ import annotations

import hashlib
import io
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import cv2
import numpy as np


FRAME_RECORD_SCHEMA = "sim2claw.orchestrator_frame_record.v1"


class FrameSourceError(RuntimeError):
    """Fail-closed remote-frame failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str, *, detail: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.detail = dict(detail or {})

    def receipt(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "detail": self.detail}


@dataclass(frozen=True)
class SnapshotResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes
    final_url: str


@dataclass(frozen=True)
class SnapshotFrame:
    image_bytes: bytes
    image_bgr: np.ndarray
    record: dict[str, Any]

    @property
    def sha256(self) -> str:
        return str(self.record["sha256"])


Requester = Callable[[str, Mapping[str, str], float, int], SnapshotResponse]


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        raise FrameSourceError(
            "redirect_rejected",
            "Silicon snapshot redirected; redirects are not allowed.",
            detail={"status": int(code), "target_host": urlsplit(newurl).hostname},
        )


def _default_requester(
    url: str,
    headers: Mapping[str, str],
    timeout: float,
    maximum_bytes: int,
) -> SnapshotResponse:
    request = Request(url, headers=dict(headers), method="GET")
    opener = build_opener(_RejectRedirects())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw_length = response.headers.get("Content-Length")
            if raw_length is not None and int(raw_length) > maximum_bytes:
                raise FrameSourceError(
                    "oversized_frame",
                    "Silicon snapshot declares more bytes than the configured maximum.",
                    detail={"declared_bytes": int(raw_length), "maximum_bytes": maximum_bytes},
                )
            body = response.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise FrameSourceError(
                    "oversized_frame",
                    "Silicon snapshot exceeded the configured maximum size.",
                    detail={"observed_bytes": len(body), "maximum_bytes": maximum_bytes},
                )
            return SnapshotResponse(
                status=int(response.status),
                headers={str(key): str(value) for key, value in response.headers.items()},
                body=body,
                final_url=str(response.geturl()),
            )
    except FrameSourceError:
        raise
    except HTTPError as error:
        raise FrameSourceError(
            "http_error",
            f"Silicon snapshot returned HTTP {error.code}.",
            detail={"status": int(error.code)},
        ) from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise FrameSourceError(
            "source_unavailable",
            f"Silicon snapshot is unavailable: {type(error).__name__}: {error}",
        ) from error


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise FrameSourceError(
            "malformed_capture_timestamp",
            "Silicon snapshot capture timestamp is not valid RFC3339.",
        ) from error
    if parsed.tzinfo is None:
        raise FrameSourceError(
            "malformed_capture_timestamp",
            "Silicon snapshot capture timestamp must include a UTC offset.",
        )
    return parsed.astimezone(UTC)


def _header_map(headers: Mapping[str, str]) -> dict[str, str]:
    return {str(key).casefold(): str(value).strip() for key, value in headers.items()}


def load_snapshot_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "sim2claw.silicon_overhead_snapshot.v1":
        raise ValueError("unexpected Silicon snapshot contract schema")
    endpoint = payload.get("endpoint") or {}
    parsed = urlsplit(str(endpoint.get("url") or ""))
    if parsed.scheme != endpoint.get("allowed_scheme") or parsed.hostname != endpoint.get(
        "allowed_host"
    ):
        raise ValueError("Silicon snapshot URL does not match its frozen allowlist")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Silicon snapshot URL contains forbidden credential or fragment data")
    return payload


class SiliconOverheadSnapshotAdapter:
    """Fetch one protected, registered board image without exposing its token."""

    def __init__(
        self,
        contract: Mapping[str, Any],
        *,
        token: str | None,
        requester: Requester = _default_requester,
        now: Callable[[], datetime] = _utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.contract = json.loads(json.dumps(contract))
        self.token = token
        self.requester = requester
        self.now = now
        self.monotonic = monotonic
        self.closed = False

    def preflight(self) -> dict[str, Any]:
        endpoint = self.contract["endpoint"]
        parsed = urlsplit(endpoint["url"])
        protected = bool(self.token)
        ready = (
            not self.closed
            and protected
            and parsed.scheme == endpoint["allowed_scheme"]
            and parsed.hostname == endpoint["allowed_host"]
        )
        return {
            "adapter_id": self.contract["adapter_id"],
            "ready": ready,
            "protected": protected,
            "source_host": parsed.hostname,
            "camera_role": self.contract["image_contract"]["camera_role"],
            "roi_contract_id": self.contract["image_contract"]["roi_contract_id"],
            "live_connectivity_verified": False,
            "reason": None if ready else "snapshot token is absent or adapter is closed",
            "physical_authority": False,
        }

    def close(self) -> None:
        self.closed = True
        self.token = None

    def fetch(self) -> SnapshotFrame:
        if self.closed:
            raise FrameSourceError("adapter_closed", "Silicon snapshot adapter is closed.")
        if not self.token:
            raise FrameSourceError(
                "authentication_unavailable",
                "Silicon snapshot token is not configured on the Studio server.",
            )
        endpoint = self.contract["endpoint"]
        url = str(endpoint["url"])
        parsed = urlsplit(url)
        if parsed.scheme != endpoint["allowed_scheme"] or parsed.hostname != endpoint["allowed_host"]:
            raise FrameSourceError("source_not_allowlisted", "Silicon snapshot source is not allowlisted.")
        started = self.monotonic()
        response = self.requester(
            url,
            {"Authorization": f"Bearer {self.token}", "Accept": "image/jpeg, image/png"},
            float(endpoint["total_timeout_seconds"]),
            int(endpoint["maximum_bytes"]),
        )
        duration_ms = round((self.monotonic() - started) * 1000.0, 3)
        final = urlsplit(response.final_url)
        if response.final_url != url:
            raise FrameSourceError(
                "redirect_rejected",
                "Silicon snapshot redirected; redirects are not allowed.",
                detail={"target_host": final.hostname},
            )
        if response.status != 200:
            raise FrameSourceError(
                "http_error",
                f"Silicon snapshot returned HTTP {response.status}.",
                detail={"status": int(response.status)},
            )
        if len(response.body) > int(endpoint["maximum_bytes"]):
            raise FrameSourceError(
                "oversized_frame",
                "Silicon snapshot exceeded the configured maximum size.",
                detail={
                    "observed_bytes": len(response.body),
                    "maximum_bytes": int(endpoint["maximum_bytes"]),
                },
            )
        headers = _header_map(response.headers)
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().casefold()
        if content_type not in endpoint["accepted_content_types"]:
            raise FrameSourceError(
                "malformed_frame",
                "Silicon snapshot content type is not accepted.",
                detail={"content_type": content_type},
            )
        required_headers = self.contract["required_response_headers"]
        missing = [name for name in required_headers if not headers.get(name.casefold())]
        if missing:
            raise FrameSourceError(
                "missing_source_metadata",
                "Silicon snapshot omitted required response metadata.",
                detail={"missing_headers": missing},
            )
        image_contract = self.contract["image_contract"]
        expected_headers = {
            "x-sim2claw-camera-role": image_contract["camera_role"],
            "x-sim2claw-roi-contract": image_contract["roi_contract_id"],
            "x-sim2claw-workspace-pose": image_contract["workspace_pose_id"],
        }
        mismatches = {
            name: {"expected": expected, "observed": headers.get(name)}
            for name, expected in expected_headers.items()
            if headers.get(name) != expected
        }
        if mismatches:
            raise FrameSourceError(
                "source_contract_mismatch",
                "Silicon snapshot metadata does not match the frozen source contract.",
                detail={"mismatches": mismatches},
            )
        try:
            registration_error_pixels = float(
                headers["x-sim2claw-registration-error-px"]
            )
        except ValueError as error:
            raise FrameSourceError(
                "malformed_source_metadata",
                "Silicon registration residual is not numeric.",
            ) from error
        if not 0 <= registration_error_pixels <= float(
            image_contract["maximum_registration_error_pixels"]
        ):
            raise FrameSourceError(
                "camera_registration_drift",
                "Silicon camera registration residual exceeds the frozen limit.",
                detail={
                    "registration_error_pixels": registration_error_pixels,
                    "maximum_registration_error_pixels": image_contract[
                        "maximum_registration_error_pixels"
                    ],
                },
            )
        captured_at = _parse_timestamp(headers["x-sim2claw-captured-at"])
        received_at = self.now().astimezone(UTC)
        age_seconds = (received_at - captured_at).total_seconds()
        freshness = self.contract["freshness"]
        if age_seconds > float(freshness["maximum_age_seconds"]):
            raise FrameSourceError(
                "stale_frame",
                "Silicon snapshot is older than the configured maximum age.",
                detail={"age_seconds": round(age_seconds, 6)},
            )
        if age_seconds < -float(freshness["maximum_future_skew_seconds"]):
            raise FrameSourceError(
                "future_frame",
                "Silicon snapshot timestamp is too far in the future.",
                detail={"age_seconds": round(age_seconds, 6)},
            )
        if not response.body:
            raise FrameSourceError("malformed_frame", "Silicon snapshot body is empty.")
        decoded = cv2.imdecode(np.frombuffer(response.body, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None or decoded.ndim != 3 or decoded.shape[2] != 3:
            raise FrameSourceError("malformed_frame", "Silicon snapshot is not a decodable RGB image.")
        height, width = decoded.shape[:2]
        if width != int(image_contract["rectified_width"]) or height != int(
            image_contract["rectified_height"]
        ):
            raise FrameSourceError(
                "source_contract_mismatch",
                "Silicon snapshot dimensions do not match the registered-board contract.",
                detail={"width": width, "height": height},
            )
        encoding = "jpeg" if content_type == "image/jpeg" else "png"
        digest = hashlib.sha256(response.body).hexdigest()
        record = {
            "schema_version": FRAME_RECORD_SCHEMA,
            "source_host": parsed.hostname,
            "camera_role": image_contract["camera_role"],
            "capture_timestamp": captured_at.isoformat(),
            "studio_receipt_timestamp": received_at.isoformat(),
            "width": width,
            "height": height,
            "encoding": encoding,
            "byte_count": len(response.body),
            "sha256": digest,
            "freshness": {
                "maximum_age_seconds": freshness["maximum_age_seconds"],
                "age_seconds": round(age_seconds, 6),
                "passed": True,
            },
            "roi_contract_id": image_contract["roi_contract_id"],
            "workspace_pose_id": image_contract["workspace_pose_id"],
            "board_pose_id": image_contract["board_pose_id"],
            "registration_error_pixels": registration_error_pixels,
            "fetch_duration_ms": duration_ms,
            "error": None,
            "physical_authority": False,
        }
        return SnapshotFrame(response.body, decoded, record)


def prepare_registered_roi(image_bgr: np.ndarray, size: tuple[int, int] = (256, 256)) -> np.ndarray:
    """Normalize rectified-board luminance for the deduplication metric only."""

    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("registered ROI must be a BGR image")
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, size, interpolation=cv2.INTER_AREA).astype(np.float64)
    mean = float(resized.mean())
    standard_deviation = float(resized.std())
    if standard_deviation < 1e-6:
        return np.full(size[::-1], 127.0, dtype=np.float64)
    normalized = (resized - mean) * (40.0 / standard_deviation) + 127.0
    return np.clip(normalized, 0.0, 255.0)


def normalized_luminance_ssim(left: np.ndarray, right: np.ndarray) -> float:
    """Frozen global SSIM used only to suppress redundant model inputs."""

    if left.shape != right.shape:
        raise ValueError("SSIM inputs must have the same shape")
    left = left.astype(np.float64)
    right = right.astype(np.float64)
    mean_left = float(left.mean())
    mean_right = float(right.mean())
    variance_left = float(left.var())
    variance_right = float(right.var())
    covariance = float(((left - mean_left) * (right - mean_right)).mean())
    c1 = (0.01 * 255.0) ** 2
    c2 = (0.03 * 255.0) ** 2
    numerator = (2 * mean_left * mean_right + c1) * (2 * covariance + c2)
    denominator = (mean_left**2 + mean_right**2 + c1) * (
        variance_left + variance_right + c2
    )
    if denominator <= 0:
        return 1.0 if np.array_equal(left, right) else 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def encode_png(image_bgr: np.ndarray) -> bytes:
    ok, encoded = cv2.imencode(".png", image_bgr)
    if not ok:
        raise ValueError("could not encode image")
    with io.BytesIO() as buffer:
        buffer.write(encoded.tobytes())
        return buffer.getvalue()
