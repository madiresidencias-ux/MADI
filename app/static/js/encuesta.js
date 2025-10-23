// static/js/encuesta.js — COMPLETO (valida sugerencias y bandejas de comentario)
(function(){
  const $ = (s,ctx=document)=>ctx.querySelector(s);
  const $$ = (s,ctx=document)=>Array.from(ctx.querySelectorAll(s));
  const byId = (id)=>document.getElementById(id);

  // Toggle de bandejas de comentario (p2, p3, p4)
  $$('.cmt-toggle').forEach(btn=>{
    const trayId = btn.getAttribute('aria-controls');
    const tray = byId(trayId);
    btn.addEventListener('click', ()=>{
      const isHidden = tray.hasAttribute('hidden');
      if(isHidden){
        tray.removeAttribute('hidden');
        btn.setAttribute('aria-expanded','true');
        const ta = tray.querySelector('textarea'); ta && ta.focus();
      }else{
        tray.setAttribute('hidden','');
        btn.setAttribute('aria-expanded','false');
      }
    });
  });

  // Abrir automáticamente la bandeja si calificación baja (1 o 2)
  $$('.stars input[type="radio"][name="p2"], .stars input[type="radio"][name="p3"], .stars input[type="radio"][name="p4"]').forEach(r=>{
    r.addEventListener('change', ()=>{
      const q = r.name; // p2 | p3 | p4
      const v = parseInt(r.value,10);
      if(v<=2){
        const btn = $(`.cmt-toggle[aria-controls="cmt-${q}"]`);
        const tray = byId(`cmt-${q}`);
        if(tray && tray.hasAttribute('hidden')){
          tray.removeAttribute('hidden');
          btn && btn.setAttribute('aria-expanded','true');
          const ta = tray.querySelector('textarea'); ta && ta.focus();
        }
      }
    });
  });

  // Contadores de caracteres para bandejas (máx 300)
  $$('textarea[name$="_comentario"]').forEach(ta=>{
    const max = parseInt(ta.getAttribute('maxlength')||'300',10);
    const badge = $(`[data-count-for="${ta.name}"]`);
    const update = ()=>{
      const len = ta.value.length;
      if(len>max) ta.value = ta.value.slice(0,max);
      if(badge) badge.textContent = `${ta.value.length}/${max}`;
    };
    ta.addEventListener('input', update);
    update();
  });

  // Envío
  const form = byId('encuesta-madi');
  form.addEventListener('submit', async (e)=>{
    e.preventDefault();
    const fd = new FormData(form);

    // estrellas seleccionadas: originales + nuevas
    ['p2','p3','p4','q_rapidez','q_amable','q_identifico','q_efectiva','q_satisf_solucion','q_satisf_web']
      .forEach(n=>{
        const r=document.querySelector(`input[name="${n}"]:checked`);
        if(r) fd.set(n, r.value);
      });

    // Validación: sugerencias obligatorio
    const sug = (fd.get('sugerencias')||'').trim();
    if(!sug){
      alert('Por favor, escribe tus sugerencias para mejorar el servicio.');
      byId('sugerencias').focus();
      return;
    }

    try{
      const resp = await fetch('/api/encuestas', { method:'POST', body:fd, credentials:'include' });
      const data = await resp.json().catch(()=>({}));
      if(!resp.ok || !data.ok) throw new Error(data.error || `HTTP ${resp.status}`);
      alert('¡Encuesta registrada! Gracias por tu retroalimentación.');
      window.location.href = "/solicitante/tickets";
    }catch(err){
      alert('No se pudo registrar: ' + (err.message || 'Error desconocido'));
    }
  });
})();