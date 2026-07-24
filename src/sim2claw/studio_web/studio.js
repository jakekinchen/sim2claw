"use strict";

const state = {
  serverHealth: null,
  readOnly: null,
  catalog: null,
  selectedEpisodeId: null,
  taskFilter: null,
  query: "",
  fingerprint: "",
  view: "replay",
  drawer: null,
  frameAnimation: null,
  frameLastTimestamp: null,
  frameIndex: 0,
  framePlaying: false,
  frameCache: new Map(),
  playbackRate: 1,
  replayMode: "recorded",
  visualTwinMode: "split",
  visualTwinReveal: 50,
  visualTwinAnimation: null,
  visualTwinOffscreen: null,
  visualTwinLastDraw: 0,
  recordingFeedIndex: 0,
  recordingWindow: null,
  threeViewer: null,
  threeLoadId: 0,
  liveSimViewer: null,
  liveSimViewerPromise: null,
  liveSimFetchActive: false,
  liveWorkspace: null,
  liveWorkspaceSession: null,
  liveWorkspaceMode: "simulator",
  liveWorkspaceViewer: null,
  liveWorkspaceViewerPromise: null,
  liveWorkspaceFetchActive: false,
  liveWorkspaceStatusFetchActive: false,
  liveWorkspaceLastFetchAt: 0,
  liveWorkspaceGeneration: 0,
  expandedTasks: new Set(),
  processHistory: new Map(),
  thumbnailObserver: null,
  recorder: null,
  recorderRequestActive: false,
  recorderRequestError: null,
  physicalPreflighting: false,
  physicalStartSequence: false,
  physicalSyncing: false,
  discardConfirmationArmed: false,
  discardConfirmationTimer: null,
  pawnBoardSelectionStep: "source",
  orchestrator: null,
  orchestratorRequestActive: false,
  orchestratorRequestError: null,
  orchestratorFrameHash: null,
  sail: null,
  sailError: null,
  sailFetchActive: false,
  sailSelectedEpisodeId: null,
  sailFrameIndex: 0,
  projectMap: null,
  projectMapError: null,
  projectMapFetchActive: false,
  twinFidelity: null,
  twinFidelityEpisodeId: null,
  twinFidelityFetchId: 0,
  drawerTrigger: null,
};

const elements = {
  connection: document.querySelector("#connection-state"),
  mobileNavToggle: document.querySelector("#mobile-nav-toggle"),
  mobileNavLabel: document.querySelector("#mobile-nav-label"),
  campaign: document.querySelector("#campaign-label"),
  passRatio: document.querySelector("#pass-ratio"),
  projectMapTrigger: document.querySelector("#project-map-trigger"),
  projectMapContent: document.querySelector("#project-map-content"),
  projectMapDrawer: document.querySelector("#project-map-drawer"),
  liveTrigger: document.querySelector("#live-trigger"),
  liveCount: document.querySelector("#live-count"),
  liveStrip: document.querySelector("#live-strip"),
  liveStripTitle: document.querySelector("#live-strip-title"),
  liveStripPhase: document.querySelector("#live-strip-phase"),
  sailStatus: document.querySelector("#sail-status"),
  sailReceipt: document.querySelector("#sail-receipt"),
  sailRankingNote: document.querySelector("#sail-ranking-note"),
  sailEpisodeList: document.querySelector("#sail-episode-list"),
  sailEpisodeProof: document.querySelector("#sail-episode-proof"),
  sailTraceHeading: document.querySelector("#sail-trace-heading"),
  sailTraceSummary: document.querySelector("#sail-trace-summary"),
  sailOpenReplay: document.querySelector("#sail-open-replay"),
  sailFrameIndex: document.querySelector("#sail-frame-index"),
  sailPhase: document.querySelector("#sail-phase"),
  sailTime: document.querySelector("#sail-time"),
  sailPhaseRail: document.querySelector("#sail-phase-rail"),
  sailScrubber: document.querySelector("#sail-scrubber"),
  sailSignalPlot: document.querySelector("#sail-signal-plot"),
  sailEvidenceSpine: document.querySelector("#sail-evidence-spine"),
  sailFrameReadouts: document.querySelector("#sail-frame-readouts"),
  sailAvailabilityGrid: document.querySelector("#sail-availability-grid"),
  sailHeatmap: document.querySelector("#sail-heatmap"),
  sailResidualStatus: document.querySelector("#sail-residual-status"),
  sailResidualFacts: document.querySelector("#sail-residual-facts"),
  sailGraphDelta: document.querySelector("#sail-graph-delta"),
  sailGraphBefore: document.querySelector("#sail-graph-before"),
  sailGraphAfter: document.querySelector("#sail-graph-after"),
  sailRevisionStrip: document.querySelector("#sail-revision-strip"),
  sailDebtScore: document.querySelector("#sail-debt-score"),
  sailDebtBoundary: document.querySelector("#sail-debt-boundary"),
  sailDebtBefore: document.querySelector("#sail-debt-before"),
  sailDebtAfter: document.querySelector("#sail-debt-after"),
  sailDebtComponents: document.querySelector("#sail-debt-components"),
  sailSelectedProbe: document.querySelector("#sail-selected-probe"),
  sailInterventionList: document.querySelector("#sail-intervention-list"),
  sailInvarianceCount: document.querySelector("#sail-invariance-count"),
  sailPosteriorList: document.querySelector("#sail-posterior-list"),
  sailTwinLevel: document.querySelector("#sail-twin-level"),
  sailGateMatrix: document.querySelector("#sail-gate-matrix"),
  sailMinimumEvidence: document.querySelector("#sail-minimum-evidence"),
  sailFigureList: document.querySelector("#sail-figure-list"),
  sailProofLegend: document.querySelector("#sail-proof-legend"),
  sailEmpty: document.querySelector("#sail-empty"),
  sailEmptyDetail: document.querySelector("#sail-empty-detail"),
  taskFilterList: document.querySelector("#task-filter-list"),
  taskFilterTemplate: document.querySelector("#task-filter-template"),
  railContext: document.querySelector("#rail-context"),
  browserHeading: document.querySelector("#browser-heading"),
  railResultCount: document.querySelector("#rail-result-count"),
  railEpisodeList: document.querySelector("#rail-episode-list"),
  railEpisodeTemplate: document.querySelector("#rail-episode-template"),
  browserRail: document.querySelector("#browser-rail"),
  mobileBrowserToggle: document.querySelector("#mobile-browser-toggle"),
  mobileBrowserLabel: document.querySelector("#mobile-browser-label"),
  railClose: document.querySelector("#rail-close"),
  search: document.querySelector("#episode-search"),
  librarySearch: document.querySelector("#library-search"),
  librarySummary: document.querySelector("#library-summary"),
  libraryGroups: document.querySelector("#library-groups"),
  episodeTemplate: document.querySelector("#episode-template"),
  stage: document.querySelector("#episode-stage"),
  replayModeSwitch: document.querySelector("#replay-mode-switch"),
  recordingFeedSwitch: document.querySelector("#recording-feed-switch"),
  comparisonLaneStrip: document.querySelector("#comparison-lane-strip"),
  physicsLaneState: document.querySelector("#physics-lane-state"),
  threeReplay: document.querySelector("#three-replay"),
  threeCanvas: document.querySelector("#three-canvas"),
  threeStatus: document.querySelector("#three-status"),
  threeReset: document.querySelector("#three-reset"),
  visualTwinCanvas: document.querySelector("#visual-twin-canvas"),
  visualTwinSeam: document.querySelector("#visual-twin-seam"),
  visualTwinToolbar: document.querySelector("#visual-twin-toolbar"),
  visualTwinReveal: document.querySelector("#visual-twin-reveal"),
  comparisonRealLabel: document.querySelector("#comparison-real-label"),
  comparisonPhysicsLabel: document.querySelector("#comparison-physics-label"),
  physicsUnavailable: document.querySelector("#physics-unavailable"),
  liveSimulationPanel: document.querySelector("#live-simulation-panel"),
  liveSimulationCanvas: document.querySelector("#live-simulation-canvas"),
  liveSimulationStatus: document.querySelector("#live-simulation-status"),
  liveSimulationBadge: document.querySelector("#live-simulation-badge"),
  liveSimulationReset: document.querySelector("#live-simulation-reset"),
  stagePortrait: document.querySelector("#stage-portrait"),
  stageKicker: document.querySelector("#stage-kicker"),
  stageTitle: document.querySelector("#stage-title"),
  stageSubtitle: document.querySelector("#stage-subtitle"),
  stageVerdict: document.querySelector("#stage-verdict"),
  cameraSourceLabel: document.querySelector("#camera-source-label"),
  cameraName: document.querySelector("#camera-name"),
  video: document.querySelector("#replay-video"),
  frame: document.querySelector("#replay-frame"),
  preview: document.querySelector("#timeline-preview"),
  previewVideo: document.querySelector("#preview-video"),
  previewFrame: document.querySelector("#preview-frame"),
  previewTimecode: document.querySelector("#preview-timecode"),
  timeline: document.querySelector("#timeline-shell"),
  timelineHead: document.querySelector("#timeline-head"),
  timelineTicks: document.querySelector("#timeline-ticks"),
  timecode: document.querySelector("#stage-timecode"),
  stageProgress: document.querySelector("#stage-progress"),
  scanHead: document.querySelector("#scan-head"),
  play: document.querySelector("#play-toggle"),
  jumpBack: document.querySelector("#jump-back"),
  jumpForward: document.querySelector("#jump-forward"),
  speed: document.querySelector("#speed-toggle"),
  scrubber: document.querySelector("#scrubber"),
  phaseRail: document.querySelector("#phase-rail"),
  transportPhase: document.querySelector("#transport-phase"),
  metrics: document.querySelector("#metric-strip"),
  twinFidelityTrigger: document.querySelector("#twin-fidelity-trigger"),
  twinFidelityContent: document.querySelector("#twin-fidelity-content"),
  twinFidelityDrawer: document.querySelector("#twin-fidelity-drawer"),
  evidenceTrigger: document.querySelector("#evidence-trigger"),
  evidenceContent: document.querySelector("#evidence-content"),
  liveWorkspaceDrawer: document.querySelector("#live-workspace-drawer"),
  liveArmState: document.querySelector("#live-arm-state"),
  liveArmTitle: document.querySelector("#live-arm-title"),
  liveArmDetail: document.querySelector("#live-arm-detail"),
  liveCameraCount: document.querySelector("#live-camera-count"),
  liveWorkspaceCanvas: document.querySelector("#live-workspace-canvas"),
  liveWorkspaceStatus: document.querySelector("#live-workspace-status"),
  liveWorkspaceReset: document.querySelector("#live-workspace-reset"),
  liveJointReadout: document.querySelector("#live-joint-readout"),
  processDrawer: document.querySelector("#process-drawer"),
  evidenceDrawer: document.querySelector("#evidence-drawer"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
  activityList: document.querySelector("#activity-list"),
  simulationCard: document.querySelector("#simulation-card"),
  robotGrid: document.querySelector("#robot-grid"),
  recorderStatus: document.querySelector("#recorder-status"),
  recordClock: document.querySelector("#record-clock"),
  recordSamples: document.querySelector("#record-samples"),
  recordRate: document.querySelector("#record-rate"),
  recordModeLabel: document.querySelector("#record-mode-label"),
  recordCamera: document.querySelector("#record-camera"),
  recordPath: document.querySelector("#record-path"),
  recorderMessage: document.querySelector("#recorder-message"),
  jointBars: document.querySelector("#joint-bars"),
  jointUnit: document.querySelector("#joint-unit"),
  sourceSquare: document.querySelector("#record-source-square"),
  target: document.querySelector("#record-target"),
  sampleHz: document.querySelector("#record-sample-hz"),
  physicalModeOption: document.querySelector("#physical-mode-option"),
  physicalSafetyCheck: document.querySelector("#physical-safety-check"),
  physicalSafetyAck: document.querySelector("#physical-safety-ack"),
  simModeState: document.querySelector("#sim-mode-state"),
  physicalModeState: document.querySelector("#physical-mode-state"),
  overheadCameraPreflight: document.querySelector("#overhead-camera-preflight"),
  wristCameraPreflight: document.querySelector("#wrist-camera-preflight"),
  leaderPreflight: document.querySelector("#leader-preflight"),
  followerPreflight: document.querySelector("#follower-preflight"),
  runtimePreflight: document.querySelector("#runtime-preflight"),
  alignmentPanel: document.querySelector("#alignment-panel"),
  alignmentStatus: document.querySelector("#alignment-status"),
  alignmentSummary: document.querySelector("#alignment-summary"),
  alignmentJoints: document.querySelector("#alignment-joints"),
  refreshPreflight: document.querySelector("#refresh-preflight"),
  verifyGateway: document.querySelector("#verify-gateway"),
  syncFollower: document.querySelector("#sync-follower"),
  startRecording: document.querySelector("#start-recording"),
  stopRecording: document.querySelector("#stop-recording"),
  labelForm: document.querySelector("#record-label-form"),
  recordLabel: document.querySelector("#record-label"),
  recordSkill: document.querySelector("#record-skill"),
  recordOutcome: document.querySelector("#record-outcome"),
  recordNotes: document.querySelector("#record-notes"),
  discardRecording: document.querySelector("#discard-recording"),
  simReplayPanel: document.querySelector("#sim-replay-panel"),
  runSimReplay: document.querySelector("#run-sim-replay"),
  simReplayMetrics: document.querySelector("#sim-replay-metrics"),
  pawnPreviewBoard: document.querySelector("#pawn-preview-board"),
  pawnBoardInstruction: document.querySelector("#pawn-board-instruction"),
  pawnPreviewSource: document.querySelector("#pawn-preview-source"),
  pawnPreviewTarget: document.querySelector("#pawn-preview-target"),
  pawnPreviewDescription: document.querySelector("#pawn-preview-description"),
  pawnMoveLine: document.querySelector("#pawn-move-line"),
  orchestratorMainStatus: document.querySelector("#orchestrator-main-status"),
  orchestratorState: document.querySelector("#orchestrator-state"),
  orchestratorStart: document.querySelector("#orchestrator-start"),
  orchestratorPause: document.querySelector("#orchestrator-pause"),
  orchestratorResume: document.querySelector("#orchestrator-resume"),
  orchestratorStop: document.querySelector("#orchestrator-stop"),
  orchestratorRefresh: document.querySelector("#orchestrator-refresh"),
  orchestratorCopy: document.querySelector("#orchestrator-copy"),
  orchestratorMode: document.querySelector("#orchestrator-mode"),
  orchestratorPolling: document.querySelector("#orchestrator-polling"),
  orchestratorUserTimer: document.querySelector("#orchestrator-user-timer"),
  orchestratorWorldTimer: document.querySelector("#orchestrator-world-timer"),
  orchestratorMessage: document.querySelector("#orchestrator-message"),
  orchestratorSourceHealth: document.querySelector("#orchestrator-source-health"),
  orchestratorSourceTitle: document.querySelector("#orchestrator-source-title"),
  orchestratorFrame: document.querySelector("#orchestrator-frame"),
  orchestratorFrameEmpty: document.querySelector("#orchestrator-frame-empty"),
  orchestratorSourceHost: document.querySelector("#orchestrator-source-host"),
  orchestratorSourceRole: document.querySelector("#orchestrator-source-role"),
  orchestratorSourceRegistration: document.querySelector("#orchestrator-source-registration"),
  orchestratorSourceTime: document.querySelector("#orchestrator-source-time"),
  orchestratorSourceHash: document.querySelector("#orchestrator-source-hash"),
  orchestratorSimilarity: document.querySelector("#orchestrator-similarity"),
  orchestratorSuppressed: document.querySelector("#orchestrator-suppressed"),
  orchestratorWorkcellState: document.querySelector("#orchestrator-workcell-state"),
  orchestratorArms: document.querySelector("#orchestrator-arms"),
  orchestratorCameras: document.querySelector("#orchestrator-cameras"),
  orchestratorBaseState: document.querySelector("#orchestrator-base-state"),
  orchestratorSquares: document.querySelector("#orchestrator-squares"),
  orchestratorMismatches: document.querySelector("#orchestrator-mismatches"),
  orchestratorConfidence: document.querySelector("#orchestrator-confidence"),
  orchestratorBaseFrame: document.querySelector("#orchestrator-base-frame"),
  orchestratorBlockers: document.querySelector("#orchestrator-blockers"),
  orchestratorVerification: document.querySelector("#orchestrator-verification"),
  orchestratorPlan: document.querySelector("#orchestrator-plan"),
  orchestratorCurrentAction: document.querySelector("#orchestrator-current-action"),
  orchestratorPostcondition: document.querySelector("#orchestrator-postcondition"),
  orchestratorReplayResult: document.querySelector("#orchestrator-replay-result"),
  orchestratorReplayStatus: document.querySelector("#orchestrator-replay-status"),
  orchestratorReplayDetail: document.querySelector("#orchestrator-replay-detail"),
  orchestratorModel: document.querySelector("#orchestrator-model"),
  orchestratorModelState: document.querySelector("#orchestrator-model-state"),
  orchestratorShadowReview: document.querySelector("#orchestrator-shadow-review"),
  orchestratorShadowOperator: document.querySelector("#orchestrator-shadow-operator"),
  orchestratorShadowChoice: document.querySelector("#orchestrator-shadow-choice"),
  orchestratorShadowNote: document.querySelector("#orchestrator-shadow-note"),
  orchestratorShadowSubmit: document.querySelector("#orchestrator-shadow-submit"),
  orchestratorShadowResult: document.querySelector("#orchestrator-shadow-result"),
  orchestratorChatForm: document.querySelector("#orchestrator-chat-form"),
  orchestratorChat: document.querySelector("#orchestrator-chat"),
  orchestratorConversation: document.querySelector("#orchestrator-conversation"),
  orchestratorSkillCount: document.querySelector("#orchestrator-skill-count"),
  orchestratorSkills: document.querySelector("#orchestrator-skills"),
  orchestratorLedgerCount: document.querySelector("#orchestrator-ledger-count"),
  orchestratorLedger: document.querySelector("#orchestrator-ledger"),
};

function text(node, value) {
  if (!node) return;
  const nextValue = value == null ? "" : String(value);
  if (node.textContent !== nextValue) node.textContent = nextValue;
}

function formatCampaign(value) {
  const replacements = new Map([
    ["groot", "GR00T"],
    ["n17", "N1.7"],
    ["vla", "VLA"],
    ["act", "ACT"],
    ["so101", "SO-101"],
  ]);
  return String(value || "")
    .replaceAll("-", "_")
    .split("_")
    .filter(Boolean)
    .map((part) => replacements.get(part.toLowerCase()) || `${part[0]?.toUpperCase() || ""}${part.slice(1)}`)
    .join(" ");
}

function formatIdentifier(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b[a-z]/g, (character) => character.toUpperCase());
}

function formatCaseMove(caseId) {
  const match = String(caseId || "").match(/(?:^|_)([a-h][1-8])_to_([a-h][1-8])(?:_|$)/i);
  if (!match) return "";
  return `${match[1].toUpperCase()}\u2192${match[2].toUpperCase()}`;
}

function episodeDisplayTitle(episode) {
  const move = formatCaseMove(episode?.case_id);
  return move ? `${episode.title} \u00b7 ${move}` : episode?.title || "Episode";
}

function shortPhaseLabel(value) {
  const label = String(value || "").toLowerCase();
  const aliases = [
    ["stand", "STAND"],
    ["advance", "ADV"],
    ["approach", "APPR"],
    ["close", "CLOSE"],
    ["grasp", "GRASP"],
    ["lift", "LIFT"],
    ["transfer", "TRANS"],
    ["transport", "TRANS"],
    ["lower", "LOWER"],
    ["release", "REL"],
    ["retreat", "RET"],
  ];
  return aliases.find(([needle]) => label.includes(needle))?.[1] || String(value || "").slice(0, 5).toUpperCase();
}

function formatTime(seconds) {
  const safe = Number.isFinite(seconds) ? Math.max(0, seconds) : 0;
  const minutes = Math.floor(safe / 60);
  const wholeSeconds = Math.floor(safe % 60);
  const milliseconds = Math.floor((safe % 1) * 1000);
  return `${String(minutes).padStart(2, "0")}:${String(wholeSeconds).padStart(2, "0")}.${String(milliseconds).padStart(3, "0")}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return null;
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${Math.round(seconds % 60)}s`;
}

function formatMetric(metric) {
  if (!metric) return "";
  return `${metric.value}${metric.unit || ""}`;
}

function hashString(value) {
  let hash = 2166136261;
  for (const character of String(value || "")) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function representativeFraction(episode) {
  const preferred = (episode.phases || []).find((phase) =>
    /grasp|close|lift|transfer|transit/i.test(phase.name)
  );
  const center = preferred
    ? (Number(preferred.start) + Number(preferred.end)) / 2
    : 0.54;
  const jitter = ((hashString(episode.id) % 9) - 4) / 100;
  return Math.max(0.12, Math.min(0.88, center + jitter));
}

function episodeById(identifier) {
  return state.catalog?.episodes.find((episode) => episode.id === identifier) || null;
}

function taskById(identifier) {
  return state.catalog?.tasks.find((task) => task.id === identifier) || null;
}

function selectedEpisode() {
  return episodeById(state.selectedEpisodeId);
}

function episodesForTask(taskId) {
  return state.catalog?.episodes.filter((episode) => episode.task_id === taskId) || [];
}

function setConnection(online, label) {
  elements.connection.classList.toggle("is-online", online);
  elements.connection.classList.toggle("is-offline", !online);
  text(elements.connection.lastElementChild, label);
}

async function fetchHealth() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) throw new Error(`health returned ${response.status}`);
    state.serverHealth = await response.json();
    state.readOnly = Boolean(state.serverHealth.read_only);
    document.body.dataset.studioMode = state.serverHealth.mode || "interactive";
  } catch (_error) {
    state.serverHealth = null;
    state.readOnly = null;
  }
}

function recordProcessHistory(processes) {
  const now = Date.now();
  processes.forEach((process) => {
    const key = process.id || String(process.pid || process.title);
    const history = state.processHistory.get(key) || [];
    const value = Number.isFinite(process.progress)
      ? process.progress
      : history.length
        ? history[history.length - 1].value
        : 0;
    const previous = history[history.length - 1];
    if (!previous || previous.value !== value || previous.phase !== process.phase || now - previous.at > 9000) {
      history.push({ at: now, value, phase: process.phase || process.status });
    }
    state.processHistory.set(key, history.slice(-30));
  });
}

async function fetchCatalog({ initial = false } = {}) {
  try {
    const response = await fetch("/api/catalog", { cache: "no-store" });
    if (!response.ok) throw new Error(`catalog returned ${response.status}`);
    const catalog = await response.json();
    recordProcessHistory(catalog.processes || []);
    state.catalog = catalog;
    setConnection(true, "Catalog live");

    const fingerprint = JSON.stringify({
      project: catalog.project,
      summary: catalog.summary,
      tasks: catalog.tasks.map((task) => [task.id, task.episode_count, task.passed_count, task.failed_count]),
      episodes: catalog.episodes.map((episode) => [episode.id, episode.status, episode.recorded_at]),
      feeds: catalog.episodes.map((episode) => [episode.id, ...(episode.recording_feeds || []).map((feed) => feed.id)]),
      processes: catalog.processes.map((process) => [process.id, process.pid, process.status, process.phase, process.progress, process.updated_at]),
      robots: catalog.robots.map((robot) => [robot.id, robot.status]),
      calibrations: (catalog.calibrations || []).map((asset) => [asset.id, asset.status, asset.model?.sha256]),
    });

    renderSummary();
    if (initial || fingerprint !== state.fingerprint) {
      state.fingerprint = fingerprint;
      renderTaskFilters();
      renderRailEpisodes();
      renderLibrary();
      renderSimulation();
      renderRobots();
      renderCalibration();
      renderActivity();

      if (!selectedEpisode()) {
        const linked = catalog.processes.find((process) => process.status === "running" && process.episode_id);
        const fallback = [...catalog.episodes].sort((left, right) => String(right.recorded_at).localeCompare(String(left.recorded_at)))[0];
        selectEpisode(linked?.episode_id || fallback?.id || null, { updateRoute: false });
      } else {
        updateSelectedCardState();
        renderEvidence(selectedEpisode());
      }
    } else if (state.drawer === "process") {
      renderActivity();
    }
  } catch (error) {
    setConnection(false, "Catalog offline");
    if (initial) {
      text(elements.stageTitle, "Viewer unavailable");
      text(elements.stageSubtitle, "Start the studio server from this repository and reload.");
    }
  }
}

function projectMapNode(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value != null) text(node, value);
  return node;
}

function projectMapLane(label, kind) {
  const lane = projectMapNode("section", `project-map-lane is-${kind}`);
  lane.append(projectMapNode("span", "project-map-lane-key", label));
  return lane;
}

function renderProjectMap() {
  const root = elements.projectMapContent;
  root.replaceChildren();
  const payload = state.projectMap;
  if (!payload || state.projectMapError) {
    const empty = projectMapNode("section", "project-map-empty");
    empty.append(
      projectMapNode("p", "eyebrow", "Project contract unavailable"),
      projectMapNode(
        "h3",
        "",
        "Studio cannot prove the shared researcher and agent map.",
      ),
      projectMapNode(
        "p",
        "",
        state.projectMapError || "No verified project-map response is available.",
      ),
    );
    root.append(empty);
    return;
  }

  const thesis = projectMapNode("section", "project-map-thesis");
  const thesisCopy = projectMapNode("div", "project-map-thesis-copy");
  thesisCopy.append(
    projectMapNode("p", "eyebrow", "One project · two interfaces · shared truth"),
    projectMapNode("h3", "", payload.title),
    projectMapNode("p", "", payload.objective),
  );
  const interfaceList = projectMapNode("dl", "project-map-interface");
  [
    ["Researcher", payload.interface?.human],
    ["Agent", payload.interface?.agent],
    ["Contract", payload.interface?.shared_truth],
  ].forEach(([label, value]) => {
    interfaceList.append(
      projectMapNode("dt", "", label),
      projectMapNode("dd", "", value || "Unavailable"),
    );
  });
  thesis.append(thesisCopy, interfaceList);

  const stages = projectMapNode("ol", "project-map-stages");
  (payload.stages || []).forEach((stage) => {
    const item = projectMapNode("li", "project-map-stage");
    item.dataset.status = stage.status || "unavailable";

    const stageHead = projectMapNode("header", "project-map-stage-head");
    stageHead.append(
      projectMapNode("span", "project-map-stage-number", String(stage.order).padStart(2, "0")),
      projectMapNode("h3", "", stage.title),
      projectMapNode(
        "span",
        "project-map-stage-status",
        String(stage.status || "unavailable").replaceAll("_", " "),
      ),
    );
    item.append(
      stageHead,
      projectMapNode("p", "project-map-purpose", stage.purpose),
    );

    const rails = projectMapNode("div", "project-map-rails");
    const humanLane = projectMapLane("Researcher", "human");
    const routeList = projectMapNode("div", "project-map-routes");
    (stage.human_views || []).forEach((view) => {
      const link = projectMapNode("a", "project-map-route", view.label);
      link.href = `#/${view.route}`;
      link.addEventListener("click", (event) => {
        event.preventDefault();
        closeDrawer();
        navigate(view.route);
      });
      routeList.append(link);
    });
    humanLane.append(routeList);

    const agentLane = projectMapLane("Agent", "agent");
    agentLane.append(
      projectMapNode(
        "strong",
        "project-map-agent-access",
        String(stage.agent?.access || "unavailable").replaceAll("_", " "),
      ),
    );
    const agentContracts = projectMapNode("div", "project-map-contracts");
    (stage.agent?.reads || []).forEach((contract) => {
      agentContracts.append(projectMapNode("code", "", contract));
    });
    (stage.agent?.commands || []).forEach((contract) => {
      agentContracts.append(projectMapNode("code", "is-command", contract));
    });
    if (!agentContracts.childElementCount) {
      agentContracts.append(projectMapNode("span", "project-map-none", "No command surface"));
    }
    agentLane.append(agentContracts);
    rails.append(humanLane, agentLane);
    item.append(rails);

    const evidence = projectMapNode("dl", "project-map-evidence");
    evidence.append(
      projectMapNode("dt", "", "Observed"),
      projectMapNode("dd", "", stage.measure || "Unavailable"),
      projectMapNode("dt", "", "Proof"),
      projectMapNode("dd", "", stage.proof || "Unavailable"),
    );
    item.append(evidence);

    if ((stage.missing || []).length) {
      const missing = projectMapNode("div", "project-map-missing");
      missing.append(projectMapNode("span", "project-map-missing-label", "Still missing"));
      const gaps = projectMapNode("div", "project-map-gap-list");
      stage.missing.forEach((gap) => {
        gaps.append(projectMapNode("span", "project-map-gap", gap));
      });
      missing.append(gaps);
      item.append(missing);
    }
    item.append(
      projectMapNode("p", "project-map-detail", stage.detail),
      projectMapNode("p", "project-map-boundary", stage.agent?.boundary),
    );
    stages.append(item);
  });

  const authority = payload.authority || {};
  const footer = projectMapNode("footer", "project-map-footer");
  const authorityValues = [
    authority.agent_is_evaluator ? "agent evaluator" : "evaluator independent",
    authority.agent_can_promote ? "agent promotion" : "promotion closed",
    authority.training_authority ? "training open" : "training closed",
    authority.robot_motion ? "motion open" : "motion closed",
  ];
  footer.append(
    projectMapNode("p", "project-map-authority", authorityValues.join(" · ")),
    projectMapNode(
      "code",
      "",
      `contract ${String(payload.config?.sha256 || "unavailable").slice(0, 12)}`,
    ),
  );
  root.append(thesis, stages, footer);
}

async function fetchProjectMap() {
  if (state.projectMapFetchActive) return;
  state.projectMapFetchActive = true;
  try {
    const response = await fetch("/api/project-map", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || payload.detail || `project map returned ${response.status}`);
    }
    state.projectMap = payload;
    state.projectMapError = null;
  } catch (error) {
    state.projectMap = null;
    state.projectMapError = error instanceof Error ? error.message : "Project map unavailable";
  } finally {
    state.projectMapFetchActive = false;
    renderProjectMap();
  }
}

function selectedSailEpisode() {
  return state.sail?.episodes?.find((episode) => episode.id === state.sailSelectedEpisodeId) || null;
}

function sailVector(value, digits = 2) {
  if (!Array.isArray(value)) return "Missing";
  return value.map((item) => Number(item).toFixed(digits)).join(" · ");
}

function sailScalar(value, unit = "", digits = 2) {
  return Number.isFinite(Number(value)) ? `${Number(value).toFixed(digits)}${unit}` : "Missing";
}

function sailNorm(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return null;
  return Math.sqrt(left.reduce((total, value, index) => total + (Number(value) - Number(right[index])) ** 2, 0));
}

function sailElement(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value != null) text(node, value);
  return node;
}

function sailDlRow(term, value) {
  const wrapper = document.createElement("div");
  wrapper.append(sailElement("dt", "", term), sailElement("dd", "", value));
  return wrapper;
}

function renderSailInventory() {
  if (!state.sail) return;
  elements.sailEpisodeList.replaceChildren();
  state.sail.episodes.forEach((episode) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sail-episode-button";
    button.dataset.ranking = episode.ranking_status;
    button.dataset.episodeId = episode.id;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(episode.id === state.sailSelectedEpisodeId));
    button.classList.toggle("is-active", episode.id === state.sailSelectedEpisodeId);
    const rank = sailElement("small", "", episode.ranking_status === "ranked_strongest_partial" ? `RANK ${String(episode.rank).padStart(2, "0")}` : "LOWER SIGNAL · RETAINED");
    const move = sailElement("b", "", episode.move);
    const outcome = sailElement("em", "", episode.relative_success_label);
    button.append(rank, move, outcome);
    button.addEventListener("click", () => selectSailEpisode(episode.id));
    elements.sailEpisodeList.append(button);
  });
  const ranking = state.sail.ranking;
  text(
    elements.sailRankingNote,
    `${ranking.selected_episode_count} strongest lead · ${ranking.lower_signal_retained_count} lower-signal partials retained · ${ranking.omitted_episode_count} omitted`,
  );
}

function sailSvgNode(tag, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, String(value)));
  return node;
}

function sailSeriesValues(episode) {
  const channels = episode.channels;
  const pawn = channels.simulated_pawn_rise_m;
  const contact = channels.simulated_pawn_contact_count;
  return [
    { label: "ACTION · elbow", color: "#ff5a1f", values: channels.action.map((row) => Number(row[2])) },
    { label: "MEASURED · elbow", color: "#6b716d", values: channels.mapped_measured_joint.map((row) => Number(row[2])) },
    { label: "SIM · elbow", color: "#145c70", values: channels.selected_simulated_joint.map((row) => Number(row[2])) },
    {
      label: "EE GAP · norm",
      color: "#8a4d95",
      values: channels.selected_simulated_end_effector_m.map((row, index) => sailNorm(row, channels.mapped_measured_end_effector_m[index])),
    },
    { label: "APERTURE · residual", color: "#9a6713", values: channels.simulated_aperture_radian.map((value, index) => Number(value) - Number(channels.mapped_measured_joint[index][5])) },
    { label: "PAWN · rise", color: "#0b6847", values: Array.isArray(pawn) ? pawn.map(Number) : null },
    { label: "CONTACT · count", color: "#a62b2b", values: Array.isArray(contact) ? contact.map(Number) : null },
  ];
}

function renderSailSignalPlot(episode) {
  const svg = elements.sailSignalPlot;
  svg.replaceChildren();
  const width = 960;
  const height = 300;
  const left = 126;
  const right = 14;
  const laneHeight = 38;
  const series = sailSeriesValues(episode);
  series.forEach((row, lane) => {
    const yTop = 12 + lane * laneHeight;
    const label = sailSvgNode("text", { x: 8, y: yTop + 19, fill: row.color, "font-size": 10, "font-family": "ui-monospace, monospace" });
    label.textContent = row.label;
    svg.append(label);
    svg.append(sailSvgNode("line", { x1: left, x2: width - right, y1: yTop + 18, y2: yTop + 18, stroke: "#cdd2cf", "stroke-width": 1 }));
    if (!Array.isArray(row.values) || !row.values.length || row.values.every((value) => !Number.isFinite(value))) {
      const missing = sailSvgNode("text", { x: left + 8, y: yTop + 22, fill: "#6b716d", "font-size": 10, "font-family": "ui-monospace, monospace" });
      missing.textContent = "MISSING — not imputed";
      svg.append(missing);
      return;
    }
    const finite = row.values.filter(Number.isFinite);
    const minimum = Math.min(...finite);
    const maximum = Math.max(...finite);
    const span = maximum - minimum || 1;
    const points = row.values.map((value, index) => {
      const x = left + index / Math.max(1, row.values.length - 1) * (width - left - right);
      const normalized = Number.isFinite(value) ? (value - minimum) / span : 0.5;
      const y = yTop + 31 - normalized * 26;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(" ");
    svg.append(sailSvgNode("polyline", { points, fill: "none", stroke: row.color, "stroke-width": 1.6, "vector-effect": "non-scaling-stroke" }));
  });
}

function renderSailPhaseRail(episode) {
  elements.sailPhaseRail.replaceChildren();
  episode.phase_intervals.forEach((interval) => {
    const segment = sailElement("span", "sail-phase-segment", formatIdentifier(interval.phase));
    const width = Number(interval.sample_count) / Number(episode.sample_count) * 100;
    segment.style.width = `${width}%`;
    segment.title = `${formatIdentifier(interval.phase)} · samples ${interval.start_sample_index_inclusive}–${interval.end_sample_index_exclusive - 1}`;
    elements.sailPhaseRail.append(segment);
  });
}

function renderSailAvailability(episode) {
  elements.sailAvailabilityGrid.replaceChildren();
  episode.availability.forEach((row) => {
    const card = document.createElement("div");
    card.className = "sail-availability";
    card.dataset.status = row.status;
    card.title = row.detail;
    card.append(
      sailElement("b", "", formatIdentifier(row.id)),
      sailElement("span", "", formatIdentifier(row.status)),
      sailElement("small", "", formatIdentifier(row.proof_class)),
    );
    elements.sailAvailabilityGrid.append(card);
  });
}

function renderSailHeatmap(episode) {
  elements.sailHeatmap.replaceChildren();
  episode.residual_cells.forEach((cell) => {
    const row = document.createElement("div");
    row.className = "sail-heatmap-row";
    const label = sailElement("span", "", formatIdentifier(cell.channel));
    label.title = cell.channel;
    const value = document.createElement("div");
    value.className = "sail-heatmap-cell";
    if (cell.rmse == null || cell.normalized_within_channel == null) {
      value.classList.add("is-missing");
      text(value, "MISSING");
    } else {
      const normalized = Math.max(0, Math.min(1, Number(cell.normalized_within_channel)));
      value.style.background = `color-mix(in srgb, var(--motion) ${Math.round(18 + normalized * 78)}%, var(--diagnostic))`;
      text(value, `${Number(cell.rmse).toPrecision(3)} ${cell.unit || ""}`);
    }
    row.append(label, value);
    elements.sailHeatmap.append(row);
  });
  elements.sailResidualFacts.replaceChildren(
    sailDlRow("Episode", episode.id),
    sailDlRow("Action", episode.action_array_sha256),
    sailDlRow("Residual receipt", state.sail.residuals.receipt_sha256),
    sailDlRow("Missingness", "Explicit masks · no imputation"),
  );
}

function renderSailFrame() {
  const episode = selectedSailEpisode();
  if (!episode) return;
  const count = episode.sample_count;
  const index = Math.max(0, Math.min(count - 1, Number(state.sailFrameIndex || 0)));
  state.sailFrameIndex = index;
  elements.sailScrubber.value = String(index);
  text(elements.sailFrameIndex, `${index + 1} / ${count}`);
  text(elements.sailPhase, formatIdentifier(episode.channels.phase[index]));
  text(elements.sailTime, formatTime(Number(episode.channels.time_seconds[index])));
  elements.sailEvidenceSpine.style.left = `${count > 1 ? index / (count - 1) * 100 : 0}%`;

  const action = episode.channels.action[index];
  const measured = episode.channels.mapped_measured_joint[index];
  const simulated = episode.channels.selected_simulated_joint[index];
  const measuredEe = episode.channels.mapped_measured_end_effector_m[index];
  const simulatedEe = episode.channels.selected_simulated_end_effector_m[index];
  const pawn = episode.channels.simulated_pawn_xyz_m?.[index];
  const contact = episode.channels.simulated_pawn_contact_count?.[index];
  const rise = episode.channels.simulated_pawn_rise_m?.[index];
  const targetGap = episode.channels.simulated_pawn_to_target_m?.[index];
  const values = [
    ["Action", sailVector(action, 2), "rad · 6 joints"],
    ["Measured / sim", `${sailScalar(measured?.[2], " rad")} / ${sailScalar(simulated?.[2], " rad")}`, "elbow flex"],
    ["End-effector gap", sailScalar(sailNorm(measuredEe, simulatedEe) * 1000, " mm", 2), "mapped physical ↔ sim"],
    ["Pawn / contact", pawn ? `${sailScalar(pawn[2], " m", 3)} · ${contact ?? 0} contacts` : "Missing", pawn ? "simulator only" : "no retained trace"],
    ["Consequence", Number.isFinite(rise) ? `${sailScalar(rise * 1000, " mm", 1)} rise · ${sailScalar(targetGap * 1000, " mm", 1)} gap` : "Missing", `target ${episode.target_square.toUpperCase()} · simulator only`],
  ];
  elements.sailFrameReadouts.replaceChildren();
  values.forEach(([label, value, note]) => {
    const card = document.createElement("div");
    card.className = "sail-frame-readout";
    card.append(sailElement("span", "", label), sailElement("b", "", value), sailElement("small", "", note));
    elements.sailFrameReadouts.append(card);
  });
}

function renderSailEpisode() {
  const episode = selectedSailEpisode();
  if (!episode) return;
  text(elements.sailEpisodeProof, episode.proof_label);
  text(elements.sailTraceHeading, `${episode.move} · ${episode.ranking_status === "ranked_strongest_partial" ? `rank ${episode.rank}` : "lower-signal retained"}`);
  text(elements.sailTraceSummary, `${episode.relative_success_summary}. Source actions remain byte-identical; physical contact, force, object trajectory, and consequence are unavailable.`);
  elements.sailScrubber.max = String(Math.max(0, episode.sample_count - 1));
  elements.sailScrubber.value = "0";
  elements.sailOpenReplay.disabled = !episode.inspection;
  text(elements.sailOpenReplay, episode.inspection ? "Open 3D replay" : "3D replay missing");
  renderSailPhaseRail(episode);
  renderSailSignalPlot(episode);
  renderSailAvailability(episode);
  renderSailHeatmap(episode);
  renderSailFrame();
}

function selectSailEpisode(identifier) {
  if (!state.sail?.episodes?.some((episode) => episode.id === identifier)) return;
  state.sailSelectedEpisodeId = identifier;
  state.sailFrameIndex = 0;
  renderSailInventory();
  renderSailEpisode();
}

function renderSailCausalViews() {
  if (!state.sail) return;
  const figures = state.sail.figures;
  elements.sailGraphBefore.src = figures.belief_before.url;
  elements.sailGraphAfter.src = figures.belief_after.url;
  const belief = state.sail.belief_revision;
  text(elements.sailGraphDelta, `${belief.before.node_count}→${belief.after.node_count} nodes · ${belief.before.edge_count}→${belief.after.edge_count} edges`);
  elements.sailRevisionStrip.replaceChildren();
  const maximumNodes = Math.max(...belief.timeline.map((row) => Number(row.node_count || 0)), 1);
  belief.timeline.forEach((row) => {
    const item = sailElement("span", "sail-revision", `R${row.revision}`);
    item.style.height = `${28 + Number(row.node_count) / maximumNodes * 42}px`;
    item.title = `${formatIdentifier(row.event_id)} · ${row.node_count} nodes · ${row.edge_count} edges · ${row.graph_digest}`;
    elements.sailRevisionStrip.append(item);
  });

  const debt = state.sail.compensation_debt;
  text(elements.sailDebtScore, `${Number(debt.score).toFixed(3)} · ${debt.triggered ? "triggered" : "clear"}`);
  text(elements.sailDebtBoundary, debt.claim_boundary);
  const before = Number(debt.before_sparse_closure || 0);
  const after = Number(debt.after_sparse_closure || 0);
  elements.sailDebtBefore.style.width = `${Math.min(100, before / Math.max(before, after, 1e-9) * 100)}%`;
  elements.sailDebtAfter.style.width = `${Math.min(100, after / Math.max(before, after, 1e-9) * 100)}%`;
  elements.sailDebtComponents.replaceChildren();
  debt.components.forEach((component) => {
    const card = document.createElement("div");
    card.className = "sail-debt-component";
    const copy = document.createElement("div");
    copy.append(sailElement("b", "", formatIdentifier(component.id)), sailElement("small", "", component.available ? formatIdentifier(component.reason) : "Not evaluable · missing posterior evidence"));
    card.append(copy, sailElement("em", "", component.available ? Number(component.weighted_contribution).toFixed(3) : "MISSING"));
    elements.sailDebtComponents.append(card);
  });

  const interventions = state.sail.interventions;
  text(elements.sailSelectedProbe, formatIdentifier(interventions.selected_simulator_probe));
  elements.sailInterventionList.replaceChildren();
  [...interventions.rows]
    .sort((left, right) => Number(left.structural_rank || 999) - Number(right.structural_rank || 999))
    .forEach((row) => {
      const card = document.createElement("div");
      card.className = "sail-intervention";
      card.classList.toggle("is-selected", row.candidate_id === interventions.selected_simulator_probe);
      const copy = document.createElement("div");
      const signatures = Object.entries(row.predicted_signatures || {}).map(([name, value]) => `${formatIdentifier(name)} ${Number(value).toFixed(2)}`).join(" · ");
      copy.append(sailElement("b", "", formatIdentifier(row.candidate_id)), sailElement("small", "", `${formatIdentifier(row.availability)} · ${signatures}`));
      card.append(copy, sailElement("em", "", row.structural_rank ? `S${row.structural_rank} · ${Number(row.structural_score).toFixed(3)}` : "PLAN"));
      elements.sailInterventionList.append(card);
    });
}

function renderSailVerdicts() {
  if (!state.sail) return;
  const posterior = state.sail.posterior_and_invariance;
  const invarianceByMechanism = new Map(posterior.invariance_results.map((row) => [row.mechanism_id, row]));
  text(elements.sailInvarianceCount, `${posterior.invariance_counts.not_evaluable_count}/${posterior.invariance_counts.mechanism_count} not evaluable`);
  elements.sailPosteriorList.replaceChildren();
  posterior.particles.forEach((particle) => {
    const verdict = invarianceByMechanism.get(particle.mechanism_id) || {};
    const card = document.createElement("div");
    card.className = "sail-posterior";
    card.dataset.verdict = verdict.verdict || "missing";
    const copy = document.createElement("div");
    const missing = particle.missing_observables?.length ? `missing ${particle.missing_observables.map(formatIdentifier).join(", ")}` : formatIdentifier(verdict.reason || particle.status);
    copy.append(sailElement("b", "", formatIdentifier(particle.family)), sailElement("small", "", missing));
    card.append(copy, sailElement("em", "", formatIdentifier(verdict.verdict || particle.status)));
    elements.sailPosteriorList.append(card);
  });

  const twin = state.sail.twin_worthiness;
  text(elements.sailTwinLevel, twin.level);
  elements.sailGateMatrix.replaceChildren();
  Object.entries(twin.matrix).forEach(([name, decision]) => {
    const card = document.createElement("div");
    card.className = "sail-gate";
    card.dataset.allowed = String(Boolean(decision.allowed));
    const copy = document.createElement("div");
    const detail = decision.allowed ? "Evaluator allowed · diagnostics only" : `${(decision.failed_gates || []).join(", ") || "gate closed"} · ${(decision.denial_codes || []).map(formatIdentifier).join(", ")}`;
    copy.append(sailElement("b", "", formatIdentifier(name)), sailElement("small", "", detail));
    card.append(copy, sailElement("em", "", decision.allowed ? "OPEN" : "DENIED"));
    elements.sailGateMatrix.append(card);
  });
  elements.sailMinimumEvidence.replaceChildren();
  Object.entries(twin.minimum_new_evidence).forEach(([gate, requirement]) => elements.sailMinimumEvidence.append(sailDlRow(gate, requirement)));
}

function renderSailPublication() {
  if (!state.sail) return;
  elements.sailFigureList.replaceChildren();
  Object.entries(state.sail.figures).forEach(([name, figure]) => {
    const link = document.createElement("a");
    link.className = "sail-figure-link";
    link.href = figure.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.append(sailElement("b", "", formatIdentifier(name)), sailElement("span", "", "Open bound SVG ↗"), sailElement("code", "", figure.sha256));
    elements.sailFigureList.append(link);
  });
  elements.sailProofLegend.replaceChildren();
  state.sail.proof_legend.forEach((row) => {
    const token = sailElement("span", "sail-proof-token", `${row.label} · ${formatIdentifier(row.authority)}`);
    token.title = row.id;
    elements.sailProofLegend.append(token);
  });
}

function renderSail() {
  if (!elements.sailEmpty) return;
  if (!state.sail) {
    elements.sailEmpty.hidden = false;
    text(elements.sailStatus, state.sailFetchActive ? "Loading evidence" : "Unavailable");
    text(elements.sailReceipt, "no verified receipt");
    text(elements.sailEmptyDetail, state.sailError || "Compile the bound observatory assets and reload Studio.");
    return;
  }
  elements.sailEmpty.hidden = true;
  text(elements.sailStatus, `${state.sail.episodes.length} episodes · read only`);
  text(elements.sailReceipt, state.sail.receipt_sha256);
  if (!selectedSailEpisode()) state.sailSelectedEpisodeId = state.sail.episodes[0]?.id || null;
  renderSailInventory();
  renderSailEpisode();
  renderSailCausalViews();
  renderSailVerdicts();
  renderSailPublication();
}

async function fetchSailObservatory() {
  if (state.sailFetchActive) return;
  state.sailFetchActive = true;
  renderSail();
  try {
    const response = await fetch("/api/sail-observatory", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.available) throw new Error(payload.error || `SAIL observatory returned ${response.status}`);
    state.sail = payload;
    state.sailError = null;
  } catch (error) {
    state.sail = null;
    state.sailError = String(error.message || error);
  } finally {
    state.sailFetchActive = false;
    renderSail();
  }
}

function renderSummary() {
  const { project, summary, processes } = state.catalog;
  text(elements.campaign, formatCampaign(project.active_campaign || "Local simulation workspace"));
  text(elements.passRatio, `${summary.passed_episodes}/${summary.episodes} passed`);
  const active = processes.filter((process) => process.status === "running");
  elements.liveStrip.hidden = active.length === 0;
  if (active.length) {
    const primary = active[0];
    text(elements.liveStripTitle, primary.title || `${primary.kind || "Process"} active`);
    text(elements.liveStripPhase, primary.phase || primary.detail || "Heartbeat received");
  }
}

function createTaskFilter({ id, title, detail, count, active }) {
  const button = elements.taskFilterTemplate.content.firstElementChild.cloneNode(true);
  button.dataset.taskId = id || "";
  button.classList.toggle("is-active", active);
  text(button.querySelector("b"), title);
  text(button.querySelector("small"), detail);
  text(button.querySelector(".task-filter-result"), count);
  button.addEventListener("click", () => {
    if (id) selectTask(id);
    else clearTaskFilter();
  });
  return button;
}

function renderTaskFilters() {
  elements.taskFilterList.replaceChildren();
  elements.taskFilterList.append(createTaskFilter({
    id: null,
    title: "All",
    detail: "",
    count: "",
    active: !state.taskFilter,
  }));
  state.catalog.tasks.forEach((task) => {
    elements.taskFilterList.append(createTaskFilter({
      id: task.id,
      title: task.title,
      detail: task.role,
      count: task.episode_count,
      active: state.taskFilter === task.id,
    }));
  });
}

function filteredEpisodes() {
  const needle = state.query.trim().toLowerCase();
  return (state.catalog?.episodes || []).filter((episode) => {
    if (state.taskFilter && episode.task_id !== state.taskFilter) return false;
    if (!needle) return true;
    const haystack = [
      episode.title,
      episode.subtitle,
      episode.task_id,
      episode.case_id,
      episode.terminal_outcome,
      episode.notes,
      ...episode.metrics.map((metric) => `${metric.label} ${metric.value}`),
    ].join(" ").toLowerCase();
    return haystack.includes(needle);
  });
}

function selectTask(taskId, { selectLatest = true, updateRoute = true } = {}) {
  state.taskFilter = taskId;
  state.query = "";
  elements.search.value = "";
  elements.librarySearch.value = "";
  renderTaskFilters();
  renderRailEpisodes();
  renderLibrary();
  if (selectLatest) {
    const episodes = filteredEpisodes();
    const latest = [...episodes].sort((left, right) => String(right.recorded_at).localeCompare(String(left.recorded_at)))[0];
    if (latest) selectEpisode(latest.id, { updateRoute: false });
  }
  if (updateRoute) history.replaceState(null, "", `#/tasks/${encodeURIComponent(taskId)}`);
}

function clearTaskFilter({ updateRoute = true } = {}) {
  state.taskFilter = null;
  renderTaskFilters();
  renderRailEpisodes();
  renderLibrary();
  if (updateRoute) history.replaceState(null, "", state.view === "library" ? "#/library" : "#/replay");
}

function renderRailEpisodes() {
  if (!state.catalog) return;
  const episodes = filteredEpisodes();
  const task = taskById(state.taskFilter);
  elements.browserRail.dataset.taskId = task?.id || "";
  text(
    elements.browserHeading,
    task?.id === "pawn_bg_ranked_grasp_v3" ? "Ranked replays" : "Choose evidence",
  );
  text(elements.railContext, task ? task.title : state.query ? "Search results" : "All episodes");
  text(elements.railResultCount, task || state.query ? episodes.length : "");
  text(
    elements.mobileBrowserLabel,
    task
      ? `Browse ${episodes.length} ${task.id === "pawn_bg_ranked_grasp_v3" ? "ranked replays" : "task episodes"}`
      : `Browse ${episodes.length} episodes`,
  );
  elements.railEpisodeList.replaceChildren();

  episodes.forEach((episode, index) => {
    const row = elements.railEpisodeTemplate.content.firstElementChild.cloneNode(true);
    row.dataset.episodeId = episode.id;
    row.classList.add(episode.status || "recorded");
    row.classList.toggle("is-active", state.selectedEpisodeId === episode.id);
    const salient = episode.metrics.find((metric) => metric.tone && metric.tone !== "neutral");
    const move = formatCaseMove(episode.case_id);
    text(row.querySelector(".rail-copy b"), episodeDisplayTitle(episode));
    text(row.querySelector(".rail-copy small"), [move ? formatIdentifier(episode.case_id.split("_")[0]) : "", salient ? `${salient.label} ${formatMetric(salient)}` : formatDuration(episode.duration_seconds) || episode.proof_label].filter(Boolean).join(" \u00b7 "));
    row.setAttribute("aria-label", `Open ${episode.title}: ${episode.subtitle}`);
    mountThumbnail(row.querySelector(".rail-thumb"), episode, index < 8);
    row.addEventListener("click", () => {
      selectEpisode(episode.id);
      elements.browserRail.classList.remove("is-mobile-open");
      elements.mobileBrowserToggle.setAttribute("aria-expanded", "false");
    });
    elements.railEpisodeList.append(row);
  });
}

function phasePortraitPath(episode) {
  const phases = episode.phases?.length
    ? episode.phases
    : [{ start: 0, end: 0.25 }, { start: 0.25, end: 0.58 }, { start: 0.58, end: 1 }];
  const seed = hashString(episode.id);
  const points = [{ x: 9, y: 45 }];
  phases.forEach((phase, index) => {
    const x = 9 + Number(phase.end || (index + 1) / phases.length) * 142;
    const byte = (seed >>> ((index % 4) * 8)) & 255;
    const direction = index % 2 === 0 ? -1 : 1;
    const y = Math.max(12, Math.min(78, 45 + direction * (12 + (byte % 25))));
    points.push({ x, y });
  });
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length; index += 1) {
    const previous = points[index - 1];
    const current = points[index];
    const middle = (previous.x + current.x) / 2;
    path += ` C ${middle} ${previous.y}, ${middle} ${current.y}, ${current.x} ${current.y}`;
  }
  return { path, end: points[points.length - 1] };
}

function drawPhasePortrait(container, episode, { stage = false } = {}) {
  if (!container || !episode) return;
  const namespace = "http://www.w3.org/2000/svg";
  const svg = container.tagName.toLowerCase() === "svg"
    ? container
    : document.createElementNS(namespace, "svg");
  svg.replaceChildren();
  svg.setAttribute("viewBox", "0 0 160 90");
  svg.setAttribute("aria-hidden", "true");
  const { path, end } = phasePortraitPath(episode);
  const line = document.createElementNS(namespace, "path");
  line.setAttribute("d", path);
  const marker = document.createElementNS(namespace, "circle");
  marker.setAttribute("cx", String(end.x));
  marker.setAttribute("cy", String(end.y));
  marker.setAttribute("r", stage ? "2.8" : "3.5");
  svg.append(line, marker);
  if (container !== svg) container.replaceChildren(svg);
}

function ensureThumbnailObserver() {
  if (state.thumbnailObserver || !("IntersectionObserver" in window)) return;
  state.thumbnailObserver = new IntersectionObserver((entries, observer) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target._startMedia?.();
      observer.unobserve(entry.target);
    });
  }, { rootMargin: "260px" });
}

function mountThumbnail(container, episode, priority = false) {
  const portrait = container.querySelector(".phase-portrait");
  drawPhasePortrait(portrait, episode);
  const media = episode.media || {};

  if (media.kind === "video" && media.url) {
    const video = document.createElement("video");
    video.muted = true;
    video.playsInline = true;
    video.tabIndex = -1;
    video.preload = priority ? "auto" : "metadata";
    video.style.rotate = `${Number(media.display_rotation_degrees || 0)}deg`;
    const start = () => {
      if (video.src) return;
      video.src = media.url;
      video.addEventListener("loadedmetadata", () => {
        const offset = representativeFraction(episode);
        if (Number.isFinite(video.duration) && video.duration > 0) video.currentTime = Math.min(video.duration - 0.05, video.duration * offset);
      }, { once: true });
      video.addEventListener("seeked", () => container.classList.add("media-ready"), { once: true });
      video.addEventListener("loadeddata", () => {
        if (!Number.isFinite(video.duration) || video.duration <= 0) container.classList.add("media-ready");
      }, { once: true });
    };
    container.prepend(video);
    container._startMedia = start;
    if (priority) start();
    else {
      ensureThumbnailObserver();
      if (state.thumbnailObserver) state.thumbnailObserver.observe(container);
      else start();
    }
  } else if (media.kind === "frames" && media.urls?.length) {
    const image = document.createElement("img");
    image.alt = "";
    const start = () => {
      if (image.src) return;
      const offset = Math.floor(media.urls.length * representativeFraction(episode));
      image.src = media.urls[Math.min(media.urls.length - 1, offset)];
      image.decode?.().catch(() => {}).finally(() => container.classList.add("media-ready"));
    };
    container.prepend(image);
    container._startMedia = start;
    if (priority) start();
    else {
      ensureThumbnailObserver();
      if (state.thumbnailObserver) state.thumbnailObserver.observe(container);
      else start();
    }
  }
}

function episodeSpecialLabel(episode) {
  if (episodeComparison(episode)) {
    return episode.comparison.physics_replay?.available ? "3 views" : "2 views · physics missing";
  }
  if (Number.isInteger(episode.rank)) return `Rank ${String(episode.rank).padStart(2, "0")}`;
  if (episode.case_id === "held_out_evaluation") return "Evaluation";
  if (episode.case_id === "scripted_probe") return "Probe";
  return "";
}

function createEpisodeCard(episode, priority) {
  const card = elements.episodeTemplate.content.firstElementChild.cloneNode(true);
  card.dataset.episodeId = episode.id;
  card.classList.add(episode.status || "recorded");
  card.classList.toggle("is-active", state.selectedEpisodeId === episode.id);
  const thumb = card.querySelector(".episode-thumb");
  mountThumbnail(thumb, episode, priority);
  text(card.querySelector(".episode-special"), episodeSpecialLabel(episode));
  text(card.querySelector(".episode-card-copy b"), episodeDisplayTitle(episode));
  text(card.querySelector(".episode-card-copy small"), episode.subtitle);

  const meta = card.querySelector(".episode-card-meta");
  const duration = document.createElement("span");
  const salient = document.createElement("strong");
  const keyMetric = episode.metrics.find((metric) => metric.tone && metric.tone !== "neutral");
  text(duration, formatDuration(episode.duration_seconds) || `${episode.frame_count || "—"} frames`);
  text(salient, keyMetric ? `${keyMetric.label} ${formatMetric(keyMetric)}` : episode.status);
  meta.replaceChildren(duration, salient);

  card.setAttribute("aria-label", `Replay ${episode.title}: ${episode.subtitle}`);
  card.addEventListener("click", () => {
    setActiveView("replay", { updateRoute: false });
    selectEpisode(episode.id);
    window.scrollTo({ top: 0, behavior: "smooth" });
  });
  return card;
}

function renderLibrary() {
  if (!state.catalog) return;
  const allMatches = filteredEpisodes();
  const task = taskById(state.taskFilter);
  elements.librarySummary.replaceChildren();
  const summaryText = document.createElement("span");
  const proofText = document.createElement("span");
  summaryText.innerHTML = `<b>${allMatches.length}</b> replayable episode${allMatches.length === 1 ? "" : "s"}${task ? ` in ${task.title}` : " across the workspace"}`;
  text(proofText, "Recorded media · evaluator-owned verdicts · inspection only");
  elements.librarySummary.append(summaryText, proofText);
  elements.libraryGroups.replaceChildren();

  state.catalog.tasks.forEach((taskRow) => {
    if (state.taskFilter && taskRow.id !== state.taskFilter) return;
    const episodes = allMatches.filter((episode) => episode.task_id === taskRow.id);
    if (!episodes.length) return;
    const previewLimit = 8;
    const expanded = episodes.length <= previewLimit || state.expandedTasks.has(taskRow.id);
    const visible = expanded ? episodes : episodes.slice(0, previewLimit);
    const group = document.createElement("section");
    group.className = "library-group";
    group.dataset.taskId = taskRow.id;

    const header = document.createElement("header");
    header.className = "group-header";
    const titleWrap = document.createElement("div");
    titleWrap.className = "group-title";
    const heading = document.createElement("h2");
    const description = document.createElement("p");
    text(heading, taskRow.title);
    text(description, `${taskRow.role} · ${taskRow.proof_label}`);
    titleWrap.append(heading, description);

    const actions = document.createElement("div");
    actions.className = "group-actions";
    const count = document.createElement("span");
    count.className = "group-count";
    text(count, `${taskRow.passed_count}/${taskRow.episode_count} passed`);
    actions.append(count);
    if (episodes.length > previewLimit) {
      const toggle = document.createElement("button");
      toggle.type = "button";
      toggle.className = "group-toggle";
      text(toggle, expanded ? "Show less" : `Show all ${episodes.length}`);
      toggle.setAttribute("aria-expanded", String(expanded));
      toggle.addEventListener("click", () => {
        if (expanded) state.expandedTasks.delete(taskRow.id);
        else state.expandedTasks.add(taskRow.id);
        renderLibrary();
      });
      actions.append(toggle);
    }
    header.append(titleWrap, actions);

    const grid = document.createElement("div");
    grid.className = "episode-grid";
    visible.forEach((episode, index) => grid.append(createEpisodeCard(episode, index < 8)));
    group.append(header, grid);
    elements.libraryGroups.append(group);
  });

  if (!elements.libraryGroups.children.length) {
    const empty = document.createElement("div");
    empty.className = "empty-activity";
    empty.innerHTML = "<b>No matching evidence</b><small>Clear the search or choose another task.</small>";
    elements.libraryGroups.append(empty);
  }
}

function episodeComparison(episode = selectedEpisode()) {
  return episode?.comparison?.schema_version === "sim2claw.studio_episode_comparison.v1"
    ? episode.comparison
    : null;
}

function hasVisualTwin(episode = selectedEpisode()) {
  return Boolean(
    episodeComparison(episode)?.visual_twin?.available
    && episode?.media?.kind === "video",
  );
}

function renderComparisonAvailability(episode) {
  const comparison = episodeComparison(episode);
  elements.comparisonLaneStrip.hidden = !comparison;
  elements.visualTwinToolbar.hidden = !hasVisualTwin(episode);
  elements.comparisonRealLabel.hidden = true;
  elements.comparisonPhysicsLabel.hidden = true;
  elements.physicsUnavailable.hidden = true;
  const physicsAvailable = Boolean(
    episode?.inspection
    && (!comparison || comparison.physics_replay?.available),
  );
  elements.replayModeSwitch.querySelectorAll("[data-replay-mode]").forEach((button) => {
    const mode = button.dataset.replayMode;
    button.disabled = (
      (mode === "compare" && !comparison)
      || (mode === "visual" && !hasVisualTwin(episode))
      || (mode === "three" && !physicsAvailable)
    );
  });
  if (!comparison) return;

  const lanes = {
    real: Boolean(comparison.real?.available),
    visual: Boolean(comparison.visual_twin?.available),
    physics: physicsAvailable,
  };
  Object.entries(lanes).forEach(([name, available]) => {
    const node = elements.comparisonLaneStrip.querySelector(
      `[data-comparison-lane="${name}"]`,
    );
    if (node) node.dataset.available = String(available);
  });
  text(
    elements.physicsLaneState,
    physicsAvailable ? "Action-frozen MuJoCo" : "Receipt-bound trace missing",
  );

}

function updateVisualTwinSeam() {
  const reveal = Math.max(8, Math.min(92, Number(state.visualTwinReveal) || 50));
  const stagePercentage = state.replayMode === "compare"
    ? reveal / 2
    : reveal;
  elements.stage.style.setProperty("--visual-reveal", `${reveal}%`);
  elements.visualTwinSeam.style.left = `${stagePercentage}%`;
  elements.visualTwinReveal.value = String(reveal);
}

function setVisualTwinMode(mode, { updateReplay = true } = {}) {
  const next = ["real", "split", "twin"].includes(mode) ? mode : "split";
  state.visualTwinMode = next;
  elements.stage.dataset.visualMode = next;
  elements.visualTwinToolbar.querySelectorAll("[data-visual-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.visualMode === next));
  });
  elements.visualTwinReveal.disabled = next !== "split";
  updateVisualTwinSeam();
  if (updateReplay && state.replayMode !== "compare") {
    setReplayMode(next === "real" ? "recorded" : "visual");
  }
  drawVisualTwinFrame();
}

function drawVisualTwinFrame() {
  const episode = selectedEpisode();
  const canvas = elements.visualTwinCanvas;
  const video = elements.video;
  if (
    !hasVisualTwin(episode)
    || !video.videoWidth
    || !video.videoHeight
    || !["visual", "compare"].includes(state.replayMode)
  ) return;

  const visibleWidth = Math.max(1, canvas.clientWidth || elements.stage.clientWidth);
  const visibleHeight = Math.max(1, canvas.clientHeight || elements.stage.clientHeight);
  const renderWidth = Math.max(240, Math.min(480, Math.round(visibleWidth)));
  const renderHeight = Math.max(135, Math.min(320, Math.round(renderWidth * visibleHeight / visibleWidth)));
  if (canvas.width !== renderWidth || canvas.height !== renderHeight) {
    canvas.width = renderWidth;
    canvas.height = renderHeight;
  }
  if (!state.visualTwinOffscreen) state.visualTwinOffscreen = document.createElement("canvas");
  const offscreen = state.visualTwinOffscreen;
  offscreen.width = renderWidth;
  offscreen.height = renderHeight;
  const context = canvas.getContext("2d", { alpha: false });
  const sourceContext = offscreen.getContext("2d", { willReadFrequently: true });
  const sourceAspect = video.videoWidth / video.videoHeight;
  const targetAspect = renderWidth / renderHeight;
  let sourceX = 0;
  let sourceY = 0;
  let sourceWidth = video.videoWidth;
  let sourceHeight = video.videoHeight;
  if (sourceAspect > targetAspect) {
    sourceWidth = video.videoHeight * targetAspect;
    sourceX = (video.videoWidth - sourceWidth) / 2;
  } else {
    sourceHeight = video.videoWidth / targetAspect;
    sourceY = (video.videoHeight - sourceHeight) / 2;
  }

  try {
    const rotation = Number(
      activeRecordingFeed(episode)?.display_rotation_degrees
      ?? episode.media?.display_rotation_degrees
      ?? 0,
    );
    sourceContext.save();
    sourceContext.clearRect(0, 0, renderWidth, renderHeight);
    sourceContext.translate(renderWidth / 2, renderHeight / 2);
    sourceContext.rotate(rotation * Math.PI / 180);
    sourceContext.drawImage(
      video,
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight,
      -renderWidth / 2,
      -renderHeight / 2,
      renderWidth,
      renderHeight,
    );
    sourceContext.restore();
    const image = sourceContext.getImageData(0, 0, renderWidth, renderHeight);
    const pixels = image.data;
    const original = new Uint8ClampedArray(pixels);
    const quantize = (value) => Math.max(0, Math.min(255, Math.round(value / 28) * 28));
    for (let y = 0; y < renderHeight; y += 1) {
      for (let x = 0; x < renderWidth; x += 1) {
        const index = (y * renderWidth + x) * 4;
        const leftIndex = (y * renderWidth + Math.max(0, x - 1)) * 4;
        const upperIndex = (Math.max(0, y - 1) * renderWidth + x) * 4;
        const luminance = original[index] * 0.299 + original[index + 1] * 0.587 + original[index + 2] * 0.114;
        const leftLuminance = original[leftIndex] * 0.299 + original[leftIndex + 1] * 0.587 + original[leftIndex + 2] * 0.114;
        const upperLuminance = original[upperIndex] * 0.299 + original[upperIndex + 1] * 0.587 + original[upperIndex + 2] * 0.114;
        const edge = Math.abs(luminance - leftLuminance) + Math.abs(luminance - upperLuminance);
        if (edge > 45) {
          pixels[index] = 13;
          pixels[index + 1] = 33;
          pixels[index + 2] = 37;
        } else {
          pixels[index] = quantize(original[index] * 0.92 + 12);
          pixels[index + 1] = quantize(original[index + 1] * 1.02 + 8);
          pixels[index + 2] = quantize(original[index + 2] * 1.08 + 10);
        }
      }
    }
    context.putImageData(image, 0, 0);
    context.save();
    context.strokeStyle = "rgba(139, 227, 220, 0.18)";
    context.lineWidth = 1;
    for (let x = 0; x < renderWidth; x += 48) {
      context.beginPath();
      context.moveTo(x + 0.5, 0);
      context.lineTo(x + 0.5, renderHeight);
      context.stroke();
    }
    for (let y = 0; y < renderHeight; y += 48) {
      context.beginPath();
      context.moveTo(0, y + 0.5);
      context.lineTo(renderWidth, y + 0.5);
      context.stroke();
    }
    context.restore();
  } catch (_error) {
    text(elements.cameraName, "VISUAL TWIN / FRAME UNAVAILABLE");
  }
}

function stopVisualTwinLoop() {
  if (state.visualTwinAnimation !== null) {
    window.cancelAnimationFrame(state.visualTwinAnimation);
  }
  state.visualTwinAnimation = null;
  state.visualTwinLastDraw = 0;
}

function startVisualTwinLoop() {
  stopVisualTwinLoop();
  const tick = (timestamp) => {
    if (
      !["visual", "compare"].includes(state.replayMode)
      || elements.video.paused
    ) {
      state.visualTwinAnimation = null;
      drawVisualTwinFrame();
      return;
    }
    if (timestamp - state.visualTwinLastDraw >= 66) {
      state.visualTwinLastDraw = timestamp;
      drawVisualTwinFrame();
    }
    state.visualTwinAnimation = window.requestAnimationFrame(tick);
  };
  state.visualTwinAnimation = window.requestAnimationFrame(tick);
}

function selectEpisode(identifier, { updateRoute = true } = {}) {
  if (!identifier) return;
  const episode = episodeById(identifier);
  if (!episode) return;
  state.selectedEpisodeId = identifier;
  state.threeLoadId += 1;
  state.threeViewer?.pause();
  stopVisualTwinLoop();
  stopFramePlayback();
  elements.video.pause();
  elements.video.removeAttribute("src");
  elements.video.load();
  elements.previewVideo.removeAttribute("src");
  elements.previewVideo.load();
  elements.frame.removeAttribute("src");
  elements.previewFrame.removeAttribute("src");
  elements.stage.classList.remove("has-video", "has-frames", "has-three");
  elements.stage.dataset.replayMode = "recorded";
  elements.replayModeSwitch.hidden = true;
  elements.recordingFeedSwitch.hidden = true;
  elements.recordingFeedSwitch.replaceChildren();
  elements.preview.className = "timeline-preview";
  elements.preview.hidden = true;
  elements.scrubber.value = "0";
  state.frameIndex = 0;
  state.visualTwinMode = "split";
  state.visualTwinReveal = 50;
  state.recordingFeedIndex = 0;
  state.recordingWindow = null;
  state.frameCache.clear();
  updateProgress(0, 0);

  const neutralMetrics = episode.metrics.filter((metric) => !metric.tone || metric.tone === "neutral");
  const inlineFacts = neutralMetrics.slice(0, 2).map((metric) => `${metric.label} ${formatMetric(metric)}`);
  if (episode.inspection?.fps) inlineFacts.push(`${episode.inspection.fps} Hz state trace`);
  else if (episode.fps) inlineFacts.push(`${episode.fps} fps`);
  text(elements.stageKicker, [episode.proof_label, ...inlineFacts].join(" · "));
  text(elements.stageTitle, episodeDisplayTitle(episode));
  text(elements.stageSubtitle, episode.subtitle);
  text(elements.cameraSourceLabel, "RECORDED VIEW");
  text(elements.cameraName, `${formatIdentifier(episode.camera || "workcell")} / SOURCE`);
  elements.stageVerdict.className = `stage-verdict ${episode.status}`;
  text(elements.stageVerdict, episode.status === "passed" ? "Evaluator pass" : episode.status);
  drawPhasePortrait(elements.stagePortrait, episode, { stage: true });
  renderComparisonAvailability(episode);
  setVisualTwinMode("split", { updateReplay: false });

  if (episode.media.kind === "video") {
    elements.stage.classList.add("has-video");
    elements.preview.classList.add("has-video");
    renderRecordingFeedSwitch(episode);
    loadRecordingFeed(episode, 0);
  } else if (episode.media.kind === "frames" && episode.media.urls.length) {
    elements.frame.src = episode.media.urls[0];
    elements.previewFrame.src = episode.media.urls[0];
    elements.stage.classList.add("has-frames");
    elements.preview.classList.add("has-frame");
    preloadFrameWindow(episode, 0);
  }

  if (episode.inspection?.kind === "threejs_state_trace") {
    elements.stage.classList.add("has-three");
    loadThreeEpisode(episode, state.threeLoadId);
  }
  const hasRecordedMedia = ["video", "frames"].includes(episode.media.kind);
  elements.replayModeSwitch.hidden = !(
    episodeComparison(episode)
    || (hasRecordedMedia && episode.inspection)
  );
  if (episodeComparison(episode)) {
    setReplayMode("compare", { pauseCurrent: false });
  } else if (episode.inspection?.kind === "threejs_state_trace") {
    setReplayMode("three", { pauseCurrent: false });
  } else {
    setReplayMode("recorded", { pauseCurrent: false });
  }

  updateTransportSemantics(episode);
  renderMetrics(episode);
  renderPhases(episode.phases || []);
  renderTimelineTicks(episode);
  renderEvidence(episode);
  void loadTwinFidelity(episode);
  updateSelectedCardState();
  if (updateRoute) history.replaceState(null, "", `#/episodes/${encodeURIComponent(identifier)}`);
}

function episodeRecordingFeeds(episode) {
  if (episode?.recording_feeds?.length) return episode.recording_feeds;
  if (episode?.media?.kind === "video" && episode.media.url) {
    return [{
      id: "recorded-source",
      title: "Recorded",
      camera: episode.camera || "workcell",
      url: episode.media.url,
      window_start_seconds: episode.media.window_start_seconds,
      window_end_seconds: episode.media.window_end_seconds,
      display_rotation_degrees: episode.media.display_rotation_degrees,
    }];
  }
  return [];
}

function activeRecordingFeed(episode = selectedEpisode()) {
  const feeds = episodeRecordingFeeds(episode);
  return feeds[Math.min(state.recordingFeedIndex, Math.max(0, feeds.length - 1))] || null;
}

function feedWindow(feed, mediaDuration = 0) {
  const start = Math.max(0, Number(feed?.window_start_seconds || 0));
  const requestedEnd = Number(feed?.window_end_seconds || 0);
  const end = requestedEnd > start
    ? Math.min(requestedEnd, mediaDuration > 0 ? mediaDuration : requestedEnd)
    : mediaDuration;
  return { start, end: Math.max(start, end || start), duration: Math.max(0, (end || start) - start) };
}

function recordingDuration(episode = selectedEpisode()) {
  if (state.recordingWindow?.duration > 0) return state.recordingWindow.duration;
  const feed = activeRecordingFeed(episode);
  const start = Number(feed?.window_start_seconds || 0);
  const end = Number(feed?.window_end_seconds || 0);
  if (end > start) return end - start;
  return Number(elements.video.duration || episode?.duration_seconds || 0);
}

function renderRecordingFeedSwitch(episode) {
  const feeds = episodeRecordingFeeds(episode);
  elements.recordingFeedSwitch.replaceChildren();
  elements.recordingFeedSwitch.hidden = feeds.length <= 1;
  feeds.forEach((feed, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.feedIndex = String(index);
    button.setAttribute("aria-pressed", String(index === state.recordingFeedIndex));
    text(button, feed.title || `Feed ${index + 1}`);
    button.addEventListener("click", () => {
      if (episode.inspection) setReplayMode("recorded");
      loadRecordingFeed(episode, index);
    });
    elements.recordingFeedSwitch.append(button);
  });
}

function loadRecordingFeed(episode, index) {
  const feeds = episodeRecordingFeeds(episode);
  const feed = feeds[index];
  if (!feed?.url) return;
  state.recordingFeedIndex = index;
  state.recordingWindow = null;
  elements.video.pause();
  elements.video.src = feed.url;
  elements.video.playbackRate = state.playbackRate;
  elements.previewVideo.src = feed.url;
  const rotation = Number(
    feed.display_rotation_degrees
    ?? episode.media?.display_rotation_degrees
    ?? 0,
  );
  elements.video.style.rotate = `${rotation}deg`;
  elements.previewVideo.style.rotate = `${rotation}deg`;
  elements.video.load();
  elements.previewVideo.load();
  elements.recordingFeedSwitch.querySelectorAll("[data-feed-index]").forEach((button) => {
    button.setAttribute("aria-pressed", String(Number(button.dataset.feedIndex) === index));
  });
  if (state.replayMode === "recorded") {
    text(elements.cameraSourceLabel, feed.kind === "physical_command_replay" ? "PHYSICAL REPLAY" : "RECORDED VIEW");
    text(elements.cameraName, `${formatIdentifier(feed.camera || episode.camera || "workcell")} / ${formatIdentifier(feed.title || "source")}`);
  }
  updateProgress(0, 0);
  renderTimelineTicks(episode);
}

function whenThreeReady() {
  if (window.Sim2Claw3D) return Promise.resolve(window.Sim2Claw3D);
  return new Promise((resolve) => {
    window.addEventListener("sim2claw-3d-ready", () => resolve(window.Sim2Claw3D), { once: true });
  });
}

async function ensureThreeViewer() {
  if (state.threeViewer) return state.threeViewer;
  const { ThreeReplayViewer } = await whenThreeReady();
  const viewer = new ThreeReplayViewer({
    canvas: elements.threeCanvas,
    status: elements.threeStatus,
  });
  viewer.onTime = ({ fraction, current }) => {
    if (state.replayMode === "three") updateProgress(fraction, current);
  };
  viewer.onPlayState = (playing) => {
    if (state.replayMode !== "three") return;
    elements.play.classList.toggle("is-playing", playing);
    elements.play.setAttribute("aria-label", playing ? "Pause episode" : "Play episode");
  };
  viewer.setRate(state.playbackRate);
  viewer.setActive(state.view === "replay" && state.replayMode === "three");
  state.threeViewer = viewer;
  return viewer;
}

async function ensureLiveSimulationViewer() {
  if (state.liveSimViewer) return state.liveSimViewer;
  if (state.liveSimViewerPromise) return state.liveSimViewerPromise;
  state.liveSimViewerPromise = (async () => {
    const { ThreeReplayViewer } = await whenThreeReady();
    const viewer = new ThreeReplayViewer({
      canvas: elements.liveSimulationCanvas,
      status: elements.liveSimulationStatus,
    });
    viewer.setActive(
      state.view === "record" && selectedRecorderMode() === "simulation_follower",
    );
    state.liveSimViewer = viewer;
    return viewer;
  })();
  try {
    return await state.liveSimViewerPromise;
  } finally {
    state.liveSimViewerPromise = null;
  }
}

async function refreshLiveSimulation() {
  if (
    state.readOnly !== false
    ||
    state.liveSimFetchActive
    || state.view !== "record"
    || selectedRecorderMode() !== "simulation_follower"
  ) return;
  state.liveSimFetchActive = true;
  try {
    const response = await fetch("/api/recorder/live-simulation", { cache: "no-store" });
    if (!response.ok) throw new Error(`live simulator returned ${response.status}`);
    const liveState = await response.json();
    const viewer = await ensureLiveSimulationViewer();
    await viewer.loadLive(liveState);
    viewer.applyLiveState(liveState);
    const active = Boolean(liveState.active);
    elements.liveSimulationBadge.dataset.active = String(active);
    text(
      elements.liveSimulationBadge,
      active ? "Live" : liveState.frame ? "Last state" : "Ready",
    );
  } catch (error) {
    text(
      elements.liveSimulationStatus,
      `Live simulator unavailable · ${error.message || String(error)}`,
    );
    elements.liveSimulationBadge.dataset.active = "false";
    text(elements.liveSimulationBadge, "Offline");
  } finally {
    state.liveSimFetchActive = false;
  }
}

function liveCameraRows(live = state.liveWorkspace) {
  return live?.cameras?.cameras || [];
}

function renderLiveWorkspace(live = state.liveWorkspace) {
  const arm = live?.arm || {};
  const status = arm.status || "checking";
  const title = {
    live: "Physical arm live",
    connected: "Physical arm ready",
    error: "Arm connection error",
    offline: "Physical arm offline",
    checking: "Checking arm",
  }[status] || "Arm unavailable";
  let detail = "No motor bus has been opened.";
  if (status === "live") {
    detail = `${arm.follower_port || "Follower bus"} · ${arm.physical_follower_torque_enabled ? "torque enabled by recorder" : "torque off / read only"}`;
  } else if (status === "connected") {
    detail = "Detected and calibrated · open Live to read the torque-off pose.";
  } else if (status === "error") {
    detail = arm.error || "The read-only gateway could not sample the arm.";
  } else if (status === "offline") {
    detail = "Both SO-101 buses and matching calibrations are required.";
  }

  elements.liveArmState.dataset.status = status;
  text(elements.liveArmTitle, title);
  text(elements.liveArmDetail, detail);
  elements.liveTrigger.classList.toggle("has-live", status === "live");
  text(elements.liveCount, status === "live" ? "Arm live" : status === "connected" ? "Arm ready" : status === "checking" ? "Checking arm" : "Arm offline");

  const cameras = liveCameraRows(live);
  const available = cameras.filter((camera) => camera.available).length;
  text(elements.liveCameraCount, cameras.length ? `${available}/${cameras.length} cameras ready` : "Checking cameras");
  cameras.forEach((camera) => {
    const card = document.querySelector(`.live-camera-card[data-camera-id="${camera.id}"]`);
    if (!card) return;
    card.dataset.available = String(Boolean(camera.available));
    text(card.querySelector("figcaption b"), camera.label);
    text(card.querySelector("figcaption small"), camera.device_name || camera.detail);
    const badge = card.querySelector("figcaption em");
    if (!card.classList.contains("is-streaming")) {
      text(badge, camera.available ? "Ready" : "Offline");
    }
    const placeholder = card.querySelector(".live-camera-frame > span");
    if (!camera.available) text(placeholder, camera.error || "Camera unavailable");
    else if (!card.classList.contains("is-streaming")) text(placeholder, "Waiting for stream");
  });

  const names = arm.joint_names || [];
  const positions = arm.follower_degrees || [];
  elements.liveJointReadout.replaceChildren();
  names.forEach((name, index) => {
    const wrapper = document.createElement("span");
    const label = document.createElement("small");
    const value = document.createElement("b");
    text(label, formatIdentifier(name));
    text(value, Number.isFinite(Number(positions[index])) ? `${Number(positions[index]).toFixed(1)}°` : "—");
    wrapper.append(label, value);
    elements.liveJointReadout.append(wrapper);
  });
}

async function ensureLiveWorkspaceViewer() {
  if (state.liveWorkspaceViewer) return state.liveWorkspaceViewer;
  if (state.liveWorkspaceViewerPromise) return state.liveWorkspaceViewerPromise;
  state.liveWorkspaceViewerPromise = (async () => {
    const { ThreeReplayViewer } = await whenThreeReady();
    const viewer = new ThreeReplayViewer({
      canvas: elements.liveWorkspaceCanvas,
      status: elements.liveWorkspaceStatus,
    });
    viewer.setActive(state.drawer === "live" && state.liveWorkspaceMode === "simulator");
    state.liveWorkspaceViewer = viewer;
    return viewer;
  })();
  try {
    return await state.liveWorkspaceViewerPromise;
  } finally {
    state.liveWorkspaceViewerPromise = null;
  }
}

function stopLiveCameraStreams() {
  document.querySelectorAll(".live-camera-card").forEach((card) => {
    const image = card.querySelector("img");
    image.removeAttribute("src");
    delete image.dataset.session;
    card.classList.remove("is-streaming");
    const camera = liveCameraRows().find((row) => row.id === card.dataset.cameraId);
    text(card.querySelector("figcaption em"), camera?.available ? "Ready" : "Offline");
    text(card.querySelector(".live-camera-frame > span"), camera?.available ? "Waiting for stream" : camera?.error || "Camera unavailable");
  });
}

function startLiveCameraStreams() {
  const token = state.liveWorkspaceSession;
  if (!token || state.drawer !== "live" || state.liveWorkspaceMode !== "cameras") return;
  liveCameraRows().forEach((camera) => {
    const card = document.querySelector(`.live-camera-card[data-camera-id="${camera.id}"]`);
    if (!card) return;
    const image = card.querySelector("img");
    if (!camera.available) {
      image.removeAttribute("src");
      text(card.querySelector("figcaption em"), "Offline");
      return;
    }
    if (image.dataset.session === token && image.hasAttribute("src")) return;
    card.classList.add("is-streaming");
    text(card.querySelector("figcaption em"), "Connecting");
    text(card.querySelector(".live-camera-frame > span"), "Opening on-demand stream");
    image.dataset.session = token;
    image.src = `/api/live/cameras/${encodeURIComponent(camera.id)}.mjpeg?session=${encodeURIComponent(token)}&v=${Date.now()}`;
  });
}

function setLiveWorkspaceMode(mode) {
  const next = mode === "cameras" ? "cameras" : "simulator";
  state.liveWorkspaceMode = next;
  document.querySelectorAll("[data-live-mode]").forEach((button) => {
    button.setAttribute("aria-selected", String(button.dataset.liveMode === next));
  });
  document.querySelectorAll("[data-live-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.livePanel !== next;
  });
  state.liveWorkspaceViewer?.setActive(state.drawer === "live" && next === "simulator");
  if (next === "cameras") startLiveCameraStreams();
  else {
    stopLiveCameraStreams();
    refreshLiveWorkspace({ force: true });
  }
}

async function endLiveWorkspaceToken(token, { useBeacon = false } = {}) {
  if (!token) return;
  const body = JSON.stringify({ action: "stop", session_id: token });
  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon("/api/live/session", new Blob([body], { type: "application/json" }));
    return;
  }
  try {
    await fetch("/api/live/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    });
  } catch (_error) {
    // The server lease is also self-expiring; closing the UI remains immediate.
  }
}

function stopLiveWorkspace({ useBeacon = false } = {}) {
  state.liveWorkspaceGeneration += 1;
  const token = state.liveWorkspaceSession;
  state.liveWorkspaceSession = null;
  state.liveWorkspaceFetchActive = false;
  stopLiveCameraStreams();
  state.liveWorkspaceViewer?.setActive(false);
  if (state.liveWorkspace?.arm) {
    state.liveWorkspace.arm.fresh = false;
    state.liveWorkspace.arm.follower_degrees = null;
    state.liveWorkspace.arm.leader_degrees = null;
    state.liveWorkspace.arm.status = state.liveWorkspace.arm.connected ? "connected" : "offline";
  }
  renderLiveWorkspace();
  if (token) void endLiveWorkspaceToken(token, { useBeacon });
}

async function startLiveWorkspace() {
  if (state.liveWorkspaceSession) return;
  const generation = ++state.liveWorkspaceGeneration;
  text(elements.liveWorkspaceStatus, "Opening torque-off arm observation…");
  try {
    const response = await fetch("/api/live/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "start" }),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) throw new Error(payload.error || `live workspace returned ${response.status}`);
    const live = payload.live;
    const token = live.session_id;
    if (generation !== state.liveWorkspaceGeneration || state.drawer !== "live") {
      void endLiveWorkspaceToken(token);
      return;
    }
    state.liveWorkspace = live;
    state.liveWorkspaceSession = token;
    state.liveWorkspaceLastFetchAt = 0;
    renderLiveWorkspace(live);
    setLiveWorkspaceMode(state.liveWorkspaceMode);
    await refreshLiveWorkspace({ force: true });
  } catch (error) {
    if (generation !== state.liveWorkspaceGeneration) return;
    text(elements.liveWorkspaceStatus, `Live workspace unavailable · ${error.message || String(error)}`);
  }
}

async function fetchLiveWorkspaceStatus() {
  if (state.readOnly !== false || state.liveWorkspaceStatusFetchActive || state.drawer === "live" || state.liveWorkspaceSession) return;
  state.liveWorkspaceStatusFetchActive = true;
  try {
    const response = await fetch("/api/live/status", { cache: "no-store" });
    if (!response.ok) throw new Error(`live status returned ${response.status}`);
    state.liveWorkspace = await response.json();
    renderLiveWorkspace();
  } catch (_error) {
    state.liveWorkspace = {
      arm: { status: "offline", connected: false },
      cameras: { cameras: [] },
    };
    renderLiveWorkspace();
  } finally {
    state.liveWorkspaceStatusFetchActive = false;
  }
}

async function refreshLiveWorkspace({ force = false } = {}) {
  const token = state.liveWorkspaceSession;
  if (!token || state.drawer !== "live" || state.liveWorkspaceFetchActive) return;
  const now = performance.now();
  const minimumInterval = state.liveWorkspaceMode === "simulator" ? 125 : 1000;
  if (!force && now - state.liveWorkspaceLastFetchAt < minimumInterval) return;
  state.liveWorkspaceLastFetchAt = now;
  state.liveWorkspaceFetchActive = true;
  try {
    const response = await fetch(`/api/live/state?session=${encodeURIComponent(token)}`, { cache: "no-store" });
    const live = await response.json();
    if (!response.ok) throw new Error(live.error || `live state returned ${response.status}`);
    if (token !== state.liveWorkspaceSession || state.drawer !== "live") return;
    state.liveWorkspace = live;
    renderLiveWorkspace(live);
    if (state.liveWorkspaceMode === "simulator") {
      if (live.simulator) {
        const viewer = await ensureLiveWorkspaceViewer();
        viewer.setActive(true);
        await viewer.loadLive(live.simulator);
        viewer.applyLiveState(live.simulator);
      } else {
        text(elements.liveWorkspaceStatus, live.arm?.error || "Connected arm has no fresh joint observation.");
      }
    }
  } catch (error) {
    if (token !== state.liveWorkspaceSession) return;
    text(elements.liveWorkspaceStatus, `Live observation paused · ${error.message || String(error)}`);
    stopLiveWorkspace();
  } finally {
    state.liveWorkspaceFetchActive = false;
  }
}

async function loadThreeEpisode(episode, loadId) {
  try {
    const viewer = await ensureThreeViewer();
    if (loadId !== state.threeLoadId || episode.id !== state.selectedEpisodeId) return;
    await viewer.load(episode.inspection);
    if (loadId !== state.threeLoadId || episode.id !== state.selectedEpisodeId) return;
    viewer.setRate(state.playbackRate);
    if (state.replayMode === "three") updateProgress(0, 0);
  } catch (error) {
    if (loadId !== state.threeLoadId) return;
    text(elements.threeStatus, `3D inspection unavailable · ${error.message}`);
  }
}

function setReplayMode(mode, { pauseCurrent = true } = {}) {
  const episode = selectedEpisode();
  const comparison = episodeComparison(episode);
  const next = (
    mode === "compare" && comparison
      ? "compare"
      : mode === "visual" && hasVisualTwin(episode)
      ? "visual"
      : mode === "three" && episode?.inspection
      ? "three"
      : "recorded"
  );
  if (pauseCurrent) {
    state.threeViewer?.pause();
    elements.video.pause();
    stopFramePlayback();
    stopVisualTwinLoop();
  }
  state.replayMode = next;
  elements.stage.dataset.replayMode = next;
  if (next === "recorded" && hasVisualTwin(episode)) {
    setVisualTwinMode("real", { updateReplay: false });
  } else if (next === "visual" && state.visualTwinMode === "real") {
    setVisualTwinMode("twin", { updateReplay: false });
  }
  const physicsAvailable = Boolean(
    episode?.inspection && (!comparison || comparison.physics_replay?.available),
  );
  elements.stage.dataset.physicsAvailable = String(physicsAvailable);
  state.threeViewer?.setActive(
    state.view === "replay"
    && physicsAvailable
    && ["three", "compare"].includes(next),
  );
  elements.replayModeSwitch.querySelectorAll("[data-replay-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.replayMode === next));
  });
  elements.visualTwinToolbar.hidden = !hasVisualTwin(episode) || next === "three";
  elements.comparisonRealLabel.hidden = next !== "compare";
  elements.comparisonPhysicsLabel.hidden = next !== "compare";
  elements.physicsUnavailable.hidden = !(
    next === "compare" && !physicsAvailable
  );
  if (next === "three") {
    text(elements.cameraSourceLabel, "PHYSICS TRACE");
    text(elements.cameraName, "MUJOCO / FREE ORBIT");
  } else if (next === "visual") {
    text(elements.cameraSourceLabel, "VISUAL TWIN");
    text(elements.cameraName, "SAME CAMERA / IMAGE SPACE / NO PHYSICS");
    drawVisualTwinFrame();
  } else if (next === "compare") {
    text(elements.cameraSourceLabel, "SYNCED COMPARE");
    text(
      elements.cameraName,
      physicsAvailable
        ? "REAL + VISUAL TWIN / ACTION-FROZEN MUJOCO"
        : "REAL + VISUAL TWIN / PHYSICS TRACE MISSING",
    );
    const windowRange = state.recordingWindow
      || feedWindow(activeRecordingFeed(episode), elements.video.duration || 0);
    const fraction = windowRange.duration > 0
      ? Math.max(0, Math.min(1, (elements.video.currentTime - windowRange.start) / windowRange.duration))
      : 0;
    if (physicsAvailable) state.threeViewer?.setFraction(fraction);
    drawVisualTwinFrame();
  } else if (episode) {
    const feed = activeRecordingFeed(episode);
    text(elements.cameraSourceLabel, feed?.kind === "physical_command_replay" ? "PHYSICAL REPLAY" : "RECORDED VIEW");
    text(elements.cameraName, `${formatIdentifier(feed?.camera || episode.camera || "workcell")} / ${formatIdentifier(feed?.title || "source")}`);
  }
  if (episode) {
    updateTransportSemantics(episode);
    renderTimelineTicks(episode);
  }
  updateVisualTwinSeam();
}

function updateTransportSemantics(episode) {
  const three = state.replayMode === "three" && episode.inspection;
  const frames = !three && episode.media.kind === "frames";
  text(elements.jumpBack, three ? "−1 state" : frames ? "−1 frame" : "−5 sec");
  text(elements.jumpForward, three ? "+1 state" : frames ? "+1 frame" : "+5 sec");
  elements.jumpBack.setAttribute("aria-label", three ? "Go back one physics state" : frames ? "Go back one frame" : "Go back five seconds");
  elements.jumpForward.setAttribute("aria-label", three ? "Go forward one physics state" : frames ? "Go forward one frame" : "Go forward five seconds");
}

function renderMetrics(episode) {
  const performance = episode.metrics.filter((metric) => metric.tone && metric.tone !== "neutral");
  const rows = performance.length ? performance : episode.metrics;
  const visible = rows.slice(0, 4);
  elements.metrics.replaceChildren();
  elements.metrics.style.setProperty("--metric-count", String(Math.max(1, visible.length)));
  visible.forEach((metric) => {
    const wrapper = document.createElement("div");
    wrapper.className = `metric ${metric.tone || "neutral"}`;
    const label = document.createElement("span");
    const value = document.createElement("b");
    text(label, metric.label);
    text(value, metric.value);
    if (metric.unit) {
      const unit = document.createElement("small");
      text(unit, metric.unit);
      value.append(unit);
    }
    wrapper.append(label, value);
    elements.metrics.append(wrapper);
  });
}

function renderPhases(phases) {
  elements.phaseRail.replaceChildren();
  const rows = phases.length ? phases : [{ name: "Replay", start: 0, end: 1 }];
  text(elements.transportPhase, rows[0].name);
  rows.forEach((phase) => {
    const segment = document.createElement("button");
    segment.type = "button";
    segment.className = "phase-segment";
    segment.dataset.start = String(phase.start);
    segment.dataset.end = String(phase.end);
    segment.style.flexGrow = String(Math.max(0.001, phase.end - phase.start));
    const label = document.createElement("span");
    text(label, phase.name);
    label.dataset.short = shortPhaseLabel(phase.name);
    segment.append(label);
    segment.setAttribute("aria-label", `Seek to ${phase.name}`);
    segment.addEventListener("click", () => seekFraction(Number(phase.start)));
    elements.phaseRail.append(segment);
  });
}

function renderTimelineTicks(episode) {
  elements.timelineTicks.replaceChildren();
  const three = state.replayMode === "three" && episode.inspection;
  const duration = three
    ? episode.inspection.duration_seconds
    : episode.media.kind === "frames"
    ? episode.media.urls.length
    : recordingDuration(episode);
  const count = 6;
  for (let index = 0; index < count; index += 1) {
    const tick = document.createElement("i");
    tick.className = "timeline-tick";
    const label = document.createElement("span");
    const value = duration * index / (count - 1);
    text(label, !three && episode.media.kind === "frames" ? `${Math.round(value)}f` : `${Math.round(value)}s`);
    tick.append(label);
    elements.timelineTicks.append(tick);
  }
}

function updateSelectedCardState() {
  document.querySelectorAll("[data-episode-id]").forEach((card) => {
    card.classList.toggle("is-active", card.dataset.episodeId === state.selectedEpisodeId);
  });
}

function togglePlayback() {
  const episode = selectedEpisode();
  if (!episode) return;
  if (state.replayMode === "three" && episode.inspection) {
    state.threeViewer?.toggle();
  } else if (episode.media.kind === "video") {
    if (elements.video.paused) {
      const windowRange = state.recordingWindow || feedWindow(activeRecordingFeed(episode), elements.video.duration || 0);
      if (windowRange.duration > 0 && elements.video.currentTime >= windowRange.end - 0.05) {
        elements.video.currentTime = windowRange.start;
      }
      elements.video.play().catch(() => {});
    }
    else elements.video.pause();
  } else if (episode.media.kind === "frames") {
    if (state.framePlaying) stopFramePlayback();
    else startFramePlayback();
  }
}

function startFramePlayback() {
  const episode = selectedEpisode();
  if (!episode || episode.media.kind !== "frames") return;
  stopFramePlayback();
  if (state.frameIndex >= episode.media.urls.length - 1) showFrame(episode, 0);
  state.framePlaying = true;
  state.frameLastTimestamp = null;
  elements.play.classList.add("is-playing");
  elements.play.setAttribute("aria-label", "Pause episode");

  const tick = (timestamp) => {
    if (!state.framePlaying) return;
    if (state.frameLastTimestamp == null) state.frameLastTimestamp = timestamp;
    const fps = Math.max(0.25, Number(episode.media.fps || episode.fps || 1) * state.playbackRate);
    const elapsed = (timestamp - state.frameLastTimestamp) / 1000;
    const advance = Math.floor(elapsed * fps);
    if (advance > 0) {
      state.frameLastTimestamp += advance / fps * 1000;
      const next = Math.min(episode.media.urls.length - 1, state.frameIndex + advance);
      showFrame(episode, next);
      if (next >= episode.media.urls.length - 1) {
        stopFramePlayback();
        return;
      }
    }
    state.frameAnimation = window.requestAnimationFrame(tick);
  };
  state.frameAnimation = window.requestAnimationFrame(tick);
}

function stopFramePlayback() {
  if (state.frameAnimation) window.cancelAnimationFrame(state.frameAnimation);
  state.frameAnimation = null;
  state.frameLastTimestamp = null;
  state.framePlaying = false;
  elements.play.classList.remove("is-playing");
  elements.play.setAttribute("aria-label", "Play episode");
}

function preloadFrameWindow(episode, center) {
  if (episode.media.kind !== "frames") return;
  const start = Math.max(0, center - 30);
  const end = Math.min(episode.media.urls.length - 1, center + 30);
  for (let index = start; index <= end; index += 1) {
    if (state.frameCache.has(index)) continue;
    const image = new Image();
    image.src = episode.media.urls[index];
    state.frameCache.set(index, image);
  }
}

function showFrame(episode, index) {
  state.frameIndex = Math.max(0, Math.min(episode.media.urls.length - 1, index));
  const cached = state.frameCache.get(state.frameIndex);
  elements.frame.src = cached?.src || episode.media.urls[state.frameIndex];
  preloadFrameWindow(episode, state.frameIndex);
  const fraction = episode.media.urls.length > 1 ? state.frameIndex / (episode.media.urls.length - 1) : 0;
  const seconds = state.frameIndex / Number(episode.media.fps || episode.fps || 1);
  updateProgress(fraction, seconds);
}

function updateProgress(fraction, seconds) {
  const safeFraction = Number.isFinite(fraction) ? Math.max(0, Math.min(1, fraction)) : 0;
  elements.scrubber.value = String(Math.round(safeFraction * 1000));
  elements.scanHead.style.left = `${safeFraction * 100}%`;
  elements.timelineHead.style.left = `${safeFraction * 100}%`;
  elements.stageProgress.style.width = `${safeFraction * 100}%`;
  text(elements.timecode, formatTime(seconds));
  document.querySelectorAll(".phase-segment").forEach((segment) => {
    const start = Number(segment.dataset.start);
    const end = Number(segment.dataset.end);
    const active = safeFraction >= start && (safeFraction < end || end === 1 && safeFraction === 1);
    segment.classList.toggle("is-active", active);
    if (active) text(elements.transportPhase, segment.textContent.trim());
  });
}

function stepFrames(delta) {
  const episode = selectedEpisode();
  if (!episode) return;
  if (state.replayMode === "three" && episode.inspection) {
    state.threeViewer?.step(delta);
    return;
  }
  if (episode.media.kind !== "frames") return;
  showFrame(episode, state.frameIndex + delta);
}

function jumpSeconds(delta) {
  const episode = selectedEpisode();
  if (!episode) return;
  if (state.replayMode === "three" && episode.inspection) {
    if (state.threeViewer) state.threeViewer.applyTime(state.threeViewer.currentTime + delta);
  } else if (episode.media.kind === "video") {
    const windowRange = state.recordingWindow || feedWindow(activeRecordingFeed(episode), elements.video.duration || 0);
    elements.video.currentTime = Math.max(windowRange.start, Math.min(windowRange.end, elements.video.currentTime + delta));
  } else {
    const fps = Number(episode.media.fps || episode.fps || 1);
    stepFrames(Math.round(delta * fps));
  }
}

function performPrimaryStep(direction) {
  const episode = selectedEpisode();
  if (!episode) return;
  if (state.replayMode === "three" && episode.inspection) state.threeViewer?.step(direction);
  else if (episode.media.kind === "frames") stepFrames(direction);
  else jumpSeconds(direction * 5);
}

function seekFraction(fraction) {
  const episode = selectedEpisode();
  if (!episode) return;
  const safe = Math.max(0, Math.min(1, fraction));
  if (state.replayMode === "three" && episode.inspection) {
    state.threeViewer?.setFraction(safe);
  } else if (episode.media.kind === "video") {
    if (Number.isFinite(elements.video.duration)) {
      const windowRange = state.recordingWindow || feedWindow(activeRecordingFeed(episode), elements.video.duration);
      elements.video.currentTime = windowRange.start + safe * windowRange.duration;
      if (state.replayMode === "compare" && episode.inspection) {
        state.threeViewer?.setFraction(safe);
      }
      drawVisualTwinFrame();
    }
  } else {
    showFrame(episode, Math.round(safe * (episode.media.urls.length - 1)));
  }
}

function cycleSpeed() {
  const rates = [0.5, 1, 2];
  state.playbackRate = rates[(rates.indexOf(state.playbackRate) + 1) % rates.length];
  elements.video.playbackRate = state.playbackRate;
  state.threeViewer?.setRate(state.playbackRate);
  text(elements.speed, `${state.playbackRate}×`);
  if (state.framePlaying) startFramePlayback();
}

function updateTimelinePreview(event) {
  const episode = selectedEpisode();
  if (!episode || window.matchMedia("(hover: none)").matches) return;
  if (state.replayMode === "three" || episode.media.kind === "none") {
    elements.preview.hidden = true;
    return;
  }
  const bounds = elements.timeline.getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
  elements.preview.hidden = false;
  elements.preview.style.left = `${Math.max(12, Math.min(88, fraction * 100))}%`;
  if (episode.media.kind === "video") {
    const windowRange = state.recordingWindow || feedWindow(activeRecordingFeed(episode), elements.previewVideo.duration || elements.video.duration);
    const duration = windowRange.duration;
    if (Number.isFinite(duration) && duration > 0) {
      const target = windowRange.start + fraction * duration;
      if (Math.abs(elements.previewVideo.currentTime - target) > 0.12) elements.previewVideo.currentTime = target;
      text(elements.previewTimecode, formatTime(target - windowRange.start));
    }
  } else {
    const index = Math.round(fraction * (episode.media.urls.length - 1));
    elements.previewFrame.src = state.frameCache.get(index)?.src || episode.media.urls[index];
    text(elements.previewTimecode, `${index + 1} / ${episode.media.urls.length}`);
  }
}

function renderEvidence(episode) {
  if (!episode) return;
  elements.evidenceContent.replaceChildren();
  const hero = document.createElement("div");
  hero.className = "evidence-hero";
  const label = document.createElement("span");
  label.className = "section-label";
  const heading = document.createElement("h3");
  const description = document.createElement("p");
  text(label, episode.proof_label);
  text(heading, episode.title);
  text(description, episode.subtitle);
  hero.append(label, heading, description);

  const table = document.createElement("dl");
  table.className = "evidence-table";
  const mediaFacts = [];
  if (episode.inspection) mediaFacts.push(`${episode.inspection.frame_count} MuJoCo states · interactive 3D`);
  const feedCount = episodeRecordingFeeds(episode).length;
  if (feedCount > 1) mediaFacts.push(`${feedCount} recorded camera feeds`);
  else if (episode.media.kind === "video") mediaFacts.push("Recorded video");
  else if (episode.media.kind === "frames") mediaFacts.push(`${episode.media.urls?.length || 0} rendered frames`);
  const rows = [
    [episode.evaluator_verdict ? "Evaluator result" : "Evidence status", episode.evaluator_verdict || episode.status],
    ["Terminal outcome", formatIdentifier(episode.terminal_outcome || "Not recorded")],
    ["Task", taskById(episode.task_id)?.title || episode.task_id],
    ["Case", formatIdentifier(episode.case_id || "Not recorded")],
    ["Recorded", episode.recorded_at ? new Date(episode.recorded_at).toLocaleString() : "Not recorded"],
    ["Proof class", episode.proof_class],
    ["Media", mediaFacts.join(" · ") || "No replay media"],
    ...(episode.notes ? [["Operator notes", episode.notes]] : []),
    ...episode.metrics.map((metric) => [metric.label, formatMetric(metric)]),
  ];
  rows.forEach(([term, value]) => {
    const wrapper = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    text(dt, term);
    text(dd, value);
    wrapper.append(dt, dd);
    table.append(wrapper);
  });

  const notice = document.createElement("div");
  notice.className = "authority-notice";
  const lock = document.createElement("span");
  lock.className = "lock-icon";
  lock.setAttribute("aria-hidden", "true");
  const noticeText = document.createElement("span");
  text(noticeText, state.catalog.project.proof_notice || "Visual replay is inspection evidence and does not grant robot or promotion authority.");
  notice.append(lock, noticeText);
  elements.evidenceContent.append(hero, table, notice);
}

function twinNode(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) text(node, value);
  return node;
}

function formatTwinValue(value) {
  if (typeof value !== "number") return value == null ? "Not observed" : String(value);
  if (Number.isInteger(value)) return String(value);
  return Math.abs(value) < 0.01 ? value.toFixed(4) : value.toFixed(3);
}

function renderTwinMeasurement(measurement) {
  const row = twinNode("div", `twin-measurement ${measurement.observed ? "is-observed" : "is-missing"}`);
  const label = twinNode("dt", "", measurement.label);
  const value = twinNode("dd");
  const primary = measurement.observed
    ? `${formatTwinValue(measurement.value)} ${measurement.unit || ""}`.trim()
    : "Not observed";
  const threshold = measurement.threshold == null
    ? ""
    : ` · gate ${measurement.comparator || ""} ${formatTwinValue(measurement.threshold)} ${measurement.unit || ""}`.trimEnd();
  value.append(
    twinNode("b", "", `${primary}${threshold}`),
    twinNode("small", "", measurement.source || "Source unavailable"),
  );
  row.append(label, value);
  return row;
}

function updateTwinSignal(projection) {
  const statuses = projection?.domains?.map((domain) => domain.status) || [];
  elements.twinFidelityTrigger.querySelectorAll(".twin-fidelity-signal i").forEach((bar, index) => {
    bar.className = statuses[index] ? `is-${statuses[index]}` : "";
  });
  elements.twinFidelityTrigger.dataset.status = projection?.evidence_status || "unavailable";
}

function renderTwinFidelity(projection) {
  elements.twinFidelityContent.replaceChildren();
  updateTwinSignal(projection);

  if (!projection?.available) {
    const unavailable = twinNode("section", "twin-unavailable");
    unavailable.append(
      twinNode("span", "section-label", "Evidence unavailable"),
      twinNode("h3", "", "No verified fidelity projection"),
      twinNode("p", "", projection?.detail || "This replay is not present in the receipt-bound observatory."),
    );
    elements.twinFidelityContent.append(unavailable);
    return;
  }

  const hero = twinNode("section", `twin-summary is-${projection.evidence_status}`);
  const eyebrow = twinNode("div", "twin-summary-topline");
  const actionBindingLabel = projection.episode.action_binding === "byte_identical_campaign_match"
    ? "Action bytes matched"
    : projection.episode.action_binding === "hash_bound_physical_packet"
    ? "Packet action hash bound"
    : "Replay evidence only";
  eyebrow.append(
    twinNode("span", "twin-proof", projection.episode.proof_label || projection.episode.proof_class),
    twinNode("span", "twin-binding", actionBindingLabel),
  );
  hero.append(
    eyebrow,
    twinNode("h3", "", projection.summary.label),
    twinNode("strong", "", formatIdentifier(projection.summary.verdict)),
    twinNode("p", "", projection.summary.detail),
  );

  const legend = twinNode("div", "twin-status-legend");
  [
    ["observed", "Observed"],
    ["missing", "Missing"],
    ["failed", "Failed gate"],
  ].forEach(([status, label]) => {
    const item = twinNode("span", `is-${status}`);
    item.append(twinNode("i", ""), document.createTextNode(label));
    legend.append(item);
  });

  const map = twinNode("section", "twin-gap-map");
  const mapHeader = twinNode("header", "twin-section-heading");
  const mapCopy = twinNode("div");
  mapCopy.append(
    twinNode("span", "section-label", "Twin gap map"),
    twinNode("h3", "", "Where the retained twin diverges"),
  );
  mapHeader.append(mapCopy, twinNode("small", "", "No aggregate score · evaluator-owned evidence only"));
  map.append(mapHeader, legend);
  const domains = twinNode("ol", "twin-domain-list");
  projection.domains.forEach((domain, index) => {
    const item = twinNode("li", `twin-domain is-${domain.status}`);
    const marker = twinNode("span", "twin-domain-marker", String(index + 1).padStart(2, "0"));
    const copy = twinNode("div", "twin-domain-copy");
    const header = twinNode("header");
    header.append(
      twinNode("h4", "", domain.label),
      twinNode("span", `twin-domain-status is-${domain.status}`, domain.status === "failed" ? "Failed gate" : formatIdentifier(domain.status)),
    );
    copy.append(header, twinNode("strong", "", domain.summary), twinNode("p", "", domain.detail));
    if (domain.measurements?.length) {
      const measurements = twinNode("dl", "twin-measurements");
      domain.measurements.forEach((measurement) => measurements.append(renderTwinMeasurement(measurement)));
      copy.append(measurements);
    }
    if (domain.missing_evidence?.length) {
      copy.append(twinNode("small", "twin-missing", `Missing: ${domain.missing_evidence.map(formatIdentifier).join(" · ")}`));
    }
    item.append(marker, copy);
    domains.append(item);
  });
  map.append(domains);

  const chain = twinNode("section", "twin-chain");
  const chainHeader = twinNode("header", "twin-section-heading");
  const chainCopy = twinNode("div");
  chainCopy.append(
    twinNode("span", "section-label", "SAIL causal chain"),
    twinNode("h3", "", "What happened, in evidence order"),
  );
  chainHeader.append(chainCopy);
  chain.append(chainHeader);
  const chainList = twinNode("ol");
  if (projection.chain?.length) {
    projection.chain.forEach((step) => {
      const item = twinNode("li", `is-${step.status}`);
      item.append(
        twinNode("span", "", step.label),
        twinNode("b", "", formatIdentifier(step.status)),
        twinNode("small", "", step.detail),
      );
      chainList.append(item);
    });
  } else {
    chainList.append(twinNode("li", "is-missing", "No action-matched intervention chain is available."));
  }
  chain.append(chainList);

  const lower = twinNode("div", "twin-lower-grid");
  const hypotheses = twinNode("section", "twin-hypotheses");
  hypotheses.append(
    twinNode("span", "section-label", "Active hypotheses"),
    twinNode("h3", "", projection.hypotheses?.length ? "Posterior remained accountable" : "No terminal posterior"),
  );
  if (projection.hypotheses?.length) {
    projection.hypotheses.forEach((hypothesis) => {
      const row = twinNode("div", "twin-hypothesis");
      const values = hypothesis.before == null || hypothesis.after == null
        ? "Not observed"
        : `${formatTwinValue(hypothesis.before)} → ${formatTwinValue(hypothesis.after)}`;
      row.append(
        twinNode("b", "", formatIdentifier(hypothesis.family || hypothesis.id)),
        twinNode("strong", "", values),
        twinNode("small", "", hypothesis.status === "unchanged" ? "Unchanged · no admitted evidence" : formatIdentifier(hypothesis.status)),
      );
      hypotheses.append(row);
    });
  } else {
    hypotheses.append(twinNode("p", "", "Receipt-bound residuals exist, but no action-matched terminal campaign owns a posterior."));
  }

  const next = twinNode("section", "twin-next-evidence");
  next.append(
    twinNode("span", "section-label", "Missing evidence / next"),
    twinNode("h3", "", projection.next_evidence.intervention_id ? formatIdentifier(projection.next_evidence.intervention_id) : "Measurement prerequisite"),
    twinNode("p", "", projection.next_evidence.summary),
  );
  const missing = twinNode("div", "twin-missing-list");
  (projection.next_evidence.measurements || []).forEach((measurement) => missing.append(twinNode("span", "", formatIdentifier(measurement))));
  if (missing.children.length) next.append(missing);
  lower.append(hypotheses, next);

  const authority = twinNode("footer", "twin-authority");
  authority.append(
    twinNode("span", "lock-icon"),
    twinNode("p", "", "Read-only diagnostic surface. Training, promotion, physical capture, physical authority, and robot motion remain closed."),
    twinNode("code", "", projection.receipt.receipt_sha256 ? `receipt ${projection.receipt.receipt_sha256.slice(0, 16)}…` : "receipt unavailable"),
  );
  elements.twinFidelityContent.append(hero, map, chain, lower, authority);
}

async function loadTwinFidelity(episode) {
  const fetchId = ++state.twinFidelityFetchId;
  state.twinFidelityEpisodeId = episode.id;
  elements.twinFidelityTrigger.disabled = false;
  elements.twinFidelityTrigger.dataset.status = "loading";
  elements.twinFidelityContent.replaceChildren(twinNode("div", "twin-fidelity-loading", "Verifying replay-bound evidence…"));
  try {
    const response = await fetch(`/api/twin-fidelity?episode_id=${encodeURIComponent(episode.id)}`, { cache: "no-store" });
    const projection = await response.json();
    if (fetchId !== state.twinFidelityFetchId || episode.id !== state.selectedEpisodeId) return;
    state.twinFidelity = projection;
    renderTwinFidelity(projection);
  } catch (error) {
    if (fetchId !== state.twinFidelityFetchId) return;
    const unavailable = {
      available: false,
      evidence_status: "unavailable",
      detail: `Twin fidelity evidence could not be loaded: ${error.message}`,
      domains: [],
    };
    state.twinFidelity = unavailable;
    renderTwinFidelity(unavailable);
  }
}

function historySparkline(process) {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.classList.add("activity-history");
  svg.setAttribute("viewBox", "0 0 180 44");
  svg.setAttribute("aria-hidden", "true");
  const key = process.id || String(process.pid || process.title);
  const history = state.processHistory.get(key) || [];
  const values = history.length > 1 ? history : [{ value: 0 }, { value: Number(process.progress || 0) }];
  const points = values.map((row, index) => {
    const x = values.length === 1 ? 0 : index / (values.length - 1) * 180;
    const y = 40 - Math.max(0, Math.min(1, Number(row.value || 0))) * 34;
    return `${x},${y}`;
  }).join(" ");
  const line = document.createElementNS(namespace, "polyline");
  line.setAttribute("points", points);
  svg.append(line);
  return svg;
}

function renderActivity() {
  const active = state.catalog.processes.filter((process) => process.status === "running");
  const recent = state.catalog.processes.filter((process) => process.status !== "running").slice(0, 4);
  const rows = [...active, ...recent];
  elements.activityList.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-activity";
    const title = document.createElement("b");
    const detail = document.createElement("small");
    text(title, "The bench is quiet");
    text(detail, "Training, evaluation, export, and simulation heartbeats will appear here automatically.");
    empty.append(title, detail);
    elements.activityList.append(empty);
    return;
  }

  rows.forEach((process) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = `activity-card ${process.status}`;
    const topline = document.createElement("div");
    topline.className = "activity-topline";
    const kind = document.createElement("span");
    const status = document.createElement("span");
    text(kind, process.kind || "process");
    text(status, process.status);
    topline.append(kind, status);
    const title = document.createElement("h3");
    text(title, process.title || "sim2claw process");
    const phase = document.createElement("p");
    text(phase, process.phase || process.detail || process.status);
    const progress = document.createElement("div");
    progress.className = "activity-progress";
    const fill = document.createElement("i");
    fill.style.setProperty("--progress", `${Math.round(Number(process.progress || 0) * 100)}%`);
    progress.append(fill);
    const metadata = document.createElement("div");
    metadata.className = "activity-meta";
    const amount = document.createElement("span");
    const source = document.createElement("span");
    text(amount, process.progress == null ? process.elapsed || "indeterminate" : `${Math.round(process.progress * 100)}%`);
    text(source, process.pid ? `PID ${process.pid}` : process.source);
    metadata.append(amount, source);
    card.append(topline, title, phase, progress, historySparkline(process), metadata);
    card.addEventListener("click", () => openActivity(process));
    elements.activityList.append(card);
  });
}

function openActivity(process) {
  closeDrawer();
  setActiveView("replay", { updateRoute: false });
  if (process.episode_id && episodeById(process.episode_id)) {
    selectEpisode(process.episode_id);
  } else if (process.task_id && taskById(process.task_id)) {
    selectTask(process.task_id);
  }
}

function renderSimulation() {
  const simulation = state.catalog.simulations[0];
  elements.simulationCard.replaceChildren();
  if (!simulation) {
    elements.simulationCard.hidden = true;
    return;
  }
  elements.simulationCard.hidden = false;
  if (simulation.poster_url) elements.simulationCard.style.backgroundImage = `url("${simulation.poster_url}")`;
  const copy = document.createElement("div");
  copy.className = "simulation-copy";
  const label = document.createElement("span");
  label.className = "section-label";
  const title = document.createElement("h2");
  const subtitle = document.createElement("p");
  text(label, `Current scene · ${simulation.asset_revision || "local"}`);
  text(title, simulation.title);
  const accuracy = simulation.simulator_accuracy;
  text(
    subtitle,
    accuracy
      ? `${simulation.subtitle}. Latest bounded fit recovered selected-piece contact; it remains a kinematic candidate, not the canonical scene.`
      : simulation.subtitle,
  );
  const facts = document.createElement("div");
  facts.className = "simulation-facts";
  const factRows = [["Tasks", simulation.task_count], ["Robots", simulation.robot_count], ["Board", simulation.board_pose_label || "Current"]];
  if (accuracy) {
    factRows.push(
      ["Train contact", `${accuracy.contact_episodes}/${accuracy.episode_count}`],
      ["Held-out contact", `${accuracy.held_out_contact_episodes}/${accuracy.held_out_episode_count}`],
      ["Completed moves", accuracy.success_episodes],
    );
  }
  factRows.forEach(([name, value]) => {
    const fact = document.createElement("span");
    const factValue = document.createElement("b");
    text(fact, name);
    text(factValue, value);
    fact.append(factValue);
    facts.append(fact);
  });
  let boundary = null;
  if (accuracy) {
    boundary = document.createElement("small");
    boundary.className = "simulation-boundary";
    text(
      boundary,
      `${formatIdentifier(accuracy.proof_state)} · ${accuracy.event_rms_mm} mm event RMS · ${accuracy.lift_episodes}/${accuracy.episode_count} lifts · ${accuracy.claim}`,
    );
  }
  copy.append(label, title, subtitle, facts);
  if (boundary) copy.append(boundary);
  elements.simulationCard.append(copy);
}

function renderRobots() {
  elements.robotGrid.replaceChildren();
  state.catalog.robots.forEach((robot) => {
    const card = document.createElement("article");
    card.className = "robot-card";
    const visual = document.createElement("div");
    visual.className = "robot-visual";
    if (robot.poster_url) visual.style.backgroundImage = `url("${robot.poster_url}")`;
    const side = document.createElement("span");
    side.className = "robot-side";
    text(side, `${robot.side} embodiment`);
    visual.append(side);

    const copy = document.createElement("div");
    copy.className = "robot-copy";
    const label = document.createElement("span");
    label.className = "section-label";
    const title = document.createElement("h2");
    const description = document.createElement("p");
    text(label, robot.model);
    text(title, robot.title);
    text(description, `${formatIdentifier(robot.role)}. This inspection view is generated from the current scene contract.`);
    const specs = document.createElement("dl");
    specs.className = "robot-specs";
    const offset = robot.board_centerline_offset_m == null
      ? Number.NaN
      : Number(robot.board_centerline_offset_m);
    [
      ["Mode", robot.mode],
      ["Scene state", formatIdentifier(robot.status)],
      ["Centerline offset", Number.isFinite(offset) ? `${Math.round(offset * 1000)} mm` : "Not registered"],
      ["Poster camera", formatIdentifier(robot.poster_camera)],
      ["Physical link", "Closed"],
    ].forEach(([term, value]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      text(dt, term);
      text(dd, value);
      row.append(dt, dd);
      specs.append(row);
    });
    copy.append(label, title, description, specs);
    card.append(visual, copy);
    elements.robotGrid.append(card);
  });
}

function renderCalibration() {
  const asset = state.catalog?.calibrations?.[0] || null;
  const load = () => {
    window.Sim2ClawCalibration?.load(asset);
    window.Sim2ClawCalibration?.setActive(state.view === "calibration");
  };
  if (window.Sim2ClawCalibration) load();
  else window.addEventListener("sim2claw-3dgs-ready", load, { once: true });
}

const jointNames = ["Shoulder pan", "Shoulder lift", "Elbow", "Wrist flex", "Wrist roll", "Gripper"];
const boardFiles = "abcdefgh";
const brownPawnSquares = ["a2", "b1", "c2", "d1", "e2", "f1", "g2", "h1"];
const tanPawnSquares = ["a8", "b7", "c8", "d7", "e8", "f7", "g8", "h7"];
const recordBrownPawnSquares = ["a1", "b2", "c1", "d2", "e1", "f2", "g1", "h2"];
const recordTanPawnSquares = ["a7", "b8", "c7", "d8", "e7", "f8", "g7", "h8"];
const lowerTwoRowSquares = boardFiles.split("").flatMap((file) => [`${file}1`, `${file}2`]);
const simulatorDestinationSquares = [
  "a1", "c1", "e1", "g1",
  "b2", "d2", "f2", "h2",
  "a3", "b3", "c3", "d3", "e3", "f3", "g3", "h3",
  "a4", "b4", "c4", "d4", "e4", "f4", "g4", "h4",
];
const recorderSettingsKey = "sim2claw.recorder.settings.v3";
const defaultRecorderSettings = Object.freeze({
  mode: "simulation_follower",
  source_square: "b1",
  target_square: "b2",
  sample_hz: 20,
});
const reversePhysicalRecorderDefaults = Object.freeze({
  source_square: "b2",
  target_square: "b1",
});
const physicalRecorderLayoutId = "reverse_sparse_lower_v1";

function previewPawnSquares() {
  return selectedRecorderMode() === "physical_follower"
    ? { brown: recordBrownPawnSquares, tan: recordTanPawnSquares }
    : { brown: brownPawnSquares, tan: tanPawnSquares };
}

function loadRecorderSettings() {
  try {
    const stored = JSON.parse(localStorage.getItem(recorderSettingsKey) || "null");
    if (!stored || typeof stored !== "object") return { ...defaultRecorderSettings };
    const storedMode = ["simulation_follower", "physical_follower"].includes(stored.mode)
      ? stored.mode
      : defaultRecorderSettings.mode;
    const storedSourceSquares = storedMode === "physical_follower"
      ? lowerTwoRowSquares
      : brownPawnSquares;
    const storedDestinationSquares = storedMode === "physical_follower"
      ? lowerTwoRowSquares
      : simulatorDestinationSquares;
    const physicalLayoutChanged = storedMode === "physical_follower"
      && stored.recording_layout !== physicalRecorderLayoutId;
    return {
      mode: storedMode,
      source_square: physicalLayoutChanged
        ? reversePhysicalRecorderDefaults.source_square
        : storedSourceSquares.includes(stored.source_square)
        ? stored.source_square
        : defaultRecorderSettings.source_square,
      target_square: physicalLayoutChanged
        ? reversePhysicalRecorderDefaults.target_square
        : storedDestinationSquares.includes(stored.target_square)
        ? stored.target_square
        : defaultRecorderSettings.target_square,
      sample_hz: Number(stored.sample_hz) === 20
        ? Number(stored.sample_hz)
        : defaultRecorderSettings.sample_hz,
    };
  } catch (_error) {
    return { ...defaultRecorderSettings };
  }
}

function persistRecorderSettings() {
  try {
    localStorage.setItem(recorderSettingsKey, JSON.stringify({
      mode: selectedRecorderMode(),
      source_square: elements.sourceSquare.value,
      target_square: elements.target.value,
      sample_hz: Number(elements.sampleHz.value),
      recording_layout: selectedRecorderMode() === "physical_follower"
        ? physicalRecorderLayoutId
        : "canonical_sparse_v1",
    }));
  } catch (_error) {
    // Private browsing or a locked-down profile may reject storage; defaults remain usable.
  }
}

function selectedRecorderMode() {
  return document.querySelector('input[name="recorder-mode"]:checked')?.value || "simulation_follower";
}

function recorderSourceSquares() {
  return selectedRecorderMode() === "physical_follower"
    ? lowerTwoRowSquares
    : brownPawnSquares;
}

function recorderDestinationSquares() {
  return selectedRecorderMode() === "physical_follower"
    ? lowerTwoRowSquares
    : simulatorDestinationSquares;
}

function setPreflightItem(element, ready, detail) {
  element.classList.toggle("is-ready", Boolean(ready));
  element.classList.toggle("is-missing", !ready);
  text(element.querySelector("small"), detail);
}

function renderJointMonitor(recorder) {
  const sample = recorder?.last_sample;
  const physical = (recorder?.mode || selectedRecorderMode()) === "physical_follower";
  const values = physical
    ? sample?.follower_actual_position_degrees
    : sample?.follower_actual_position_rad;
  text(elements.jointUnit, physical ? "degrees" : "radians");
  elements.jointBars.replaceChildren();
  jointNames.forEach((name, index) => {
    const value = Number(values?.[index]);
    const row = document.createElement("div");
    row.className = "joint-row";
    const label = document.createElement("span");
    const track = document.createElement("i");
    const marker = document.createElement("b");
    const readout = document.createElement("code");
    text(label, name);
    const normalized = Number.isFinite(value)
      ? physical
        ? (value + 180) / 360
        : (value + Math.PI) / (2 * Math.PI)
      : 0.5;
    marker.style.setProperty("--joint-position", `${Math.max(0, Math.min(1, normalized)) * 100}%`);
    text(readout, Number.isFinite(value) ? `${value.toFixed(physical ? 1 : 3)}` : "—");
    track.append(marker);
    row.append(label, track, readout);
    elements.jointBars.append(row);
  });
}

function renderRecorder() {
  const recorder = state.recorder;
  if (!recorder) return;
  const preflight = recorder.preflight;
  const status = recorder.status || "idle";
  document.body.dataset.recorderStatus = status;
  const active = ["starting", "recording", "stopping"].includes(status);
  const awaitingLabel = status === "awaiting_label";
  const hasError = status === "error";
  const selectedMode = selectedRecorderMode();
  elements.liveSimulationPanel.hidden = selectedMode !== "simulation_follower";
  const simReady = Boolean(preflight?.modes?.simulation_follower?.ready);
  const physicalReady = Boolean(preflight?.modes?.physical_follower?.ready);
  const errorDetails = recorder.error_details || recorder.last_error_details;
  const gatewayPreflight = recorder.physical_gateway_sync
    || recorder.physical_gateway_preflight
    || (errorDetails?.calibration_offset_leader_minus_follower ? errorDetails : null);
  const registrationReady = Boolean(
    gatewayPreflight?.paired_pose_registration_ready,
  );

  text(elements.recorderStatus, formatIdentifier(status));
  elements.recorderStatus.dataset.status = status;
  text(elements.recordClock, formatTime(Number(recorder.duration_seconds || 0)));
  text(elements.recordSamples, recorder.sample_count || 0);
  text(elements.recordRate, `${recorder.sample_hz || elements.sampleHz.value} Hz`);
  text(elements.recordModeLabel, (recorder.mode || selectedMode) === "physical_follower" ? "PHYSICAL" : "SIM");
  const cameraStatus = recorder.overhead_video?.status;
  const wristCameraStatus = recorder.wrist_video?.status;
  const physicalCapture = (recorder.mode || selectedMode) === "physical_follower";
  text(
    elements.recordCamera,
    physicalCapture && cameraStatus === "recording" && wristCameraStatus === "recording"
      ? "C922 + D405 REC"
      : physicalCapture && cameraStatus === "completed" && wristCameraStatus === "completed"
        ? "2 feeds saved"
        : physicalCapture
          ? "C922 + D405 on Start"
          : cameraStatus === "recording"
      ? "C922 REC"
      : cameraStatus === "completed"
        ? "C922 saved"
        : "C922 on Start",
  );
  text(elements.recordPath, recorder.saved_path || recorder.draft_path || "datasets/manipulation_source_recordings/");

  text(elements.simModeState, simReady ? "Ready" : "Missing");
  text(elements.physicalModeState, physicalReady ? "Ready" : "Missing");
  elements.physicalModeOption.classList.toggle("is-disabled", !physicalReady);
  elements.physicalModeOption.querySelector("input").disabled = !physicalReady || active || awaitingLabel;
  document.querySelectorAll('input[name="recorder-mode"]').forEach((input) => {
    if (input.value === "simulation_follower") input.disabled = active || awaitingLabel;
    input.closest(".mode-option").classList.toggle("is-selected", input.checked);
  });
  elements.physicalSafetyCheck.hidden = selectedMode !== "physical_follower";

  const leader = preflight?.devices?.leader;
  const follower = preflight?.devices?.follower;
  const runtime = preflight?.runtime;
  setPreflightItem(elements.leaderPreflight, leader?.connected && preflight?.calibrations?.leader?.present, leader?.connected ? `Bus ${leader.serial_suffix} · calibrated` : "Expected leader bus not found");
  setPreflightItem(elements.followerPreflight, follower?.connected && preflight?.calibrations?.follower?.present, gatewayPreflight?.passed ? `Bus ${follower.serial_suffix} · torque-off verified` : follower?.connected ? `Bus ${follower.serial_suffix} · calibrated` : "Expected follower bus not found");
  setPreflightItem(elements.runtimePreflight, runtime?.lerobot_version === runtime?.required_lerobot_version, runtime?.lerobot_version ? `LeRobot ${runtime.lerobot_version}` : "LeRobot runtime missing");
  const cameraInventory = liveCameraRows();
  const overheadCamera = cameraInventory.find((camera) => camera.id === "logitech-overhead");
  const wristCamera = cameraInventory.find((camera) => camera.id === "d405-wrist");
  setPreflightItem(
    elements.overheadCameraPreflight,
    Boolean(overheadCamera?.available),
    overheadCamera?.available
      ? overheadCamera.device_name || "C922 exact-name input ready"
      : overheadCamera?.error || "C922 not discovered",
  );
  setPreflightItem(
    elements.wristCameraPreflight,
    Boolean(wristCamera?.available),
    wristCamera?.available
      ? wristCamera.device_name || "D405 exact-name input ready"
      : wristCamera?.error || "D405 wrist not discovered",
  );

  elements.alignmentPanel.hidden = selectedMode !== "physical_follower";
  elements.alignmentPanel.classList.toggle("is-ready", registrationReady);
  elements.alignmentPanel.classList.toggle("is-blocked", Boolean(gatewayPreflight) && !registrationReady);
  text(elements.alignmentStatus, !gatewayPreflight ? "Check or sync both buses" : registrationReady ? "Follower and leader are synchronized" : "Pose mismatch is outside the guard");
  text(elements.alignmentSummary, !gatewayPreflight
    ? "Check is read-only. Separate Sync finishes torque-off. Start records both diagnostic cameras, then syncs and torque-holds the follower through countdown in one gateway session."
    : registrationReady
      ? `Maximum calibration offset ${Number(gatewayPreflight.maximum_body_calibration_offset_degrees).toFixed(1)}°. Start rechecks this pair after continuous Sync and torque-held countdown, then maps relative motion.`
      : `Maximum calibration offset ${Number(gatewayPreflight.maximum_body_calibration_offset_degrees).toFixed(1)}°. Start may bounded-sync a nearby pair; any body mismatch over 20° is refused.`);
  elements.alignmentJoints.replaceChildren();
  const alignmentDelta = gatewayPreflight?.calibration_offset_leader_minus_follower;
  if (alignmentDelta) {
    jointNames.forEach((name, index) => {
      const item = document.createElement("span");
      const label = document.createElement("small");
      const value = document.createElement("b");
      text(label, name);
      text(value, `${Number(alignmentDelta[index]).toFixed(1)}${index === 5 ? "" : "°"}`);
      item.append(label, value);
      elements.alignmentJoints.append(item);
    });
  }

  const selectedReady = selectedMode === "physical_follower" ? physicalReady : simReady;
  elements.startRecording.disabled = state.recorderRequestActive || state.physicalPreflighting || state.physicalStartSequence || state.physicalSyncing || active || awaitingLabel || hasError || !selectedReady || (selectedMode === "physical_follower" && !elements.physicalSafetyAck.checked);
  elements.stopRecording.disabled = state.recorderRequestActive || !["starting", "recording"].includes(status);
  elements.labelForm.hidden = !awaitingLabel && !hasError;
  elements.labelForm.classList.toggle("is-error", hasError);
  elements.labelForm.querySelector(".save-button").hidden = hasError;
  elements.labelForm.querySelectorAll("input, select, textarea").forEach((field) => { field.disabled = hasError; });
  elements.discardRecording.hidden = !awaitingLabel && !hasError;
  text(
    elements.discardRecording,
    hasError
      ? "Return to ready"
      : state.discardConfirmationArmed
        ? "Click again to discard"
        : "Discard draft",
  );
  elements.sourceSquare.disabled = active || awaitingLabel;
  elements.target.disabled = active || awaitingLabel;
  elements.sampleHz.disabled = active || awaitingLabel;
  updatePawnBoardInteractivity(active || awaitingLabel);
  elements.verifyGateway.hidden = selectedMode !== "physical_follower";
  elements.verifyGateway.disabled = state.recorderRequestActive || active || !physicalReady;
  elements.syncFollower.hidden = selectedMode !== "physical_follower";
  elements.syncFollower.disabled = state.recorderRequestActive || state.physicalSyncing || active || awaitingLabel || !physicalReady || !elements.physicalSafetyAck.checked;

  const canReplayPhysical = status === "saved" && recorder.mode === "physical_follower";
  elements.simReplayPanel.hidden = !canReplayPhysical;
  elements.runSimReplay.disabled = state.recorderRequestActive;
  const replay = recorder.sim_replay;
  elements.simReplayMetrics.hidden = !replay;
  elements.simReplayMetrics.replaceChildren();
  if (replay) {
    [
      ["Body RMSE", `${Number(replay.aggregate_body_joint_rmse_degrees).toFixed(2)}°`],
      ["Worst body error", `${Number(replay.maximum_body_joint_error_degrees).toFixed(2)}°`],
      ["Gripper RMSE", `${Number(replay.gripper_rmse_actuator_rad).toFixed(4)} rad`],
      ["Samples", replay.sample_count],
    ].forEach(([label, value]) => {
      const row = document.createElement("div");
      const term = document.createElement("dt");
      const detail = document.createElement("dd");
      text(term, label);
      text(detail, value);
      row.append(term, detail);
      elements.simReplayMetrics.append(row);
    });
  }

  if (state.recorderRequestError) {
    text(elements.recorderMessage, state.recorderRequestError);
  } else if (state.physicalPreflighting) {
    text(elements.recorderMessage, "Automatically verifying both buses torque-off and measuring the paired-pose offset…");
  } else if (state.physicalStartSequence) {
    text(elements.recorderMessage, "The C922 and D405 are recording. The server is syncing the nearby follower, keeping torque held through the countdown, then registering relative zero. Keep both arms still and the workcell clear.");
  } else if (state.physicalSyncing) {
    text(elements.recorderMessage, "Ramping the nearby follower to the leader pose through the reviewed gateway; torque will be off again when Sync completes.");
  } else if (status === "recording") {
    text(elements.recorderMessage, physicalCapture ? "Recording leader targets, follower state, C922 overhead video, and the D405 wrist stream. Stop when this demonstration or correction is complete." : "Recording leader targets, simulator state, and independent C922 overhead video. Stop when this demonstration or correction is complete.");
  } else if (status === "starting") {
    text(elements.recorderMessage, physicalCapture ? "Starting exact-name C922 and D405 captures before opening either arm bus…" : "Starting the overhead C922 first, then opening the leader bus and initializing the simulator follower…");
  } else if (status === "stopping") {
    text(elements.recorderMessage, physicalCapture ? "Arm control is stopping; retaining diagnostic post-roll and finalizing both camera artifacts…" : "Arm control is stopping; retaining one second of C922 post-roll and finalizing the video…");
  } else if (awaitingLabel) {
    text(elements.recorderMessage, physicalCapture ? "Recording stopped. Both camera sources and the D405 browser derivative are verified; add the observed skill and outcome before saving." : "Recording stopped. The C922 video and one-second post-roll are retained; add the observed skill and outcome before saving.");
  } else if (status === "saved") {
    text(elements.recorderMessage, `Saved ${recorder.sample_count} samples. This episode is still pending replay and separate evaluator admission.`);
  } else if (hasError) {
    text(elements.recorderMessage, `${recorder.error || "Recording failed closed."} Torque is off. ${errorDetails?.stage ? `Failure stage: ${formatIdentifier(errorDetails.stage)}. ` : ""}Return to ready does not delete the failed trace.`);
  } else if (recorder.last_error) {
    text(elements.recorderMessage, `Previous attempt stopped safely: ${recorder.last_error} ${errorDetails?.stage ? `Failure stage: ${formatIdentifier(errorDetails.stage)}. Six-joint diagnostics were retained. ` : ""}Ready to retry; the failed trace was retained at ${recorder.last_failed_attempt_path || "failed-attempt storage"}.`);
  } else if (!selectedReady) {
    text(elements.recorderMessage, preflight?.modes?.[selectedMode]?.reason || "Selected follower is not ready.");
  } else if (selectedMode === "physical_follower" && !gatewayPreflight) {
    text(elements.recorderMessage, "Ready: Start records the C922 and D405 first, then syncs and holds the nearby follower through a server-owned countdown before relative teleoperation. Sync is also available separately.");
  } else if (selectedMode === "physical_follower" && !registrationReady) {
    text(elements.recorderMessage, "The current pair is outside the 12° registration guard. Start can bounded-sync a nearby pair up to 20°; otherwise physically match the arms and verify again.");
  } else if (selectedMode === "physical_follower") {
    text(elements.recorderMessage, "Ready: Start records both diagnostic cameras, re-syncs the pair, and keeps follower torque held through countdown before relative teleoperation.");
  } else {
    text(elements.recorderMessage, "Move the leader to a comfortable starting pose. The simulator initializes from that pose when recording begins.");
  }
  renderJointMonitor(recorder);
}

async function fetchRecorder() {
  if (state.readOnly !== false || state.recorderRequestActive) return;
  try {
    const response = await fetch("/api/recorder", { cache: "no-store" });
    if (!response.ok) throw new Error(`recorder returned ${response.status}`);
    state.recorder = await response.json();
    renderRecorder();
  } catch (error) {
    text(elements.recorderMessage, "Recorder service is unavailable. Restart the local Studio server.");
  }
}

async function postRecorder(action, payload = {}) {
  state.recorderRequestError = null;
  state.recorderRequestActive = true;
  renderRecorder();
  let succeeded = false;
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 55000);
  try {
    const response = await fetch(`/api/recorder/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || `recorder returned ${response.status}`);
    state.recorder = result.recorder;
    succeeded = true;
  } catch (error) {
    state.recorderRequestError = error.name === "AbortError"
      ? "Recorder request timed out. Refresh recorder status and preflight before retrying."
      : error.message || String(error);
  } finally {
    window.clearTimeout(timeout);
    state.recorderRequestActive = false;
    renderRecorder();
  }
  return succeeded;
}

async function beginRecording() {
  const physical = selectedRecorderMode() === "physical_follower";
  const payload = {
    mode: selectedRecorderMode(),
    source_square: elements.sourceSquare.value,
    target_square: elements.target.value,
    sample_hz: Number(elements.sampleHz.value),
    physical_safety_acknowledged: elements.physicalSafetyAck.checked,
    server_owned_prestart_sequence: physical,
  };
  if (physical) {
    state.physicalStartSequence = true;
    renderRecorder();
  }
  await postRecorder("start", payload);
  state.physicalStartSequence = false;
  renderRecorder();
}

async function syncPhysicalFollower() {
  state.physicalSyncing = true;
  renderRecorder();
  await postRecorder("gateway-sync", {
    physical_safety_acknowledged: elements.physicalSafetyAck.checked,
  });
  state.physicalSyncing = false;
  renderRecorder();
}

function updateDestinationOptions(preferred = elements.target.value || "b2") {
  elements.target.replaceChildren();
  for (const square of recorderDestinationSquares()) {
    const option = document.createElement("option");
    option.value = square;
    text(option, square.toUpperCase());
    if (square === preferred) option.selected = true;
    elements.target.append(option);
  }
}

function boardSquareDescription(square, { brown, tan } = previewPawnSquares()) {
  const coordinate = square.toUpperCase();
  if (brown.includes(square)) return `${coordinate}, brown pawn`;
  if (tan.includes(square)) return `${coordinate}, tan pawn`;
  return `${coordinate}, empty square`;
}

function updatePawnBoardInteractivity(locked = elements.sourceSquare.disabled) {
  const selectingSource = state.pawnBoardSelectionStep === "source";
  const validSquares = selectingSource ? recorderSourceSquares() : recorderDestinationSquares();
  const instruction = selectingSource
    ? selectedRecorderMode() === "physical_follower"
      ? "Choose source square · click any lower-row square"
      : "Choose source pawn · click a brown pawn"
    : selectedRecorderMode() === "physical_follower"
      ? "Choose destination · click any lower-row square"
      : "Choose destination · click an empty square in rows 1–4";
  text(elements.pawnBoardInstruction, locked ? "Board selection is locked while recording" : instruction);
  elements.pawnPreviewBoard.dataset.selectionStep = state.pawnBoardSelectionStep;
  elements.pawnPreviewBoard.setAttribute("aria-disabled", String(locked));
  elements.pawnPreviewBoard.querySelectorAll("button[data-square]").forEach((cell) => {
    const selectable = !locked && validSquares.includes(cell.dataset.square);
    cell.disabled = !selectable;
    cell.classList.toggle("is-selectable", selectable);
    cell.setAttribute(
      "aria-label",
      `${boardSquareDescription(cell.dataset.square)}${selectable ? `; select as ${state.pawnBoardSelectionStep}` : ""}`,
    );
  });
}

function selectPawnBoardSquare(square) {
  if (state.pawnBoardSelectionStep === "source") {
    if (!recorderSourceSquares().includes(square)) return;
    elements.sourceSquare.value = square;
    state.pawnBoardSelectionStep = "destination";
  } else {
    if (!recorderDestinationSquares().includes(square)) return;
    elements.target.value = square;
    state.pawnBoardSelectionStep = "source";
  }
  renderPawnMovePreview();
  persistRecorderSettings();
}

function renderPawnMovePreview() {
  const source = elements.sourceSquare.value || "b1";
  const destination = elements.target.value || "b2";
  const physical = selectedRecorderMode() === "physical_follower";
  const { brown: previewBrownPawnSquares, tan: previewTanPawnSquares } = previewPawnSquares();
  const sourceLabel = physical && !previewBrownPawnSquares.includes(source)
    ? "source square"
    : "brown pawn";
  text(elements.pawnPreviewSource, source.toUpperCase());
  text(elements.pawnPreviewTarget, destination.toUpperCase());
  text(
    elements.pawnPreviewDescription,
    physical
      ? `Record the ${sourceLabel} from ${source.toUpperCase()} to ${destination.toUpperCase()}. Physical source metadata is not constrained by the sparse simulator layout.`
      : `Move the brown pawn from ${source.toUpperCase()} to ${destination.toUpperCase()}. Brown and tan pawns not selected remain in place.`,
  );
  elements.pawnPreviewBoard.setAttribute(
    "aria-label",
    `${physical ? "Physical reverse sparse source-square movement" : "Brown pawn movement"} from ${source.toUpperCase()} to ${destination.toUpperCase()} on a two-sided sparse pawn board`,
  );
  elements.pawnPreviewBoard.replaceChildren();
  for (const rank of [8, 7, 6, 5, 4, 3, 2, 1]) {
    for (const file of boardFiles) {
      const square = `${file}${rank}`;
      const cell = document.createElement("button");
      cell.type = "button";
      cell.className = "pawn-board-cell";
      cell.dataset.square = square;
      if ((boardFiles.indexOf(file) + rank) % 2 === 0) cell.classList.add("is-dark");
      if (square === source) cell.classList.add("is-source");
      if (square === destination) cell.classList.add("is-destination");
      if (previewBrownPawnSquares.includes(square)) {
        const pawn = document.createElement("i");
        pawn.className = "pawn-token";
        pawn.setAttribute("aria-hidden", "true");
        cell.append(pawn);
      } else if (previewTanPawnSquares.includes(square)) {
        const pawn = document.createElement("i");
        pawn.className = "pawn-token is-tan";
        pawn.setAttribute("aria-hidden", "true");
        cell.append(pawn);
      }
      const coordinate = document.createElement("small");
      text(coordinate, square.toUpperCase());
      cell.append(coordinate);
      elements.pawnPreviewBoard.append(cell);
    }
  }
  updatePawnBoardInteractivity();
  const sourceX = boardFiles.indexOf(source[0]) + 0.5;
  const sourceY = 8 - Number(source[1]) + 0.5;
  const targetX = boardFiles.indexOf(destination[0]) + 0.5;
  const targetY = 8 - Number(destination[1]) + 0.5;
  const dx = targetX - sourceX;
  const dy = targetY - sourceY;
  const length = Math.hypot(dx, dy) || 1;
  const inset = 0.28;
  elements.pawnMoveLine.setAttribute("x1", String(sourceX + (dx / length) * inset));
  elements.pawnMoveLine.setAttribute("y1", String(sourceY + (dy / length) * inset));
  elements.pawnMoveLine.setAttribute("x2", String(targetX - (dx / length) * inset));
  elements.pawnMoveLine.setAttribute("y2", String(targetY - (dy / length) * inset));
}

function initializeRecorderForm() {
  const settings = loadRecorderSettings();
  const mode = document.querySelector(`input[name="recorder-mode"][value="${settings.mode}"]`);
  if (mode) mode.checked = true;
  for (const square of recorderSourceSquares()) {
    const option = document.createElement("option");
    option.value = square;
    text(
      option,
      `${square.toUpperCase()} · ${previewPawnSquares().brown.includes(square) ? "brown pawn" : "source square"}`,
    );
    elements.sourceSquare.append(option);
  }
  elements.sourceSquare.value = settings.source_square;
  updateDestinationOptions(settings.target_square);
  elements.sampleHz.value = String(settings.sample_hz);
  renderPawnMovePreview();
  renderJointMonitor(null);
}

function refreshRecorderSquareOptions(preferredSource = null, preferredTarget = null) {
  const source = preferredSource || elements.sourceSquare.value;
  const target = preferredTarget || elements.target.value;
  elements.sourceSquare.replaceChildren();
  for (const square of recorderSourceSquares()) {
    const option = document.createElement("option");
    option.value = square;
    text(
      option,
      `${square.toUpperCase()} · ${previewPawnSquares().brown.includes(square) ? "brown pawn" : "source square"}`,
    );
    elements.sourceSquare.append(option);
  }
  elements.sourceSquare.value = recorderSourceSquares().includes(source)
    ? source
    : recorderSourceSquares()[0];
  updateDestinationOptions(
    recorderDestinationSquares().includes(target)
      ? target
      : recorderDestinationSquares()[0],
  );
  state.pawnBoardSelectionStep = "source";
  renderPawnMovePreview();
  persistRecorderSettings();
}

function formatCountdown(seconds) {
  const safe = Math.max(0, Math.ceil(Number(seconds) || 0));
  const minutes = Math.floor(safe / 60);
  return `${String(minutes).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function orchestratorActionLabel(action) {
  if (!action) return "None";
  const skill = action.skill_id || action.decision;
  const source = action.arguments?.source_square;
  const destination = action.arguments?.destination_square;
  return source && destination
    ? `${skill} · ${source.toUpperCase()}→${destination.toUpperCase()}`
    : String(skill || "None");
}

function orchestratorEventDetail(row) {
  const payload = row?.payload || {};
  return payload.reason
    || payload.skill_id
    || payload.code
    || payload.frame?.sha256?.slice(0, 12)
    || payload.decision?.decision
    || "receipt recorded";
}

function orchestratorHasActiveTextSelection() {
  const selection = window.getSelection?.();
  const root = document.querySelector('[data-view-panel="orchestrator"]');
  if (!root || !selection || selection.isCollapsed || selection.rangeCount === 0) return false;
  return root.contains(selection.anchorNode) || root.contains(selection.focusNode);
}

async function copyOrchestratorText() {
  const root = document.querySelector('[data-view-panel="orchestrator"]');
  const value = root?.innerText?.trim();
  if (!value) return;
  const previousLabel = elements.orchestratorCopy.textContent;
  try {
    await navigator.clipboard.writeText(value);
    text(elements.orchestratorCopy, "Copied");
  } catch (_error) {
    const field = document.createElement("textarea");
    field.value = value;
    field.setAttribute("readonly", "");
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.append(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    text(elements.orchestratorCopy, copied ? "Copied" : "Copy failed");
  }
  window.setTimeout(() => text(elements.orchestratorCopy, previousLabel), 1600);
}

function renderOrchestrator() {
  const runtime = state.orchestrator;
  if (!runtime) return;
  const available = runtime.available !== false;
  const machineState = runtime.state || "STOPPED";
  const mainStatus = runtime.main_status || "stopped";
  text(elements.orchestratorState, machineState);
  text(elements.orchestratorMainStatus, formatIdentifier(mainStatus));
  elements.orchestratorMainStatus.dataset.status = mainStatus;

  const previousMode = elements.orchestratorMode.value || runtime.mode || "observe_only";
  elements.orchestratorMode.replaceChildren();
  Object.entries(runtime.modes || {}).forEach(([identifier, capability]) => {
    const option = document.createElement("option");
    option.value = identifier;
    option.disabled = !capability.selectable;
    option.title = capability.reason || "Preflight passed";
    text(option, `${formatIdentifier(identifier)}${capability.selectable ? "" : " · unavailable"}`);
    elements.orchestratorMode.append(option);
  });
  const preferredMode = machineState === "STOPPED" && runtime.modes?.demo_physical?.selectable
    ? "demo_physical"
    : machineState === "STOPPED" && runtime.modes?.[previousMode]
      ? previousMode
      : runtime.mode;
  elements.orchestratorMode.value = preferredMode || "observe_only";
  elements.orchestratorMode.disabled = !available || machineState !== "STOPPED" || state.orchestratorRequestActive;

  if (document.activeElement !== elements.orchestratorPolling) {
    elements.orchestratorPolling.value = String(runtime.settings?.polling_interval_seconds ?? 15);
  }
  elements.orchestratorPolling.min = String(runtime.settings?.polling_minimum_seconds ?? 2);
  elements.orchestratorPolling.max = String(runtime.settings?.polling_maximum_seconds ?? 300);
  elements.orchestratorPolling.disabled = !available || state.orchestratorRequestActive;
  text(elements.orchestratorUserTimer, formatCountdown(runtime.timers?.user_remaining_seconds ?? 300));
  text(elements.orchestratorWorldTimer, formatCountdown(runtime.timers?.world_action_remaining_seconds ?? 300));

  const activeStates = new Set(["STARTING", "OBSERVING", "AWAITING_MODEL", "PROPOSED_ACTION", "EXECUTING_SKILL", "VERIFYING"]);
  const selectedCapability = runtime.modes?.[elements.orchestratorMode.value];
  elements.orchestratorStart.disabled = !available || machineState !== "STOPPED" || !selectedCapability?.selectable || state.orchestratorRequestActive;
  elements.orchestratorPause.disabled = !activeStates.has(machineState) || state.orchestratorRequestActive;
  elements.orchestratorResume.disabled = machineState !== "PAUSED" || state.orchestratorRequestActive;
  elements.orchestratorStop.disabled = machineState === "STOPPED" || state.orchestratorRequestActive;
  const canPreviewStopped = machineState === "STOPPED" && runtime.source?.ready;
  elements.orchestratorRefresh.disabled = (!activeStates.has(machineState) && !canPreviewStopped) || state.orchestratorRequestActive;
  text(elements.orchestratorRefresh, machineState === "STOPPED" ? "Preview overhead" : "Refresh frame");
  elements.orchestratorChat.disabled = !activeStates.has(machineState) || state.orchestratorRequestActive;
  const chatButton = elements.orchestratorChatForm.querySelector("button");
  if (chatButton) chatButton.disabled = !activeStates.has(machineState) || state.orchestratorRequestActive;

  const demo = runtime.demo_loop || {};
  let message = demo.ready
    ? "Demo physical ready. Type “loop it” to run the fixed five-minute script."
    : "Loopback controls ready.";
  if (!available) message = runtime.reason || "Task Orchestrator is unavailable.";
  else if (state.orchestratorRequestError) message = state.orchestratorRequestError;
  else if (runtime.fault) message = `${formatIdentifier(runtime.fault.category)}: ${runtime.fault.message || runtime.fault.code || "session fault"}`;
  else if (machineState === "PAUSED") message = `Paused: ${formatIdentifier(runtime.pause_reason || "operator request")}`;
  else if (machineState === "STOPPED" && runtime.task_outcome === "complete") message = "Verified complete by the deterministic managed-region checker.";
  else if (machineState === "STOPPED" && !selectedCapability?.selectable) message = selectedCapability?.reason || "Selected mode did not pass preflight.";
  else if (runtime.source?.health === "fault") message = runtime.source.latest_error?.message || "Overhead source faulted.";
  else if (demo.status === "running" || demo.status === "stopping") message = `Demo loop ${demo.status} · ${demo.completed_moves || 0}/${demo.total_moves || 12} moves complete · Stop finishes the current guarded move.`;
  else if (demo.status === "failed") message = demo.error || "The fixed demo loop failed safely.";
  text(elements.orchestratorMessage, message);

  const source = runtime.source || {};
  text(elements.orchestratorSourceTitle, source.label || formatIdentifier(source.camera_id || "Overhead source"));
  text(elements.orchestratorSourceHealth, formatIdentifier(source.health || "unknown"));
  text(elements.orchestratorSourceHost, source.device_name || source.host || "—");
  text(elements.orchestratorSourceRole, source.camera_role || "—");
  text(elements.orchestratorSourceRegistration, formatIdentifier(source.registration_state || "unknown"));
  text(elements.orchestratorSourceTime, source.latest_captured_at ? new Date(source.latest_captured_at).toLocaleTimeString() : "—");
  const frameHash = source.latest_accepted_sha256 || source.latest_preview_sha256;
  text(elements.orchestratorSourceHash, frameHash ? frameHash.slice(0, 16) : "—");
  text(elements.orchestratorSimilarity, runtime.comparison?.similarity == null ? "—" : Number(runtime.comparison.similarity).toFixed(4));
  text(elements.orchestratorSuppressed, runtime.comparison?.suppression_count ?? 0);
  if (frameHash && frameHash !== state.orchestratorFrameHash) {
    state.orchestratorFrameHash = frameHash;
    elements.orchestratorFrame.src = `/api/orchestrator/frame?sha=${encodeURIComponent(frameHash)}`;
    elements.orchestratorFrame.hidden = false;
    elements.orchestratorFrameEmpty.hidden = true;
  } else if (!frameHash) {
    elements.orchestratorFrame.hidden = true;
    elements.orchestratorFrameEmpty.hidden = false;
  }

  const workcell = runtime.workcell || {};
  const arms = workcell.arms || [];
  const cameras = workcell.cameras || [];
  const connectedArms = arms.filter((row) => row.connected).length;
  const availableCameras = cameras.filter((row) => row.available).length;
  text(elements.orchestratorWorkcellState, `${connectedArms}/${arms.length || 1} follower · ${availableCameras}/${cameras.length || 1} overhead${demo.physical_authority ? " · DEMO OPEN" : ""}`);
  elements.orchestratorArms.replaceChildren();
  arms.forEach((arm) => {
    const row = document.createElement("div");
    row.className = "orchestrator-device-row";
    row.dataset.ready = String(Boolean(arm.connected));
    const copy = document.createElement("div");
    const name = document.createElement("b");
    const detail = document.createElement("small");
    text(name, `${formatIdentifier(arm.role)} arm`);
    text(detail, arm.port || `Expected ${arm.serial_suffix || "SO-101"} bus`);
    copy.append(name, detail);
    const status = document.createElement("em");
    text(status, arm.connected ? (demo.ready ? "Connected · demo script ready" : "Connected · preflight on run") : "Offline");
    row.append(copy, status);
    elements.orchestratorArms.append(row);
  });
  elements.orchestratorCameras.replaceChildren();
  cameras.forEach((camera) => {
    const row = document.createElement("div");
    row.className = "orchestrator-device-row";
    row.dataset.ready = String(Boolean(camera.available));
    row.dataset.primary = String(Boolean(camera.primary_for_orchestrator));
    const copy = document.createElement("div");
    const name = document.createElement("b");
    const detail = document.createElement("small");
    text(name, `${camera.label}${camera.primary_for_orchestrator ? " · primary" : ""}`);
    text(detail, camera.device_name || camera.role || camera.detail);
    copy.append(name, detail);
    const status = document.createElement("em");
    text(status, camera.busy ? `Busy · ${formatIdentifier(camera.busy_owner)}` : camera.available ? "Ready" : "Offline");
    row.append(copy, status);
    elements.orchestratorCameras.append(row);
  });

  const base = runtime.base_case;
  text(elements.orchestratorBaseState, base ? formatIdentifier(base.state) : "Awaiting frame");
  text(elements.orchestratorMismatches, base?.mismatched_files?.length ? base.mismatched_files.map((value) => value.toUpperCase()).join(", ") : "None");
  text(elements.orchestratorConfidence, base ? `${(Number(base.confidence) * 100).toFixed(1)}%` : "—");
  text(elements.orchestratorBaseFrame, base?.evidence_frame_sha256 ? base.evidence_frame_sha256.slice(0, 16) : "—");
  elements.orchestratorSquares.replaceChildren();
  for (const fileName of ["b", "c", "d", "e", "f", "g"]) {
    for (const rank of [1, 2]) {
      const square = `${fileName}${rank}`;
      const observation = base?.squares?.[square];
      const card = document.createElement("div");
      card.className = "orchestrator-square";
      card.dataset.occupancy = observation?.status || "unknown";
      const label = document.createElement("b");
      text(label, square.toUpperCase());
      const status = document.createElement("span");
      text(status, observation ? formatIdentifier(observation.status) : "—");
      card.append(label, status);
      elements.orchestratorSquares.append(card);
    }
  }
  elements.orchestratorBlockers.replaceChildren();
  (base?.blockers || []).forEach((blocker) => {
    const badge = document.createElement("span");
    text(badge, `${formatIdentifier(blocker.kind)}${blocker.square || blocker.file ? ` · ${(blocker.square || blocker.file).toUpperCase()}` : ""}`);
    elements.orchestratorBlockers.append(badge);
  });

  const queue = runtime.action_queue || {};
  const proposed = queue.proposed_plan?.[0];
  text(elements.orchestratorVerification, formatIdentifier(queue.verification || "not_started"));
  text(elements.orchestratorPlan, orchestratorActionLabel(proposed));
  text(elements.orchestratorCurrentAction, orchestratorActionLabel(queue.current_action));
  text(elements.orchestratorPostcondition, queue.expected_postcondition ? JSON.stringify(queue.expected_postcondition) : "None");
  const replay = runtime.supervised_replay;
  elements.orchestratorReplayResult.hidden = !replay;
  if (replay) {
    text(elements.orchestratorReplayStatus, `${formatIdentifier(replay.status)} · B2→B1 · torque ${replay.torque_enabled_after ? "on" : "off"}`);
    text(
      elements.orchestratorReplayDetail,
      replay.status === "completed"
        ? `${replay.completed_sample_count}/${replay.source_sample_count} commands completed · ${replay.exact_command_sample_count} exact · outcome requires visual review · recorded replay, not ACT`
        : `${replay.failure_message || "Replay failed safely"} · no task-success claim`,
    );
  }
  text(elements.orchestratorModel, `${runtime.model?.label || "5.6 luna"} · ${runtime.model?.reasoning_effort || "medium"}`);
  text(elements.orchestratorModelState, runtime.model?.identity_verified ? "Exact identity verified" : runtime.model?.credential_configured ? "Credential configured" : "Credential unavailable");

  elements.orchestratorConversation.replaceChildren();
  (runtime.conversation || []).forEach((message) => {
    const row = document.createElement("div");
    row.className = "orchestrator-conversation-row";
    row.dataset.role = message.role;
    const role = document.createElement("b");
    text(role, message.role === "assistant" ? "5.6 luna" : "You");
    const body = document.createElement("span");
    text(body, message.message);
    row.append(role, body);
    elements.orchestratorConversation.append(row);
  });

  const skills = runtime.allowed_skills || [];
  const shadowVisible = runtime.mode === "physical_shadow";
  elements.orchestratorShadowReview.hidden = !shadowVisible;
  if (shadowVisible) {
    const previousShadowChoice = elements.orchestratorShadowChoice.value;
    elements.orchestratorShadowChoice.replaceChildren();
    const noAction = document.createElement("option");
    noAction.value = "";
    text(noAction, "No action / ask user");
    elements.orchestratorShadowChoice.append(noAction);
    skills.filter((skill) => skill.callable && skill.execution_modes?.includes("physical_shadow")).forEach((skill) => {
      const option = document.createElement("option");
      option.value = skill.skill_id;
      text(option, skill.skill_id);
      elements.orchestratorShadowChoice.append(option);
    });
    if ([...elements.orchestratorShadowChoice.options].some((option) => option.value === previousShadowChoice)) {
      elements.orchestratorShadowChoice.value = previousShadowChoice;
    }
    const waitingForShadowChoice = machineState === "PAUSED" && queue.verification === "awaiting_operator_shadow_choice";
    elements.orchestratorShadowOperator.disabled = !waitingForShadowChoice || state.orchestratorRequestActive;
    elements.orchestratorShadowChoice.disabled = !waitingForShadowChoice || state.orchestratorRequestActive;
    elements.orchestratorShadowNote.disabled = !waitingForShadowChoice || state.orchestratorRequestActive;
    elements.orchestratorShadowSubmit.disabled = !waitingForShadowChoice || !elements.orchestratorShadowOperator.value.trim() || state.orchestratorRequestActive;
    const comparison = runtime.physical_shadow?.latest_comparison;
    const shadowSummary = comparison ? runtime.physical_shadow?.by_proposed_skill?.[comparison.model_proposal?.skill_id] : null;
    text(elements.orchestratorShadowResult, comparison ? `${comparison.exact_choice_match ? "Exact match" : "Choice mismatch"} · ${comparison.operator_identity} · trial ${shadowSummary?.trials || 1}/${shadowSummary?.minimum_supervised_trials || 5} · no hardware command` : "No comparison recorded");
  }
  const readySkills = skills.filter((skill) => skill.callable).length;
  text(elements.orchestratorSkillCount, `${readySkills} ready · ${skills.length} registered`);
  elements.orchestratorSkills.replaceChildren();
  skills.forEach((skill) => {
    const row = document.createElement("div");
    row.className = "orchestrator-skill-row";
    const detail = document.createElement("div");
    const name = document.createElement("b");
    text(name, skill.skill_id);
    const identity = document.createElement("small");
    text(identity, skill.checkpoint_sha256 ? `checkpoint ${skill.checkpoint_sha256.slice(0, 12)} · evaluator ${skill.evaluator_receipt_sha256?.slice(0, 12)} · promotion ${skill.promotion_receipt_sha256?.slice(0, 12)}` : "No promoted checkpoint/evaluator/promotion receipt");
    const runtimeDetail = document.createElement("small");
    const executionModes = skill.execution_modes?.length ? skill.execution_modes.map(formatIdentifier).join(", ") : "unavailable";
    const lastResult = skill.last_result?.status || (skill.last_result?.postcondition_verification?.passed === true ? "verified" : "no result");
    text(runtimeDetail, `mode ${executionModes} · last ${formatIdentifier(lastResult)}`);
    detail.append(name, identity, runtimeDetail);
    const readiness = document.createElement("em");
    text(readiness, formatIdentifier(skill.readiness));
    row.append(detail, readiness);
    elements.orchestratorSkills.append(row);
  });

  const ledger = runtime.ledger || [];
  text(elements.orchestratorLedgerCount, `${ledger.length} events`);
  elements.orchestratorLedger.replaceChildren();
  [...ledger].reverse().forEach((entry) => {
    const row = document.createElement("div");
    row.className = "orchestrator-ledger-row";
    const detail = document.createElement("div");
    const event = document.createElement("b");
    text(event, formatIdentifier(entry.event));
    const summary = document.createElement("small");
    text(summary, orchestratorEventDetail(entry));
    detail.append(event, summary);
    const timestamp = document.createElement("time");
    text(timestamp, entry.recorded_at ? new Date(entry.recorded_at).toLocaleTimeString() : "—");
    row.append(detail, timestamp);
    elements.orchestratorLedger.append(row);
  });
}

async function fetchOrchestrator() {
  if (state.view !== "orchestrator" && state.orchestrator) return;
  try {
    const response = await fetch("/api/orchestrator", { cache: "no-store" });
    if (!response.ok) throw new Error(`orchestrator returned ${response.status}`);
    state.orchestrator = await response.json();
    if (!state.orchestratorRequestActive) state.orchestratorRequestError = null;
  } catch (error) {
    state.orchestratorRequestError = String(error.message || error);
  }
  if (!orchestratorHasActiveTextSelection()) renderOrchestrator();
}

async function postOrchestrator(path, payload) {
  if (state.orchestratorRequestActive) return;
  state.orchestratorRequestActive = true;
  state.orchestratorRequestError = null;
  renderOrchestrator();
  try {
    const response = await fetch(`/api/orchestrator/${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || `orchestrator returned ${response.status}`);
    state.orchestrator = result.orchestrator;
  } catch (error) {
    state.orchestratorRequestError = String(error.message || error);
  } finally {
    state.orchestratorRequestActive = false;
    renderOrchestrator();
  }
}

function setActiveView(view, { updateRoute = true } = {}) {
  const safeView = ["replay", "sail", "library", "calibration", "robots", "orchestrator", "record"].includes(view) ? view : "replay";
  state.view = safeView;
  document.body.dataset.view = safeView;
  text(elements.mobileNavLabel, safeView === "orchestrator" ? "Tasks" : formatIdentifier(safeView));
  document.querySelector(".masthead")?.classList.remove("nav-open");
  elements.mobileNavToggle?.setAttribute("aria-expanded", "false");
  state.threeViewer?.setActive(safeView === "replay" && state.replayMode === "three");
  state.liveSimViewer?.setActive(
    safeView === "record" && selectedRecorderMode() === "simulation_follower",
  );
  window.Sim2ClawCalibration?.setActive(safeView === "calibration");
  if (safeView === "orchestrator") fetchOrchestrator();
  if (safeView === "sail" && !state.sail && !state.sailFetchActive) fetchSailObservatory();
  document.querySelectorAll("[data-route]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.route === safeView && button.classList.contains("view-button"));
  });
  elements.browserRail.classList.remove("is-mobile-open");
  elements.mobileBrowserToggle.setAttribute("aria-expanded", "false");
  if (updateRoute) history.replaceState(null, "", `#/${safeView}`);
  window.scrollTo({ top: 0, behavior: "instant" });
}

function navigate(view) {
  setActiveView(view);
}

function restoreRoute() {
  const parts = location.hash.replace(/^#\//, "").split("/").map(decodeURIComponent);
  const route = parts[0];
  if (route === "tasks" && parts[1] && taskById(parts[1])) {
    setActiveView("replay", { updateRoute: false });
    selectTask(parts[1], { selectLatest: false, updateRoute: false });
    const firstTaskEpisode = filteredEpisodes()[0];
    if (
      firstTaskEpisode
      && selectedEpisode()?.task_id !== parts[1]
    ) {
      selectEpisode(firstTaskEpisode.id, { updateRoute: false });
    }
    return;
  }
  if (route === "episodes" && parts[1] && episodeById(parts[1])) {
    const episode = episodeById(parts[1]);
    setActiveView("replay", { updateRoute: false });
    selectTask(episode.task_id, { selectLatest: false, updateRoute: false });
    selectEpisode(parts[1], { updateRoute: false });
    return;
  }
  if (route === "library" || route === "episodes") {
    setActiveView("library", { updateRoute: false });
    return;
  }
  if (route === "sail") {
    setActiveView("sail", { updateRoute: false });
    return;
  }
  if (route === "robots") {
    setActiveView("robots", { updateRoute: false });
    return;
  }
  if (route === "calibration") {
    setActiveView("calibration", { updateRoute: false });
    return;
  }
  if (route === "orchestrator") {
    setActiveView("orchestrator", { updateRoute: false });
    return;
  }
  if (route === "record") {
    setActiveView("record", { updateRoute: false });
    return;
  }
  setActiveView("replay", { updateRoute: false });
}

function openDrawer(name) {
  const drawers = {
    project: elements.projectMapDrawer,
    live: elements.liveWorkspaceDrawer,
    process: elements.processDrawer,
    twin: elements.twinFidelityDrawer,
    evidence: elements.evidenceDrawer,
  };
  const drawer = drawers[name];
  if (!drawer) return;
  if (state.drawer === "live" && name !== "live") stopLiveWorkspace();
  Object.entries(drawers).forEach(([key, item]) => {
    if (key === name) return;
    item.classList.remove("is-open");
    item.setAttribute("aria-hidden", "true");
  });
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
  elements.drawerBackdrop.hidden = false;
  state.drawer = name;
  state.drawerTrigger = document.activeElement;
  elements.projectMapTrigger.setAttribute("aria-expanded", String(name === "project"));
  elements.liveTrigger.setAttribute("aria-expanded", String(name === "live"));
  elements.twinFidelityTrigger.setAttribute("aria-expanded", String(name === "twin"));
  elements.evidenceTrigger.setAttribute("aria-expanded", String(name === "evidence"));
  if (name === "project") void fetchProjectMap();
  if (name === "live") void startLiveWorkspace();
  drawer.querySelector("button")?.focus({ preventScroll: true });
}

function closeDrawer() {
  if (state.drawer === "live") stopLiveWorkspace();
  elements.projectMapDrawer.classList.remove("is-open");
  elements.liveWorkspaceDrawer.classList.remove("is-open");
  elements.processDrawer.classList.remove("is-open");
  elements.twinFidelityDrawer.classList.remove("is-open");
  elements.evidenceDrawer.classList.remove("is-open");
  elements.projectMapDrawer.setAttribute("aria-hidden", "true");
  elements.liveWorkspaceDrawer.setAttribute("aria-hidden", "true");
  elements.processDrawer.setAttribute("aria-hidden", "true");
  elements.twinFidelityDrawer.setAttribute("aria-hidden", "true");
  elements.evidenceDrawer.setAttribute("aria-hidden", "true");
  elements.drawerBackdrop.hidden = true;
  elements.projectMapTrigger.setAttribute("aria-expanded", "false");
  elements.liveTrigger.setAttribute("aria-expanded", "false");
  elements.twinFidelityTrigger.setAttribute("aria-expanded", "false");
  elements.evidenceTrigger.setAttribute("aria-expanded", "false");
  const trigger = state.drawerTrigger;
  state.drawer = null;
  state.drawerTrigger = null;
  trigger?.focus({ preventScroll: true });
}

function setQuery(value) {
  state.query = value;
  if (elements.search.value !== value) elements.search.value = value;
  if (elements.librarySearch.value !== value) elements.librarySearch.value = value;
  renderRailEpisodes();
  renderLibrary();
}

elements.video.addEventListener("loadedmetadata", () => {
  if (elements.video.videoWidth && elements.video.videoHeight) {
    elements.stage.style.setProperty("--stage-ratio", `${elements.video.videoWidth} / ${elements.video.videoHeight}`);
  }
  const episode = selectedEpisode();
  const feed = activeRecordingFeed(episode);
  state.recordingWindow = feedWindow(feed, elements.video.duration || 0);
  if (state.recordingWindow.start > 0 && Math.abs(elements.video.currentTime - state.recordingWindow.start) > 0.05) {
    elements.video.currentTime = state.recordingWindow.start;
  }
  renderTimelineTicks(episode);
  drawVisualTwinFrame();
});
elements.frame.addEventListener("load", () => {
  if (elements.frame.naturalWidth && elements.frame.naturalHeight) {
    elements.stage.style.setProperty("--stage-ratio", `${elements.frame.naturalWidth} / ${elements.frame.naturalHeight}`);
  }
});
elements.video.addEventListener("timeupdate", () => {
  if (state.replayMode === "three") return;
  const windowRange = state.recordingWindow || feedWindow(activeRecordingFeed(), elements.video.duration || 0);
  if (windowRange.duration > 0 && elements.video.currentTime >= windowRange.end - 0.01) {
    elements.video.currentTime = windowRange.end;
    elements.video.pause();
  }
  const current = Math.max(0, elements.video.currentTime - windowRange.start);
  const fraction = windowRange.duration ? current / windowRange.duration : 0;
  if (state.replayMode === "compare" && selectedEpisode()?.inspection) {
    state.threeViewer?.setFraction(fraction);
  }
  updateProgress(fraction, current);
  drawVisualTwinFrame();
});
elements.video.addEventListener("play", () => {
  if (state.replayMode === "three") return;
  elements.play.classList.add("is-playing");
  elements.play.setAttribute("aria-label", "Pause episode");
  startVisualTwinLoop();
});
elements.video.addEventListener("pause", () => {
  if (state.replayMode === "three") return;
  elements.play.classList.remove("is-playing");
  elements.play.setAttribute("aria-label", "Play episode");
  stopVisualTwinLoop();
  drawVisualTwinFrame();
});
elements.video.addEventListener("ended", () => elements.play.classList.remove("is-playing"));
elements.play.addEventListener("click", togglePlayback);
elements.stage.addEventListener("dblclick", togglePlayback);
elements.stage.addEventListener("keydown", (event) => {
  if (event.key === " ") {
    event.preventDefault();
    togglePlayback();
  } else if (event.key === "ArrowLeft") {
    event.preventDefault();
    jumpSeconds(-5);
  } else if (event.key === "ArrowRight") {
    event.preventDefault();
    jumpSeconds(5);
  } else if (event.key === ",") {
    event.preventDefault();
    stepFrames(-1);
  } else if (event.key === ".") {
    event.preventDefault();
    stepFrames(1);
  }
});
elements.jumpBack.addEventListener("click", () => performPrimaryStep(-1));
elements.jumpForward.addEventListener("click", () => performPrimaryStep(1));
elements.speed.addEventListener("click", cycleSpeed);
elements.scrubber.addEventListener("input", () => seekFraction(Number(elements.scrubber.value) / 1000));
elements.sailScrubber?.addEventListener("input", () => {
  state.sailFrameIndex = Number(elements.sailScrubber.value);
  renderSailFrame();
});
elements.sailOpenReplay?.addEventListener("click", () => {
  const sailEpisode = selectedSailEpisode();
  if (!sailEpisode?.inspection || !state.catalog) return;
  const replay = state.catalog.episodes.find((episode) => episode.action_array_sha256 === sailEpisode.action_array_sha256);
  if (!replay) return;
  setActiveView("replay", { updateRoute: false });
  selectTask(replay.task_id, { selectLatest: false, updateRoute: false });
  selectEpisode(replay.id);
});
elements.replayModeSwitch.querySelectorAll("[data-replay-mode]").forEach((button) => {
  button.addEventListener("click", () => {
    if (button.dataset.replayMode === "recorded") {
      setVisualTwinMode("real", { updateReplay: false });
    } else if (button.dataset.replayMode === "visual") {
      setVisualTwinMode("twin", { updateReplay: false });
    } else if (button.dataset.replayMode === "compare") {
      setVisualTwinMode("split", { updateReplay: false });
    }
    setReplayMode(button.dataset.replayMode);
  });
});
elements.visualTwinToolbar.querySelectorAll("[data-visual-mode]").forEach((button) => {
  button.addEventListener("click", () => setVisualTwinMode(button.dataset.visualMode));
});
elements.visualTwinReveal.addEventListener("input", () => {
  state.visualTwinReveal = Number(elements.visualTwinReveal.value);
  if (state.visualTwinMode !== "split") {
    setVisualTwinMode("split", { updateReplay: state.replayMode !== "compare" });
  } else {
    updateVisualTwinSeam();
  }
});
elements.video.addEventListener("loadeddata", drawVisualTwinFrame);
elements.video.addEventListener("seeked", drawVisualTwinFrame);
window.addEventListener("resize", () => {
  updateVisualTwinSeam();
  drawVisualTwinFrame();
});
elements.threeReset.addEventListener("click", () => state.threeViewer?.resetCamera());
elements.liveSimulationReset.addEventListener("click", () => state.liveSimViewer?.resetCamera());
elements.liveWorkspaceReset.addEventListener("click", () => state.liveWorkspaceViewer?.resetCamera());
document.querySelectorAll("[data-live-mode]").forEach((button) => {
  button.addEventListener("click", () => setLiveWorkspaceMode(button.dataset.liveMode));
});
document.querySelectorAll(".live-camera-card").forEach((card) => {
  const image = card.querySelector("img");
  image.addEventListener("load", () => {
    if (
      state.drawer !== "live"
      || state.liveWorkspaceMode !== "cameras"
      || image.dataset.session !== state.liveWorkspaceSession
      || !image.src.includes("/api/live/cameras/")
    ) return;
    card.classList.add("is-streaming");
    text(card.querySelector("figcaption em"), "Live");
    text(card.querySelector(".live-camera-frame > span"), "Live stream");
  });
  image.addEventListener("error", () => {
    if (!image.hasAttribute("src")) return;
    card.classList.remove("is-streaming");
    text(card.querySelector("figcaption em"), "Unavailable");
    text(card.querySelector(".live-camera-frame > span"), "Stream unavailable");
  });
});
elements.timeline.addEventListener("pointermove", updateTimelinePreview);
elements.timeline.addEventListener("pointerleave", () => { elements.preview.hidden = true; });
elements.search.addEventListener("input", () => setQuery(elements.search.value));
elements.librarySearch.addEventListener("input", () => setQuery(elements.librarySearch.value));
elements.projectMapTrigger.addEventListener("click", () => openDrawer("project"));
elements.liveTrigger.addEventListener("click", () => openDrawer("live"));
document.querySelector("#live-strip-open").addEventListener("click", () => openDrawer("process"));
elements.twinFidelityTrigger.addEventListener("click", () => openDrawer("twin"));
elements.evidenceTrigger.addEventListener("click", () => openDrawer("evidence"));
elements.drawerBackdrop.addEventListener("click", closeDrawer);
document.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", closeDrawer));
elements.mobileBrowserToggle.addEventListener("click", () => {
  const open = !elements.browserRail.classList.contains("is-mobile-open");
  elements.browserRail.classList.toggle("is-mobile-open", open);
  elements.mobileBrowserToggle.setAttribute("aria-expanded", String(open));
  if (open) elements.browserRail.scrollIntoView({ behavior: "smooth", block: "start" });
});
elements.mobileNavToggle?.addEventListener("click", () => {
  const masthead = document.querySelector(".masthead");
  const open = !masthead.classList.contains("nav-open");
  masthead.classList.toggle("nav-open", open);
  elements.mobileNavToggle.setAttribute("aria-expanded", String(open));
});
elements.railClose.addEventListener("click", () => {
  elements.browserRail.classList.remove("is-mobile-open");
  elements.mobileBrowserToggle.setAttribute("aria-expanded", "false");
});
document.querySelectorAll('input[name="recorder-mode"]').forEach((input) => input.addEventListener("change", () => {
  const reverseDefaults = input.checked && input.value === "physical_follower"
    ? reversePhysicalRecorderDefaults
    : {};
  refreshRecorderSquareOptions(reverseDefaults.source_square, reverseDefaults.target_square);
  persistRecorderSettings();
  renderRecorder();
  state.liveSimViewer?.setActive(
    state.view === "record" && selectedRecorderMode() === "simulation_follower",
  );
  refreshLiveSimulation();
}));
elements.physicalSafetyAck.addEventListener("change", renderRecorder);
elements.sourceSquare.addEventListener("change", () => {
  updateDestinationOptions();
  state.pawnBoardSelectionStep = "source";
  renderPawnMovePreview();
  persistRecorderSettings();
});
elements.target.addEventListener("change", () => {
  state.pawnBoardSelectionStep = "source";
  renderPawnMovePreview();
  persistRecorderSettings();
});
elements.pawnPreviewBoard.addEventListener("click", (event) => {
  const cell = event.target.closest("button[data-square]");
  if (!cell || cell.disabled) return;
  selectPawnBoardSquare(cell.dataset.square);
});
elements.sampleHz.addEventListener("change", () => {
  text(elements.recordRate, `${elements.sampleHz.value} Hz`);
  persistRecorderSettings();
});
elements.refreshPreflight.addEventListener("click", () => postRecorder("preflight"));
elements.verifyGateway.addEventListener("click", () => postRecorder("gateway-preflight"));
elements.syncFollower.addEventListener("click", syncPhysicalFollower);
elements.startRecording.addEventListener("click", beginRecording);
elements.stopRecording.addEventListener("click", () => postRecorder("stop"));
elements.runSimReplay.addEventListener("click", () => postRecorder("sim-replay"));
elements.labelForm.addEventListener("submit", (event) => {
  event.preventDefault();
  postRecorder("finalize", {
    label: elements.recordLabel.value,
    skill: elements.recordSkill.value,
    outcome: elements.recordOutcome.value,
    notes: elements.recordNotes.value,
  });
});
elements.discardRecording.addEventListener("click", () => {
  const failed = state.recorder?.status === "error";
  if (failed) {
    postRecorder("discard");
    return;
  }
  if (!state.discardConfirmationArmed) {
    state.discardConfirmationArmed = true;
    if (state.discardConfirmationTimer) window.clearTimeout(state.discardConfirmationTimer);
    state.discardConfirmationTimer = window.setTimeout(() => {
      state.discardConfirmationArmed = false;
      state.discardConfirmationTimer = null;
      renderRecorder();
    }, 5000);
    renderRecorder();
    return;
  }
  state.discardConfirmationArmed = false;
  if (state.discardConfirmationTimer) window.clearTimeout(state.discardConfirmationTimer);
  state.discardConfirmationTimer = null;
  postRecorder("discard");
});
elements.orchestratorStart.addEventListener("click", () => postOrchestrator("session", {
  action: "start",
  mode: elements.orchestratorMode.value,
  polling_interval_seconds: Number(elements.orchestratorPolling.value),
}));
elements.orchestratorPause.addEventListener("click", () => postOrchestrator("session", { action: "pause" }));
elements.orchestratorResume.addEventListener("click", () => postOrchestrator("session", { action: "resume" }));
elements.orchestratorStop.addEventListener("click", () => postOrchestrator("session", { action: "stop" }));
elements.orchestratorRefresh.addEventListener("click", () => postOrchestrator(
  state.orchestrator?.state === "STOPPED" ? "preview" : "refresh",
  {},
));
elements.orchestratorCopy.addEventListener("click", copyOrchestratorText);
elements.orchestratorPolling.addEventListener("change", () => {
  if (state.orchestrator?.state === "STOPPED") return;
  postOrchestrator("session", {
    action: "configure",
    polling_interval_seconds: Number(elements.orchestratorPolling.value),
  });
});
elements.orchestratorChatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = elements.orchestratorChat.value.trim();
  if (!message) return;
  postOrchestrator("chat", { message });
  elements.orchestratorChat.value = "";
});
elements.orchestratorShadowOperator.addEventListener("input", renderOrchestrator);
elements.orchestratorShadowReview.addEventListener("submit", (event) => {
  event.preventDefault();
  const operatorIdentity = elements.orchestratorShadowOperator.value.trim();
  if (!operatorIdentity) return;
  postOrchestrator("shadow-choice", {
    skill_id: elements.orchestratorShadowChoice.value || null,
    operator_identity: operatorIdentity,
    note: elements.orchestratorShadowNote.value.trim(),
  });
});
elements.orchestratorFrame.addEventListener("error", () => {
  elements.orchestratorFrame.hidden = true;
  elements.orchestratorFrameEmpty.hidden = false;
  text(elements.orchestratorFrameEmpty, "Accepted frame unavailable");
});
document.querySelectorAll("[data-route]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.route)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.drawer) closeDrawer();
  if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
    event.preventDefault();
    const target = state.view === "library"
      ? elements.librarySearch
      : state.view === "orchestrator"
        ? elements.orchestratorChat
        : elements.search;
    target.focus();
  }
});
window.addEventListener("hashchange", restoreRoute);
window.addEventListener("pagehide", () => stopLiveWorkspace({ useBeacon: true }));

initializeRecorderForm();
fetchHealth().finally(() => {
  fetchCatalog({ initial: true }).then(restoreRoute);
  fetchProjectMap();
  fetchSailObservatory();
  fetchRecorder();
  fetchLiveWorkspaceStatus();
  fetchOrchestrator();
  refreshLiveSimulation();
});
window.setInterval(() => fetchCatalog(), 2000);
window.setInterval(() => fetchRecorder(), 500);
window.setInterval(() => fetchLiveWorkspaceStatus(), 5000);
window.setInterval(() => fetchOrchestrator(), 1000);
window.setInterval(() => refreshLiveWorkspace(), 100);
window.setInterval(() => refreshLiveSimulation(), 50);
