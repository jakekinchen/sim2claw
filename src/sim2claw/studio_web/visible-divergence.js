const state = {
  proof: null,
  playing: false,
  speedIndex: 1,
  speeds: [0.5, 1, 2],
  syncing: false,
};

const physical = document.querySelector("#physical-video");
const simulator = document.querySelector("#simulator-video");
const playToggle = document.querySelector("#play-toggle");
const scrubber = document.querySelector("#scrubber");
const playhead = document.querySelector("#playhead");
const timecode = document.querySelector("#timecode");
const sampleNumber = document.querySelector("#sample-number");
const markerLayer = document.querySelector("#marker-layer");
const divergenceBand = document.querySelector("#divergence-band");
const speedToggle = document.querySelector("#speed-toggle");

function formatTime(seconds) {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const remainder = safe - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${remainder.toFixed(2).padStart(5, "0")}`;
}

function frameFromTime(seconds) {
  if (!state.proof) return 0;
  return Math.min(
    state.proof.timeline.frame_count - 1,
    Math.max(0, Math.round(seconds * state.proof.timeline.fps)),
  );
}

function renderPlayhead() {
  if (!state.proof) return;
  const frame = frameFromTime(physical.currentTime);
  const percent = frame / (state.proof.timeline.frame_count - 1) * 100;
  scrubber.value = String(frame);
  playhead.style.left = `${percent}%`;
  sampleNumber.textContent = String(frame);
  timecode.textContent = formatTime(frame / state.proof.timeline.fps);
}

function synchronize(force = false) {
  if (state.syncing || !state.proof) return;
  const delta = simulator.currentTime - physical.currentTime;
  if (force || Math.abs(delta) > 0.04) {
    state.syncing = true;
    simulator.currentTime = physical.currentTime;
    state.syncing = false;
  }
}

async function setPlaying(next) {
  state.playing = Boolean(next);
  playToggle.classList.toggle("is-playing", state.playing);
  playToggle.querySelector("span").textContent = state.playing ? "Pause both" : "Play both";
  playToggle.setAttribute("aria-label", state.playing ? "Pause both videos" : "Play both videos");
  if (state.playing) {
    synchronize(true);
    try {
      await Promise.all([physical.play(), simulator.play()]);
    } catch {
      state.playing = false;
      playToggle.classList.remove("is-playing");
      playToggle.querySelector("span").textContent = "Play both";
    }
  } else {
    physical.pause();
    simulator.pause();
  }
}

function seekFrame(frame) {
  if (!state.proof) return;
  const next = Math.min(
    state.proof.timeline.frame_count - 1,
    Math.max(0, Number(frame) || 0),
  );
  const seconds = next / state.proof.timeline.fps;
  physical.currentTime = seconds;
  simulator.currentTime = seconds;
  renderPlayhead();
}

function renderProof(proof) {
  state.proof = proof;
  physical.src = proof.media.physical.url;
  simulator.src = proof.media.simulator.url;
  document.querySelector("#artifact-id").textContent = proof.artifact_sha256.slice(0, 16);

  const start = proof.registered_planar_endpoints.initial.pixel_error;
  const finish = proof.registered_planar_endpoints.terminal.pixel_error;
  document.querySelector("#start-error").textContent = `${start.toFixed(2)} px`;
  document.querySelector("#finish-error").textContent = `${finish.toFixed(2)} px`;
  document.querySelector("#split-time").textContent =
    `${proof.divergence_boundary.seconds[0].toFixed(2)}–${proof.divergence_boundary.seconds[1].toFixed(2)} s`;
  document.querySelector("#interpretation-copy").textContent =
    proof.registered_planar_endpoints.interpretation;

  const denominator = proof.timeline.frame_count - 1;
  const [startSample, endSample] = proof.divergence_boundary.sample_interval;
  divergenceBand.style.left = `${startSample / denominator * 100}%`;
  divergenceBand.style.width = `${(endSample - startSample) / denominator * 100}%`;
  markerLayer.replaceChildren(...proof.markers.map((marker) => {
    const element = document.createElement("i");
    element.className = `marker ${marker.tone}`;
    element.style.left = `${marker.sample / denominator * 100}%`;
    element.dataset.label = `${marker.sample} · ${marker.label}`;
    return element;
  }));
  renderPlayhead();
}

async function loadProof() {
  try {
    const response = await fetch("/api/visible-divergence", { cache: "no-store" });
    const payload = await response.json();
    if (!response.ok || !payload.available) {
      throw new Error(payload.error || "Receipt did not verify");
    }
    renderProof(payload);
  } catch (error) {
    document.querySelector("#comparison").hidden = true;
    document.querySelector(".transport").hidden = true;
    document.querySelector("#unavailable").hidden = false;
    document.querySelector("#unavailable-detail").textContent = String(error.message || error);
  }
}

playToggle.addEventListener("click", () => setPlaying(!state.playing));
document.querySelector("#step-back").addEventListener("click", () => {
  setPlaying(false);
  seekFrame(frameFromTime(physical.currentTime) - 1);
});
document.querySelector("#step-forward").addEventListener("click", () => {
  setPlaying(false);
  seekFrame(frameFromTime(physical.currentTime) + 1);
});
document.querySelector("#jump-divergence").addEventListener("click", () => {
  setPlaying(false);
  seekFrame(state.proof?.divergence_boundary.sample_interval[0] || 0);
});
scrubber.addEventListener("input", () => {
  setPlaying(false);
  seekFrame(Number(scrubber.value));
});
speedToggle.addEventListener("click", () => {
  state.speedIndex = (state.speedIndex + 1) % state.speeds.length;
  const speed = state.speeds[state.speedIndex];
  physical.playbackRate = speed;
  simulator.playbackRate = speed;
  speedToggle.textContent = `${speed}×`;
});
physical.addEventListener("timeupdate", () => {
  synchronize();
  renderPlayhead();
});
physical.addEventListener("ended", () => setPlaying(false));
simulator.addEventListener("seeking", () => renderPlayhead());
document.addEventListener("keydown", (event) => {
  if (event.target instanceof HTMLInputElement || event.target instanceof HTMLButtonElement) return;
  if (event.code === "Space") {
    event.preventDefault();
    setPlaying(!state.playing);
  } else if (event.code === "ArrowLeft") {
    seekFrame(frameFromTime(physical.currentTime) - 1);
  } else if (event.code === "ArrowRight") {
    seekFrame(frameFromTime(physical.currentTime) + 1);
  }
});

loadProof();
