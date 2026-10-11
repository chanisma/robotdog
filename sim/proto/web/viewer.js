// 3D 화면: MuJoCo 모델의 시각용 메시로 Lite3 를 만들고, 시뮬레이터가 보내는 바디 자세(frame)를 적용한다.
// 좌표계는 MuJoCo 와 같은 Z-up 을 그대로 쓴다.
import * as THREE from "three";
import { OrbitControls } from "/web/vendor/OrbitControls.js";

const PALETTE = {
  TORSO: { color: 0x2b313b, metalness: 0.35, roughness: 0.45 },
  HIP: { color: 0x3a4250, metalness: 0.4, roughness: 0.4 },
  THIGH: { color: 0x22272f, metalness: 0.3, roughness: 0.5 },
  SHANK: { color: 0x9aa4b2, metalness: 0.55, roughness: 0.35 },
  FOOT: { color: 0x15181d, metalness: 0.1, roughness: 0.8 },
  PAYLOAD: { color: 0xf59e0b, metalness: 0.1, roughness: 0.55 },
};
const COM_COLOR = 0xffd166;
const SUPPORT = { ok: 0x34d399, bad: 0xf87171, two: 0xfbbf24 };

function partOf(bodyName) {
  for (const key of Object.keys(PALETTE)) if (bodyName.includes(key)) return key;
  return "TORSO";
}

export class Viewer {
  constructor(el) {
    this.el = el;
    this.follow = true;
    this.bodies = [];
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    el.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.fog = new THREE.Fog(0x10141a, 5, 14);
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 100);
    this.camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.minDistance = 0.5;
    this.controls.maxDistance = 8;
    this.resetView();

    this._lights();
    this._floor();
    this.target = new THREE.Vector3(0, 0, 0.25);
    this.showCom = true;
    this.payloadMeshes = [];
    this._comVisuals();
    new ResizeObserver(() => this._resize()).observe(el);
    this._resize();
    this.renderer.setAnimationLoop(() => this._tick());
  }

  _lights() {
    this.scene.add(new THREE.HemisphereLight(0xcfe0ff, 0x1a1d22, 0.9));
    const key = new THREE.DirectionalLight(0xffffff, 2.2);
    key.position.set(2.5, -2, 4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    const sc = key.shadow.camera;
    sc.left = -2; sc.right = 2; sc.top = 2; sc.bottom = -2; sc.near = 0.5; sc.far = 12;
    key.shadow.bias = -0.0004;
    key.shadow.radius = 4;
    this.key = key;
    this.scene.add(key, key.target);
    const rim = new THREE.DirectionalLight(0x7aa8ff, 0.8);
    rim.position.set(-3, 3, 2);
    this.scene.add(rim);
  }

  _floor() {
    const ground = new THREE.Mesh(
      new THREE.CircleGeometry(30, 64),
      new THREE.MeshStandardMaterial({ color: 0x161b22, roughness: 0.95, metalness: 0 }));
    ground.receiveShadow = true;
    this.scene.add(ground);
    const grid = new THREE.GridHelper(30, 60, 0x2c3542, 0x212833);
    grid.rotation.x = Math.PI / 2;
    grid.position.z = 0.001;
    this.scene.add(grid);
    const major = new THREE.GridHelper(30, 30, 0x3a4658, 0x2a3341);
    major.rotation.x = Math.PI / 2;
    major.position.z = 0.002;
    major.material.opacity = 0.6;
    major.material.transparent = true;
    this.scene.add(major);
  }

  // 무게중심 점·수직선·바닥 표시와 지지 다각형. 몸에 가려지지 않도록 깊이 검사 없이 맨 위에 그린다.
  _comVisuals() {
    const g = new THREE.Group();
    const top = (m) => { m.depthTest = false; m.transparent = true; return m; };
    this.comDot = new THREE.Mesh(new THREE.SphereGeometry(0.02, 20, 14), top(new THREE.MeshBasicMaterial({ color: COM_COLOR })));
    this.comHalo = new THREE.Mesh(new THREE.SphereGeometry(0.03, 20, 14), top(new THREE.MeshBasicMaterial({ color: 0x000000, opacity: 0.45 })));
    this.comLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]),
      top(new THREE.LineDashedMaterial({ color: COM_COLOR, dashSize: 0.02, gapSize: 0.015 })));
    this.comMark = new THREE.Mesh(new THREE.RingGeometry(0.018, 0.034, 32), top(new THREE.MeshBasicMaterial({ color: COM_COLOR, side: THREE.DoubleSide })));
    this.supFill = new THREE.Mesh(new THREE.BufferGeometry(), top(new THREE.MeshBasicMaterial({ color: SUPPORT.ok, opacity: 0.22, side: THREE.DoubleSide })));
    this.supEdge = new THREE.LineLoop(new THREE.BufferGeometry(), top(new THREE.LineBasicMaterial({ color: SUPPORT.ok })));
    for (const [o, r] of [[this.supFill, 5], [this.supEdge, 6], [this.comLine, 7], [this.comMark, 8], [this.comHalo, 9], [this.comDot, 10]]) {
      o.renderOrder = r;
      o.frustumCulled = false;            // 모양이 매 프레임 바뀌므로 화면 밖 판정(경계 구)을 쓰지 않음
      g.add(o);
    }
    this.comGroup = g;
    this.scene.add(g);
  }

  setComVisible(on) {
    this.showCom = on;
    this.comGroup.visible = on;
  }

  _updateCom(com, sup, margin) {
    if (!com) return;
    const [x, y, z] = com;
    this.comDot.position.set(x, y, z);
    this.comHalo.position.set(x, y, z);
    this.comMark.position.set(x, y, 0.004);
    this.comLine.geometry.setFromPoints([new THREE.Vector3(x, y, z), new THREE.Vector3(x, y, 0.004)]);
    this.comLine.computeLineDistances();
    const color = sup.length === 2 ? SUPPORT.two : margin !== null && margin >= 0 ? SUPPORT.ok : SUPPORT.bad;
    this.supFill.material.color.setHex(color);
    this.supEdge.material.color.setHex(color);
    this.comMark.material.color.setHex(sup.length >= 2 ? color : COM_COLOR);
    const pts = sup.map(([a, b]) => new THREE.Vector3(a, b, 0.003));
    this.supEdge.geometry.setFromPoints(pts);
    if (pts.length >= 3) {
      const idx = [];
      for (let i = 1; i < pts.length - 1; i++) idx.push(0, i, i + 1);
      this.supFill.geometry.setFromPoints(pts);
      this.supFill.geometry.setIndex(idx);
      this.supFill.visible = true;
    } else {
      this.supFill.visible = false;
    }
  }

  async load() {
    const scene = await (await fetch("/api/scene")).json();
    const meshCache = {};
    const loadMesh = async (mid) => {
      if (!meshCache[mid]) {
        meshCache[mid] = fetch(`/api/mesh/${mid}`).then((r) => r.arrayBuffer()).then((buf) => {
          const head = new Uint32Array(buf, 0, 2);
          const [nv, nf] = head;
          const verts = new Float32Array(buf, 8, nv * 3);
          const faces = new Uint32Array(buf, 8 + nv * 12, nf * 3);
          const g = new THREE.BufferGeometry();
          g.setAttribute("position", new THREE.BufferAttribute(verts, 3));
          g.setIndex(new THREE.BufferAttribute(faces, 1));
          g.computeVertexNormals();
          return g;
        });
      }
      return meshCache[mid];
    };
    for (let i = 0; i < scene.nbody; i++) {
      const grp = new THREE.Group();
      grp.matrixAutoUpdate = true;
      this.scene.add(grp);
      this.bodies.push(grp);
    }
    const mats = {};
    for (const [k, v] of Object.entries(PALETTE)) mats[k] = new THREE.MeshStandardMaterial(v);
    for (const g of scene.geoms) {
      const mat = mats[partOf(g.bodyName)];
      let geom;
      if (g.type === "mesh") geom = await loadMesh(g.mesh);
      else if (g.type === "box") geom = new THREE.BoxGeometry(2 * g.size[0], 2 * g.size[1], 2 * g.size[2]);
      else geom = new THREE.SphereGeometry(g.radius, 24, 16);
      const mesh = new THREE.Mesh(geom, mat);
      mesh.position.set(...g.pos);
      mesh.quaternion.set(g.quat[1], g.quat[2], g.quat[3], g.quat[0]);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.bodies[g.body].add(mesh);
      if (g.bodyName === "PAYLOAD") { mesh.visible = false; this.payloadMeshes.push(mesh); }
    }
  }

  // frame: p = [x,y,z]*nbody, q = [w,x,y,z]*nbody (MuJoCo xpos / xquat)
  applyFrame(p, q, extra = {}) {
    for (let i = 0; i < this.bodies.length; i++) {
      const b = this.bodies[i];
      b.position.set(p[3 * i], p[3 * i + 1], p[3 * i + 2]);
      b.quaternion.set(q[4 * i + 1], q[4 * i + 2], q[4 * i + 3], q[4 * i]);
    }
    if (this.bodies[1]) this.target.set(p[3], p[4], Math.max(0.15, p[5] * 0.75));
    for (const m of this.payloadMeshes) m.visible = (extra.pm ?? 0) > 0.05;
    if (this.showCom) this._updateCom(extra.com, extra.sup ?? [], extra.margin ?? null);
  }

  resetView() {
    const t = this.target || new THREE.Vector3(0, 0, 0.25);
    this.camera.position.set(t.x + 0.95, t.y - 1.1, t.z + 0.5);
    this.controls.target.copy(t);
  }

  _resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.renderer.domElement.style.width = w + "px";
    this.renderer.domElement.style.height = h + "px";
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  _tick() {
    if (this.follow) {
      // 로봇을 따라 카메라와 목표점을 함께 부드럽게 옮긴다 (사용자가 돌린 각도는 유지)
      const delta = this.target.clone().sub(this.controls.target).multiplyScalar(0.12);
      this.controls.target.add(delta);
      this.camera.position.add(delta);
    }
    this.key.position.set(this.controls.target.x + 2.5, this.controls.target.y - 2, 4);
    this.key.target.position.copy(this.controls.target);
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
