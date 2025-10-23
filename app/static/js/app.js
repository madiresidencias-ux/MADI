// Footer: año actual
document.getElementById('y')?.textContent = new Date().getFullYear();

(function () {
  const $ = (s, ctx = document) => ctx.querySelector(s);
  const $$ = (s, ctx = document) => Array.from(ctx.querySelectorAll(s));

  // Endpoints (inyectables por window.API) + fallback
  const API = window.API || {
    LIST: '/api/usuarios',
    GET: (id) => `/api/usuarios/${id}`,
    ESTADO: (id) => `/api/usuarios/${id}/estado`,
    UPDATE: (id) => `/api/usuarios/${id}`,
  };
  const ep = (key, id) => {
    const v = API[key];
    if (typeof v === 'function') return v(id);
    return typeof v === 'string' ? v.replace('__ID__', id) : '';
  };

  // --------- Helper fetch robusto ---------
  async function api(url, opts = {}) {
    const baseOpts = {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    };

    const res = await fetch(url, { ...baseOpts, ...opts });

    // Detecta redirecciones a /login o respuestas HTML (por 302 o template)
    const ct = res.headers.get('content-type') || '';
    if (res.redirected || (!ct.includes('application/json') && !ct.includes('json'))) {
      window.location.href = '/login';
      throw { msg: 'Sesión perdida. Redirigiendo a login.' };
    }

    let data = null;
    try { data = await res.json(); } catch {}

    if (res.status === 401) {
      window.location.href = '/login';
      throw { msg: 'No autenticado. Redirigiendo a login.' };
    }
    if (res.status === 403) {
      throw { msg: 'No autorizado para esta acción.' };
    }
    if (!res.ok) throw (data || { msg: 'Error API' });

    return data;
  }

  function toast($el, text, ok = true) {
    if (!$el) return;
    $el.textContent = text;
    $el.style.color = ok ? '#2ca84a' : '#c02b2b';
    setTimeout(() => { $el.textContent = ''; }, 4000);
  }

  // Debounce simple
  function debounce(fn, ms = 200) {
    let t; return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // ==========================
  //  MÓDULO USUARIOS (solo si existe la tabla)
  // ==========================
  const tableBody = $('#tbl-usuarios tbody');
  if (tableBody) {
    const form = $('#form-usuario');
    const msg = $('#form-msg');
    const btnSave = $('#btn-save');
    const btnGen = $('#btn-gen');
    const btnCopy = $('#btn-copy');
    const inputPwd = $('#password');
    const q = $('#q');

    // Modal edición
    const modal = $('#modal-edit');
    const editMsg = $('#edit-msg');
    const formEdit = $('#form-edit');
    const editId = $('#edit-id');
    const editUser = $('#edit-username');
    const editEmail = $('#edit-email');
    const editRole = $('#edit-role');
    const editArea = $('#edit-area');
    const editPass = $('#edit-password');

    function openModal() {
      if (!modal) return;
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      document.body.style.overflow = 'hidden';
    }
    function closeModal() {
      if (!modal) return;
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
      formEdit?.reset();
      if (editMsg) editMsg.textContent = '';
    }
    if (modal) {
      modal.addEventListener('click', e => { if (e.target.dataset.close) closeModal(); });
      document.addEventListener('keydown', e => { if (e.key === 'Escape' && modal.classList.contains('open')) closeModal(); });
    }

    function genPassword(n = 12) {
      const A = 'ABCDEFGHJKLMNPQRSTUVWXYZ', a = 'abcdefghijkmnopqrstuvwxyz', d = '23456789', s = '!@#$%&*?';
      const pool = A + a + d + s;
      const out = [
        A[Math.floor(Math.random() * A.length)],
        a[Math.floor(Math.random() * a.length)],
        d[Math.floor(Math.random() * d.length)]
      ];
      while (out.length < n) out.push(pool[Math.floor(Math.random() * pool.length)]);
      for (let i = out.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [out[i], out[j]] = [out[j], out[i]];
      }
      return out.join('');
    }

    btnGen?.addEventListener('click', () => {
      if (!inputPwd) return;
      inputPwd.value = genPassword(12);
      inputPwd.focus(); inputPwd.select();
    });

    btnCopy?.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(inputPwd?.value || '');
        toast(msg, 'Contraseña copiada', true);
      } catch (e) {
        toast(msg, 'No se pudo copiar', false);
      }
    });

    form?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const fd = new FormData(form);
      const payload = {
        username: fd.get('username')?.toString().trim(),
        email: (fd.get('email') || '').toString().trim() || null,
        role_id: Number(fd.get('role_id')),
        area_id: fd.get('area_id') ? Number(fd.get('area_id')) : null,
        password: fd.get('password')?.toString() || ''
      };
      if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Guardando...'; }
      try {
        const data = await api(ep('LIST'), { method: 'POST', body: JSON.stringify(payload) });
        if (!data?.ok) throw { msg: 'No se pudo guardar' };
        form.reset();
        toast(msg, 'Usuario creado correctamente', true);
        loadUsuarios();
      } catch (err) {
        toast(msg, err?.msg || 'Error al guardar', false);
      } finally {
        if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Guardar usuario'; }
      }
    });

    let cache = [];
    function render(rows) {
      rows = Array.isArray(rows) ? rows : [];
      const needle = (q?.value || '').toLowerCase();
      const filtered = !needle ? rows : rows.filter(r => {
        return [r.username, r.email, r.rol, r.area].some(v => (v || '').toLowerCase().includes(needle));
      });
      tableBody.innerHTML = filtered.map(r => `
        <tr>
          <td>${r.id}</td>
          <td>${r.username || ''}</td>
          <td>${r.email || ''}</td>
          <td>${r.rol || ''}</td>
          <td>${r.area || ''}</td>
          <td><span class="state">${r.is_active ? '<span class="dot on"></span>Activo' : '<span class="dot off"></span>Inactivo'}</span></td>
          <td class="actions-td">
            <button class="btn ghost btn-edit" data-id="${r.id}">Editar</button>
            <button class="btn ghost btn-toggle" data-id="${r.id}">${r.is_active ? 'Desactivar' : 'Activar'}</button>
          </td>
        </tr>
      `).join('') || `<tr><td colspan="7">Sin registros</td></tr>`;
    }

    async function loadUsuarios() {
      try {
        cache = await api(ep('LIST'));
        render(cache);
      } catch (e) {
        toast(msg, 'No se pudo cargar el listado', false);
        tableBody.innerHTML = `<tr><td colspan="7">No se pudo cargar el listado</td></tr>`;
      }
    }

    q?.addEventListener('input', debounce(() => render(cache), 200));

    tableBody.addEventListener('click', async ev => {
      const editBtn = ev.target.closest('.btn-edit');
      const togBtn = ev.target.closest('.btn-toggle');

      if (editBtn) {
        const id = Number(editBtn.dataset.id);
        try {
          const u = await api(ep('GET', id));
          if (editId) editId.value = u.id;
          if (editUser) editUser.value = u.username || '';
          if (editEmail) editEmail.value = u.email || '';
          if (editRole) editRole.value = (u.role_id ?? '') + '';
          if (editArea) editArea.value = (u.area_id ?? '') + '';
          if (editPass) editPass.value = '';
          openModal();
        } catch (e) {
          toast(msg, 'No se pudo cargar el usuario', false);
        }
        return;
      }

      if (togBtn) {
        const id = Number(togBtn.dataset.id);
        try {
          await api(ep('ESTADO', id), { method: 'PATCH' });
          await loadUsuarios();
          toast(msg, 'Estado actualizado', true);
        } catch (e) {
          toast(msg, 'No se pudo actualizar el estado', false);
        }
        return;
      }
    });

    formEdit?.addEventListener('submit', async ev => {
      ev.preventDefault();
      const payload = {
        username: editUser?.value.trim(),
        email: (editEmail?.value || '').trim() || null,
        role_id: Number(editRole?.value),
        area_id: editArea?.value ? Number(editArea.value) : null,
      };
      const newPwd = (editPass?.value || '').trim();
      if (newPwd) payload.password = newPwd;

      const id = Number(editId?.value);
      const btn = $('#btn-update');
      if (btn) { btn.disabled = true; btn.textContent = 'Guardando...'; }

      try {
        await api(ep('UPDATE', id), { method: 'PUT', body: JSON.stringify(payload) });
        toast(editMsg, 'Cambios guardados', true);
        closeModal();
        loadUsuarios();
      } catch (err) {
        toast(editMsg, err?.msg || 'No se pudo actualizar', false);
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Guardar cambios'; }
      }
    });

    // init
    loadUsuarios();
  }
})();