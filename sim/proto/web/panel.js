// 조작 패널: 슬라이더·그림으로 값을 바꾸며 로봇이 어떻게 움직이는지 보고, 같은 동작의 코드를 보여 준다.
const SVGNS = "http://www.w3.org/2000/svg";
const COLORS = { thigh: "#5b9bff", shank: "#ff9f43", hipx: "#a78bfa", foot: "#ff5d6c", target: "#5d6778", grid: "#1e252f", text: "#7b8596" };
const SEND_MS = 50;
const deg = (r) => (r * 180) / Math.PI;
const rad = (d) => (d * Math.PI) / 180;

function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
function colorCode(lines) {
  return lines.map((l) => {
    if (l.trim().startsWith("#")) return `<span class="c">${esc(l)}</span>`;
    let h = esc(l);
    h = h.replace(/("[^"]*")/g, '<span class="s">$1</span>');
    h = h.replace(/(dog\.\w+)/g, '<span class="f">$1</span>');
    h = h.replace(/(?<![\w"])(-?\d+(?:\.\d+)?)(?![\w"])/g, '<span class="n">$1</span>');
    h = h.replace(/(#.*)$/, '<span class="c">$1</span>');
    return h;
  }).join("\n");
}

export class Panel {
  constructor(meta, send, insertCode) {
    this.m = meta;
    this.sendRaw = send;
    this.insertCode = insertCode;
    this.goal = null;          // 패널이 보내는 목표각(도) 12개
    this.state = null;
    this.locked = false;
    this.lastJoint = "knee";
    this.leg = "FL";
    this.footLeg = "all";
    this.tab = "joint";
    this.pending = null;
    this.timer = null;
    this.foot = { x: 2, z: 31 };   // cm
    this.gait = { T: 0.4, step: 8, lift: 8, height: 31 };
    this.tick = 0;
    this._buildTabs();
    this._buildJoint();
    this._buildFoot();
    this._buildGait();
    this._buildCom();
    this._buildTop();
    document.getElementById("btn-insert").onclick = () => this.insertCode(this.codeLines().join("\n") + "\n");
    this.refreshCode();
  }

  // ---------- 공통 ----------
  _buildTabs() {
    document.querySelectorAll(".tab").forEach((b) => b.onclick = () => {
      document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === b));
      document.querySelectorAll(".tab-page").forEach((p) => p.classList.toggle("active", p.dataset.page === b.dataset.tab));
      this.tab = b.dataset.tab;
      this.refreshCode();
    });
  }

  _buildTop() {
    document.querySelectorAll("#pose-seg button").forEach((b) => b.onclick = () => this.pose(b.dataset.pose));
    const kp = document.getElementById("kp");
    kp.oninput = () => {
      document.getElementById("kp-val").textContent = kp.value;
      this.queue({ op: "stiffness", kp: +kp.value });
    };
  }

  seg(container, items, value, onPick) {
    container.innerHTML = "";
    for (const [v, label] of items) {
      const b = document.createElement("button");
      b.textContent = label;
      b.classList.toggle("active", v === value);
      b.onclick = () => {
        container.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
        onPick(v);
      };
      container.appendChild(b);
    }
  }

  // 슬라이더 + 숫자 입력 칸. 숫자를 직접 쓰고 Enter(또는 칸 밖을 누르기)하면 적용된다.
  slider(parent, { name, code, min, max, step = 1, value, cls = "", meaning, unit = "", prefix = "", onInput }) {
    const digits = step < 1 ? String(step).split(".")[1].length : 0;
    const wrap = document.createElement("div");
    wrap.className = "slider";
    wrap.innerHTML = `<div class="slider-top"><span class="slider-name">${name}${code ? `<code>${code}</code>` : ""}</span>
      <span class="slider-val">${prefix ? `<span class="muted">${prefix}</span>` : ""}
        <input type="number" class="num" min="${min}" max="${max}" step="${step}" value="${value}" title="숫자를 쓰고 Enter">
        <span class="unit">${unit}</span><span class="extra"></span></span></div>
      <input type="range" class="${cls}" min="${min}" max="${max}" step="${step}" value="${value}">
      ${meaning ? `<div class="slider-meaning">${meaning}</div>` : ""}`;
    parent.appendChild(wrap);
    const input = wrap.querySelector("input[type=range]");
    const num = wrap.querySelector("input.num");
    const extra = wrap.querySelector(".extra");
    const show = (v) => { if (document.activeElement !== num) num.value = (+v).toFixed(digits); };
    input.oninput = () => { show(input.value); onInput(+input.value); };
    const apply = () => {
      let v = parseFloat(num.value);
      if (Number.isNaN(v)) { num.value = (+input.value).toFixed(digits); return; }   // 숫자가 아니면 원래 값으로
      v = Math.min(max, Math.max(min, Math.round(v / step) * step));
      v = +v.toFixed(digits);
      num.value = v.toFixed(digits);
      num.classList.toggle("clamped", v !== parseFloat(num.dataset.typed ?? v));
      input.value = v;
      onInput(v);
    };
    num.addEventListener("input", () => { num.dataset.typed = num.value; num.classList.remove("clamped"); });
    num.addEventListener("change", apply);
    num.addEventListener("keydown", (e) => {
      e.stopPropagation();                                  // 숫자 칸에서 누른 키가 단축키(F5 등)로 가지 않게
      if (e.key === "Enter") { apply(); num.blur(); }
      if (e.key === "ArrowUp" || e.key === "ArrowDown") setTimeout(apply);   // ↑/↓ 로 한 칸씩 바로 적용
      if (e.key === "Escape") { show(input.value); num.blur(); }
    });
    show(value);
    return { input, num, set: (v) => { input.value = v; show(v); }, readout: (html) => { extra.innerHTML = html; } };
  }

  // ---------- ① 관절 하나씩 ----------
  _buildJoint() {
    this.seg(document.getElementById("leg-seg"), this.m.legs.map((l) => [l, `${this.m.legNames[l]} ${l}`]), "FL",
      (v) => { this.leg = v; this.syncSliders(); this.refreshCode(); this.drawJointViews(); });
    this.allLegs = document.getElementById("all-legs");
    this.allLegs.onchange = () => this.refreshCode();
    const box = document.getElementById("joint-sliders");
    const cls = { hip_x: "hipx", hip_y: "thigh", knee: "shank" };
    this.jsl = {};
    for (const j of this.m.joints) {
      const info = this.m.jointInfo[j];
      this.jsl[j] = this.slider(box, {
        name: info.name, code: j, min: Math.round(info.range[0]), max: Math.round(info.range[1]), value: 0, cls: cls[j],
        meaning: `${info.meaning}  (범위 ${Math.round(info.range[0])}° ~ ${Math.round(info.range[1])}°)`, unit: "°", prefix: "목표",
        onInput: (v) => this.onJoint(j, v),
      });
    }
    this.side = document.getElementById("side-view");
    this.back = document.getElementById("back-view");
  }

  onJoint(j, v) {
    if (!this.goal) return;
    const legs = this.allLegs.checked ? this.m.legs : [this.leg];
    for (const leg of legs) this.goal[this.m.legs.indexOf(leg) * 3 + this.m.joints.indexOf(j)] = v;
    this.lastJoint = j;
    this.queue({ op: "joints", deg: [...this.goal] });
    this.refreshCode();
  }

  syncSliders() {
    if (!this.goal) return;
    const i = this.m.legs.indexOf(this.leg) * 3;
    this.m.joints.forEach((j, k) => this.jsl[j].set(this.goal[i + k]));
  }

  // ---------- 기구학 ----------
  fk(hy, kn) {
    const q1 = rad(hy), q2 = rad(kn), T = this.m.thigh, S = this.m.shank;
    return [T * Math.sin(q1) + S * Math.sin(q1 + q2), -(T * Math.cos(q1) + S * Math.cos(q1 + q2))];
  }
  ik(x, z) {
    const T = this.m.thigh, S = this.m.shank;
    const c = (x * x + z * z - T * T - S * S) / (2 * T * S);
    if (Math.abs(c) > 1) return null;
    const q2 = Math.acos(c);
    const q1 = Math.atan2(x, -z) - Math.atan2(S * Math.sin(q2), T + S * Math.cos(q2));
    return [deg(q1), deg(q2)];
  }

  // 옆에서 본 다리 그림 (엉덩이 관절 = 원점, cm 눈금)
  drawSide(svg, W, H, s, actual, target, { reach = false, drag = null } = {}) {
    svg.innerHTML = "";
    const ox = W / 2, oy = 30;
    const px = (x, z) => [ox + x * s, oy - z * s];
    for (let cm = -40; cm <= 40; cm += 10) {
      const [x] = px(cm / 100, 0);
      el("line", { x1: x, y1: 0, x2: x, y2: H, stroke: COLORS.grid }, svg);
      if (cm % 20 === 0) el("text", { x, y: H - 6, fill: COLORS.text, "font-size": 11, "text-anchor": "middle" }, svg).textContent = cm;
    }
    for (let cm = 0; cm <= 50; cm += 10) {
      const [, y] = px(0, -cm / 100);
      el("line", { x1: 0, y1: y, x2: W, y2: y, stroke: COLORS.grid }, svg);
      if (cm) el("text", { x: 4, y: y - 2, fill: COLORS.text, "font-size": 13 }, svg).textContent = `-${cm}`;
    }
    el("text", { x: W - 6, y: H - 6, fill: COLORS.text, "font-size": 12, "text-anchor": "end" }, svg).textContent = "앞 → (cm)";
    el("rect", { x: ox - 70, y: oy - 22, width: 140, height: 14, rx: 4, fill: "#2a313c" }, svg);
    el("text", { x: ox, y: oy - 11, fill: "#9aa4b2", "font-size": 11, "text-anchor": "middle" }, svg).textContent = "몸통 (옆에서 본 모습)";
    if (reach) {
      const r = (this.m.thigh + this.m.shank) * s;
      el("circle", { cx: ox, cy: oy, r, fill: "none", stroke: "#5a2f36", "stroke-dasharray": "4 4" }, svg);
    }
    const leg = (hy, kn, a, w, dash) => {
      const q1 = rad(hy);
      const k = px(this.m.thigh * Math.sin(q1), -this.m.thigh * Math.cos(q1));
      const f = px(...this.fk(hy, kn));
      const st = { "stroke-width": w, "stroke-linecap": "round", ...(dash ? { "stroke-dasharray": dash } : {}) };
      el("line", { x1: ox, y1: oy, x2: k[0], y2: k[1], stroke: a ? COLORS.thigh : COLORS.target, ...st }, svg);
      el("line", { x1: k[0], y1: k[1], x2: f[0], y2: f[1], stroke: a ? COLORS.shank : COLORS.target, ...st }, svg);
      return { k, f };
    };
    if (target) leg(target[0], target[1], false, 3, "5 4");
    const { k, f } = leg(actual[0], actual[1], true, 8);
    el("circle", { cx: ox, cy: oy, r: 6, fill: "#e6e9ef" }, svg);
    el("circle", { cx: k[0], cy: k[1], r: 5, fill: "#e6e9ef" }, svg);
    const foot = el("circle", { cx: f[0], cy: f[1], r: drag ? 9 : 7, fill: COLORS.foot }, svg);
    if (drag) foot.style.cursor = "grab";
    const [fx, fz] = this.fk(actual[0], actual[1]);
    el("text", { x: ox + 10, y: oy + 16, fill: COLORS.thigh, "font-size": 12 }, svg).textContent = `hip_y ${actual[0].toFixed(0)}°`;
    el("text", { x: k[0] + 9, y: k[1] + 4, fill: COLORS.shank, "font-size": 12 }, svg).textContent = `knee ${actual[1].toFixed(0)}°`;
    el("text", { x: f[0] + 11, y: f[1] + 14, fill: COLORS.foot, "font-size": 12 }, svg).textContent =
      `발 (${(fx * 100).toFixed(0)}, ${(fz * 100).toFixed(0)}) cm`;
  }

  drawBack(svg, hx, target) {
    svg.innerHTML = "";
    const W = 160, H = 250, ox = 80, oy = 30, L = 170;
    el("line", { x1: ox, y1: 0, x2: ox, y2: H, stroke: COLORS.grid }, svg);
    el("rect", { x: ox - 60, y: oy - 22, width: 120, height: 14, rx: 4, fill: "#2a313c" }, svg);
    el("text", { x: ox - 32, y: oy - 11, fill: "#9aa4b2", "font-size": 11, "text-anchor": "middle" }, svg).textContent = "왼쪽";
    el("text", { x: ox + 32, y: oy - 11, fill: "#9aa4b2", "font-size": 11, "text-anchor": "middle" }, svg).textContent = "오른쪽";
    const line = (a, color, w, dash) => {
      const fx = ox + Math.sin(rad(a)) * L, fy = oy + Math.cos(rad(a)) * L;
      el("line", { x1: ox, y1: oy, x2: fx, y2: fy, stroke: color, "stroke-width": w, "stroke-linecap": "round", ...(dash ? { "stroke-dasharray": dash } : {}) }, svg);
      return [fx, fy];
    };
    if (target !== undefined) line(target, COLORS.target, 3, "5 4");
    const [fx, fy] = line(hx, COLORS.hipx, 8);
    el("circle", { cx: ox, cy: oy, r: 6, fill: "#e6e9ef" }, svg);
    el("circle", { cx: fx, cy: fy, r: 7, fill: COLORS.foot }, svg);
    el("text", { x: ox, y: H - 24, fill: COLORS.text, "font-size": 12, "text-anchor": "middle" }, svg).textContent = "뒤에서 본 모습";
    el("text", { x: ox, y: H - 9, fill: COLORS.hipx, "font-size": 13, "text-anchor": "middle" }, svg).textContent = `hip_x ${hx.toFixed(0)}°`;
  }

  drawJointViews() {
    if (!this.state) return;
    const i = this.m.legs.indexOf(this.leg) * 3, q = this.state.q, t = this.state.target;
    this.drawSide(this.side, 300, 250, 520, [q[i + 1], q[i + 2]], [t[i + 1], t[i + 2]]);
    this.drawBack(this.back, q[i], t[i]);
  }

  // ---------- ② 발 위치로 ----------
  _buildFoot() {
    this.seg(document.getElementById("foot-seg"), [["all", "네 발 모두"], ...this.m.legs.map((l) => [l, this.m.legNames[l]])], "all",
      (v) => { this.footLeg = v; this.refreshCode(); });
    const box = document.getElementById("foot-sliders");
    this.fx = this.slider(box, { name: "앞뒤 x", min: -20, max: 20, value: this.foot.x, cls: "thigh", unit: "cm",
      meaning: "+ 앞 / − 뒤 (엉덩이 관절 기준, cm)", onInput: (v) => { this.foot.x = v; this.onFoot(); } });
    this.fz = this.slider(box, { name: "엉덩이 아래 깊이", min: 12, max: 40, value: this.foot.z, cls: "shank", unit: "cm",
      meaning: "클수록 다리를 펴서 몸이 높아져요 (cm)", onInput: (v) => { this.foot.z = v; this.onFoot(); } });
    this.footSvg = document.getElementById("foot-view");
    const W = 330, H = 260, s = 540, ox = W / 2, oy = 26;
    const toM = (e) => {
      const r = this.footSvg.getBoundingClientRect();
      const x = ((e.clientX - r.left) / r.width) * W, y = ((e.clientY - r.top) / r.height) * H;
      return [Math.round(((x - ox) / s) * 100), Math.round(((y - oy) / s) * 100)];
    };
    let dragging = false;
    const move = (e) => {
      if (!dragging) return;
      const [x, z] = toM(e);
      this.foot.x = Math.max(-20, Math.min(20, x));
      this.foot.z = Math.max(12, Math.min(40, z));
      this.fx.set(this.foot.x); this.fz.set(this.foot.z);
      this.onFoot();
    };
    this.footSvg.addEventListener("pointerdown", (e) => { dragging = true; this.footSvg.setPointerCapture(e.pointerId); move(e); });
    this.footSvg.addEventListener("pointermove", move);
    this.footSvg.addEventListener("pointerup", () => { dragging = false; });
    this.drawFoot();
  }

  onFoot() {
    this.drawFoot();
    this.refreshCode();
    const r = this.ik(this.foot.x / 100, -this.foot.z / 100);
    if (!r || !this.goal) return;
    const legs = this.footLeg === "all" ? this.m.legs : [this.footLeg];
    for (const leg of legs) {
      const i = this.m.legs.indexOf(leg) * 3;
      this.goal[i + 1] = +r[0].toFixed(1);
      this.goal[i + 2] = +r[1].toFixed(1);
    }
    this.queue({ op: "joints", deg: [...this.goal] });
  }

  drawFoot() {
    const r = this.ik(this.foot.x / 100, -this.foot.z / 100);
    const out = document.getElementById("ik-result");
    if (r) {
      this.drawSide(this.footSvg, 330, 260, 540, r, null, { reach: true, drag: true });
      out.className = "ik-result";
      out.innerHTML = `→ 계산된 각도 &nbsp; <span style="color:var(--thigh)">hip_y = ${r[0].toFixed(1)}°</span> &nbsp; <span style="color:var(--shank)">knee = ${r[1].toFixed(1)}°</span>`;
    } else {
      this.drawSide(this.footSvg, 330, 260, 540, [-37.2, 74.5], null, { reach: true, drag: true });
      out.className = "ik-result bad";
      out.textContent = "✖ 다리가 닿을 수 없는 위치예요 (허벅지 20 cm + 정강이 21 cm = 최대 41 cm)";
    }
  }

  // ---------- ③ 걸음새 ----------
  _buildGait() {
    const box = document.getElementById("gait-sliders");
    const defs = [
      ["T", "한 주기 시간 T", 0.25, 0.8, 0.05, "짧을수록 빠른 발놀림", "초"],
      ["step", "보폭 STEP", 0, 14, 1, "한 주기에 나아가는 거리", "cm"],
      ["lift", "발 드는 높이 LIFT", 0, 12, 1, "0 이면 발이 바닥에 끌려요", "cm"],
      ["height", "딛는 깊이 HEIGHT", 24, 36, 1, "엉덩이 관절 아래로", "cm"],
    ];
    this.gsl = {};
    for (const [k, name, min, max, step, meaning, unit] of defs) {
      this.gsl[k] = this.slider(box, { name, min, max, step, value: this.gait[k], meaning, unit,
        onInput: (v) => { this.gait[k] = v; this.onGait(); } });
    }
    document.getElementById("gait-start").onclick = () => this.send({ op: "gait", on: true, ...this.gaitParams() });
    document.getElementById("gait-stop").onclick = () => { this.send({ op: "gait", on: false }); this.goal = null; };
    this.onGait(false);
  }

  gaitParams() {
    const g = this.gait;
    return { T: g.T, step: g.step / 100, lift: g.lift / 100, height: -g.height / 100 };
  }

  onGait(send = true) {
    document.getElementById("gait-speed").textContent = `이론 속도 = 보폭 ÷ 주기 = ${(this.gait.step / this.gait.T).toFixed(0)} cm/s`;
    this.drawGait();
    this.refreshCode();
    if (send && this.state && this.state.gait) this.queue({ op: "gait", on: true, ...this.gaitParams() });
  }

  drawGait() {
    const svg = document.getElementById("gait-view");
    svg.innerHTML = "";
    const { step, lift } = this.gait;
    const s = 1300, ox = 165, gy = 140;
    const pts = (from, to) => {
      const out = [];
      for (let i = from; i <= to; i++) {
        const p = i / 60;
        let x, z;
        if (p < 0.5) { x = step / 2 - step * (p / 0.5); z = 0; } else { const u = (p - 0.5) / 0.5; x = -step / 2 + step * u; z = lift * Math.sin(Math.PI * u); }
        out.push(`${ox + (x / 100) * s},${gy - (z / 100) * s}`);
      }
      return out.join(" ");
    };
    el("defs", {}, svg).innerHTML = `<marker id="ah" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="context-stroke"/></marker>`;
    el("line", { x1: 15, y1: gy + 5, x2: 315, y2: gy + 5, stroke: "#3a4352", "stroke-width": 2 }, svg);
    el("text", { x: 18, y: gy + 20, fill: COLORS.text, "font-size": 12 }, svg).textContent = "바닥";
    el("polyline", { points: pts(0, 30), fill: "none", stroke: "#c08a5b", "stroke-width": 4, "marker-end": "url(#ah)" }, svg);
    el("polyline", { points: pts(30, 60), fill: "none", stroke: "#34d399", "stroke-width": 4, "marker-end": "url(#ah)" }, svg);
    el("text", { x: ox, y: gy + 22, fill: "#c08a5b", "font-size": 13, "text-anchor": "middle" }, svg).textContent = `딛기: 발을 뒤로 밀기 · 보폭 ${step} cm`;
    el("text", { x: ox, y: gy - (lift / 100) * s - 10, fill: "#34d399", "font-size": 13, "text-anchor": "middle" }, svg).textContent = `옮기기: 들어서 앞으로 · ${lift} cm`;
    el("text", { x: 322, y: 14, fill: COLORS.text, "font-size": 12, "text-anchor": "end" }, svg).textContent = "한 다리 발끝의 길 (옆에서, 앞 →)";
  }

  // ---------- ④ 무게중심 ----------
  _buildCom() {
    this.payload = { kg: 0, x: 0, y: 0 };            // kg, cm, cm
    const box = document.getElementById("payload-sliders");
    const upd = () => { this.refreshCode(); this.queue({ op: "payload", kg: this.payload.kg, x: this.payload.x / 100, y: this.payload.y / 100 }); };
    this.psl = {
      kg: this.slider(box, { name: "짐 무게", min: 0, max: this.m.payloadMax, step: 0.1, value: 0, unit: "kg", cls: "hipx",
        onInput: (v) => { this.payload.kg = v; upd(); } }),
      x: this.slider(box, { name: "짐 위치 앞뒤 (+앞 / −뒤)", min: -20, max: 20, value: 0, unit: "cm", cls: "thigh",
        onInput: (v) => { this.payload.x = v; upd(); } }),
      y: this.slider(box, { name: "짐 위치 좌우 (+왼쪽 / −오른쪽)", min: -12, max: 12, value: 0, unit: "cm", cls: "shank",
        onInput: (v) => { this.payload.y = v; upd(); } }),
    };
    document.getElementById("payload-clear").onclick = () => {
      this.payload = { kg: 0, x: 0, y: 0 };
      for (const k of ["kg", "x", "y"]) this.psl[k].set(0);
      upd();
    };
    this.drawCom();
  }

  comStatus(st) {
    if (!st || st.margin === null || st.margin === undefined) return ["", "–", "바닥에 닿은 발이 1개 이하예요 (공중에 떠 있거나 넘어짐)"];
    const n = st.contact.filter(Boolean).length;
    if (n === 2) return ["two", `${st.margin.toFixed(1)} cm`, "두 발로만 서 있어요. 가만히 있으면 넘어지고, 걸을 때처럼 계속 발을 바꿔 디뎌야 균형이 잡혀요"];
    if (st.margin >= 0) return ["ok", `+${st.margin.toFixed(1)} cm`, `안정: 무게중심(노란 점)이 바닥에 닿은 발들이 만든 영역(지지 다각형) 안쪽으로 ${st.margin.toFixed(1)} cm 들어와 있어요`];
    return ["bad", `${st.margin.toFixed(1)} cm`, `위험: 무게중심이 지지 다각형 밖으로 ${(-st.margin).toFixed(1)} cm 나갔어요 → 넘어져요`];
  }

  // 위에서 본 모습 (몸통 기준, 앞 = 위쪽)
  drawCom() {
    const svg = document.getElementById("com-view");
    svg.innerHTML = "";
    const W = 300, H = 300, s = 560, cx = W / 2, cy = H / 2 + 6;
    const P = ([x, y]) => [cx - y * s, cy - x * s];
    for (let cm = -20; cm <= 20; cm += 10) {
      const [gx] = P([0, cm / 100]), [, gy] = P([cm / 100, 0]);
      el("line", { x1: gx, y1: 0, x2: gx, y2: H, stroke: COLORS.grid }, svg);
      el("line", { x1: 0, y1: gy, x2: W, y2: gy, stroke: COLORS.grid }, svg);
    }
    el("text", { x: cx, y: 16, fill: COLORS.text, "font-size": 12, "text-anchor": "middle" }, svg).textContent = "앞 ↑  (위에서 본 모습)";
    el("text", { x: 8, y: cy + 4, fill: COLORS.text, "font-size": 11 }, svg).textContent = "왼쪽";
    el("text", { x: W - 8, y: cy + 4, fill: COLORS.text, "font-size": 11, "text-anchor": "end" }, svg).textContent = "오른쪽";
    const [tx, ty] = P([0.235, 0.1]);
    el("rect", { x: tx, y: ty, width: 0.2 * s, height: 0.47 * s, rx: 10, fill: "#232a35", stroke: "#3a4352" }, svg);
    const st = this.state;
    const [kg, px, py] = st?.payload ?? [this.payload.kg, this.payload.x / 100, this.payload.y / 100];
    if (kg > 0.05) {
      const [bx, by] = P([px + 0.08, py + 0.06]);
      el("rect", { x: bx, y: by, width: 0.12 * s, height: 0.16 * s, rx: 4, fill: "rgba(245,158,11,.35)", stroke: "#f59e0b" }, svg);
      el("text", { x: bx + 0.06 * s, y: by + 0.08 * s + 4, fill: "#fbbf24", "font-size": 11, "text-anchor": "middle" }, svg).textContent = `짐 ${kg.toFixed(1)}kg`;
    }
    if (!st || !st.feet_b) return;
    const [cls] = this.comStatus(st);
    const col = { ok: "#34d399", bad: "#f87171", two: "#fbbf24", "": "#5d6778" }[cls];
    if (st.sup_b.length >= 3) el("polygon", { points: st.sup_b.map((q) => P(q).join(",")).join(" "), fill: col, "fill-opacity": 0.2, stroke: col, "stroke-width": 2 }, svg);
    else if (st.sup_b.length === 2) el("line", { x1: P(st.sup_b[0])[0], y1: P(st.sup_b[0])[1], x2: P(st.sup_b[1])[0], y2: P(st.sup_b[1])[1], stroke: col, "stroke-width": 4 }, svg);
    st.feet_b.forEach((f, i) => {
      const [fx, fy] = P(f);
      el("circle", { cx: fx, cy: fy, r: 8, fill: st.contact[i] ? "#e6e9ef" : "none", stroke: "#e6e9ef", "stroke-width": 2, "stroke-dasharray": st.contact[i] ? "" : "3 3" }, svg);
      el("text", { x: fx, y: fy + (f[0] > 0 ? -13 : 22), fill: COLORS.text, "font-size": 11, "text-anchor": "middle" }, svg).textContent = this.m.legs[i];
    });
    const [mx, my] = P(st.com_b);
    el("line", { x1: mx - 12, y1: my, x2: mx + 12, y2: my, stroke: "#ffd166", "stroke-width": 2 }, svg);
    el("line", { x1: mx, y1: my - 12, x2: mx, y2: my + 12, stroke: "#ffd166", "stroke-width": 2 }, svg);
    el("circle", { cx: mx, cy: my, r: 6, fill: "#ffd166", stroke: "#0e1116", "stroke-width": 2 }, svg);
    el("text", { x: 8, y: H - 10, fill: COLORS.text, "font-size": 11 }, svg).textContent = "● 발이 바닥에 닿음   ◌ 떠 있음";
  }

  // ---------- 코드 보기 ----------
  codeLines() {
    if (this.tab === "joint") {
      const j = this.lastJoint, legs = this.allLegs.checked ? this.m.legs : [this.leg];
      const i0 = this.m.legs.indexOf(legs[0]) * 3 + this.m.joints.indexOf(j);
      const d = Math.round(this.goal ? this.goal[i0] : +this.jsl[j].input.value);
      return [`# ${this.m.legNames[legs[0]]} 다리 '${this.m.jointInfo[j].name}' 관절을 ${d}° 로`,
        `# 딥 로보틱스 공식 형식: 관절 ${i0}번 ${this.m.officialNames[i0]} 목표각 ${rad(d).toFixed(3)} rad`,
        ...legs.map((l) => `dog.set_angle("${l}", "${j}", ${d})`)];
    }
    if (this.tab === "foot") {
      const x = (this.foot.x / 100).toFixed(2), z = (-this.foot.z / 100).toFixed(2);
      const head = [`# 발끝을 엉덩이 관절에서 앞으로 ${this.foot.x} cm, 아래로 ${this.foot.z} cm 에`,
        `# 코드는 m 단위: cm ÷ 100 → x = ${x}, z = ${z}`];
      return head.concat(this.footLeg === "all" ? [`dog.set_feet({leg: (${x}, ${z}) for leg in LEGS}, seconds=0.8)`]
        : [`dog.set_feet({"${this.footLeg}": (${x}, ${z})}, seconds=0.8)`]);
    }
    if (this.tab === "com") {
      const { kg, x, y } = this.payload;
      const m = this.state?.margin;
      return [`# 무게중심 여유: 지금 ${m === null || m === undefined ? "–" : m.toFixed(1) + " cm"} (음수면 지지 다각형 밖 → 넘어짐)`,
        `print(dog.get_com_margin())`,
        `print(dog.get_com())            # 무게중심 위치 (x, y, z) m`,
        `dog.set_payload(${kg.toFixed(1)}, x=${(x / 100).toFixed(2)}, y=${(y / 100).toFixed(2)})   # 시뮬레이터 전용: 짐 올리기`];
    }
    const g = this.gaitParams();
    return ["# J5 걸음새 샘플 맨 위의 값들 (m 단위)", `T = ${g.T.toFixed(2)}          # 한 주기 시간 (초)`,
      `STEP = ${g.step.toFixed(2)}      # 보폭`, `LIFT = ${g.lift.toFixed(2)}      # 발 드는 높이`, `HEIGHT = ${g.height.toFixed(2)}   # 딛는 발 높이`];
  }

  refreshCode() {
    document.getElementById("code-preview").innerHTML = colorCode(this.codeLines());
  }

  // ---------- 보내기 / 받기 ----------
  pose(name) {
    this.goal = [...this.m.poses[name]];
    this.syncSliders();
    this.send({ op: "pose", name });
  }

  queue(msg) {
    this.pending = msg;
    if (!this.timer) this.timer = setTimeout(() => { this.timer = null; if (this.pending) { this.send(this.pending); this.pending = null; } }, SEND_MS);
  }

  send(msg) {
    if (this.locked) return;
    this.sendRaw({ type: "panel", ...msg });
  }

  setLocked(on) {
    this.locked = on;
    document.getElementById("panel-pane").classList.toggle("locked", on);
  }

  resync() { this.goal = null; }

  onState(st) {
    this.state = st;
    if (!this.goal) { this.goal = [...st.target]; this.syncSliders(); this.refreshCode(); }
    const i = this.m.legs.indexOf(this.leg) * 3;
    this.m.joints.forEach((j, k) => this.jsl[j].readout(`<span class="muted">· 실제</span> <b>${st.q[i + k].toFixed(1)}°</b>`));
    const kp = document.getElementById("kp");
    if (!this.pending && document.activeElement !== kp && Math.abs(+kp.value - st.kp) > 0.5) {
      kp.value = st.kp; document.getElementById("kp-val").textContent = Math.round(st.kp);
    }
    if (this.tab === "joint") this.drawJointViews();
    if (this.tab === "com") {
      const [cls, big, text] = this.comStatus(st);
      const box = document.getElementById("com-status");
      box.className = "com-status " + cls;
      box.innerHTML = `<b>${big}</b><span>${text}</span>`;
      this.drawCom();
      if (!this.pending && st.payload) {                 // 코드에서 짐을 바꿨을 때 슬라이더도 맞춤
        const [kg, px, py] = st.payload;
        const cur = { kg, x: Math.round(px * 100), y: Math.round(py * 100) };
        for (const k of ["kg", "x", "y"]) {
          if (Math.abs(cur[k] - this.payload[k]) > 0.05) { this.payload[k] = cur[k]; this.psl[k].set(cur[k]); }
        }
      }
      if (this.tick++ % 5 === 0) this.refreshCode();
    }
  }
}
