/* =========================================================================
 *  TÉCNICO · JS
 *  - Listado (disponibles/asignados/historial)
 *  - Detalle con evidencias/notas
 *  - Asignación: “solo yo” o “en equipo”
 *  - Cambiar estado (RESUELTO exige observaciones + evidencias opcionales)
 *  - Perfil del técnico con contadores
 * ========================================================================= */

/* --------------------------- DOM & ESTADO -------------------------------- */
const $ = s => document.querySelector(s);

// Elementos base
const grid         = $('#grid');
const dlg          = $('#dlg');
const dlgBody      = $('#dlgBody');
const btnClose     = $('#dlgClose');
const btnRefresh   = $('#btnRefresh');
const q            = $('#q');

// Acciones del detalle
const btnTomar     = $('#btnTomar');
const estadoSel    = $('#estadoSel');
const btnEstado    = $('#btnEstado');

// Diálogo de asignación
const assignDlg        = $('#assignDlg');
const optSolo          = $('#optSolo');
const optEquipo        = $('#optEquipo');
const assignEquipoWrap = $('#assignEquipoWrap');
const assignList       = $('#assignList');
const assignNoOthers   = $('#assignNoOthers');
const assignCancel     = $('#assignCancel');
const assignConfirm    = $('#assignConfirm');

// Flujo “resolver”
const solveBlock   = $('#solveBlock');
const obsInput     = $('#obsTecnico');
const filesInput   = $('#evidencias');

// Scope actual (viene en <body data-scope="...">)
const scope = (document.body.dataset.scope || 'disponibles').toLowerCase();

// Estado JS
let currentId = null;
let cache     = [];
let tecnicos  = [];
let me        = null;
let assigning = false;

/* ----------------------------- HELPERS ----------------------------------- */
function toast(message, type = 'ok') {
  const wrap = document.getElementById('toastWrap');
  const t = document.createElement('div');
  t.className = `toast toast--${type}`;
  t.innerHTML = `
    <svg class="toast__icon" viewBox="0 0 24 24"><path d="M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4z"/></svg>
    <p class="toast__text">${message}</p>`;
  (wrap || document.body).appendChild(t);
  setTimeout(() => {
    t.classList.add('toast--hide');
    t.addEventListener('animationend', () => t.remove(), { once: true });
  }, 1200);
}

async function $json(url, opts = {}) {
  const res = await fetch(url, {
    credentials: 'same-origin',
    headers: { 'Accept': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const j = await res.json(); if (j?.msg) msg = j.msg; } catch {}
    throw new Error(msg);
  }
  try { return await res.json(); } catch { return null; }
}

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function badgeEstado(est) {
  const c = est === 'EN_CURSO' ? 'tk-en_curso'
        : est === 'RESUELTO'  ? 'tk-resuelto'
        : est === 'CANCELADO' ? 'tk-cancelado'
        : 'tk-pendiente';
  return `<span class="tk-estado ${c}">${est}</span>`;
}

/* --------------------------- PERFIL TÉCNICO ------------------------------ */
function initialsFrom(name) {
  const clean = (name || '').trim();
  if (!clean) return 'T';
  const parts = clean.split(/[._\-\s]+/).filter(Boolean);
  return (parts.slice(0, 2).map(p => p[0]).join('') || clean[0]).toUpperCase();
}

async function renderTechProfile() {
  const host = document.getElementById('techProfile');
  if (!host) return;

  let meData;
  try { meData = await $json('/api/session/me'); } catch { return; }

  const scopes = ['disponibles', 'asignados', 'historial'];
  const counts = { disponibles: 0, asignados: 0, historial: 0 };

  await Promise.all(scopes.map(async s => {
    try {
      const arr = await $json(`/api/tecnico/tickets?scope=${s}`);
      counts[s] = Array.isArray(arr) ? arr.length : 0;
    } catch {}
  }));

  const initials = initialsFrom(meData.username || meData.email || 'T');
  const email = meData.email || 'sin correo';
  const area  = meData.area_name || 'Sin área';

  host.innerHTML = `
    <div class="tech-avatar" aria-hidden="true"><span>${initials}</span></div>
    <div class="tech-info">
      <div class="name">${meData.username}</div>
      <div class="meta">
        <span class="tag" title="Rol">${meData.role}</span>
        <span class="tag" title="Área">${area}</span>
        <span title="Correo">${email}</span>
      </div>
    </div>
    <div class="tech-stats" aria-label="Resumen de tickets">
      <div class="tech-stat"><span id="statDisponibles" class="num">${counts.disponibles}</span><span class="lbl">Disponibles</span></div>
      <div class="tech-stat"><span id="statAsignados"  class="num">${counts.asignados}</span><span class="lbl">Mis asignados</span></div>
      <div class="tech-stat"><span id="statHistorial"  class="num">${counts.historial}</span><span class="lbl">Historial</span></div>
    </div>
  `;
}

async function refreshTechCounters() {
  const ids = {
    disponibles: document.getElementById('statDisponibles'),
    asignados:   document.getElementById('statAsignados'),
    historial:   document.getElementById('statHistorial'),
  };
  if (!ids.disponibles) return;
  try {
    const [d, a, h] = await Promise.all([
      $json('/api/tecnico/tickets?scope=disponibles').catch(() => []),
      $json('/api/tecnico/tickets?scope=asignados').catch(() => []),
      $json('/api/tecnico/tickets?scope=historial').catch(() => []),
    ]);
    ids.disponibles.textContent = Array.isArray(d) ? d.length : 0;
    ids.asignados.textContent   = Array.isArray(a) ? a.length : 0;
    ids.historial.textContent   = Array.isArray(h) ? h.length : 0;
  } catch {}
}

/* ------------------------------ LISTADO ---------------------------------- */
function skeleton(n = 6) {
  grid.innerHTML = new Array(n).fill(0).map(() => `
    <div class="tk-card">
      <div class="tk-h">
        <span class="skeleton" style="height:14px;width:120px;border-radius:8px"></span>
        <span class="skeleton" style="height:20px;width:92px;border-radius:999px"></span>
      </div>
      <div class="skeleton" style="height:20px;width:70%;border-radius:8px"></div>
      <div class="skeleton" style="height:12px;width:55%;border-radius:8px;margin-top:6px"></div>
      <div class="skeleton" style="height:12px;width:40%;border-radius:8px;margin-top:6px"></div>
      <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">
        <span class="skeleton" style="height:36px;width:96px;border-radius:999px"></span>
        <span class="skeleton" style="height:36px;width:116px;border-radius:999px"></span>
      </div>
    </div>`).join('');
}

function card(t) {
  return `
    <article class="tk-card" tabindex="0" aria-label="Ticket #${t.id}">
      <div class="tk-h">
        <span class="tk-area">${escapeHtml(t.area || '(Área)')}</span>
        ${badgeEstado(t.estado)}
      </div>
      <h3 class="tk-title">#${t.id} · ${escapeHtml(t.asunto || '(Sin asunto)')}</h3>
      <div class="tk-meta">
        <span><strong>Solicitante:</strong> ${escapeHtml(t.solicitante_nombre || 'N/D')}</span>
        <span><strong>Creado:</strong> ${escapeHtml(t.creado_en || '')}</span>
        ${t.asignados ? `<span><strong>Asignados:</strong> ${escapeHtml(t.asignados)}</span>` : ''}
      </div>
      <div class="tk-f">
        <button class="btn" onclick="ver(${t.id})">Ver</button>
        ${scope === 'disponibles' ? `<button class="btn btn-primary" onclick="tomar(${t.id})">Asignarme</button>` : ''}
      </div>
    </article>`;
}

function render(list) {
  grid.innerHTML = list.length
    ? list.map(card).join('')
    : `<div class="empty">No hay tickets.</div>`;
}

function aplicarFiltro() {
  const term = (q.value || '').toLowerCase().trim();
  if (!term) return render(cache);
  const f = cache.filter(t =>
    (t.asunto || '').toLowerCase().includes(term) ||
    (t.solicitante_nombre || '').toLowerCase().includes(term)
  );
  render(f);
}

async function cargar() {
  skeleton();
  cache = await $json(`/api/tecnico/tickets?scope=${encodeURIComponent(scope)}`).catch(() => []);
  aplicarFiltro();
}

async function refreshGrid() { await cargar(); }

/* ------------------------------ DETALLE ---------------------------------- */
async function ver(id) {
  const data = await $json(`/api/tecnico/tickets/${id}`).catch(() => null);
  if (!data?.ok) { toast('No se pudo cargar', 'err'); return; }

  const t = data.ticket;
  currentId = t.id;

  const asign = (data.asignados || []).map(a => a.username).join(', ') || 'Nadie';
  const notasHtml = (data.notas || []).map(n =>
    `<li><strong>${escapeHtml(n.autor)}</strong> — ${escapeHtml(n.creado_en)}<br>${escapeHtml(n.texto)}</li>`
  ).join('');

  const adj = data.adjuntos || [];
  const galHtml = adj.length ? `
    <div class="tk-desc" style="margin-top:10px">
      <span>Evidencias</span>
      <div class="tk-att-grid">
        ${adj.map(a => `
          <a class="tk-att" href="${a.url}" target="_blank" rel="noopener">
            <img src="${a.url}" alt="Evidencia ${escapeHtml(a.name)}">
          </a>`).join('')}
      </div>
    </div>` : '';

  dlgBody.innerHTML = `
    <h3 id="dlgTitle" class="tk-title">#${t.id} · ${escapeHtml(t.asunto || '')}</h3>
    <div class="tk-kv"><span>Estado</span> ${badgeEstado(t.estado)}</div>
    <div class="tk-kv"><span>Área</span> ${escapeHtml(t.area || 'N/D')}</div>
    <div class="tk-kv"><span>Solicitante</span> ${escapeHtml(t.solicitante_nombre || 'N/D')}</div>
    <div class="tk-kv"><span>Asignados</span> ${escapeHtml(asign)}</div>

    <div class="tk-desc">
      <span>Descripción</span>
      <pre>${escapeHtml(t.descripcion || '')}</pre>
    </div>
    ${galHtml}
    ${notasHtml ? `<div class="tk-desc" style="margin-top:10px">
      <span>Notas recientes</span>
      <ul style="margin:6px 0 0 18px">${notasHtml}</ul>
    </div>` : '' }
  `;

  // Guardar id del ticket en el diálogo para el flujo de RESUELTO
  dlg.dataset.id = String(t.id);

  // Mostrar controles según scope
  if (btnTomar)   btnTomar.style.display  = (scope === 'disponibles') ? ''  : 'none';
  if (estadoSel)  estadoSel.style.display = (scope === 'asignados')   ? ''  : 'none';
  if (btnEstado)  btnEstado.style.display = (scope === 'asignados')   ? ''  : 'none';

  if (btnTomar) btnTomar.onclick = () => tomar(t.id);

  if (typeof dlg.showModal === 'function') dlg.showModal();
}
window.ver = ver;

btnClose?.addEventListener('click', () => dlg.close());

/* -------------------------- ASIGNACIÓN EQUIPO ---------------------------- */
async function loadTecnicos() {
  try { tecnicos = await $json('/api/tecnicos'); }
  catch { tecnicos = []; }
}

function renderAssignList() {
  const meId  = me?.user_id;
  const otros = tecnicos.filter(tk => tk.id !== meId);
  assignList.innerHTML = '';

  if (!otros.length) {
    assignNoOthers.style.display = '';
  } else {
    assignNoOthers.style.display = 'none';
    otros.forEach(tk => {
      const id = `as_${tk.id}`;
      const row = document.createElement('label');
      row.style = 'display:flex;align-items:center;gap:8px;padding:8px;border:1px solid var(--line);border-radius:10px;background:#fff;';
      row.innerHTML = `
        <input type="checkbox" id="${id}" value="${tk.id}">
        <span style="font-weight:800;color:var(--brand)">${escapeHtml(tk.username)}</span>`;
      assignList.appendChild(row);
    });
  }
  optEquipo.disabled = otros.length === 0;
}

async function tomar(id) {
  currentId = id;

  // Radios por defecto
  if (optSolo)   optSolo.checked = true;
  if (optEquipo) optEquipo.checked = false;
  assignEquipoWrap.style.display = 'none';

  renderAssignList();
  assignDlg.showModal();
}
window.tomar = tomar;

// Toggle radios
optSolo?.addEventListener('change', () => { if (optSolo.checked)   assignEquipoWrap.style.display = 'none'; });
optEquipo?.addEventListener('change', () => { if (optEquipo.checked) assignEquipoWrap.style.display = '';   });

assignCancel?.addEventListener('click', () => assignDlg.close());

assignConfirm?.addEventListener('click', async () => {
  if (assigning) return;
  assigning = true;
  assignConfirm.disabled = true;

  try {
    // 1) Me asigno
    await fetch(`/api/tecnico/tickets/${currentId}/tomar`, { method: 'POST' });

    // 2) Equipo adicional
    if (optEquipo?.checked) {
      const ids = [...assignList.querySelectorAll('input[type="checkbox"]:checked')]
        .map(i => parseInt(i.value, 10));
      if (ids.length) {
        const rr = await fetch(`/api/tecnico/tickets/${currentId}/asignar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ usuario_ids: ids }),
        });
        if (!rr.ok) throw new Error('No se pudo asignar equipo');
      }
    }

    toast('Asignación realizada ✅');
    assignDlg.close();
    dlg.close();
    await refreshGrid();
    await refreshTechCounters();

  } catch (e) {
    toast('No se pudo asignar', 'err');
  } finally {
    assigning = false;
    assignConfirm.disabled = false;
  }
});

/* ---------------------- CAMBIAR ESTADO / RESOLVER ------------------------ */
function toggleSolveBlock() {
  if (!estadoSel || !solveBlock) return;
  const show = (estadoSel.value === 'RESUELTO');
  solveBlock.style.display = show ? 'block' : 'none';
  if (obsInput) obsInput.required = show;
}

estadoSel?.addEventListener('change', toggleSolveBlock);
toggleSolveBlock();

btnEstado?.addEventListener('click', async () => {
  if (!currentId) return;
  const estado = estadoSel.value;
  const tid = dlg?.dataset?.id || currentId;

  try {
    if (estado === 'RESUELTO') {
      // Observaciones obligatorias
      const nota = (obsInput?.value || '').trim();
      if (!nota) { obsInput?.focus(); toast('Escribe tus observaciones para resolver.'); return; }

      // Evidencias opcionales (máx 3)
      if (filesInput?.files?.length) {
        const fd = new FormData();
        Array.from(filesInput.files).slice(0, 3).forEach(f => fd.append('imagenes', f));
        await $json(`/api/tecnico/tickets/${tid}/evidencia`, { method: 'POST', body: fd });
      }

      // Cambiar estado con nota
      await $json(`/api/tecnico/tickets/${tid}/estado`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado: 'RESUELTO', nota }),
      });

      toast('Ticket marcado como RESUELTO.');
    } else {
      // Otros estados
      await $json(`/api/tecnico/tickets/${tid}/estado`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ estado }),
      });
      toast(`Estado actualizado a ${estado}.`);
    }

    dlg.close();
    await refreshGrid();
    await refreshTechCounters();

  } catch (err) {
    toast(err.message || 'No se pudo actualizar el estado.', 'err');
  }
});

/* ------------------------------- EVENTOS --------------------------------- */
btnRefresh?.addEventListener('click', async () => {
  await refreshGrid();
  setTimeout(refreshTechCounters, 150);
});

q?.addEventListener('input', aplicarFiltro);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (assignDlg?.open) assignDlg.close();
    if (dlg?.open)       dlg.close();
  }
});

/* -------------------------------- INIT ----------------------------------- */
(async function init() {
  // usuario básico y técnicos
  me = await $json('/api/session/basic').catch(() => null);
  await loadTecnicos();

  // perfil + grilla
  await renderTechProfile();
  await cargar();
})();
