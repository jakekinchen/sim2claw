"use strict";

const text = (node, value) => { node.textContent = value; };
const pretty = (value) => String(value).replaceAll("_", " ");

function card(className, label, value) {
  const node = document.createElement("article");
  node.className = className;
  const number = document.createElement("b");
  const caption = document.createElement("span");
  text(number, value);
  text(caption, label);
  node.append(number, caption);
  return node;
}

async function load() {
  const response = await fetch("/publication/sail_project_application_v1/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`Manifest returned ${response.status}`);
  const data = await response.json();
  text(document.querySelector("#safe-claim"), data.safe_claim);
  text(document.querySelector("#receipt"), `Receipt ${data.source_receipt.sha256}`);

  const deltas = data.candidate.diagnostic_deltas;
  const metrics = [
    ["Lifts", `${data.candidate.task_counts.lifted}/11`],
    ["Lift + transport", `${data.candidate.task_counts.lift_and_transport}/11`],
    ["Strict success", `${data.candidate.task_counts.strict_successes}/11`],
    ["Whole-base endings", `+${deltas.whole_base_inside_destination_count}`],
    ["Mean final distance", `${(100 * deltas.mean_final_target_distance_relative).toFixed(1)}%`],
    ["Mean post-grasp slip", `${(100 * deltas.mean_post_grasp_slip_relative).toFixed(1)}%`],
  ];
  document.querySelector("#metric-grid").append(...metrics.map(([label, value]) => card("metric", label, value)));

  const mechanism = document.querySelector("#mechanism-list");
  data.contact_localization.findings.forEach((finding) => {
    const item = document.createElement("li");
    text(item, finding);
    mechanism.append(item);
  });

  const gates = document.querySelector("#gate-list");
  Object.entries(data.candidate.gates).forEach(([name, passed]) => {
    const term = document.createElement("dt");
    const decision = document.createElement("dd");
    text(term, pretty(name));
    text(decision, passed ? "PASS" : "FAIL");
    decision.className = passed ? "pass" : "fail";
    gates.append(term, decision);
  });

  const failures = document.querySelector("#failure-grid");
  Object.entries(data.failure_counts)
    .sort((left, right) => right[1] - left[1])
    .forEach(([name, count]) => failures.append(card("failure", pretty(name), String(count))));

  const ledger = document.querySelector("#ledger");
  data.resolved_inconsistencies.forEach((row) => {
    const article = document.createElement("article");
    const heading = document.createElement("b");
    const detail = document.createElement("p");
    text(heading, `${pretty(row.id)} · ${pretty(row.status)}`);
    text(detail, row.finding);
    article.append(heading, detail);
    ledger.append(article);
  });
}

async function loadRetentionCloseout() {
  const response = await fetch("/publication/sail_grasp_retention_resolution_v1/manifest.json", { cache: "no-store" });
  if (!response.ok) throw new Error(`Retention manifest returned ${response.status}`);
  const data = await response.json();
  text(document.querySelector("#retention-claim"), data.safe_claim);
  text(document.querySelector("#retention-measurement"), data.required_measurement);
  const result = data.result;
  const metrics = [
    ["Candidate replays", result.candidate_runs],
    ["Anchor passes", result.anchor_passes],
    ["Baseline loss", `frame ${result.baseline_contact_loss_source_index}`],
    ["Aligned-pad loss", `frame ${result.aligned_pad_contact_loss_source_index}`],
    ["Best retention", `frame ${result.best_retention_contact_loss_source_index}/401`],
    ["Best aperture error", `${result.best_loaded_aperture_error_degrees.toFixed(2)}°`],
  ];
  document.querySelector("#retention-metrics").append(...metrics.map(([label, value]) => card("metric", label, value)));
  const diagnosis = document.querySelector("#retention-diagnosis");
  data.diagnosis.forEach((finding) => {
    const item = document.createElement("li");
    text(item, finding);
    diagnosis.append(item);
  });
}

load().catch((error) => text(document.querySelector("#safe-claim"), `Publication unavailable: ${error.message}`));
loadRetentionCloseout().catch((error) => text(document.querySelector("#retention-claim"), `Retention publication unavailable: ${error.message}`));
