"use strict";

const state = {
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
  expandedTasks: new Set(),
  processHistory: new Map(),
  thumbnailObserver: null,
};

const elements = {
  connection: document.querySelector("#connection-state"),
  campaign: document.querySelector("#campaign-label"),
  passRatio: document.querySelector("#pass-ratio"),
  liveTrigger: document.querySelector("#live-trigger"),
  liveCount: document.querySelector("#live-count"),
  liveStrip: document.querySelector("#live-strip"),
  liveStripTitle: document.querySelector("#live-strip-title"),
  liveStripPhase: document.querySelector("#live-strip-phase"),
  taskFilterList: document.querySelector("#task-filter-list"),
  taskFilterTemplate: document.querySelector("#task-filter-template"),
  railContext: document.querySelector("#rail-context"),
  railResultCount: document.querySelector("#rail-result-count"),
  railEpisodeList: document.querySelector("#rail-episode-list"),
  railEpisodeTemplate: document.querySelector("#rail-episode-template"),
  browserRail: document.querySelector("#browser-rail"),
  mobileBrowserToggle: document.querySelector("#mobile-browser-toggle"),
  railClose: document.querySelector("#rail-close"),
  search: document.querySelector("#episode-search"),
  librarySearch: document.querySelector("#library-search"),
  librarySummary: document.querySelector("#library-summary"),
  libraryGroups: document.querySelector("#library-groups"),
  episodeTemplate: document.querySelector("#episode-template"),
  stage: document.querySelector("#episode-stage"),
  stagePortrait: document.querySelector("#stage-portrait"),
  stageKicker: document.querySelector("#stage-kicker"),
  stageTitle: document.querySelector("#stage-title"),
  stageSubtitle: document.querySelector("#stage-subtitle"),
  stageVerdict: document.querySelector("#stage-verdict"),
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
  metrics: document.querySelector("#metric-strip"),
  evidenceTrigger: document.querySelector("#evidence-trigger"),
  evidenceContent: document.querySelector("#evidence-content"),
  processDrawer: document.querySelector("#process-drawer"),
  evidenceDrawer: document.querySelector("#evidence-drawer"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
  activityList: document.querySelector("#activity-list"),
  simulationCard: document.querySelector("#simulation-card"),
  robotGrid: document.querySelector("#robot-grid"),
};

function text(node, value) {
  if (node) node.textContent = value == null ? "" : String(value);
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
      processes: catalog.processes.map((process) => [process.id, process.pid, process.status, process.phase, process.progress, process.updated_at]),
      robots: catalog.robots.map((robot) => [robot.id, robot.status]),
    });

    renderSummary();
    if (initial || fingerprint !== state.fingerprint) {
      state.fingerprint = fingerprint;
      renderTaskFilters();
      renderRailEpisodes();
      renderLibrary();
      renderSimulation();
      renderRobots();
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

function renderSummary() {
  const { project, summary, processes } = state.catalog;
  text(elements.campaign, formatCampaign(project.active_campaign || "Local simulation workspace"));
  text(elements.passRatio, `${summary.passed_episodes}/${summary.episodes} passed`);
  const active = processes.filter((process) => process.status === "running");
  text(elements.liveCount, `${active.length} live`);
  elements.liveTrigger.classList.toggle("has-live", active.length > 0);
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
  text(elements.railContext, task ? task.title : state.query ? "Search results" : "All episodes");
  text(elements.railResultCount, task || state.query ? episodes.length : "");
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
    row.addEventListener("click", () => selectEpisode(episode.id));
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
    const start = () => {
      if (video.src) return;
      video.src = media.url;
      video.addEventListener("loadedmetadata", () => {
        const offset = 0.28 + (hashString(episode.id) % 38) / 100;
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
      const offset = Math.floor(media.urls.length * (0.45 + (hashString(episode.id) % 30) / 100));
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

function selectEpisode(identifier, { updateRoute = true } = {}) {
  if (!identifier) return;
  const episode = episodeById(identifier);
  if (!episode) return;
  state.selectedEpisodeId = identifier;
  stopFramePlayback();
  elements.video.pause();
  elements.video.removeAttribute("src");
  elements.video.load();
  elements.previewVideo.removeAttribute("src");
  elements.previewVideo.load();
  elements.frame.removeAttribute("src");
  elements.previewFrame.removeAttribute("src");
  elements.stage.classList.remove("has-video", "has-frames");
  elements.preview.className = "timeline-preview";
  elements.preview.hidden = true;
  elements.scrubber.value = "0";
  state.frameIndex = 0;
  state.frameCache.clear();
  updateProgress(0, 0);

  const neutralMetrics = episode.metrics.filter((metric) => !metric.tone || metric.tone === "neutral");
  const inlineFacts = neutralMetrics.slice(0, 2).map((metric) => `${metric.label} ${formatMetric(metric)}`);
  if (episode.fps) inlineFacts.push(`${episode.fps} fps`);
  text(elements.stageKicker, [episode.proof_label, ...inlineFacts].join(" · "));
  text(elements.stageTitle, episodeDisplayTitle(episode));
  text(elements.stageSubtitle, episode.subtitle);
  elements.stageVerdict.className = `stage-verdict ${episode.status}`;
  text(elements.stageVerdict, episode.status === "passed" ? "Evaluator pass" : episode.status);
  drawPhasePortrait(elements.stagePortrait, episode, { stage: true });

  if (episode.media.kind === "video") {
    elements.video.src = episode.media.url;
    elements.video.playbackRate = state.playbackRate;
    elements.previewVideo.src = episode.media.url;
    elements.stage.classList.add("has-video");
    elements.preview.classList.add("has-video");
    elements.video.load();
  } else if (episode.media.kind === "frames" && episode.media.urls.length) {
    elements.frame.src = episode.media.urls[0];
    elements.previewFrame.src = episode.media.urls[0];
    elements.stage.classList.add("has-frames");
    elements.preview.classList.add("has-frame");
    preloadFrameWindow(episode, 0);
  }

  updateTransportSemantics(episode);
  renderMetrics(episode);
  renderPhases(episode.phases || []);
  renderTimelineTicks(episode);
  renderEvidence(episode);
  updateSelectedCardState();
  if (updateRoute) history.replaceState(null, "", `#/episodes/${encodeURIComponent(identifier)}`);
}

function updateTransportSemantics(episode) {
  const frames = episode.media.kind === "frames";
  text(elements.jumpBack, frames ? "−1 frame" : "−5 sec");
  text(elements.jumpForward, frames ? "+1 frame" : "+5 sec");
  elements.jumpBack.setAttribute("aria-label", frames ? "Go back one frame" : "Go back five seconds");
  elements.jumpForward.setAttribute("aria-label", frames ? "Go forward one frame" : "Go forward five seconds");
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
  const duration = episode.media.kind === "frames"
    ? episode.media.urls.length
    : episode.duration_seconds || 0;
  const count = 6;
  for (let index = 0; index < count; index += 1) {
    const tick = document.createElement("i");
    tick.className = "timeline-tick";
    const label = document.createElement("span");
    const value = duration * index / (count - 1);
    text(label, episode.media.kind === "frames" ? `${Math.round(value)}f` : `${Math.round(value)}s`);
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
  if (episode.media.kind === "video") {
    if (elements.video.paused) elements.video.play().catch(() => {});
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
    segment.classList.toggle("is-active", safeFraction >= start && (safeFraction < end || end === 1 && safeFraction === 1));
  });
}

function stepFrames(delta) {
  const episode = selectedEpisode();
  if (!episode || episode.media.kind !== "frames") return;
  showFrame(episode, state.frameIndex + delta);
}

function jumpSeconds(delta) {
  const episode = selectedEpisode();
  if (!episode) return;
  if (episode.media.kind === "video") {
    elements.video.currentTime = Math.max(0, Math.min(elements.video.duration || 0, elements.video.currentTime + delta));
  } else {
    const fps = Number(episode.media.fps || episode.fps || 1);
    stepFrames(Math.round(delta * fps));
  }
}

function performPrimaryStep(direction) {
  const episode = selectedEpisode();
  if (!episode) return;
  if (episode.media.kind === "frames") stepFrames(direction);
  else jumpSeconds(direction * 5);
}

function seekFraction(fraction) {
  const episode = selectedEpisode();
  if (!episode) return;
  const safe = Math.max(0, Math.min(1, fraction));
  if (episode.media.kind === "video") {
    if (Number.isFinite(elements.video.duration)) elements.video.currentTime = safe * elements.video.duration;
  } else {
    showFrame(episode, Math.round(safe * (episode.media.urls.length - 1)));
  }
}

function cycleSpeed() {
  const rates = [0.5, 1, 2];
  state.playbackRate = rates[(rates.indexOf(state.playbackRate) + 1) % rates.length];
  elements.video.playbackRate = state.playbackRate;
  text(elements.speed, `${state.playbackRate}×`);
  if (state.framePlaying) startFramePlayback();
}

function updateTimelinePreview(event) {
  const episode = selectedEpisode();
  if (!episode || window.matchMedia("(hover: none)").matches) return;
  const bounds = elements.timeline.getBoundingClientRect();
  const fraction = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
  elements.preview.hidden = false;
  elements.preview.style.left = `${Math.max(12, Math.min(88, fraction * 100))}%`;
  if (episode.media.kind === "video") {
    const duration = elements.previewVideo.duration || elements.video.duration;
    if (Number.isFinite(duration) && duration > 0) {
      const target = fraction * duration;
      if (Math.abs(elements.previewVideo.currentTime - target) > 0.12) elements.previewVideo.currentTime = target;
      text(elements.previewTimecode, formatTime(target));
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
  const rows = [
    ["Evaluator result", episode.status],
    ["Terminal outcome", formatIdentifier(episode.terminal_outcome || "Not recorded")],
    ["Task", taskById(episode.task_id)?.title || episode.task_id],
    ["Case", formatIdentifier(episode.case_id || "Not recorded")],
    ["Recorded", episode.recorded_at ? new Date(episode.recorded_at).toLocaleString() : "Not recorded"],
    ["Proof class", episode.proof_class],
    ["Media", episode.media.kind === "video" ? "Recorded video" : `${episode.media.urls?.length || 0} rendered frames`],
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
  text(label, "Loaded simulation");
  text(title, simulation.title);
  text(subtitle, simulation.subtitle);
  const facts = document.createElement("div");
  facts.className = "simulation-facts";
  [["Tasks", simulation.task_count], ["Robots", simulation.robot_count], ["State", "Ready"]].forEach(([name, value]) => {
    const fact = document.createElement("span");
    const factValue = document.createElement("b");
    text(fact, name);
    text(factValue, value);
    fact.append(factValue);
    facts.append(fact);
  });
  copy.append(label, title, subtitle, facts);
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
    text(description, "Present in the loaded MuJoCo scene for visual replay and simulation evidence inspection.");
    const specs = document.createElement("dl");
    specs.className = "robot-specs";
    [
      ["Mode", robot.mode],
      ["Scene state", formatIdentifier(robot.status)],
      ["Side", formatIdentifier(robot.side)],
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

function setActiveView(view, { updateRoute = true } = {}) {
  const safeView = ["replay", "library", "robots"].includes(view) ? view : "replay";
  state.view = safeView;
  document.body.dataset.view = safeView;
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
    return;
  }
  if (route === "episodes" && parts[1] && episodeById(parts[1])) {
    setActiveView("replay", { updateRoute: false });
    selectEpisode(parts[1], { updateRoute: false });
    return;
  }
  if (route === "library" || route === "episodes") {
    setActiveView("library", { updateRoute: false });
    return;
  }
  if (route === "robots") {
    setActiveView("robots", { updateRoute: false });
    return;
  }
  setActiveView("replay", { updateRoute: false });
}

function openDrawer(name) {
  const drawer = name === "process" ? elements.processDrawer : elements.evidenceDrawer;
  const other = name === "process" ? elements.evidenceDrawer : elements.processDrawer;
  other.classList.remove("is-open");
  other.setAttribute("aria-hidden", "true");
  drawer.classList.add("is-open");
  drawer.setAttribute("aria-hidden", "false");
  elements.drawerBackdrop.hidden = false;
  state.drawer = name;
  elements.liveTrigger.setAttribute("aria-expanded", String(name === "process"));
  elements.evidenceTrigger.setAttribute("aria-expanded", String(name === "evidence"));
  drawer.querySelector("button")?.focus({ preventScroll: true });
}

function closeDrawer() {
  elements.processDrawer.classList.remove("is-open");
  elements.evidenceDrawer.classList.remove("is-open");
  elements.processDrawer.setAttribute("aria-hidden", "true");
  elements.evidenceDrawer.setAttribute("aria-hidden", "true");
  elements.drawerBackdrop.hidden = true;
  elements.liveTrigger.setAttribute("aria-expanded", "false");
  elements.evidenceTrigger.setAttribute("aria-expanded", "false");
  state.drawer = null;
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
});
elements.frame.addEventListener("load", () => {
  if (elements.frame.naturalWidth && elements.frame.naturalHeight) {
    elements.stage.style.setProperty("--stage-ratio", `${elements.frame.naturalWidth} / ${elements.frame.naturalHeight}`);
  }
});
elements.video.addEventListener("timeupdate", () => {
  const duration = elements.video.duration;
  updateProgress(duration ? elements.video.currentTime / duration : 0, elements.video.currentTime);
});
elements.video.addEventListener("play", () => {
  elements.play.classList.add("is-playing");
  elements.play.setAttribute("aria-label", "Pause episode");
});
elements.video.addEventListener("pause", () => {
  elements.play.classList.remove("is-playing");
  elements.play.setAttribute("aria-label", "Play episode");
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
elements.timeline.addEventListener("pointermove", updateTimelinePreview);
elements.timeline.addEventListener("pointerleave", () => { elements.preview.hidden = true; });
elements.search.addEventListener("input", () => setQuery(elements.search.value));
elements.librarySearch.addEventListener("input", () => setQuery(elements.librarySearch.value));
elements.liveTrigger.addEventListener("click", () => openDrawer("process"));
document.querySelector("#live-strip-open").addEventListener("click", () => openDrawer("process"));
elements.evidenceTrigger.addEventListener("click", () => openDrawer("evidence"));
elements.drawerBackdrop.addEventListener("click", closeDrawer);
document.querySelectorAll("[data-close-drawer]").forEach((button) => button.addEventListener("click", closeDrawer));
elements.mobileBrowserToggle.addEventListener("click", () => {
  const open = !elements.browserRail.classList.contains("is-mobile-open");
  elements.browserRail.classList.toggle("is-mobile-open", open);
  elements.mobileBrowserToggle.setAttribute("aria-expanded", String(open));
  if (open) elements.browserRail.scrollIntoView({ behavior: "smooth", block: "start" });
});
elements.railClose.addEventListener("click", () => {
  elements.browserRail.classList.remove("is-mobile-open");
  elements.mobileBrowserToggle.setAttribute("aria-expanded", "false");
});
document.querySelectorAll("[data-route]").forEach((button) => button.addEventListener("click", () => navigate(button.dataset.route)));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.drawer) closeDrawer();
  if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
    event.preventDefault();
    const target = state.view === "library" ? elements.librarySearch : elements.search;
    target.focus();
  }
});
window.addEventListener("hashchange", restoreRoute);

fetchCatalog({ initial: true }).then(restoreRoute);
window.setInterval(() => fetchCatalog(), 2000);
