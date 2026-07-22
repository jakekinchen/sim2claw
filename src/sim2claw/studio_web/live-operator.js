const MANIFEST_URL = "/publication/sail_live_operator_v1/manifest.json";

const byId = (id) => document.getElementById(id);
const setText = (id, value) => { byId(id).textContent = String(value); };
const pretty = (value) => String(value).replaceAll("_", " ");

function renderStages(stages) {
  const root = byId("operator-stages");
  root.replaceChildren(...stages.map((stage, index) => {
    const item = document.createElement("li");
    const number = document.createElement("span");
    number.textContent = String(index + 1).padStart(2, "0");
    const title = document.createElement("b");
    title.textContent = pretty(stage.stage);
    const status = document.createElement("small");
    status.textContent = pretty(stage.status);
    item.append(number, title, status);
    return item;
  }));
}

function renderMechanisms(mechanisms) {
  const root = byId("mechanisms");
  root.replaceChildren(...mechanisms.map((mechanism) => {
    const row = document.createElement("div");
    row.className = "mechanism-row";
    const header = document.createElement("header");
    const label = document.createElement("b");
    label.textContent = pretty(mechanism.mechanism_id);
    const probability = document.createElement("span");
    probability.textContent = `${(mechanism.probability * 100).toFixed(0)}%`;
    header.append(label, probability);
    const track = document.createElement("div");
    track.className = "belief-track";
    const bar = document.createElement("i");
    bar.style.width = `${mechanism.probability * 100}%`;
    track.append(bar);
    row.append(header, track);
    return row;
  }));
}

function addDefinition(root, term, description) {
  const dt = document.createElement("dt");
  dt.textContent = term;
  const dd = document.createElement("dd");
  dd.textContent = description;
  root.append(dt, dd);
}

function renderAblation(data) {
  const root = byId("ablation-body");
  const rows = [
    ["Manual sequence", data.manual.completed_campaigns, data.manual.simulator_evaluations, data.manual.anchor_passes, data.manual.abstention_quality],
    ["SAIL live operator", "1 operator", data.sail.simulator_evaluations, 0, data.sail.abstention_quality],
  ];
  root.replaceChildren(...rows.map((values) => {
    const row = document.createElement("tr");
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = pretty(value);
      row.append(cell);
    });
    return row;
  }));
}

async function load() {
  const response = await fetch(MANIFEST_URL, {cache: "no-store"});
  if (!response.ok) throw new Error(`manifest request failed: ${response.status}`);
  const data = await response.json();
  setText("summary", data.summary);
  setText("verdict", pretty(data.verdict).toUpperCase());
  setText("receipt", `receipt ${data.receipt.sha256.slice(0, 16)}…`);
  setText("budget-used", data.budget.used_interventions);
  setText("budget-max", data.budget.maximum_interventions);
  setText("anchor-budget", `${data.budget.used_anchor_replays} / ${data.budget.maximum_anchor_replays} anchor replays`);
  setText("manual-campaigns", data.ablation.manual.completed_campaigns);
  setText("manual-replays", data.ablation.manual.simulator_evaluations);
  setText("anchor-passes", data.ablation.manual.anchor_passes);
  setText("sail-replays", data.ablation.sail.simulator_evaluations);
  setText("posterior-note", data.posterior.note);
  setText("measurement-summary", data.measurement.summary);
  setText("ablation-note", data.ablation.note);
  setText("wip-note", data.ablation.incomplete_work_note);
  setText("action-hash", `action sha256 ${data.action_sha256}`);
  renderStages(data.operator_trace);
  renderMechanisms(data.posterior.mechanisms);
  renderAblation(data.ablation);
  const details = byId("measurement-details");
  addDefinition(details, "Channels", data.measurement.measurements.join(", "));
  addDefinition(details, "Sampling", `≥ ${data.measurement.minimum_sampling_hz} Hz`);
  addDefinition(details, "Synchronization", data.measurement.synchronization);
  addDefinition(details, "Authority", "capture false · robot motion false");
}

load().catch((error) => {
  setText("summary", `Read-only evidence unavailable: ${error.message}`);
  setText("verdict", "MANIFEST ERROR");
});
