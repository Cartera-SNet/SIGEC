/* SIGEC - comportamiento general de la interfaz */
(function () {
  var body = document.body;

  // Menú lateral (hamburguesa)
  var hamb = document.getElementById('hamb');
  if (hamb) hamb.addEventListener('click', function () {
    if (window.innerWidth <= 900) { body.classList.toggle('nav-open'); body.classList.remove('nav-closed'); }
    else body.classList.toggle('nav-closed');
  });

  // Móvil: el menú es un cajón; se cierra al tocar el fondo o una opción
  var scrim = document.getElementById('scrim');
  if (scrim) scrim.addEventListener('click', function () { body.classList.remove('nav-open'); });
  document.querySelectorAll('.nav a').forEach(function (l) {
    l.addEventListener('click', function () { if (window.innerWidth <= 900) body.classList.remove('nav-open'); });
  });

  // Móvil: cada celda lleva el nombre de su columna para mostrar las tablas como tarjetas
  document.querySelectorAll('table.tbl').forEach(function (t) {
    var heads = Array.prototype.map.call(t.querySelectorAll('thead th'), function (h) { return h.textContent.trim(); });
    t.querySelectorAll('tbody tr').forEach(function (tr) {
      Array.prototype.forEach.call(tr.children, function (td, i) { if (!td.hasAttribute('colspan') && heads[i]) td.setAttribute('data-label', heads[i]); });
    });
  });

  // Cerrar menús desplegables al hacer clic fuera
  document.addEventListener('click', function (e) {
    document.querySelectorAll('.dd.open').forEach(function (d) { if (!d.contains(e.target)) d.classList.remove('open'); });
  });

  // Confirmaciones en formularios/botones: data-confirm="mensaje"
  document.addEventListener('submit', function (e) {
    var m = e.target.getAttribute('data-confirm');
    if (m && !window.confirm(m)) e.preventDefault();
    var p = e.target.getAttribute('data-motivo');   // motivo obligatorio (RN-06)
    if (p && !e.defaultPrevented) {
      var t = (window.prompt(p) || '').trim();
      if (!t) { e.preventDefault(); return; }
      e.target.querySelector('input[name=motivo]').value = t;
    }
  });

  // Mensajes flash se ocultan solos
  setTimeout(function () { document.querySelectorAll('.flash-success').forEach(function (f) { f.style.display = 'none'; }); }, 7000);

  // Los campos de fecha abren el calendario con un clic en cualquier parte
  document.addEventListener('click', function (e) {
    var t = e.target; if (t && t.type === 'date' && t.showPicker) { try { t.showPicker(); } catch (x) {} }
  });

  window.abrirClave = function () { var f = document.getElementById('form-clave'); if (f) f.style.display = 'grid'; };

  // ------------------------------------------------------------ Asistente IA
  var fab = document.getElementById('ia-fab'), panel = document.getElementById('ia-panel');
  if (!fab) return;
  var msgs = document.getElementById('ia-msgs'), form = document.getElementById('ia-form'),
      input = document.getElementById('ia-input'), sug = document.getElementById('ia-sug'), hist = [];

  function md(t) {
    // Escapa el HTML y aplica un markdown mínimo: **negrita**, *cursiva*, `código`, listas y enlaces SOLO internos (/ruta)
    t = t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    t = t.replace(/\[([^\]]+)\]\((\/[^)\s]*)\)/g, function (m, txt, url) {
      if (url.indexOf('//') === 0 || /[<>"']/.test(url)) return m;
      return '<a href="' + url + '">' + txt + '</a>';
    });
    t = t.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, '$1<i>$2</i>')
         .replace(/`([^`\n]+)`/g, '<code>$1</code>');
    return t.replace(/^[ \t]*[-•]\s+/gm, '• ');
  }
  function add(cls, html, extra) {
    var d = document.createElement('div'); d.className = 'ia-m ' + cls; d.innerHTML = html;
    if (extra) { var s = document.createElement('small'); s.textContent = extra; d.appendChild(s); }
    msgs.appendChild(d); msgs.scrollTop = msgs.scrollHeight; return d;
  }
  function toggle() { panel.classList.toggle('open'); if (panel.classList.contains('open')) input.focus(); }
  fab.addEventListener('click', toggle);
  document.getElementById('ia-close').addEventListener('click', toggle);

  function preguntar(texto) {
    texto = (texto || '').trim(); if (!texto) return;
    add('me', md(texto)); hist.push({ rol: 'user', texto: texto }); input.value = ''; sug.style.display = 'none';
    var t = add('bot typing', 'Pensando y consultando…');
    fetch(window.SIGEC.api, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.SIGEC.csrf },
      body: JSON.stringify({ pregunta: texto, historial: hist.slice(-6), pagina: window.SIGEC.pagina })
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); }).then(function (d) {
      t.remove();
      var bm = add('bot', md(d.respuesta || 'Sin respuesta.'), d.motor ? 'Motor: ' + d.motor.replace('claude:', 'Claude · ') : '');
      msgs.scrollTop = Math.max(bm.offsetTop - 10, 0);
      hist.push({ rol: 'assistant', texto: d.respuesta });
    }).catch(function () { t.remove(); add('bot', 'No pude responder en este momento (revisa tu conexión o inicia sesión de nuevo). Intenta otra vez.'); });
  }
  form.addEventListener('submit', function (e) { e.preventDefault(); preguntar(input.value); });
  sug.querySelectorAll('button').forEach(function (b) { b.addEventListener('click', function () { preguntar(b.textContent); }); });
})();
