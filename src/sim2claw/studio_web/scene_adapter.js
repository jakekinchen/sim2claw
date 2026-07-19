import * as THREE from "./vendor/three/three.module.min.js";
import { STLLoader } from "./vendor/three/addons/loaders/STLLoader.js";

export const WXYZ = (values) => new THREE.Quaternion(
  values[1], values[2], values[3], values[0],
);

export function primitiveGeometry(geom) {
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

function sceneMaterial(geom, mode) {
  const [red, green, blue, alpha] = geom.rgba;
  if (mode === "calibration_overlay") {
    const color = new THREE.Color(red, green, blue).lerp(new THREE.Color(0x57d39b), 0.42);
    return new THREE.MeshBasicMaterial({
      color,
      transparent: true,
      opacity: Math.min(0.46, Math.max(0.18, alpha * 0.42)),
      depthWrite: false,
      side: THREE.DoubleSide,
    });
  }
  return new THREE.MeshStandardMaterial({
    color: new THREE.Color(red, green, blue),
    roughness: 0.72,
    metalness: geom.type === "mesh" ? 0.08 : 0.02,
    transparent: alpha < 0.999,
    opacity: alpha,
    depthWrite: alpha >= 0.5,
    side: THREE.DoubleSide,
  });
}

export async function buildSceneManifestLayer({ root, manifest, mode = "replay" }) {
  const bodyGroups = new Map();
  const meshes = new Map(manifest.meshes.map((mesh) => [mesh.id, mesh]));
  for (const body of manifest.bodies) {
    const group = new THREE.Group();
    group.name = body.name;
    group.userData.bodyName = body.name;
    group.position.fromArray(body.initial_position);
    group.quaternion.copy(WXYZ(body.initial_quaternion_wxyz));
    bodyGroups.set(body.name, group);
    root.add(group);
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

  for (const geom of manifest.geoms) {
    let geometry;
    if (geom.type === "mesh") geometry = (await getMeshGeometry(meshes.get(geom.mesh_id))).clone();
    else geometry = primitiveGeometry(geom);
    if (!geometry) continue;
    const object = new THREE.Mesh(geometry, sceneMaterial(geom, mode));
    object.name = geom.name;
    object.position.fromArray(geom.position);
    object.quaternion.copy(WXYZ(geom.quaternion_wxyz));
    object.userData.bodyName = manifest.bodies[geom.body_id]?.name;
    object.userData.geomName = geom.name;
    const bodyName = manifest.bodies[geom.body_id]?.name;
    if (bodyName) bodyGroups.get(bodyName)?.add(object);
  }
  return { bodyGroups };
}

export function disposeSceneLayer(root) {
  for (const child of [...root.children]) {
    child.traverse((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((value) => value.dispose());
      else object.material?.dispose?.();
    });
    root.remove(child);
  }
}
