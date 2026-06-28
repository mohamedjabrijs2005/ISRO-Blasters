/**
 * Astraeus NOC — Frontend Application v3
 * Air-Gapped MPLS Predictive Copilot — Full Feature Dashboard
 */

// ─── State ────────────────────────────────────────────────────────────────────
const S = {
  ws: null, snap: null, preds: null,
  missions: [], oamEvents: [],
  scenarios: [], wsUp: false,
  chatBusy: false, filterMode: 'all',
  flowOffsets: {}, animFrame: null,
};

// ─── Colors ───────────────────────────────────────────────────────────────────
const C = {
  emerald:'#10b981', emeraldL:'#34d399',
  blue:   '#3b82f6', blueL:   '#60a5fa',
  cyan:   '#06b6d4', cyanL:   '#22d3ee',
  amber:  '#f59e0b', amberL:  '#fbbf24',
  rose:   '#f43f5e', roseL:   '#fb7185',
  violet: '#8b5cf6', violetL: '#a78bfa',
};

const utilCol = u => u >= .85 ? C.roseL : u >= .70 ? C.amberL : C.emeraldL;
const healthCol = h => h === 'critical' ? C.roseL : h === 'warning' ? C.amberL : C.emeraldL;

// ─── WebSocket ────────────────────────────────────────────────────────────────
function connectWS() {
  S.ws = new WebSocket(`ws://${location.host}/ws`);
  S.ws.onopen  = () => { S.wsUp = true; toast('Connected to Astraeus NOC', 'success'); };
  S.ws.onmessage = ({ data }) => {
    const msg = JSON.parse(data);
    if (msg.type === 'initial_state' || msg.type === 'telemetry_update') {
      S.snap     = msg.data.snapshot;
      S.preds    = msg.data.predictions;
      S.missions = msg.data.missions || S.missions;
      S.oamEvents= msg.data.oam_events || S.oamEvents;
      renderAll();
      hideLoading();
    } else if (msg.type === 'chat_response') {
      removeTyping(); appendAIMsg(msg.data);
      S.chatBusy = false; el('send-btn').disabled = false;
    } else if (msg.type === 'anomaly_injected') {
      toast(`Scenario injected: ${msg.scenario}`, 'warning');
    } else if (msg.type === 'reroute_result') {
      onReroute(msg.data);
    }
  };
  S.ws.onclose = () => { S.wsUp = false; toast('Reconnecting...', 'warning'); setTimeout(connectWS, 3000); };
}

// ─── Render All ───────────────────────────────────────────────────────────────
function renderAll() {
  if (!S.snap || !S.preds) return;
  renderTopbar();
  renderMetrics();
  renderMissions();
  renderNodeRail();
  renderAlerts();
  renderLSPGrid();
  renderCharts();
  renderHeatmap();
  renderLabelTable();
  renderOAMFeed();
  updateAIBadge();
}

// ─── Topbar ───────────────────────────────────────────────────────────────────
function renderTopbar() {
  const h = S.preds.network_health || 'healthy';
  const r = S.preds.network_risk_score || 0;
  const a = (S.preds.active_alerts || []).length;
  const chip = el('health-chip');
  chip.className = `health-chip ${h === 'healthy' ? 'healthy' : h === 'degraded' ? 'degraded' : 'critical'}`;
  el('health-text').textContent = h.toUpperCase();
  const rv = el('risk-score-val');
  rv.textContent = `${r.toFixed(0)} / 100`;
  rv.style.color = r >= 70 ? C.roseL : r >= 45 ? C.amberL : C.emeraldL;
  el('alert-count-val').textContent = a;
}

function updateAIBadge() {
  fetch('/api/status').then(r=>r.json()).then(d=>{
    el('ai-badge-text').textContent = d.llm_available ? `AI: ${d.llm_model}` : 'AI: Rule-Based';
    const mode = el('ai-mode-text');
    mode.textContent = d.llm_available ? `● Online · ${d.llm_model}` : '● Rule-Based Offline Mode';
    mode.style.color = d.llm_available ? C.emeraldL : C.amberL;
  }).catch(()=>{});
}

// ─── Metrics ──────────────────────────────────────────────────────────────────
function renderMetrics() {
  const lsps  = S.snap.lsps || [];
  const nodes = Object.values(S.snap.nodes || {});
  const peak  = Math.max(...lsps.map(l => l.utilization || 0));
  const avgLat= lsps.length ? lsps.reduce((s,l)=>s+(l.latency_ms||0),0)/lsps.length : 0;
  const alerts= (S.preds.active_alerts||[]).length;

  el('m-nodes').textContent  = `${nodes.filter(n=>n.status==='UP').length}/${nodes.length}`;
  el('m-lsps').textContent   = `${lsps.filter(l=>l.status==='UP').length}/${lsps.length}`;
  el('m-util').textContent   = `${(peak*100).toFixed(0)}%`;
  el('m-lat').textContent    = `${avgLat.toFixed(0)} ms`;
  el('m-alerts').textContent = alerts;

  el('m-util').style.color   = utilCol(peak);
  el('m-alerts').style.color = alerts > 0 ? C.roseL : C.emeraldL;
}

// ─── Mission Control ──────────────────────────────────────────────────────────
function renderMissions() {
  if (!S.missions.length) return;
  const banner = el('mission-banner');
  banner.innerHTML = '';

  S.missions.forEach(m => {
    const isActive = m.status === 'active';
    const col = m.color || '#3b82f6';
    const card = document.createElement('div');
    card.className = `mission-card ${m.status}`;
    card.style.setProperty('--mc', col);

    const sigQ = m.signal_quality_pct ? `${m.signal_quality_pct.toFixed(1)}%` : 'Pre-launch';
    const rate = m.telemetry_rate_mbps ? `${m.telemetry_rate_mbps.toFixed(1)} Mbps` : 'Standby';

    card.innerHTML = `
      <div class="mission-tag ${m.status}">
        ${isActive ? `<div class="mission-dot" style="color:${col}"></div>` : ''}
        ${m.status.toUpperCase()}
      </div>
      <div class="mission-name" title="${m.name}">${m.name}</div>
      <div class="mission-orbit">${m.orbit} · ${m.phase}</div>
      <div class="mission-stats">
        <div class="mission-stat">
          <label>TELEMETRY</label>
          <span style="color:${col}">${rate}</span>
        </div>
        <div class="mission-stat">
          <label>SIG QUAL</label>
          <span>${sigQ}</span>
        </div>
        <div class="mission-stat">
          <label>LSP</label>
          <span>${m.primary_lsp}</span>
        </div>
      </div>`;
    card.onclick = () => sendSuggestion(`What is the telemetry and network status for mission ${m.id} on ${m.primary_lsp}?`);
    banner.appendChild(card);
  });
}

// ─── Node Rail ────────────────────────────────────────────────────────────────
const NODE_ORDER = ['LER-BLR','LER-SDSC','LSR-HASAN','LSR-PB','LER-MU','LER-BIAK'];

function renderNodeRail() {
  const nodes = S.snap.nodes || {};
  const rail  = el('node-rail');
  rail.innerHTML = '';
  NODE_ORDER.forEach(id => {
    const n = nodes[id]; if (!n) return;
    const isDown = n.status === 'DOWN';
    const cpuCol = n.cpu_pct > 80 ? 'var(--rose-400)' : n.cpu_pct > 60 ? 'var(--amber-400)' : 'var(--text-secondary)';
    const tmpCol = n.temp_c  > 70 ? 'var(--amber-400)' : 'var(--text-secondary)';
    const d = document.createElement('div');
    d.className = `node-tile ${isDown?'down':'up'}`;
    d.innerHTML = `
      <div class="node-tile-name">${n.label}</div>
      <div class="node-tile-type">${n.type} · ${n.role}</div>
      <div class="node-stats">
        <div class="node-stat"><label>CPU</label><span style="color:${cpuCol}">${n.cpu_pct.toFixed(0)}%</span></div>
        <div class="node-stat"><label>MEM</label><span>${n.mem_pct.toFixed(0)}%</span></div>
        <div class="node-stat"><label>LBLS</label><span>${n.label_table_size}</span></div>
        <div class="node-stat"><label>TEMP</label><span style="color:${tmpCol}">${n.temp_c.toFixed(0)}°C</span></div>
      </div>`;
    rail.appendChild(d);
  });
}

// ─── Alerts ───────────────────────────────────────────────────────────────────
function renderAlerts() {
  const alerts    = S.preds.active_alerts || [];
  const anomalies = S.snap.active_anomalies || [];
  const body      = el('alerts-body');
  const badge     = el('alert-count-badge');
  const total     = alerts.length + anomalies.length;

  badge.textContent = `${total} alert${total !== 1 ? 's' : ''}`;
  badge.className   = `alert-count-badge ${total === 0 ? 'zero' : ''}`;

  if (total === 0) {
    body.innerHTML = `<div class="no-alert-state"><div class="no-alert-icon">✅</div><div>All systems nominal</div><div style="font-size:10px;color:var(--text-tertiary)">No predictive alerts</div></div>`;
    return;
  }

  let html = '';
  anomalies.forEach(a => {
    html += `<div class="alert-row event">
      <div class="alert-icon-wrap">⚡</div>
      <div class="alert-body">
        <div class="alert-msg"><strong>${esc(a.name)}</strong> — ${esc(a.description)}</div>
        <div class="alert-meta">Live Event · ${new Date().toLocaleTimeString()}</div>
      </div></div>`;
  });
  alerts.forEach(a => {
    const isCrit = a.risk_score >= 70;
    html += `<div class="alert-row ${isCrit?'critical':'warning'}">
      <div class="alert-icon-wrap">${isCrit?'🔴':'🟡'}</div>
      <div class="alert-body">
        <div class="alert-msg">${esc(a.message)}</div>
        <div class="alert-chips">
          <button class="chip accept" onclick="doReroute('${a.lsp_id}','LSR-HASAN',this)">✓ Accept Reroute</button>
          <button class="chip ask"    onclick="askAbout('${a.lsp_id}')">🤖 Ask AI</button>
        </div>
        <div class="alert-meta">Risk: ${a.risk_score.toFixed(0)}/100 · ${new Date(a.timestamp).toLocaleTimeString()}</div>
      </div></div>`;
  });
  body.innerHTML = html;
}

// ─── LSP Grid ─────────────────────────────────────────────────────────────────
function renderLSPGrid() {
  const lsps  = S.snap.lsps || [];
  const preds = S.preds.lsp_predictions || {};
  const grid  = el('lsp-grid');

  let filtered = lsps;
  if (S.filterMode === 'critical') filtered = lsps.filter(l => l.health==='critical'||l.status==='DOWN');
  else if (S.filterMode === 'warning') filtered = lsps.filter(l => l.health!=='nominal'||l.status==='DOWN');

  const sorted = [...filtered].sort((a,b) => ({critical:0,warning:1,nominal:2}[a.health]||2) - ({critical:0,warning:1,nominal:2}[b.health]||2));
  grid.innerHTML = '';

  sorted.forEach(lsp => {
    const p    = preds[lsp.id] || {};
    const h    = lsp.status==='DOWN' ? 'critical' : (lsp.health||'nominal');
    const risk = p.risk_score || 0;
    const rl   = p.risk_level || 'nominal';
    const util = ((lsp.utilization||0)*100).toFixed(1);
    const uCol = utilCol(lsp.utilization||0);
    const wmin = p.time_to_warning_min;

    const tile = document.createElement('div');
    tile.className = `lsp-tile ${h}`;
    tile.onclick = () => sendSuggestion(`Full status and forecast for ${lsp.id}`);
    tile.innerHTML = `
      <div class="lsp-tile-top">
        <span class="lsp-id">${lsp.id}</span>
        <div class="lsp-badges">
          <span class="badge ${h}">${lsp.status==='DOWN'?'DOWN':h.toUpperCase()}</span>
          <span class="risk-pill ${rl}">${risk.toFixed(0)}</span>
        </div>
      </div>
      <div class="lsp-route">${lsp.src} → ${lsp.dst}</div>
      <div class="lsp-metrics-row">
        <div class="lsp-metric"><span class="lsp-metric-l">Util</span><span class="lsp-metric-v" style="color:${uCol}">${util}%</span></div>
        <div class="lsp-metric"><span class="lsp-metric-l">Latency</span><span class="lsp-metric-v">${(lsp.latency_ms||0).toFixed(1)}ms</span></div>
        <div class="lsp-metric"><span class="lsp-metric-l">Loss</span><span class="lsp-metric-v" style="color:${(lsp.packet_loss||0)>.02?C.roseL:'inherit'}">${((lsp.packet_loss||0)*100).toFixed(2)}%</span></div>
      </div>
      <div class="util-track"><div class="util-fill" style="width:${util}%;background:${uCol}"></div></div>
      <div class="lsp-footer">
        ${wmin?`<span class="lsp-forecast-hint">⏱ ${wmin}min to warning</span>`:'<span></span>'}
        <span class="lsp-type-tag">${lsp.type||'N/A'}</span>
      </div>
      ${lsp.rerouted_via?`<div style="font-size:9px;color:var(--emerald-400);font-family:var(--font-mono);margin-top:5px">✓ Rerouted via ${lsp.rerouted_via}</div>`:''}`;
    grid.appendChild(tile);
  });
}

// ─── Heatmap ──────────────────────────────────────────────────────────────────
function renderHeatmap() {
  const lsps = S.snap.lsps || [];
  const hist = S.snap.history || {};
  const grid = el('heatmap-grid');
  if (!grid) return;
  grid.innerHTML = '';

  lsps.forEach(lsp => {
    const h    = (hist[lsp.id] || []).slice(-20);
    const vals = h.map(p => p.utilization || 0);
    while (vals.length < 20) vals.unshift(0);

    const row = document.createElement('div');
    row.className = 'heatmap-row';

    const label = document.createElement('div');
    label.className   = 'heatmap-label';
    label.textContent = lsp.id;
    row.appendChild(label);

    const cells = document.createElement('div');
    cells.className = 'heatmap-cells';

    vals.forEach(v => {
      const cell = document.createElement('div');
      cell.className = 'heatmap-cell';
      const pct = Math.min(100, v * 100);
      // Color scale: emerald → amber → rose
      let bg;
      if (pct < 50) {
        const t = pct / 50;
        bg = lerpColor('#10b981', '#f59e0b', t);
      } else {
        const t = (pct - 50) / 50;
        bg = lerpColor('#f59e0b', '#f43f5e', t);
      }
      cell.style.background = bg;
      cell.style.opacity    = 0.15 + (pct / 100) * 0.85;
      cell.setAttribute('data-val', pct.toFixed(0));
      cells.appendChild(cell);
    });

    row.appendChild(cells);
    grid.appendChild(row);
  });
}

function lerpColor(a, b, t) {
  const ah = parseInt(a.slice(1), 16), bh = parseInt(b.slice(1), 16);
  const ar = (ah >> 16) & 0xff, ag = (ah >> 8) & 0xff, ab = ah & 0xff;
  const br = (bh >> 16) & 0xff, bg = (bh >> 8) & 0xff, bb = bh & 0xff;
  const r = Math.round(ar + (br - ar) * t);
  const g = Math.round(ag + (bg - ag) * t);
  const bv= Math.round(ab + (bb - ab) * t);
  return `rgb(${r},${g},${bv})`;
}

// ─── Label Forwarding Table ───────────────────────────────────────────────────
function renderLabelTable() {
  const lsps  = S.snap.lsps || [];
  const tbody = el('label-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  lsps.forEach(lsp => {
    const tr = document.createElement('tr');
    const priClass = lsp.priority || 'medium';
    tr.innerHTML = `
      <td style="font-weight:700;color:var(--text-primary)">${lsp.id}</td>
      <td><span class="lbl-in">${lsp.label_in || '—'}</span></td>
      <td><span class="lbl-out">${lsp.label_out || '—'}</span></td>
      <td style="color:var(--text-secondary)">${lsp.type || '—'}</td>
      <td><span class="lbl-pri ${priClass}">${(lsp.priority||'medium').toUpperCase()}</span></td>`;
    tbody.appendChild(tr);
  });
}

// ─── OAM Events Feed ──────────────────────────────────────────────────────────
function renderOAMFeed() {
  if (!S.oamEvents.length) return;
  const body = el('oam-body');
  if (!body) return;

  body.innerHTML = '';
  S.oamEvents.forEach(ev => {
    const row = document.createElement('div');
    row.className = 'oam-row';
    const ts = new Date(ev.timestamp);
    const ago = Math.round((Date.now() - ts.getTime()) / 1000);
    const agoStr = ago < 60 ? `${ago}s ago` : `${Math.round(ago/60)}m ago`;

    row.innerHTML = `
      <div class="oam-sev ${ev.severity}"></div>
      <div class="oam-type">${ev.type}</div>
      <div class="oam-msg">${esc(ev.message)}</div>
      <div class="oam-time">${agoStr}</div>`;
    body.appendChild(row);
  });

  // Update OAM stats
  fetch('/api/oam').then(r=>r.json()).then(d=>{
    const s = d.stats || {};
    if(el('oam-total')) el('oam-total').textContent = s.total || 0;
    if(el('oam-crit'))  el('oam-crit').textContent  = s.critical || 0;
    if(el('oam-warn'))  el('oam-warn').textContent  = s.warning || 0;
    if(el('oam-frr'))   el('oam-frr').textContent   = s.frr_triggers || 0;
  }).catch(()=>{});
}

// ─── Charts ───────────────────────────────────────────────────────────────────
function renderCharts() {
  if (!S.preds) return;
  const history = S.snap.history || {};
  const preds   = S.preds.lsp_predictions || {};
  drawChart('chart-lsp101', history['LSP-101']||[], preds['LSP-101'], 'utilization', 1);
  drawChart('chart-lsp103', history['LSP-103']||[], preds['LSP-103'], 'latency_ms', 100);
}

function drawChart(id, hist, pred, metric, maxVal) {
  const canvas = el(id); if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height;
  ctx.clearRect(0, 0, W, H);

  const histPts = hist.slice(-40).map(h => h[metric] || 0);
  const forePts = pred ? (pred.forecast[metric] || []) : [];
  const all = [...histPts, ...forePts];
  if (all.length < 2) return;

  const maxData = maxVal === 1 ? Math.max(1, ...all) * 1.12 : maxVal;
  const N = all.length, split = histPts.length;
  const xp = i => (i / (N - 1)) * (W - 16) + 8;
  const yp = v => H - 6 - (v / maxData) * (H - 14);

  // Grid lines
  ctx.strokeStyle = 'rgba(0, 0, 0, 0.04)'; ctx.lineWidth = 1;
  [0.25, 0.5, 0.75].forEach(t => {
    const y = yp(maxData * t);
    ctx.beginPath(); ctx.moveTo(8, y); ctx.lineTo(W-8, y); ctx.stroke();
  });

  // Threshold lines
  if (metric === 'utilization') {
    drawThresh(ctx, W, yp(0.85), 'rgba(244,63,94,0.5)',  '85%');
    drawThresh(ctx, W, yp(0.70), 'rgba(245,158,11,0.4)', '70%');
  }

  // Gradient fill
  const grad = ctx.createLinearGradient(0, 0, 0, H);
  grad.addColorStop(0,   'rgba(59,130,246,0.22)');
  grad.addColorStop(0.7, 'rgba(59,130,246,0.04)');
  grad.addColorStop(1,   'rgba(59,130,246,0.0)');
  ctx.beginPath();
  histPts.forEach((v,i) => i===0 ? ctx.moveTo(xp(i),yp(v)) : ctx.lineTo(xp(i),yp(v)));
  ctx.lineTo(xp(split-1),H); ctx.lineTo(xp(0),H); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  // History line — smooth bezier
  ctx.beginPath(); ctx.strokeStyle = C.blueL; ctx.lineWidth = 2;
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  histPts.forEach((v,i) => {
    if (i === 0) { ctx.moveTo(xp(i), yp(v)); return; }
    const px = (xp(i) + xp(i-1)) / 2;
    ctx.bezierCurveTo(px, yp(histPts[i-1]), px, yp(v), xp(i), yp(v));
  });
  ctx.stroke();

  // Last dot
  if (histPts.length > 0) {
    const lx = xp(split-1), ly = yp(histPts[histPts.length-1]);
    ctx.beginPath(); ctx.arc(lx, ly, 3.5, 0, Math.PI*2);
    ctx.fillStyle = C.blueL; ctx.shadowColor = C.blueL; ctx.shadowBlur = 8;
    ctx.fill(); ctx.shadowBlur = 0;
  }

  // Divider
  if (forePts.length > 0) {
    ctx.save();
    ctx.strokeStyle = 'rgba(0, 0, 0, 0.1)'; ctx.lineWidth = 1;
    ctx.setLineDash([3,3]);
    ctx.beginPath(); ctx.moveTo(xp(split-1),0); ctx.lineTo(xp(split-1),H); ctx.stroke();
    ctx.setLineDash([]); ctx.restore();

    const peak = Math.max(...forePts);
    const fCol = peak > (metric === 'utilization' ? 0.85 : 80) ? C.roseL : C.amberL;

    ctx.save(); ctx.strokeStyle = fCol; ctx.lineWidth = 1.5;
    ctx.setLineDash([5,4]); ctx.lineJoin = 'round';
    ctx.beginPath();
    const startY = yp(histPts[histPts.length-1]);
    ctx.moveTo(xp(split-1), startY);
    forePts.forEach((v,i) => ctx.lineTo(xp(split+i), yp(v)));
    ctx.stroke(); ctx.setLineDash([]); ctx.restore();

    const fx = xp(split+forePts.length-1), fy = yp(forePts[forePts.length-1]);
    ctx.beginPath(); ctx.arc(fx,fy,3,0,Math.PI*2);
    ctx.fillStyle = fCol; ctx.shadowColor = fCol; ctx.shadowBlur = 8;
    ctx.fill(); ctx.shadowBlur = 0;
  }

  // Value label
  if (histPts.length) {
    const cur = histPts[histPts.length-1];
    const lbl = metric === 'utilization' ? `${(cur*100).toFixed(1)}%` : `${cur.toFixed(1)}ms`;
    ctx.fillStyle = C.cyanL; ctx.font = '600 10px JetBrains Mono,monospace';
    ctx.fillText(lbl, 10, 15);
  }
}

function drawThresh(ctx, W, y, color, label) {
  ctx.save();
  ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.setLineDash([2,4]);
  ctx.beginPath(); ctx.moveTo(8,y); ctx.lineTo(W-8,y); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = color; ctx.font = '10px JetBrains Mono,monospace';
  ctx.fillText(label, W-36, y-3);
  ctx.restore();
}

// ─── Topology Canvas ──────────────────────────────────────────────────────────
const TOPO_POS = {
  'LER-BLR':   { x:.50, y:.48 },
  'LER-SDSC':  { x:.24, y:.18 },
  'LSR-HASAN': { x:.74, y:.28 },
  'LSR-PB':    { x:.82, y:.68 },
  'LER-MU':    { x:.13, y:.78 },
  'LER-BIAK':  { x:.88, y:.20 },
};

function renderTopology() {
  const canvas = el('topology-canvas'); if (!canvas || !S.snap) return;
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width*dpr; canvas.height = rect.height*dpr;
  const ctx = canvas.getContext('2d');
  ctx.scale(dpr, dpr);
  const W = rect.width, H = rect.height;
  ctx.clearRect(0,0,W,H);

  const lsps  = S.snap.lsps || [];
  const nodes = S.snap.nodes || {};
  const preds = (S.preds||{}).lsp_predictions||{};
  const px = {};
  Object.entries(TOPO_POS).forEach(([id,pos]) => px[id] = {x:pos.x*W, y:pos.y*H});

  // ── Draw curved LSP links ──
  lsps.forEach(lsp => {
    const src = px[lsp.src], dst = px[lsp.dst]; if (!src || !dst) return;
    const h    = lsp.status==='DOWN' ? 'critical' : (lsp.health||'nominal');
    const col  = h==='critical' ? C.roseL : h==='warning' ? C.amberL : C.emeraldL;
    const util = lsp.utilization || 0;

    // Control point for bezier curve — perpendicular offset
    const mx = (src.x+dst.x)/2, my = (src.y+dst.y)/2;
    const dx = dst.x-src.x, dy = dst.y-src.y;
    const len = Math.sqrt(dx*dx+dy*dy);
    const nx = -dy/len, ny = dx/len;
    const curve = len * 0.12;
    const cpx = mx + nx*curve, cpy = my + ny*curve;

    // Glow
    if (h !== 'nominal') {
      ctx.save();
      ctx.shadowColor = col; ctx.shadowBlur = h==='critical' ? 22 : 10;
      ctx.strokeStyle = col+'38'; ctx.lineWidth = 10;
      ctx.beginPath(); ctx.moveTo(src.x,src.y);
      ctx.quadraticCurveTo(cpx,cpy,dst.x,dst.y); ctx.stroke();
      ctx.restore();
    }

    // Main curved link
    ctx.save();
    if (lsp.status==='DOWN') ctx.setLineDash([6,5]);
    ctx.strokeStyle = col+(lsp.status==='DOWN'?'70':'bb');
    ctx.lineWidth = 1.5 + util * 3.5; ctx.lineCap='round';
    ctx.beginPath(); ctx.moveTo(src.x,src.y);
    ctx.quadraticCurveTo(cpx,cpy,dst.x,dst.y);
    ctx.stroke(); ctx.setLineDash([]); ctx.restore();

    // Animated packet along bezier curve
    if (lsp.status !== 'DOWN') {
      const key = lsp.id;
      if (S.flowOffsets[key]===undefined) S.flowOffsets[key]=Math.random();
      S.flowOffsets[key] = (S.flowOffsets[key] + 0.006*(0.4+util)) % 1;
      const t = S.flowOffsets[key];
      // Point on quadratic bezier
      const bx = (1-t)*(1-t)*src.x + 2*(1-t)*t*cpx + t*t*dst.x;
      const by = (1-t)*(1-t)*src.y + 2*(1-t)*t*cpy + t*t*dst.y;
      ctx.save();
      ctx.shadowColor=col; ctx.shadowBlur=10;
      ctx.beginPath(); ctx.arc(bx,by,3,0,Math.PI*2);
      ctx.fillStyle=col; ctx.fill(); ctx.restore();
    }

    // Label at bezier midpoint
    const t2 = 0.5;
    const lx = (1-t2)*(1-t2)*src.x + 2*(1-t2)*t2*cpx + t2*t2*dst.x;
    const ly = (1-t2)*(1-t2)*src.y + 2*(1-t2)*t2*cpy + t2*t2*dst.y;

    ctx.fillStyle='rgba(255, 255, 255, 0.95)';
    ctx.beginPath(); ctx.roundRect(lx-19,ly-9,38,17,4); ctx.fill();
    ctx.fillStyle=col; ctx.font='600 10px JetBrains Mono,monospace';
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(`${(util*100).toFixed(0)}%`,lx,ly-0.5);
    ctx.fillStyle='rgba(100, 116, 139, 0.8)'; ctx.font='9px JetBrains Mono,monospace';
    ctx.fillText(lsp.id,lx,ly+13);
    ctx.textAlign='left'; ctx.textBaseline='alphabetic';
  });

  // ── Draw nodes ──
  Object.entries(nodes).forEach(([id,node]) => {
    const pos=px[id]; if(!pos) return;
    const isLER  = node.type==='LER';
    const isDown = node.status==='DOWN';
    const col    = isDown ? C.roseL : isLER ? C.blueL : C.cyanL;
    const r      = isLER ? 24 : 19;

    // Outer glow ring
    ctx.save();
    ctx.shadowColor=col; ctx.shadowBlur = isDown ? 30 : 18;
    ctx.strokeStyle=col+(isDown?'80':'40'); ctx.lineWidth=isDown?2:1.5;
    ctx.beginPath(); ctx.arc(pos.x,pos.y,r+3,0,Math.PI*2); ctx.stroke();
    ctx.restore();

    // Fill
    const grad = ctx.createRadialGradient(pos.x-4,pos.y-5,0,pos.x,pos.y,r);
    grad.addColorStop(0, col+'55'); grad.addColorStop(1, col+'18');
    ctx.beginPath(); ctx.arc(pos.x,pos.y,r,0,Math.PI*2);
    ctx.fillStyle=grad; ctx.strokeStyle=col+'cc'; ctx.lineWidth=1.5;
    ctx.fill(); ctx.stroke();

    // Type label
    ctx.fillStyle=col; ctx.font=`700 ${isLER?10:9}px JetBrains Mono,monospace`;
    ctx.textAlign='center'; ctx.textBaseline='middle';
    ctx.fillText(node.type,pos.x,pos.y);

    // Name below
    ctx.fillStyle='#1e293b'; ctx.font=`600 ${isLER?10:9}px Inter,sans-serif`;
    ctx.textBaseline='top'; ctx.fillText(node.label,pos.x,pos.y+r+6);
    ctx.textAlign='left'; ctx.textBaseline='alphabetic';
  });
}

function animateTopology() {
  renderTopology();
  S.animFrame = requestAnimationFrame(animateTopology);
}

// ─── Chat ─────────────────────────────────────────────────────────────────────
function sendChat() {
  const inp = el('chat-input');
  const query = inp.value.trim();
  if (!query || S.chatBusy) return;
  appendUserMsg(query);
  inp.value=''; autoGrow(inp);
  S.chatBusy=true; el('send-btn').disabled=true;

  const body = el('chat-body');
  const tDiv = document.createElement('div');
  tDiv.className='message ai'; tDiv.id='typing-row';
  tDiv.innerHTML=`<div class="msg-orb">🤖</div><div class="typing-row"><div class="t-dot"></div><div class="t-dot"></div><div class="t-dot"></div></div>`;
  body.appendChild(tDiv); body.scrollTop=body.scrollHeight;

  if (S.ws && S.ws.readyState===WebSocket.OPEN) {
    S.ws.send(JSON.stringify({type:'chat',query}));
  } else {
    fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query})})
    .then(r=>r.json()).then(d=>{ removeTyping(); appendAIMsg(d); S.chatBusy=false; el('send-btn').disabled=false; })
    .catch(()=>{ removeTyping(); appendAIMsg({response:'Backend error.',mode:'error',latency_ms:0}); S.chatBusy=false; el('send-btn').disabled=false; });
  }
}

function appendUserMsg(text) {
  const body=el('chat-body');
  const d=document.createElement('div'); d.className='message user';
  d.innerHTML=`<div class="msg-orb">OP</div><div class="msg-content"><div class="msg-bubble">${esc(text)}</div><div class="msg-time">${new Date().toLocaleTimeString()}</div></div>`;
  body.appendChild(d); body.scrollTop=body.scrollHeight;
}

function appendAIMsg(data) {
  const body=el('chat-body');
  const d=document.createElement('div'); d.className='message ai';
  const modeT = data.mode==='llm' ? (data.model||'LLM') : 'Rule-Based';
  d.innerHTML=`<div class="msg-orb">🤖</div><div class="msg-content"><div class="msg-bubble">${esc(data.response||'No response')}</div><div class="msg-time">Astraeus · ${modeT} · ${data.latency_ms||0}ms · ${new Date().toLocaleTimeString()}</div></div>`;
  body.appendChild(d); body.scrollTop=body.scrollHeight;
}

function removeTyping() { const t=el('typing-row'); if(t) t.remove(); }
function sendSuggestion(text) { el('chat-input').value=text; sendChat(); }
function clearChat() {
  el('chat-body').innerHTML=`<div class="message ai"><div class="msg-orb">🤖</div><div class="msg-content"><div class="msg-bubble">Chat cleared. Ready to assist.</div><div class="msg-time">Astraeus · ${new Date().toLocaleTimeString()}</div></div></div>`;
}
function handleKey(e) { if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendChat();} }
function autoGrow(el) { el.style.height='auto'; el.style.height=Math.min(el.scrollHeight,110)+'px'; }

// ─── Actions ──────────────────────────────────────────────────────────────────
function doReroute(lspId, via, btn) {
  btn.disabled=true; btn.textContent='⏳ Applying...';
  if(S.ws&&S.ws.readyState===WebSocket.OPEN) {
    S.ws.send(JSON.stringify({type:'reroute',lsp_id:lspId,via_node:via}));
  } else {
    fetch('/api/reroute',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lsp_id:lspId,via_node:via})})
    .then(r=>r.json()).then(onReroute).catch(()=>toast('Reroute failed','error'));
  }
}

function onReroute(data) {
  if(data.success) {
    toast(`✓ ${data.lsp_id} rerouted. ${(data.old_utilization*100).toFixed(0)}% → ${(data.new_utilization*100).toFixed(0)}%`,'success');
    sendSuggestion(`Confirm reroute result for ${data.lsp_id}`);
  } else toast(`Reroute failed: ${data.message}`,'error');
}

function askAbout(lspId) { sendSuggestion(`Explain risk and recommended action for ${lspId}`); }

// ─── Scenarios ────────────────────────────────────────────────────────────────
async function loadScenarios() {
  try {
    const d = await fetch('/api/scenarios').then(r=>r.json());
    S.scenarios = d.scenarios||[];
    const list = el('scenario-list');
    list.innerHTML='';
    S.scenarios.forEach(s=>{
      const b=document.createElement('button');
      b.className='scenario-btn'; b.textContent=s.name; b.title=s.description;
      b.onclick=()=>injectScenario(s.name);
      list.appendChild(b);
    });
  } catch(_){}
}

function injectScenario(name) {
  if(S.ws&&S.ws.readyState===WebSocket.OPEN) S.ws.send(JSON.stringify({type:'inject_anomaly',scenario:name}));
  else fetch('/api/inject_anomaly',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:name})});
  toast(`Injecting: ${name}`,'warning');
  setTimeout(()=>sendSuggestion('What is happening on the network right now?'),1500);
}

// ─── Topology controls ────────────────────────────────────────────────────────
function resetTopologyView() { renderTopology(); }
function filterLSPs(mode) {
  S.filterMode=mode;
  ['lsp-filter','lsp-filter-grid'].forEach(id=>{if(el(id))el(id).value=mode;});
  renderLSPGrid();
}

// ─── Toast ────────────────────────────────────────────────────────────────────
function toast(msg,type='info') {
  const c=el('toasts');
  const t=document.createElement('div'); t.className=`toast ${type}`; t.textContent=msg;
  c.appendChild(t);
  setTimeout(()=>{t.style.transition='all 0.3s ease';t.style.opacity='0';t.style.transform='translateY(10px)';setTimeout(()=>t.remove(),320);},3500);
}

// ─── Clock ────────────────────────────────────────────────────────────────────
function tickClock() {
  const ist = new Date(Date.now()+5.5*3600000);
  el('clock').textContent=ist.toISOString().slice(11,19)+' IST';
}

// ─── Loading ──────────────────────────────────────────────────────────────────
function hideLoading() {
  const ov=el('loading-overlay'); if(!ov||ov.classList.contains('hidden')) return;
  ov.classList.add('hidden'); setTimeout(()=>ov.style.display='none',700);
}

// ─── Fallback poll ────────────────────────────────────────────────────────────
async function pollREST() {
  try {
    const [tel,mis,oam]=await Promise.all([
      fetch('/api/telemetry').then(r=>r.json()),
      fetch('/api/missions').then(r=>r.json()),
      fetch('/api/oam').then(r=>r.json()),
    ]);
    S.snap=tel.snapshot; S.preds=tel.predictions;
    S.missions=mis.missions||[];
    S.oamEvents=oam.events||[];
    renderAll(); hideLoading();
  } catch(_){ toast('Backend not reachable — start server','error'); }

  setInterval(async()=>{
    if(!S.wsUp){
      try{
        const [t,m,o]=await Promise.all([fetch('/api/telemetry').then(r=>r.json()),fetch('/api/missions').then(r=>r.json()),fetch('/api/oam').then(r=>r.json())]);
        S.snap=t.snapshot;S.preds=t.predictions;S.missions=m.missions||[];S.oamEvents=o.events||[];
        renderAll();
      }catch(_){}
    }
  },3000);
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }
function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

// ─── Init ─────────────────────────────────────────────────────────────────────
async function init() {
  tickClock(); setInterval(tickClock,1000);
  await loadScenarios();
  // WebSockets disabled for serverless
  animateTopology();
  pollREST();
}

document.addEventListener('DOMContentLoaded', init);
