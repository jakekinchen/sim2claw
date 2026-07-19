import * as THREE from "./vendor/three/three.module.min.js";
import { OrbitControls } from "./vendor/three/addons/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "./vendor/spark/spark.module.js";
import {
  buildSceneManifestLayer,
  disposeSceneLayer,
} from "./scene_adapter.js";

const element = (selector) => document.querySelector(selector);

class CalibrationViewer {
  constructor() {
    this.canvas = element("#calibration-canvas");
    this.status = element("#calibration-status");
    this.active = false;
    this.asset = null;
    this.assetSha = null;
    this.mesh = null;
    this.sceneManifestRevision = null;
    this.loadGeneration = 0;

    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: false,
      alpha: false,
      powerPreference: "high-performance",
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.setClearColor(0x0c100e, 1);

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(43, 1, 0.01, 200);
    this.camera.position.set(5.5, 3.8, 6.5);
    this.cameraHome = this.camera.position.clone();
    this.cameraTarget = new THREE.Vector3(0, 0.3, 0);
    this.cameraUp = new THREE.Vector3(0, 1, 0);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.07;
    this.controls.target.copy(this.cameraTarget);

    this.spark = new SparkRenderer({ renderer: this.renderer });
    this.scene.add(this.spark);
    this.transformGroup = new THREE.Group();
    this.normalizationGroup = new THREE.Group();
    this.transformGroup.add(this.normalizationGroup);
    this.scene.add(this.transformGroup);

    this.datum = new THREE.Group();
    const grid = new THREE.GridHelper(10, 20, 0x8aa98f, 0x2c4336);
    grid.material.transparent = true;
    grid.material.opacity = 0.52;
    this.datum.add(grid);
    const axes = new THREE.AxesHelper(2.4);
    axes.material.depthTest = false;
    this.datum.add(axes);
    const boundary = new THREE.LineSegments(
      new THREE.EdgesGeometry(new THREE.BoxGeometry(4.8, 0.03, 3.6)),
      new THREE.LineBasicMaterial({ color: 0xdce6dc, transparent: true, opacity: 0.44 }),
    );
    boundary.position.y = 0.02;
    this.datum.add(boundary);

    this.sceneOverlay = new THREE.Group();
    this.sceneOverlay.name = "accepted-mujoco-scene-overlay";
    // MuJoCo is Z-up; the calibration workspace is Three.js Y-up.
    this.sceneOverlay.rotation.x = -Math.PI / 2;
    this.datum.add(this.sceneOverlay);
    this.scene.add(this.datum);

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(this.canvas.parentElement);
    this.bindControls();
    this.loadScene();
    this.animate();
  }

  setStatus(value) {
    if (this.status) this.status.textContent = value;
  }

  bindControls() {
    document.querySelectorAll("[data-transform]").forEach((input) => {
      input.addEventListener("input", () => this.applyTransform());
    });
    element("#calibration-fit")?.addEventListener("click", () => this.fit());
    element("#calibration-reset")?.addEventListener("click", () => this.reset());
    element("#calibration-frame-toggle")?.addEventListener("click", (event) => {
      this.datum.visible = !this.datum.visible;
      event.currentTarget.setAttribute("aria-pressed", String(this.datum.visible));
      event.currentTarget.textContent = `Simulation datum ${this.datum.visible ? "on" : "off"}`;
    });
    element("#calibration-scene-toggle")?.addEventListener("click", (event) => {
      this.sceneOverlay.visible = !this.sceneOverlay.visible;
      event.currentTarget.setAttribute("aria-pressed", String(this.sceneOverlay.visible));
      event.currentTarget.textContent = `Accepted scene ${this.sceneOverlay.visible ? "on" : "off"}`;
    });
  }

  formatIdentifier(value) {
    return String(value || "—").replaceAll("_", " ");
  }

  populateSceneSynthesis(proposalPayload) {
    const synthesis = proposalPayload?.proposal || {};
    const write = (selector, value) => {
      const node = element(selector);
      if (node) node.textContent = value == null ? "—" : String(value);
    };
    write("#scene-synthesis-status", this.formatIdentifier(synthesis.status));
    write("#scene-synthesis-method", "Display-only LLM analysis · video + 3DGS");
    write("#scene-synthesis-outputs", "Read-only hierarchy · drives no geometry");
    write("#scene-synthesis-revision", String(proposalPayload?.proposal_sha256 || "").slice(0, 12));

    const root = element("#scene-hierarchy");
    if (!root) return;
    root.replaceChildren();
    const renderNode = (node) => {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = node.label || node.id;
      const role = document.createElement("small");
      role.textContent = this.formatIdentifier(node.role);
      item.append(label, role);
      if (node.children?.length) {
        const children = document.createElement("ul");
        node.children.forEach((child) => children.append(renderNode(child)));
        item.append(children);
      }
      return item;
    };
    if (synthesis.hierarchy) root.append(renderNode(synthesis.hierarchy));
  }

  async loadScene() {
    const sceneState = element("#calibration-scene-state");
    if (sceneState) sceneState.textContent = "Loading accepted scene…";
    try {
      const [response, proposalResponse] = await Promise.all([
        fetch("/api/scene?layout=sparse_two_sided_pawns", { cache: "no-store" }),
        fetch("/api/scene-synthesis", { cache: "no-store" }),
      ]);
      if (!response.ok) throw new Error("scene manifest unavailable");
      const manifest = await response.json();
      if (manifest.schema_version !== "sim2claw.mujoco_scene_manifest.v1") {
        throw new Error("unsupported scene manifest");
      }
      if (proposalResponse.ok) {
        this.populateSceneSynthesis(await proposalResponse.json());
      } else {
        this.populateSceneSynthesis(null);
      }
      if (manifest.revision_sha256 !== this.sceneManifestRevision) {
        disposeSceneLayer(this.sceneOverlay);
        await buildSceneManifestLayer({
          root: this.sceneOverlay,
          manifest,
          mode: "calibration_overlay",
        });
        this.sceneManifestRevision = manifest.revision_sha256;
      }
      if (sceneState) {
        sceneState.textContent = `${manifest.model.body_count} bodies · accepted Three.js projection`;
      }
    } catch (error) {
      if (sceneState) sceneState.textContent = `Accepted scene unavailable · ${error?.message || String(error)}`;
      const hierarchy = element("#scene-hierarchy");
      if (hierarchy) hierarchy.textContent = "Scene hierarchy unavailable.";
    }
  }

  transformValue(name) {
    return Number(document.querySelector(`[data-transform="${name}"]`)?.value || 0);
  }

  applyTransform() {
    this.transformGroup.position.set(
      this.transformValue("position-x"),
      this.transformValue("position-y"),
      this.transformValue("position-z"),
    );
    this.transformGroup.rotation.set(
      THREE.MathUtils.degToRad(this.transformValue("rotation-x")),
      THREE.MathUtils.degToRad(this.transformValue("rotation-y")),
      THREE.MathUtils.degToRad(this.transformValue("rotation-z")),
    );
    this.transformGroup.scale.setScalar(this.transformValue("scale") || 1);
    document.querySelectorAll("[data-transform-output]").forEach((output) => {
      const name = output.dataset.transformOutput;
      const value = this.transformValue(name);
      output.textContent = name.startsWith("rotation-")
        ? `${Math.round(value)}°`
        : name === "scale"
        ? `${value.toFixed(2)}×`
        : value.toFixed(2);
    });
  }

  reset() {
    document.querySelectorAll("[data-transform]").forEach((input) => {
      input.value = input.dataset.transform === "scale" ? "1" : "0";
    });
    this.applyTransform();
    this.fit();
  }

  resize() {
    const bounds = this.canvas.getBoundingClientRect();
    const width = Math.max(1, Math.round(bounds.width));
    const height = Math.max(1, Math.round(bounds.height));
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.renderer.setSize(width, height, false);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
    }
  }

  fit() {
    this.controls.target.copy(this.cameraTarget);
    this.camera.position.copy(this.cameraHome);
    this.camera.up.copy(this.cameraUp);
    this.camera.near = 0.01;
    this.camera.far = 200;
    this.camera.updateProjectionMatrix();
    this.controls.update();
  }

  populateMetadata(asset) {
    const model = asset?.model || {};
    const write = (selector, value) => {
      const node = element(selector);
      if (node) node.textContent = value == null ? "—" : String(value);
    };
    write("#calibration-title", asset?.title || "Robo Scanner workcell splat");
    write("#calibration-subtitle", asset?.subtitle || "Verified visual calibration asset");
    write("#calibration-splats", model.splat_count?.toLocaleString?.() || "—");
    write("#calibration-source", asset?.source_name || "—");
    write("#calibration-renderer", asset?.renderer || "Spark · local WebGL2");
    write("#calibration-proof-notice p", asset?.proof_notice || "Visual alignment only; no physical or collision authority.");

    const preview = element("#calibration-preview");
    if (preview) {
      if (asset?.preview?.url) preview.src = asset.preview.url;
      else preview.removeAttribute("src");
    }
    const orbit = element("#calibration-orbit");
    if (orbit) {
      if (asset?.orbit?.url && orbit.src !== new URL(asset.orbit.url, location.href).href) {
        orbit.src = asset.orbit.url;
        orbit.load();
      } else if (!asset?.orbit?.url) {
        orbit.removeAttribute("src");
      }
    }
  }

  async load(asset) {
    this.asset = asset || null;
    this.populateMetadata(asset);
    if (!asset?.model?.url || asset.status !== "ready") {
      this.setStatus("Verified 3DGS release is not available on this device.");
      return;
    }
    if (this.assetSha === asset.model.sha256 && this.mesh) return;

    const generation = ++this.loadGeneration;
    this.assetSha = asset.model.sha256;
    if (this.mesh) {
      this.normalizationGroup.remove(this.mesh);
      this.mesh.dispose();
      this.mesh = null;
    }
    this.setStatus("Loading verified Gaussian splat · 0%");

    try {
      const mesh = new SplatMesh({
        url: asset.model.url,
        onProgress: (event) => {
          if (generation !== this.loadGeneration || !event.lengthComputable) return;
          const percent = Math.min(99, Math.round(100 * event.loaded / event.total));
          this.setStatus(`Loading verified Gaussian splat · ${percent}%`);
        },
      });
      this.normalizationGroup.add(mesh);
      await mesh.initialized;
      if (generation !== this.loadGeneration) {
        this.normalizationGroup.remove(mesh);
        mesh.dispose();
        return;
      }

      const view = asset.studio_view || {};
      const target = Array.isArray(view.preferred_target) && view.preferred_target.length === 3
        ? new THREE.Vector3(...view.preferred_target.map(Number))
        : null;
      const exactCenter = Array.isArray(view.exact_camera_center) && view.exact_camera_center.length === 3
        ? new THREE.Vector3(...view.exact_camera_center.map(Number))
        : null;
      const rotation = view.exact_camera_world_to_camera_rotation;
      if (target && exactCenter && target.toArray().every(Number.isFinite) && exactCenter.toArray().every(Number.isFinite)) {
        mesh.position.copy(target).multiplyScalar(-1);
        this.normalizationGroup.scale.setScalar(1);
        this.cameraHome.copy(exactCenter).sub(target);
        if (Array.isArray(rotation) && rotation.length === 3 && rotation.every((row) => Array.isArray(row) && row.length === 3)) {
          const forward = new THREE.Vector3(...rotation[2].map(Number)).normalize();
          this.cameraTarget.copy(this.cameraHome).addScaledVector(
            forward,
            Number(view.preferred_radius || 4.8),
          );
          this.cameraUp.set(...rotation[1].map((value) => -Number(value))).normalize();
          this.camera.fov = Number(view.exact_camera_vertical_fov_degrees || 43);
        } else {
          this.cameraTarget.set(0, 0, 0);
          this.cameraUp.set(0, 1, 0);
          this.camera.fov = 43;
        }
      } else {
        const bounds = mesh.getBoundingBox(true);
        const center = bounds.getCenter(new THREE.Vector3());
        const size = bounds.getSize(new THREE.Vector3());
        const maximum = Math.max(size.x, size.y, size.z, 0.001);
        mesh.position.copy(center).multiplyScalar(-1);
        this.normalizationGroup.scale.setScalar(4.4 / maximum);
        this.cameraTarget.set(0, 0.3, 0);
        this.cameraHome.set(4.83, 3.02, 5.38);
        this.cameraUp.set(0, 1, 0);
        this.camera.fov = 43;
      }
      this.mesh = mesh;
      this.fit();
      this.setStatus(`${Number(asset.model.splat_count || mesh.numSplats).toLocaleString()} splats · orbit to inspect`);
    } catch (error) {
      if (generation !== this.loadGeneration) return;
      this.assetSha = null;
      this.setStatus(`3DGS unavailable · ${error?.message || String(error)}`);
    }
  }

  setActive(active) {
    this.active = Boolean(active);
    if (this.active) {
      this.resize();
      this.controls.update();
    }
  }

  animate() {
    requestAnimationFrame(() => this.animate());
    if (!this.active) return;
    this.resize();
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

let viewer;
try {
  viewer = new CalibrationViewer();
  window.Sim2ClawCalibration = {
    load: (asset) => viewer.load(asset),
    setActive: (active) => viewer.setActive(active),
  };
} catch (error) {
  const status = element("#calibration-status");
  if (status) status.textContent = `3DGS renderer unavailable · ${error?.message || String(error)}`;
  window.Sim2ClawCalibration = {
    load: () => {},
    setActive: () => {},
  };
}

window.dispatchEvent(new CustomEvent("sim2claw-3dgs-ready"));
