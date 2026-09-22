/* PDFim v2 — belge görünümü, komutlar ve klavye. En son yüklenir ve uygulamayı başlatır.
 *
 * Sayfalar Python tarafında PyMuPDF ile PNG olarak çizilir ve yerel sunucudan <img> ile yüklenir
 * (page_server.py). Ekrandaki yerleşim PDF noktası (pt) cinsinden sayfa boyutlarından hesaplanır;
 * böylece görüntü gelmeden de sayfa kutuları doğru boyutta durur ve kaydırma zıplamaz.
 */
'use strict';

const ZOOM_MIN = 0.25, ZOOM_MAX = 4;
const STAGE_PAD = 48;              // #pages yan boşluğu — app.css ile aynı olmalı
const THUMB_W = 200;               // küçük resim genişliği (CSS px)
const TOOL_HINTS = {
  secim: 'Tıkla: seç · Sürükle: taşı · Çift tık: düzenle',
  metin: 'Yazı eklemek için tıklayın · Metne tıklayınca düzenlenir',
  'metin-sec': 'Alan sürükleyin — seçilen metin kopyalanır',
  'alan-sil': 'Silinecek alanı sürükleyin',
};
const MODE_NAMES = { duzenle: 'Düzenleme', aciklama: 'Açıklama & Not', sayfalar: 'Sayfalar', form: 'Form & İmza' };

/* ── Belge durumu ─────────────────────────────────────────────────────────── */

function applyState(state) {
  const prev = app.doc;
  app.doc = state && state.open ? state : null;
  const doc = app.doc;

  $('doc-title').textContent = doc ? doc.name : 'Belge açılmadı';
  $('doc-title').title = doc ? doc.path : '';
  $('empty-state').classList.toggle('is-hidden', !!doc);
  $('btn-save').disabled = !doc;
  $('btn-undo').disabled = !(doc && doc.canUndo);
  $('btn-redo').disabled = !(doc && doc.canRedo);
  document.body.classList.toggle('has-doc', !!doc);

  if (!doc) {
    app.layers.clear();
    buildPages();
    renderInspector();
    renderRecent(state ? state.recent : []);
    return;
  }
  const rebuild = !prev || prev.gen !== doc.gen || prev.pages.length !== doc.pages.length;
  if (rebuild && (!prev || prev.path !== doc.path || app.freshOpen)) app.pageSel = new Set();
  if (rebuild) {
    // Yeni belge → en baştan, genişliğe sığdırarak.
    // Aynı belge yeniden yüklendi (geri al / yinele) → kaydırma konumu ve sayfa korunur.
    const sameFile = prev && prev.path === doc.path && !app.freshOpen;
    const stage = $('stage'), top = sameFile ? stage.scrollTop : 0;
    app.current = sameFile ? Math.min(app.current, doc.pages.length - 1) : 0;
    if (!sameFile) app.fit = 'width';
    app.freshOpen = false;
    app.layers.clear();
    app.sel = null;
    app.highlight = null;
    app.hover = null;
    buildPages();
    if (app.fit) fitZoom(app.fit, false);
    stage.scrollTop = top;
    setCurrent(app.current);
    renderInspector();
  } else {
    // Yalnız değişen sayfaların görüntüsü ve kutuları yenilenir
    doc.versions.forEach((v, i) => { if (v !== prev.versions[i]) refreshPage(i); });
  }
  if (app.mode === 'sayfalar') buildGrid();
  updatePageCounter();
}

function refreshPage(i) {
  if (app.sel && app.sel.page === i) app.sel = null;
  if (app.highlight && app.highlight.page === i) app.highlight = null;
  if (app.hover && app.hover.page === i) app.hover = null;
  if (visiblePages.has(app.pageEls[i])) { loadPageImage(app.pageEls[i]); fetchLayer(i); }
  else renderLayer(i);
  const t = app.thumbEls[i];
  if (t && t.firstChild.dataset.key) loadThumb(t, i);
  renderInspector();
}

function renderRecent(paths) {
  const list = $('recent-list');
  list.replaceChildren();
  if (!paths || !paths.length) return;
  const h = document.createElement('div');
  h.className = 'caps';
  h.textContent = 'Son açılanlar';
  list.append(h);
  for (const p of paths) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'recent-item';
    b.title = p;
    const cut = Math.max(p.lastIndexOf('\\'), p.lastIndexOf('/'));
    b.innerHTML = '<span class="ms">picture_as_pdf</span><span class="recent-text"><span class="recent-name"></span><span class="recent-dir"></span></span>';
    b.querySelector('.recent-name').textContent = p.slice(cut + 1);
    b.querySelector('.recent-dir').textContent = p.slice(0, cut);
    b.addEventListener('click', async () => handleOpenResult(await serial(() => api().open_path(p))));
    list.append(b);
  }
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
  app.freshOpen = true;   // aynı dosya yeniden açılsa bile "yeni belge" gibi davran
  applyState(result.state);
}

/* ── Sayfa yerleşimi ──────────────────────────────────────────────────────── */

function buildPages() {
  const pages = $('pages'), thumbs = $('thumb-list');
  commitOpenEdit();
  hideFormatBar();
  pages.replaceChildren();
  thumbs.replaceChildren();
  app.pageEls = [];
  app.pending.clear();       // geçici katmanlar eski sayfa öğeleriyle birlikte gitti
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
    img.addEventListener('load', () => onPageImageLoad(i, img));
    const layer = document.createElement('div');
    layer.className = 'layer';
    bindLayer(layer, i);
    page.append(img, layer);
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
    el.style.width = `${Math.round(w * k())}px`;
    el.style.height = `${Math.round(h * k())}px`;
  });
  $('zoom-slider').value = Math.round(app.zoom * 100);
  $('zoom-label').textContent = `${Math.round(app.zoom * 100)}%`;
}

/* Çizim ölçeği: ekran pikseli başına bir görüntü pikseli (yüksek DPI ekranlarda keskin) */
function renderScale() {
  return +(k() * (window.devicePixelRatio || 1)).toFixed(3);
}

function pageUrl(i, scale) {
  return `../page/${i}.png?s=${scale}&v=${app.doc.versions[i]}`;
}

function loadPageImage(page) {
  const i = +page.dataset.index, s = renderScale();
  const img = page.firstChild, key = `${app.doc.versions[i]}:${s}`;
  if (img.dataset.key === key) return;
  img.dataset.key = key;
  img.src = pageUrl(i, s);
}

function loadThumb(thumb, i) {
  const img = thumb.firstChild;
  const s = +(THUMB_W / app.doc.pages[i][0] * (window.devicePixelRatio || 1)).toFixed(3);
  const key = `${app.doc.versions[i]}:${s}`;
  if (img.dataset.key === key) return;
  img.dataset.key = key;
  img.src = pageUrl(i, s);
}

// Sayfa görüntüleri ve kutuları yalnız ekrana yaklaşınca istenir (yüzlerce sayfalık datasheet'ler için şart)
const visiblePages = new Set();
const pageObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) {
      visiblePages.add(e.target);
      loadPageImage(e.target);
      fetchLayer(+e.target.dataset.index);
    } else {
      visiblePages.delete(e.target);
    }
  }
}, { root: $('stage'), rootMargin: '600px 0px' });

const thumbObserver = new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (e.isIntersecting) loadThumb(e.target, app.thumbEls.indexOf(e.target));
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
  renderAllLayers();          // kutular pt'den yeniden hesaplanır
  layoutEditor();
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
  $('stage').scrollTo({ top: app.pageEls[i].offsetTop - STAGE_PAD / 2, behavior });
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
  if (!app.sel) renderInspector();
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
  let hint = TOOL_HINTS[app.tool];
  if (app.mode === 'sayfalar') hint = 'Sürükleyerek sıralayın · Ctrl/Shift ile çoklu seçim · Çift tık: düzenle';
  if (app.placing) hint = 'Yapıştırılacak yere tıklayın · Metin kenarlarına yapışır · Esc: vazgeç';
  else if (isEditing()) hint = 'Enter: uygula · Esc: vazgeç';
  const parts = [hint];
  if (app.doc) parts.push(paperName(...app.doc.pages[app.current]));
  $('status-text').textContent = parts.join('  ·  ');
}

/* ── Komutlar ─────────────────────────────────────────────────────────────── */

const commands = {
  async open() { commitOpenEdit(); handleOpenResult(await serial(() => api().open_dialog())); },
  async save() {
    if (!app.doc) return;
    commitOpenEdit();                 // açık düzenleme önce uygulansın (sıra kuyruğu garanti eder)
    const r = await serial(() => api().save());
    if (!r) return;
    if (r.ok) { applyState(r.state); toast('Kaydedildi'); return; }
    // Dosya başka programda açıksa (Adobe, Outlook önizleme…) başka yere kaydetmeyi öner
    if (window.confirm(`Dosya kaydedilemedi.\n\n${r.error}\n\nFarklı bir yere kaydetmek ister misiniz?`)) commands.saveAs();
  },
  async saveAs() {
    if (!app.doc) return;
    commitOpenEdit();
    if (await mutate(() => api().save_as())) toast('Kaydedildi');
  },
  async undo() {
    commitOpenEdit();
    if (app.doc && app.doc.canUndo) applyState(await serial(() => api().undo()));
  },
  async redo() {
    commitOpenEdit();
    if (app.doc && app.doc.canRedo) applyState(await serial(() => api().redo()));
  },
  async addImage() {
    if (!app.doc) return;
    const i = app.current;
    const r = await mutate(() => api().add_image(i), 'Resim eklendi · Sürükle: kılavuzlara yapışır · Alt: serbest');
    if (r) { setTool('secim'); selectImageNear(i, r.rect); }
  },
  copy() {
    if (!app.doc) return;
    if (app.sel && app.sel.type === 'span') return copyText('span', app.sel.page, app.sel.item);
    if (app.highlight && app.highlight.rects.length) return selectTextIn(app.highlight.page, app.highlight.rect);
    toast('Önce bir metne tıklayın ya da Metin Seç (Ctrl+3) ile alan seçin.');
  },
  async paste() {
    if (app.doc) usePasteInfo(await api().clipboard_info());
  },
  selectAll() { if (app.doc) selectPageText(app.current); },
  deleteSelected() {
    if (app.sel && app.sel.type === 'image') deleteImage(app.sel.page, app.sel.item);
  },
  escape() {
    if (menuOpen()) return hideMenu();
    if (app.placing) return endPlacement();
    clearTransient();
  },
  zoomIn() { setZoom(app.zoom * 1.2); },
  zoomOut() { setZoom(app.zoom / 1.2); },
  fitWidth() { fitZoom('width'); },
  fitPage() { fitZoom('page'); },
};

/** Panodaki içerikle yapıştır: resim ekrandaki sayfaya, metin önizlemeyle tıklanan yere */
async function usePasteInfo(info) {
  if (info.kind === 'image') {
    const i = app.current;
    const r = await mutate(() => api().paste_image(i, null), 'Resim yapıştırıldı');
    if (r) { setTool('secim'); selectImageNear(i, r.rect); }
  } else if (info.kind === 'text') {
    startPlacement(info);
  } else {
    toast(info.locked ? 'Pano başka bir programda açık — biraz sonra tekrar deneyin.'
                      : 'Panoda yapıştırılacak metin veya resim yok.');
  }
}

const READY_MODES = new Set(['duzenle', 'sayfalar']);

function setMode(mode) {
  if (!READY_MODES.has(mode)) {
    toast(`${MODE_NAMES[mode]} modülü sonraki aşamada gelecek`);
    return;
  }
  if (mode === app.mode) return;
  const prev = app.mode;
  app.mode = mode;
  document.querySelectorAll('#mode-tabs [data-mode]').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.mode === mode));
  if (mode === 'sayfalar') enterPagesMode();
  else if (prev === 'sayfalar') leavePagesMode();
  renderInspector();
  updateStatus();
}

function setTool(tool) {
  if (tool === app.tool) return;
  commitOpenEdit();
  endPlacement();
  app.tool = tool;
  document.querySelectorAll('#tool-strip [data-tool]').forEach((b) =>
    b.classList.toggle('is-active', b.dataset.tool === tool));
  $('pages').dataset.tool = tool;
  clearTransient();
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
  const actions = { 'add-image': commands.addImage, copy: commands.copy, paste: commands.paste };
  document.querySelectorAll('#tool-strip [data-action]').forEach((b) =>
    b.addEventListener('click', () => actions[b.dataset.action]()));

  let scrollRaf = 0;
  $('stage').addEventListener('scroll', () => {
    hideMenu();
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
    hideMenu();
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (app.fit) fitZoom(app.fit, false); }, 120);
  });

  document.addEventListener('keydown', onKey);
  bindFormatBar();
  bindPageGrid();
}

const TOOL_KEYS = { 1: 'secim', 2: 'metin', 3: 'metin-sec', 4: 'alan-sil' };

function onKey(e) {
  // Olay document'e gelmiş olabilir (öğe değil) → matches yok
  const inField = e.target instanceof Element && e.target.matches('input, textarea, select, [contenteditable="true"]');
  const key = e.key.toLowerCase();
  let handled = true;
  // Sayfalar modunun kendi tuşları (Del, Esc, Ctrl+A, Ctrl+D); geri kalanı (Ctrl+Z…) aşağıda
  if (app.mode === 'sayfalar' && app.doc && !inField && onPagesKey(e, key)) {
    e.preventDefault();
    return;
  }
  if (e.ctrlKey && key === 'o') commands.open();
  else if (e.ctrlKey && key === 's' && e.shiftKey) commands.saveAs();
  else if (e.ctrlKey && key === 's') commands.save();
  else if (inField) handled = false;   // metin kutusundayken Ctrl+Z, Ctrl+C vb. kutunun kendisine kalsın
  else if (e.key === 'Escape') commands.escape();
  else if (e.key === 'Delete' || e.key === 'Backspace') commands.deleteSelected();
  else if (!e.ctrlKey) handled = false;
  else if (key === 'z' && e.shiftKey) commands.redo();
  else if (key === 'z') commands.undo();
  else if (key === 'y') commands.redo();
  else if (key === 'c') commands.copy();
  else if (key === 'v') commands.paste();
  else if (key === 'a') commands.selectAll();
  else if (key === 'i') commands.addImage();
  else if (key === '=' || key === '+') commands.zoomIn();
  else if (key === '-') commands.zoomOut();
  else if (key === 'w' && e.shiftKey) commands.fitPage();
  else if (key === 'w') commands.fitWidth();
  else if (TOOL_KEYS[key]) setTool(TOOL_KEYS[key]);
  else handled = false;
  if (handled) e.preventDefault();
}

/* ── Başlangıç ────────────────────────────────────────────────────────────── */

// Python tarafındaki istisnalar köprü Promise'ini reddeder; sessizce kaybolmasın
window.addEventListener('unhandledrejection', (e) => {
  const err = e.reason || {};
  showError(`İşlem tamamlanamadı.\n(${err.message || err})`);
});

bind();
setMode('duzenle');
app.tool = null;
setTool('secim');
applyState(null);

window.addEventListener('pywebviewready', async () => applyState(await api().get_state()));
