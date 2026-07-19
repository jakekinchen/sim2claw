"use strict";

const rail = document.querySelector("#stage-rail");
const template = document.querySelector("#stage-template");
const artifactViewer = document.querySelector("#artifact-viewer");

function text(node, value, fallback = "—") {
  node.textContent = value || fallback;
}

function statusLabel(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

async function inspectArtifact(path) {
  const response = await fetch(
    `/api/learning-factory/artifact?path=${encodeURIComponent(path)}`,
    { cache: "no-store" },
  );
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
  text(document.querySelector("#artifact-path"), payload.path);
  document.querySelector("#artifact-json").textContent = JSON.stringify(payload.artifact, null, 2);
  artifactViewer.hidden = false;
  artifactViewer.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderStage(stage) {
  const fragment = template.content.cloneNode(true);
  const card = fragment.querySelector(".stage-card");
  const summary = fragment.querySelector(".stage-summary");
  const details = fragment.querySelector(".stage-details");
  card.dataset.status = stage.status;
  text(fragment.querySelector(".stage-index"), stage.stage);
  text(fragment.querySelector(".stage-name"), stage.name);
  text(fragment.querySelector(".stage-purpose"), stage.purpose);
  text(fragment.querySelector(".stage-status"), statusLabel(stage.status));
  text(fragment.querySelector(".stage-owner"), stage.verdict_owner);
  text(fragment.querySelector(".stage-output"), stage.output_contract);
  text(fragment.querySelector(".stage-evidence"), stage.latest_evidence, "No attempt yet");
  text(fragment.querySelector(".stage-action"), stage.available_codex_action);
  text(fragment.querySelector(".stage-command"), stage.resume_command);
  const evidence = stage.evidence;
  text(fragment.querySelector(".stage-proof"), evidence?.proof_class);
  text(fragment.querySelector(".stage-output-digest"), evidence?.output_sha256);
  text(fragment.querySelector(".stage-result-digest"), evidence?.result_sha256);
  text(fragment.querySelector(".stage-finished"), evidence?.finished_at);
  const artifactButton = fragment.querySelector(".view-artifact");
  if (evidence?.output_ref?.path) {
    artifactButton.hidden = false;
    artifactButton.addEventListener("click", async () => {
      try {
        await inspectArtifact(evidence.output_ref.path);
      } catch (error) {
        artifactButton.textContent = error.message;
      }
    });
  }

  const blockerPanel = fragment.querySelector(".blocker-panel");
  const blockerList = fragment.querySelector(".stage-blockers");
  if (stage.blockers.length) {
    blockerPanel.hidden = false;
    stage.blockers.forEach((blocker) => {
      const item = document.createElement("li");
      item.textContent = blocker;
      blockerList.append(item);
    });
  }

  summary.addEventListener("click", () => {
    const expanded = summary.getAttribute("aria-expanded") === "true";
    summary.setAttribute("aria-expanded", String(!expanded));
    details.hidden = expanded;
  });
  fragment.querySelector(".copy-command").addEventListener("click", async (event) => {
    await navigator.clipboard.writeText(stage.resume_command);
    const button = event.currentTarget;
    button.textContent = "Copied";
    window.setTimeout(() => { button.textContent = "Copy resume command"; }, 1400);
  });
  rail.append(fragment);
}

function renderHistory(history) {
  const root = document.querySelector("#campaign-history");
  history.forEach((generation) => {
    const item = document.createElement("li");
    item.dataset.status = generation.overall_status;
    const route = generation.route_targets.length
      ? `reopened ${generation.route_targets.join(", ")}`
      : "root generation";
    const number = document.createElement("span");
    number.className = "history-generation";
    number.textContent = `G${String(generation.generation).padStart(4, "0")}`;
    const copy = document.createElement("span");
    copy.className = "history-copy";
    const state = document.createElement("strong");
    state.textContent = statusLabel(generation.overall_status);
    const summary = document.createElement("span");
    summary.textContent = `${route} · ${generation.completed_stage_count}/14 stages · ${generation.attempt_count} attempts`;
    copy.append(state, summary);
    const latest = document.createElement("code");
    latest.textContent = generation.latest_stage || "not started";
    item.append(number, copy, latest);
    root.append(item);
  });
  if (!history.length) {
    const item = document.createElement("li");
    item.className = "history-empty";
    item.textContent = "No generation receipts exist yet.";
    root.append(item);
  }
}

async function loadFactory() {
  try {
    const response = await fetch("/api/learning-factory", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    const factory = payload.factory;
    text(document.querySelector("#project-id"), factory.project_id);
    text(document.querySelector("#current-stage"), factory.current_stage, "Complete");
    text(document.querySelector("#next-stage"), factory.next_ready_stage, "None ready");
    text(document.querySelector("#overall-status"), statusLabel(factory.overall_status));
    text(
      document.querySelector("#campaign-generation"),
      `${factory.campaign_id} / G${String(factory.generation).padStart(4, "0")}`,
    );
    factory.stages.forEach(renderStage);
    renderHistory(payload.campaign_history || []);
  } catch (error) {
    const panel = document.querySelector("#factory-error");
    panel.hidden = false;
    text(document.querySelector("#factory-error-message"), error.message);
    text(document.querySelector("#overall-status"), "Unavailable");
  }
}

document.querySelector("#close-artifact").addEventListener("click", () => {
  artifactViewer.hidden = true;
});

loadFactory();
