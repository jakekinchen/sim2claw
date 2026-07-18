import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/addons/controls/OrbitControls.js";
import { STLLoader } from "./vendor/three/addons/loaders/STLLoader.js";

const WXYZ = (values) => new THREE.Quaternion(values[1], values[2], values[3], values[0]);

class ThreeReplayViewer {
  constructor({ canvas, status }) {
    this.canvas = canvas;
    this.status = status;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;

    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(0x111315);
    this.scene.fog = new THREE.FogExp2(0x111315, 0.045);
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.005, 30);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.07;
    this.controls.screenSpacePanning = true;
    this.controls.minDistance = 0.08;
    this.controls.maxDistance = 8;

    this.scene.add(new THREE.HemisphereLight(0xe8f0ff, 0x5b4634, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.4);
    key.position.set(-1.5, -2.2, 3.8);
    this.scene.add(key);
    const fill = new THREE.DirectionalLight(0xffb588, 1.4);
    fill.position.set(2.5, 1.2, 1.6);
    this.scene.add(fill);

    this.sceneRoot = new THREE.Group();
    this.scene.add(this.sceneRoot);
    this.contactRoot = new THREE.Group();
    this.scene.add(this.contactRoot);
    this.contactMarkers = [];
    this.bodyGroups = new Map();
    this.bodyTraceIndices = [];
    this.trace = null;
    this.manifest = null;
    this.liveSceneUrl = null;
    this.liveBodyKey = null;
    this.currentTime = 0;
    this.playing = false;
    this.playbackRate = 1;
    this.lastWallTime = performance.now();
    this.onTime = null;
    this.onPlayState = null;
    this.cameraHome = null;
    this.renderWidth = 0;
    this.renderHeight = 0;

    this.raycaster = new THREE.Raycaster();
    this.pointer = new THREE.Vector2();
    this.pointerStart = null;
    canvas.addEventListener("pointerdown", (event) => {
      this.pointerStart = [event.clientX, event.clientY];
    });
    canvas.addEventListener("pointerup", (event) => this.pick(event));
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas.parentElement);
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  setStatus(message) {
    if (this.status) this.status.textContent = message;
  }

  async load(inspection) {
    this.pause();
    this.currentTime = 0;
    this.setStatus("Loading MuJoCo scene…");
    const [sceneResponse, traceResponse] = await Promise.all([
      fetch(inspection.scene_url, { cache: "no-store" }),
      fetch(inspection.trace_url, { cache: "no-store" }),
    ]);
    if (!sceneResponse.ok || !traceResponse.ok) {
      throw new Error("The scene manifest or episode trace could not be loaded.");
    }
    const [manifest, trace] = await Promise.all([
      sceneResponse.json(),
      traceResponse.json(),
    ]);
    if (manifest.schema_version !== "sim2claw.mujoco_scene_manifest.v1") {
      throw new Error("Unsupported MuJoCo scene manifest.");
    }
    if (trace.schema_version !== "sim2claw.mujoco_body_state_trace.v1") {
      throw new Error("Unsupported MuJoCo episode trace.");
    }
    if (
      trace.scene?.manifest_revision_sha256 &&
      trace.scene.manifest_revision_sha256 !== manifest.revision_sha256
    ) {
      throw new Error("Episode trace and scene manifest revisions do not match.");
    }

    this.clearScene();
    this.manifest = manifest;
    this.trace = trace;
    await this.buildScene();
    this.bodyTraceIndices = trace.body_names.map((name) => this.bodyGroups.get(name) || null);
    this.buildContactMarkers();
    this.resetCamera();
    this.applyTime(0);
    this.setStatus(
      `${trace.frame_count} MuJoCo states · ${Number(trace.fps).toFixed(0)} Hz · drag to orbit`,
    );
  }

  async loadLive({ scene_url: sceneUrl, manifest_revision_sha256: expectedRevision }) {
    if (!sceneUrl) throw new Error("The live simulator did not publish a scene URL.");
    if (this.liveSceneUrl === sceneUrl && this.manifest) return;
    this.pause();
    this.setStatus("Loading live MuJoCo scene…");
    const response = await fetch(sceneUrl, { cache: "no-store" });
    if (!response.ok) throw new Error("The live MuJoCo scene could not be loaded.");
    const manifest = await response.json();
    if (manifest.schema_version !== "sim2claw.mujoco_scene_manifest.v1") {
      throw new Error("Unsupported live MuJoCo scene manifest.");
    }
    if (expectedRevision && expectedRevision !== manifest.revision_sha256) {
      throw new Error("The live simulator and browser scene revisions do not match.");
    }
    this.clearScene();
    this.trace = null;
    this.manifest = manifest;
    this.liveSceneUrl = sceneUrl;
    this.liveBodyKey = null;
    await this.buildScene();
    this.resetCamera();
    this.setStatus("Simulator ready · waiting for Start");
  }

  applyLiveState(liveState) {
    const frame = liveState?.frame;
    const bodyNames = liveState?.body_names || [];
    if (!this.manifest || !frame || !bodyNames.length) return;
    const bodyKey = bodyNames.join("\u0000");
    if (bodyKey !== this.liveBodyKey) {
      this.bodyTraceIndices = bodyNames.map((name) => this.bodyGroups.get(name) || null);
      this.liveBodyKey = bodyKey;
    }
    const position = new THREE.Vector3();
    const quaternion = new THREE.Quaternion();
    this.bodyTraceIndices.forEach((group, index) => {
      if (!group) return;
      position.fromArray(frame.p, index * 3);
      const qIndex = index * 4;
      quaternion.set(
        frame.q[qIndex + 1],
        frame.q[qIndex + 2],
        frame.q[qIndex + 3],
        frame.q[qIndex],
      );
      group.position.copy(position);
      group.quaternion.copy(quaternion);
    });
    this.updateContacts(frame.c);
    this.setStatus(
      liveState.active
        ? `LIVE · state ${Number(liveState.frame_index) + 1} · drag to orbit`
        : `Last simulator state · ${Number(frame.t || 0).toFixed(2)}s · drag to orbit`,
    );
  }

  clearScene() {
    for (const child of [...this.sceneRoot.children]) {
      child.traverse((object) => {
        object.geometry?.dispose?.();
        if (Array.isArray(object.material)) object.material.forEach((value) => value.dispose());
        else object.material?.dispose?.();
      });
      this.sceneRoot.remove(child);
    }
    for (const marker of this.contactMarkers) {
      marker.geometry.dispose();
      marker.material.dispose();
      this.contactRoot.remove(marker);
    }
    this.contactMarkers = [];
    this.bodyGroups.clear();
  }

  async buildScene() {
    const meshes = new Map(this.manifest.meshes.map((mesh) => [mesh.id, mesh]));
    for (const body of this.manifest.bodies) {
      const group = new THREE.Group();
      group.name = body.name;
      group.userData.bodyName = body.name;
      group.position.fromArray(body.initial_position);
      group.quaternion.copy(WXYZ(body.initial_quaternion_wxyz));
      this.bodyGroups.set(body.name, group);
      this.sceneRoot.add(group);
    }

    const stlLoader = new STLLoader();
    const meshGeometryPromises = new Map();
    const getMeshGeometry = (mesh) => {
      if (!meshGeometryPromises.has(mesh.id)) {
        meshGeometryPromises.set(
          mesh.id,
          stlLoader.loadAsync(mesh.asset_url).then((geometry) => {
            geometry.scale(...mesh.scale);
            geometry.translate(
              -mesh.compiler_position[0],
              -mesh.compiler_position[1],
              -mesh.compiler_position[2],
            );
            geometry.applyQuaternion(WXYZ(mesh.compiler_quaternion_wxyz).conjugate());
            geometry.computeVertexNormals();
            return geometry;
          }),
        );
      }
      return meshGeometryPromises.get(mesh.id);
    };

    for (const geom of this.manifest.geoms) {
      let geometry;
      if (geom.type === "mesh") {
        geometry = (await getMeshGeometry(meshes.get(geom.mesh_id))).clone();
      } else {
        geometry = this.primitiveGeometry(geom);
      }
      if (!geometry) continue;
      const [red, green, blue, alpha] = geom.rgba;
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(red, green, blue),
        roughness: 0.72,
        metalness: geom.type === "mesh" ? 0.08 : 0.02,
        transparent: alpha < 0.999,
        opacity: alpha,
        depthWrite: alpha >= 0.5,
        side: THREE.DoubleSide,
      });
      const object = new THREE.Mesh(geometry, material);
      object.name = geom.name;
      object.position.fromArray(geom.position);
      object.quaternion.copy(WXYZ(geom.quaternion_wxyz));
      object.userData.bodyName = this.manifest.bodies[geom.body_id]?.name;
      object.userData.geomName = geom.name;
      this.manifest.bodies[geom.body_id] &&
        this.bodyGroups.get(this.manifest.bodies[geom.body_id].name)?.add(object);
    }
  }

  primitiveGeometry(geom) {
    const [x, y, z] = geom.size;
    if (geom.type === "box") return new THREE.BoxGeometry(2 * x, 2 * y, 2 * z);
    if (geom.type === "sphere") return new THREE.SphereGeometry(x, 20, 14);
    if (geom.type === "ellipsoid") {
      const geometry = new THREE.SphereGeometry(1, 20, 14);
      geometry.scale(x, y, z);
      return geometry;
    }
    if (geom.type === "cylinder") {
      const geometry = new THREE.CylinderGeometry(x, x, 2 * y, 20);
      geometry.rotateX(Math.PI / 2);
      return geometry;
    }
    if (geom.type === "capsule") {
      const geometry = new THREE.CapsuleGeometry(x, 2 * y, 7, 14);
      geometry.rotateX(Math.PI / 2);
      return geometry;
    }
    if (geom.type === "plane") return new THREE.PlaneGeometry(2 * x, 2 * y);
    return null;
  }

  buildContactMarkers() {
    for (let index = 0; index < 24; index += 1) {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.006, 10, 8),
        new THREE.MeshBasicMaterial({ color: 0xff6a33, transparent: true, opacity: 0.9 }),
      );
      marker.visible = false;
      this.contactMarkers.push(marker);
      this.contactRoot.add(marker);
    }
  }

  resetCamera() {
    if (!this.manifest) return;
    const suggested = this.manifest.suggested_camera;
    const center = new THREE.Vector3().fromArray(
      suggested?.target || this.manifest.model.center,
    );
    const extent = Number(this.manifest.model.extent) || 1;
    const position = suggested
      ? new THREE.Vector3().fromArray(suggested.position)
      : center.clone().add(new THREE.Vector3(0.8, -1.25, 0.72).multiplyScalar(extent));
    this.camera.position.copy(position);
    this.camera.up.set(0, 0, 1);
    this.camera.fov = Number(suggested?.fov_degrees) || 38;
    this.controls.target.copy(center);
    this.camera.near = Math.max(0.002, extent / 1000);
    this.camera.far = Math.max(20, extent * 20);
    this.camera.updateProjectionMatrix();
    this.controls.update();
    this.cameraHome = { position: position.clone(), target: center.clone() };
  }

  applyTime(seconds) {
    if (!this.trace?.frames?.length) return;
    const frames = this.trace.frames;
    const duration = Number(this.trace.duration_seconds) || 0;
    this.currentTime = Math.max(0, Math.min(Number(seconds) || 0, duration));
    let low = 0;
    let high = frames.length - 1;
    while (low < high) {
      const mid = Math.ceil((low + high) / 2);
      if (Number(frames[mid].t) <= this.currentTime) low = mid;
      else high = mid - 1;
    }
    const first = frames[low];
    const second = frames[Math.min(low + 1, frames.length - 1)];
    const span = Math.max(0, Number(second.t) - Number(first.t));
    const alpha = span > 0 ? (this.currentTime - Number(first.t)) / span : 0;
    const firstPosition = new THREE.Vector3();
    const secondPosition = new THREE.Vector3();
    const firstQuaternion = new THREE.Quaternion();
    const secondQuaternion = new THREE.Quaternion();
    this.bodyTraceIndices.forEach((group, index) => {
      if (!group) return;
      firstPosition.fromArray(first.p, index * 3);
      secondPosition.fromArray(second.p, index * 3);
      group.position.copy(firstPosition).lerp(secondPosition, alpha);
      const qIndex = index * 4;
      firstQuaternion.set(first.q[qIndex + 1], first.q[qIndex + 2], first.q[qIndex + 3], first.q[qIndex]);
      secondQuaternion.set(second.q[qIndex + 1], second.q[qIndex + 2], second.q[qIndex + 3], second.q[qIndex]);
      group.quaternion.copy(firstQuaternion).slerp(secondQuaternion, alpha);
    });
    this.updateContacts(alpha < 0.5 ? first.c : second.c);
    this.onTime?.({
      current: this.currentTime,
      duration,
      fraction: duration > 0 ? this.currentTime / duration : 0,
      phase: alpha < 0.5 ? first.phase : second.phase,
    });
  }

  updateContacts(contacts = []) {
    this.contactMarkers.forEach((marker, index) => {
      const contact = contacts[index];
      marker.visible = Boolean(contact);
      if (contact) marker.position.set(contact[2], contact[3], contact[4]);
    });
  }

  setFraction(fraction) {
    const duration = Number(this.trace?.duration_seconds) || 0;
    this.applyTime(Math.max(0, Math.min(1, Number(fraction) || 0)) * duration);
  }

  play() {
    if (!this.trace) return;
    if (this.currentTime >= Number(this.trace.duration_seconds) - 1e-6) this.applyTime(0);
    this.playing = true;
    this.lastWallTime = performance.now();
    this.onPlayState?.(true);
  }

  pause() {
    if (!this.playing) return;
    this.playing = false;
    this.onPlayState?.(false);
  }

  toggle() {
    if (this.playing) this.pause();
    else this.play();
  }

  step(direction) {
    this.pause();
    const step = 1 / Math.max(1, Number(this.trace?.fps) || 30);
    this.applyTime(this.currentTime + Math.sign(direction || 1) * step);
  }

  setRate(rate) {
    this.playbackRate = Number(rate) || 1;
  }

  pick(event) {
    if (!this.pointerStart || !this.trace) return;
    if (Math.hypot(event.clientX - this.pointerStart[0], event.clientY - this.pointerStart[1]) > 4) return;
    const bounds = this.canvas.getBoundingClientRect();
    this.pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
    this.pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
    this.raycaster.setFromCamera(this.pointer, this.camera);
    const hit = this.raycaster.intersectObjects([...this.sceneRoot.children], true)[0];
    if (hit) {
      this.setStatus(`${hit.object.userData.bodyName || "body"} · ${hit.object.userData.geomName || "geometry"}`);
    }
  }

  resize() {
    const parent = this.canvas.parentElement;
    const width = Math.max(1, parent.clientWidth);
    const height = Math.max(1, parent.clientHeight);
    if (this.renderWidth !== width || this.renderHeight !== height) {
      this.renderWidth = width;
      this.renderHeight = height;
      this.renderer.setSize(width, height, false);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    }
  }

  animate(wallTime) {
    const delta = Math.min(0.1, Math.max(0, (wallTime - this.lastWallTime) / 1000));
    this.lastWallTime = wallTime;
    if (this.playing && this.trace) {
      const duration = Number(this.trace.duration_seconds) || 0;
      const next = this.currentTime + delta * this.playbackRate;
      if (next >= duration) {
        this.applyTime(duration);
        this.pause();
      } else {
        this.applyTime(next);
      }
    }
    this.controls.update();
    this.resize();
    this.renderer.render(this.scene, this.camera);
    requestAnimationFrame(this.animate);
  }
}

window.Sim2Claw3D = { ThreeReplayViewer };
window.dispatchEvent(new CustomEvent("sim2claw-3d-ready"));
