#!/usr/bin/env bash
set -euo pipefail

REMOTE="${SIM2CLAW_BREV_INSTANCE:-nemoclaw-e3fca7}"
SANDBOX="${SIM2CLAW_SANDBOX:-sim2claw-hackathon}"
PROJECT="${SIM2CLAW_PROJECT:-configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
readonly REMOTE_IDENTIFIER_PATTERN='^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$'

validate_remote_identifier() {
  local variable_name="$1"
  local value="$2"
  if [[ ! "$value" =~ $REMOTE_IDENTIFIER_PATTERN ]]; then
    printf '%s must match %s; observed %q\n' \
      "$variable_name" "$REMOTE_IDENTIFIER_PATTERN" "$value" >&2
    return 1
  fi
}

validate_remote_identifier SIM2CLAW_BREV_INSTANCE "$REMOTE"
validate_remote_identifier SIM2CLAW_SANDBOX "$SANDBOX"

cd "$REPO_ROOT"
dirty_status="$(git status --porcelain=v1 --untracked-files=all)"
if [[ -n "$dirty_status" ]]; then
  printf 'deploy requires a clean committed HEAD; refusing tracked/untracked dirt:\n%s\n' \
    "$dirty_status" >&2
  exit 1
fi
source_revision="$(git rev-parse --verify HEAD)"
if [[ ! "$source_revision" =~ ^[0-9a-f]{40}$ && ! "$source_revision" =~ ^[0-9a-f]{64}$ ]]; then
  printf 'invalid source revision: %s\n' "$source_revision" >&2
  exit 1
fi

LOCAL_STAGE="$(mktemp -d "${TMPDIR:-/tmp}/sim2claw-nemoclaw-deploy.XXXXXX")"
trap 'rm -rf "$LOCAL_STAGE"' EXIT
REMOTE_STAGE="/tmp/sim2claw-nemoclaw-deploy/$source_revision"
source_archive="$LOCAL_STAGE/sim2claw-source.tar"
project_bundle="$LOCAL_STAGE/sim2claw-project.tar"
bundle_receipt="$LOCAL_STAGE/project-bundle-receipt.json"
bundle_inspection="$LOCAL_STAGE/project-bundle-inspection.json"
source_inspection="$LOCAL_STAGE/source-archive-inspection.json"
source_identity_json="{\"git_head\":\"$source_revision\",\"schema_version\":\"sim2claw.source_archive_identity.v1\",\"working_tree_clean\":true}"

git archive \
  --format=tar \
  --add-virtual-file="_sim2claw_source/revision.json:$source_identity_json" \
  --output="$source_archive" \
  "$source_revision"
uv run sim2claw project-pack \
  --project "$PROJECT" \
  --output "$project_bundle" >"$bundle_receipt"
source_sha256="$(sha256sum "$source_archive" | awk '{print $1}')"
project_sha256="$(sha256sum "$project_bundle" | awk '{print $1}')"
uv run python scripts/nemoclaw/inspect-source-archive.py \
  "$source_archive" "$source_sha256" "$source_revision" >"$source_inspection"
receipt_project_sha256="$(uv run python - "$bundle_receipt" <<'PY'
import json
import pathlib
import sys

print(json.loads(pathlib.Path(sys.argv[1]).read_text())["bundle_sha256"])
PY
)"
if [[ "$receipt_project_sha256" != "$project_sha256" ]]; then
  printf 'local project bundle receipt digest mismatch\n' >&2
  exit 1
fi
uv run sim2claw project-inspect \
  --project "$PROJECT" \
  --bundle "$project_bundle" \
  --expected-bundle-sha256 "$project_sha256" >"$bundle_inspection"
bundle_revision="$(uv run python - "$bundle_inspection" <<'PY'
import json
import pathlib
import sys

bundle = json.loads(pathlib.Path(sys.argv[1]).read_text())["bundle"]
if bundle["source_revision"]["working_tree_clean"] is not True:
    raise SystemExit("project bundle source revision is not clean")
print(bundle["source_revision"]["git_head"])
PY
)"
if [[ "$bundle_revision" != "$source_revision" ]]; then
  printf 'project bundle/source archive revision mismatch: %s != %s\n' \
    "$bundle_revision" "$source_revision" >&2
  exit 1
fi

printf 'source_revision=%s\nsource_archive_sha256=%s\nproject_bundle_sha256=%s\n' \
  "$source_revision" "$source_sha256" "$project_sha256"

brev exec "$REMOTE" "mkdir -p '$REMOTE_STAGE'"
brev copy "$source_archive" "$REMOTE:$REMOTE_STAGE/sim2claw-source.tar"
brev copy "$project_bundle" "$REMOTE:$REMOTE_STAGE/sim2claw-project.tar"

brev exec "$REMOTE" \
  "cd '$REMOTE_STAGE' && printf '%s  %s\n%s  %s\n' '$source_sha256' sim2claw-source.tar '$project_sha256' sim2claw-project.tar | sha256sum --check --strict -"

brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' upload '$REMOTE_STAGE/sim2claw-source.tar' /sandbox/inbox/sim2claw-source.tar"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' upload '$REMOTE_STAGE/sim2claw-project.tar' /sandbox/inbox/sim2claw-project.tar"

brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec -- env SOURCE_SHA='$source_sha256' PROJECT_SHA='$project_sha256' sh -c 'printf \"%s  %s\\n%s  %s\\n\" \"\$SOURCE_SHA\" /sandbox/inbox/sim2claw-source.tar \"\$PROJECT_SHA\" /sandbox/inbox/sim2claw-project.tar | sha256sum --check --strict -'"

brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec -- env EXPECTED_SOURCE_IDENTITY='$source_identity_json' sh -c 'observed=\$(tar -xOf /sandbox/inbox/sim2claw-source.tar _sim2claw_source/revision.json) && test \"\$observed\" = \"\$EXPECTED_SOURCE_IDENTITY\" && test ! -e /sandbox/sim2claw && mkdir /sandbox/sim2claw && tar --exclude=\"_sim2claw_source/*\" -xf /sandbox/inbox/sim2claw-source.tar -C /sandbox/sim2claw'"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec -- env PYTHONPATH=/sandbox/sim2claw/src python3 /sandbox/sim2claw/scripts/nemoclaw/inspect-project-bundle.py /sandbox/inbox/sim2claw-project.tar '$project_sha256' '$source_revision'"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec -- tar -xf /sandbox/inbox/sim2claw-project.tar -C /sandbox/sim2claw --exclude='_sim2claw_bundle/*'"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec --workdir /sandbox/sim2claw -- bash scripts/nemoclaw/bootstrap.sh"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec --workdir /sandbox/sim2claw -- bash scripts/nemoclaw/start-studio.sh"
brev exec "$REMOTE" "openshell service expose '$SANDBOX' 4173 studio"
brev exec "$REMOTE" \
  "nemoclaw '$SANDBOX' exec --workdir /sandbox/sim2claw -- env SIM2CLAW_SOURCE_REVISION='$source_revision' SIM2CLAW_SOURCE_ARCHIVE_SHA256='$source_sha256' SIM2CLAW_PROJECT_BUNDLE_SHA256='$project_sha256' bash scripts/nemoclaw/verify-deployment.sh"
