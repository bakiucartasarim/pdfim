/* PDFim v2 — arayüz mantığı.
 *
 * Sayfalar Python tarafında PyMuPDF ile PNG olarak çizilir ve yerel sunucudan <img> ile yüklenir
 * (page_server.py). Ekrandaki yerleşim PDF noktası (pt) cinsinden sayfa boyutlarından hesaplanır;
 * böylece görüntü gelmeden de sayfa kutuları doğru boyutta durur ve kaydırma zıplamaz.
 */
'use strict';

const PT_TO_PX = 96 / 72;          // %100 yakınlaştırmada 1 pt kaç CSS pikseli
const ZOOM_MIN = 0.25, ZOOM_MAX = 4;
const STAGE_PAD = 48;              // #pages kenar boşluğu (sığdırma hesabı için)
const THUMB_W = 200;               // küçük resim genişliği (CSS px)
const MODE_NAMES = { duzenle: 'Düzenleme', aciklama: 'Açıklama & Not', sayfalar: 'Sayfalar', form: 'Form & İmza' };
const TOOL_NAMES = { secim: 'Seçim', metin: 'Metin', resim: 'Resim', 'metin-sec': 'Metin Seç', 'alan-sil': 'Alan Sil' };

const $ = (id) => document.getElementById(id);
const api = () => window.pywebview && window.pywebview.api;

const app = window.app = {
  doc: null,          // Python get_state() çıktısı; belge yoksa null
  zoom: 1,
  fit: 'width',       // 'width' | 'page' | null — pencere boyu değişince yeniden sığdırılır
  current: 0,         // ekrandaki sayfa (0 tabanlı)
  mode: 'duzenle',
  tool: 'secim',
  pageEls: [],
  thumbEls: [],
};

/* ── Belge durumu ─────────────────────────────────────────────────────────── */

function applyState(state) {
  const wasOpen = !!app.doc;
  const prevRev = app.doc && app.doc.rev;
  app.doc = state && state.open ? state : null;

  $('doc-title').textContent = app.doc ? app.doc.name : 'Belge açılmadı';
  $('doc-title').title = app.doc ? app.doc.path : '';
  $('empty-state').classList.toggle('is-hidden', !!app.doc);
  $('btn-save').disabled = !app.doc;
  $('btn-undo').disabled = !(app.doc && app.doc.canUndo);
  $('btn-redo').disabled = !(app.doc && app.doc.canRedo);
  document.body.classList.toggle('has-doc', !!app.doc);

  if (!app.doc) {
    buildPages();
    return;
  }
  if (app.doc.rev !== prevRev) {
    // Yeni belge → en baştan, genişliğe sığdırarak.
    // Aynı belgenin yeni revizyonu (geri al vb.) → kaydırma konumu ve sayfa korunur.
    const stage = $('stage'), top = wasOpen ? stage.scrollTop : 0;
    app.current = wasOpen ? Math.min(app.current, app.doc.pages.length - 1) : 0;
    if (!wasOpen) app.fit = 'width';
    buildPages();
    if (app.fit) fitZoom(app.fit, false);
    stage.scrollTop = top;
    setCurrent(app.current);
  }
  updatePageCounter();
}

app.onExternalOpen = (result) => handleOpenResult(result);

async function handleOpenResult(result) {
  // Parolalı dosya: doğru parola girilene ya da vazgeçilene kadar sor
  while (result && !result.ok && result.needsPassword) {
    const pw = window.prompt(`${result.error}\nParolayı girin:`);
    if (pw === null) return;
    result = await api().open_path(result.path, pw);
  }
  if (!result) return;
  if (!result.ok) return showError(result.error);
  app.doc = null;   // aynı dosya yeniden açılsa bile "yeni belge" gibi davran
  applyState(result.state);
}

/* ── Sayfa yerleşimi ──────────────────────────────────────────────────────── */

function buildPages() {
  const pages = $('pages'), thumbs = $('thumb-list');
  pages.replaceChildren();
  thumbs.replaceChildren();
  app.pageEls = [];
  app.thumbEls = [];
  pageObserver.disconnect();
  thumbObserver.disconnect();
  visiblePages.clear();   // ayrılmış eski sayfalar sette kalıp yeniden istenmesin
  $('thumb-count').textContent = app.doc ? `(${app.doc.pages.length})` : '';
  $('page-total').textContent = app.doc ? `/ ${app.doc.pages.length}` : '/ 0';
  if (!app.doc) return;

  app.doc.pages.forEach(([w, h], i) => {
    const page = document.createElement('div');
    page.className = 'page';
    page.dataset.index = i;
    const img = document.createElement('img');
    img.alt = `Sayfa ${i + 1}`;
    img.draggable = false;
    page.append(img);
    pages.append(page);
    app.pageEls.push(page);
    pageObserver.observe(page);

    const thumb = document.createElement('button');
    thumb.className = 'thumb';
    thumb.type = 'button';
    const timg = document.createElement('img');
    timg.alt = '';
    timg.draggable = false;
    timg.style.aspectRatio = `${w} / ${h}`;
    const label = document.createElement('span');
    label.className = 'thumb-label';
    label.textContent = i + 1;
    thumb.append(timg, label);
    thumb.addEventListener('click', () => scrollToPage(i));
    thumbs.append(thumb);
    app.thumbEls.push(thumb);
    thumbObserver.observe(thumb);
  });
  layoutPages();
}

function layoutPages() {
  if (!app.doc) return;
  app.doc.pages.forEach(([w, h], i) => {
    const el = app.pageEls[i];
    el.style.width = `${Math.round(w * PT_TO_PX * app.zoom)}px`;
    el.style.height = `${Math.round(h * PT_TO_PX * app.zoom)}px`;
  });
  $('zoom-slider').value = Math.round(app.zoom * 100);
  $('zoom-label').textContent = `${Math.round(app.zoom * 100)}%`;
}

/* Çizim ölçeği: ekran pikseli başına bir görüntü pikseli (yüksek DPI ekranlarda keskin) */
function renderScale() {
  return +(app.zoom * PT_TO_PX * (window.devicePixelRatio || 1)).toFixed(3);
}

function pageUrl(i, scale) {
  return `../page/${i}.png?s=${scale}&v=${app.doc.rev}`;
}

function loadPageImage(page) {
  const i = +page.dataset.index, s = renderScale();
  const img = page.firstChild;
  if (img.dataset.key === `${app.doc.rev}:${s}`) return;
  img.dataset.key = `${app.doc.rev}:${s}`;
  img.src = pageUrl(i, s);
}

// Sayfa görüntüleri yalnız ekrana yaklaşınca istenir (yüzlerce sayfalık datasheet'ler için şart)
const visiblePages = new Set();
const pageObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) { visiblePages.add(e.target); loadPageImage(e.target); }
    else visiblePages.delete(e.target);
  }
}, { root: $('stage'), rootMargin: '600px 0px' });

const thumbObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting) continue;
    const thumb = e.target, i = app.thumbEls.indexOf(thumb), img = thumb.firstChild;
    const s = +(THUMB_W / app.doc.pages[i][0] * (window.devicePixelRatio || 1)).toFixed(3);
    if (img.dataset.key !== `${app.doc.rev}:${s}`) {
      img.dataset.key = `${app.doc.rev}:${s}`;
      img.src = pageUrl(i, s);
    }
  }
}, { root: $('thumb-list'), rootMargin: '400px 0px' });

/* ── Yakınlaştırma ────────────────────────────────────────────────────────── */

let rerenderTimer = 0;

function setZoom(z, keepFit = false) {
  if (!app.doc) return;
  z = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, z));
  if (!keepFit) app.fit = null;
  const stage = $('stage');
  // Ekranın ortasındaki nokta yakınlaştırmadan sonra da ortada kalsın
  const anchor = (stage.scrollTop + stage.clientHeight / 2) / Math.max(1, stage.scrollHeight);
  const anchorX = (stage.scrollLeft + stage.clientWidth / 2) / Math.max(1, stage.scrollWidth);
  app.zoom = z;
  layoutPages();
  stage.scrollTop = anchor * stage.scrollHeight - stage.clientHeight / 2;
  stage.scrollLeft = anchorX * stage.scrollWidth - stage.clientWidth / 2;
  // Kaydırıcı sürüklenirken her adımda çizdirme; görüntü CSS ile büyür, durunca keskinleşir
  clearTimeout(rerenderTimer);
  rerenderTimer = setTimeout(() => visiblePages.forEach(loadPageImage), 180);
}

function fitZoom(kind, userAction = true) {
  if (!app.doc) return;
  const stage = $('stage');
  const [w, h] = app.doc.pages[app.current] || app.doc.pages[0];
  const availW = stage.clientWidth - 2 * STAGE_PAD;
  const availH = stage.clientHeight - 2 * STAGE_PAD;
  let z = availW / (w * PT_TO_PX);
  if (kind === 'page') z = Math.min(z, availH / (h * PT_TO_PX));
  setZoom(z, true);
  app.fit = kind;
  if (userAction) scrollToPage(app.current, 'auto');
}

/* ── Sayfa gezinme ────────────────────────────────────────────────────────── */

function scrollToPage(i, behavior = 'smooth') {
  if (!app.doc) return;
  i = Math.min(app.doc.pages.length - 1, Math.max(0, i));
  const stage = $('stage'), el = app.pageEls[i];
  stage.scrollTo({ top: el.offsetTop - STAGE_PAD / 2, behavior });
  setCurrent(i);
}

function setCurrent(i) {
  if (app.thumbEls[app.current]) app.thumbEls[app.current].classList.remove('is-active');
  app.current = i;
  const t = app.thumbEls[i];
  if (t) {
    t.classList.add('is-active');
    t.scrollIntoView({ block: 'nearest' });
  }
  updatePageCounter();
}

function updatePageCounter() {
  const n = app.doc ? app.doc.pages.length : 0;
  const cur = app.doc ? app.current + 1 : 0;
  $('page-counter').textContent = app.doc ? `Sayfa ${cur} / ${n}` : '';
  if (document.activeElement !== $('page-input')) $('page-input').value = app.doc ? cur : '';
  updateStatus();
}

/* Ekranın dikey ortasından geçen sayfa "şu anki" sayfadır */
function pageAtViewCenter() {
  const stage = $('stage'), y = stage.scrollTop + stage.clientHeight / 2;
  let lo = 0, hi = app.pageEls.length - 1;
  while (lo < hi) {   // sayfalar yukarıdan aşağı sıralı → ikili arama
    const mid = (lo + hi + 1) >> 1;
    if (app.pageEls[mid].offsetTop <= y) lo = mid; else hi = mid - 1;
  }
  return lo;
}

/* ── Durum hapı ───────────────────────────────────────────────────────────── */

const PAPER = [['A3', 297, 420], ['A4', 210, 297], ['A5', 148, 210], ['Letter', 216, 279], ['Legal', 216, 356]];

function paperName(wPt, hPt) {
  const w = wPt / 72 * 25.4, h = hPt / 72 * 25.4;
  const [a, b] = w < h ? [w, h] : [h, w];
  const hit = PAPER.find(([, pw, ph]) => Math.abs(a - pw) < 3 && Math.abs(b - ph) < 3);
  const size = `${Math.round(w)} × ${Math.round(h)} mm`;
  return hit ? `${hit[0]} (${size})` : size;
}

function updateStatus() {
  const parts = [`${MODE_NAMES[app.mode]} · ${TOOL_NAMES[app.tool]}`];
  if (app.doc) parts.push(paperName(...app.doc.pages[app.current]));
  $('status-text').textContent = parts.join('  ·  ');
}

/* ── Bildirimler ──────────────────────────────────────────────────────────── */

let toastTimer = 0;
function toast(msg) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('is-visible'), 2600);
}

function showError(msg) {
  window.alert(msg || 'Beklenmeyen bir hata oluştu.');
}

/* ── Komutlar ─────────────────────────────────────────────────────────────── */

const commands = {
  async open() { handleOpenResult(await api().open_dialog()); },
  async save() {
    if (!app.doc) return;
    const r = await api().save();
    if (!r) return;
    if (!r.ok) return showError(r.error);
    applyState(r.state);
    toast('Kaydedildi');
  },
  async saveAs() {
    if (!app.doc) return;
    const r = await api().save_as();
    if (!r) return;
    if (!r.ok) return showError(r.error);
    applyState(r.state);
    toast('Kaydedildi');
  },
  async undo() { if (app.doc && app.doc.canUndo) applyState(await api().undo()); },
  async redo() { if (app.doc && app.doc.canRedo) applyState(await api().redo()); },
  zoomIn() { setZoom(app.zoom * 1.2); },
  zoomOut() { setZoom(app.zoom / 1.2); },
  fitWidth() { fitZoom('width'); },
  fitPage() { fitZoom('page'); },
};

function setMode(mode) {
  app.mode = mode;
  document.querySelectorAll('#mode-tabs [data-mode]').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.mode === mode));
  if (mode !== 'duzenle') toast(`${MODE_NAMES[mode]} modülü sonraki aşamada gelecek`);
  updateStatus();
}

function setTool(tool) {
  app.tool = tool;
  document.querySelectorAll('#tool-strip [data-tool]').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.tool === tool));
  updateStatus();
}

/* ── Olay bağlama ─────────────────────────────────────────────────────────── */

function bind() {
  const on = (id, fn) => $(id).addEventListener('click', fn);
  on('btn-open', commands.open);
  on('btn-open-empty', commands.open);
  on('btn-save', commands.save);
  on('btn-undo', commands.undo);
  on('btn-redo', commands.redo);
  on('zoom-in', commands.zoomIn);
  on('zoom-out', commands.zoomOut);
  on('fit-width', commands.fitWidth);
  on('fit-page', commands.fitPage);
  on('page-prev', () => scrollToPage(app.current - 1));
  on('page-next', () => scrollToPage(app.current + 1));
  on('inspector-close', () => document.body.classList.add('inspector-closed'));
  on('btn-inspector', () => document.body.classList.toggle('inspector-closed'));

  $('zoom-slider').addEventListener('input', (e) => setZoom(e.target.value / 100));
  $('page-input').addEventListener('change', (e) => {
    const n = parseInt(e.target.value, 10);
    if (n) scrollToPage(n - 1, 'auto'); else updatePageCounter();
    e.target.blur();
  });
  $('page-input').addEventListener('keydown', (e) => { if (e.key === 'Escape') { updatePageCounter(); e.target.blur(); } });

  document.querySelectorAll('#mode-tabs [data-mode]').forEach((b) =>
    b.addEventListener('click', () => setMode(b.dataset.mode)));
  document.querySelectorAll('#tool-strip [data-tool]').forEach((b) =>
    b.addEventListener('click', () => setTool(b.dataset.tool)));

  let scrollRaf = 0;
  $('stage').addEventListener('scroll', () => {
    if (scrollRaf || !app.doc) return;
    scrollRaf = requestAnimationFrame(() => {
      scrollRaf = 0;
      const i = pageAtViewCenter();
      if (i !== app.current) setCurrent(i);
    });
  });

  // Ctrl + tekerlek: yakınlaştır (tarayıcının kendi sayfa yakınlaştırması yerine)
  $('stage').addEventListener('wheel', (e) => {
    if (!e.ctrlKey) return;
    e.preventDefault();
    setZoom(app.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1));
  }, { passive: false });

  let resizeTimer = 0;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (app.fit) fitZoom(app.fit, false); }, 120);
  });

  document.addEventListener('keydown', onKey);
}

const TOOL_KEYS = { 1: 'metin', 2: 'resim', 3: 'metin-sec', 4: 'alan-sil' };   // v1 ile aynı

function onKey(e) {
  if (!e.ctrlKey) return;
  const inField = e.target.matches('input, textarea, [contenteditable="true"]');
  const k = e.key.toLowerCase();
  let handled = true;
  if (k === 'o') commands.open();
  else if (k === 's' && e.shiftKey) commands.saveAs();
  else if (k === 's') commands.save();
  else if (inField) handled = false;   // metin kutusundayken Ctrl+Z vb. kutunun kendisine kalsın
  else if (k === 'z' && e.shiftKey) commands.redo();
  else if (k === 'z') commands.undo();
  else if (k === 'y') commands.redo();
  else if (k === '=' || k === '+') commands.zoomIn();
  else if (k === '-') commands.zoomOut();
  else if (k === 'w' && e.shiftKey) commands.fitPage();
  else if (k === 'w') commands.fitWidth();
  else if (TOOL_KEYS[k]) setTool(TOOL_KEYS[k]);
  else handled = false;
  if (handled) e.preventDefault();
}

/* ── Başlangıç ────────────────────────────────────────────────────────────── */

// Python tarafındaki istisnalar köprü Promise'ini reddeder; sessizce kaybolmasın
window.addEventListener('unhandledrejection', (e) => {
  const err = e.reason || {};
  showError(`İşlem tamamlanamadı.
(${err.message || err})`);
});

bind();
setMode('duzenle');
setTool('secim');
applyState(null);

window.addEventListener('pywebviewready', async () => applyState(await api().get_state()));
