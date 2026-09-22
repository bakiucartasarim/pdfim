/* Metin düzenleme kutusu + yüzen biçim çubuğu.
 *
 * Mevcut metin (span) düzenlenirken seçilen biçim metnin tamamına Enter'da uygulanır.
 * PDF'te paragraf yapısı olmadığı için iki yana yaslama, madde işareti, satır aralığı gibi
 * Word düğmeleri bilerek yok (v1 format_bar.py ile aynı).
 */
'use strict';

const SIZES = [6, 7, 8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72];
// Datasheet'lerde sık geçen, klavyede olmayan karakterler
const SYMBOLS = [
  ['²', 'kare'], ['³', 'küp'], ['°', 'derece'], ['µ', 'mikro'], ['Ω', 'ohm'],
  ['±', 'artı-eksi'], ['×', 'çarpı'], ['÷', 'bölü'], ['≤', 'küçük eşit'], ['≥', 'büyük eşit'],
  ['≈', 'yaklaşık'], ['≠', 'eşit değil'], ['‰', 'binde'], ['½', 'yarım'], ['¼', 'çeyrek'],
  ['Ø', 'çap'], ['•', 'madde'], ['→', 'ok'], ['™', 'ticari marka'], ['®', 'tescilli'], ['©', 'telif'],
];
const NEW_TEXT_FMT = { family: 'Arial', size: 10, bold: false, italic: false, underline: false, color: 0, align: 'left' };

let edit = null;   // { page, span, at, fmt, initial, input, done }
let fontsLoaded = false;

const sameFmt = (a, b) => Object.keys(a).every((key) => a[key] === b[key]);

/* ── Açma ─────────────────────────────────────────────────────────────────── */

/** span verilirse o metni düzenler; verilmezse at=[x, yÜst] (pt) noktasına yeni metin. */
function openEditor(page, span, at) {
  if (edit) finishEdit(true);
  loadFontList();
  const flags = span ? span.flags : 0;
  const fmt = span
    ? { family: null, size: +span.size.toFixed(1), bold: !!(flags & 16), italic: !!(flags & 2),
        underline: false, color: span.color, align: 'left' }
    : { ...(app.newTextFmt || NEW_TEXT_FMT) };

  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'edit-box';
  input.spellcheck = false;
  input.value = span ? span.text : '';
  app.pageEls[page].querySelector('.layer').append(input);

  edit = { page, span, at: span ? [span.rect[0], span.rect[1]] : at, fmt, initial: { ...fmt }, input, done: false };
  setSelection(null);

  input.addEventListener('keydown', onEditKey);
  input.addEventListener('input', layoutEditor);
  input.addEventListener('blur', (e) => {
    // Odak biçim çubuğuna geçtiyse düzenleme sürüyor
    if (e.relatedTarget && e.relatedTarget.closest('#fmt-bar')) return;
    finishEdit(true);
  });

  showFormatBar();
  applyFormatToInput();
  input.focus();
  input.select();
  updateStatus();
}

function isEditing() { return !!edit; }

/** Açık düzenleme varsa uygula (kaydet / geri al öncesi) */
function commitOpenEdit() { if (edit) finishEdit(true); }

/* ── Yerleşim ve önizleme ─────────────────────────────────────────────────── */

function previewFamily() {
  const f = edit.fmt;
  return f.family || (edit.span && edit.span.family) || 'Arial';
}

function applyFormatToInput() {
  const f = edit.fmt, s = edit.input.style;
  s.fontFamily = `"${previewFamily()}", Arial, sans-serif`;
  s.fontWeight = f.bold ? '700' : '400';
  s.fontStyle = f.italic ? 'italic' : 'normal';
  s.textDecoration = f.underline ? 'underline' : 'none';
  s.color = hex(f.color);
  s.textAlign = f.align;
  syncFormatBar();
  layoutEditor();
}

const measureCtx = document.createElement('canvas').getContext('2d');

/** Kutu metnin konumunda; kalın/büyük font ya da uzayan metin sığsın diye genişler */
function layoutEditor() {
  if (!edit) return;
  const kk = k(), f = edit.fmt, s = edit.input.style;
  const px = f.size * kk;
  const [x, y] = edit.at;
  const r = edit.span ? edit.span.rect : [x, y, x, y + f.size * 1.25];
  s.fontSize = `${px}px`;
  measureCtx.font = `${f.italic ? 'italic ' : ''}${f.bold ? 700 : 400} ${px}px ${s.fontFamily}`;
  const need = measureCtx.measureText(edit.input.value + '  ').width + 12;
  const w = Math.max((r[2] - r[0]) * kk + 8, 80, need);
  const h = Math.max((r[3] - r[1]) * kk, px * 1.25) + 6;
  s.left = `${r[0] * kk - 4}px`;
  s.top = `${r[1] * kk - 3}px`;
  s.width = `${w}px`;
  s.height = `${h}px`;
  placeFormatBar();
}

/* ── Uygula / vazgeç ──────────────────────────────────────────────────────── */

function finishEdit(commit) {
  if (!edit || edit.done) return;
  const e = edit;
  e.done = true;                   // input.remove() de blur tetikler — ikinci kez işlenmesin
  edit = null;
  e.input.remove();
  hideFormatBar();
  updateStatus();
  if (!commit) return;

  const text = e.input.value;
  let call, msg;
  if (e.span) {
    const styled = !sameFmt(e.fmt, e.initial);
    if (text === e.span.text && !styled) return;
    if (!text.trim()) return mutate(() => api().replace_text(e.page, e.span, text, null));   // hata mesajı için
    call = () => api().replace_text(e.page, e.span, text, styled ? e.fmt : null);
    msg = 'Metin güncellendi';
  } else {
    if (!text.trim()) return;
    app.newTextFmt = { ...e.fmt };          // sonraki yeni metin aynı biçimle başlasın
    // Kutunun üst kenarı tıklanan nokta; PDF'e taban çizgisi verilir
    const base = e.at[1] + e.fmt.size * 0.8;
    const st = { ...e.fmt, font: e.fmt.family || 'Arial' };
    call = () => api().insert_text(e.page, e.at[0], base, text, st);
    msg = 'Metin eklendi';
  }
  showPending(e, text);
  mutate(call, msg).then((r) => { if (!r) clearPending(e.page); });
}

/* ── Anında gösterim ──────────────────────────────────────────────────────────
 * Enter'dan sonra yeni sayfa görüntüsü ~150 ms sonra gelir; o arada eski metin görünüp
 * yenisine "sıçrıyordu". Yeni görüntü yüklenene kadar eski metnin üstü beyazla örtülür ve
 * yeni metin aynı biçimle gösterilir (app.js: sayfa görüntüsü yüklenince clearPending). */

function showPending(e, text) {
  const layer = app.pageEls[e.page] && app.pageEls[e.page].querySelector('.layer');
  if (!layer) return;
  const kk = k(), f = e.fmt, els = [];
  const r = e.span ? e.span.rect : [e.at[0], e.at[1], e.at[0], e.at[1] + f.size * 1.25];
  if (e.span) {
    // Yalnız eski metnin kutusu örtülür (düzenleme kutusu en az 80 px; yandaki hücreler kaybolmasın)
    const cover = boxEl('pending-cover', [r[0] - 1, r[1] - 1, r[2] + 1, r[3] + 1]);
    els.push(cover);
  }
  const t = document.createElement('div');
  t.className = 'pending-text';
  t.textContent = text;
  Object.assign(t.style, {
    left: `${r[0] * kk}px`, top: `${r[1] * kk}px`,
    width: `${(r[2] - r[0]) * kk}px`, height: `${(r[3] - r[1]) * kk}px`,
    lineHeight: `${(r[3] - r[1]) * kk}px`,
    fontFamily: `"${f.family || (e.span && e.span.family) || 'Arial'}", Arial, sans-serif`,
    fontSize: `${f.size * kk}px`, fontWeight: f.bold ? 700 : 400, fontStyle: f.italic ? 'italic' : 'normal',
    textDecoration: f.underline ? 'underline' : 'none', color: hex(f.color),
    textAlign: e.span ? f.align : 'left',
  });
  els.push(t);
  els.forEach((el) => layer.append(el));
  clearPending(e.page);
  const entry = { version: app.doc.versions[e.page], els };
  app.pending.set(e.page, entry);
  // Görüntü hiç gelmezse (sayfa ekrandan çıktı, istek düştü) kalıcı hayalet kalmasın
  setTimeout(() => { if (app.pending.get(e.page) === entry) clearPending(e.page); }, 5000);
}

function clearPending(page) {
  const p = app.pending.get(page);
  if (!p) return;
  p.els.forEach((el) => el.remove());
  app.pending.delete(page);
}

/** Sayfa görüntüsü yüklendi: düzenlemeden *sonraki* sürümse geçici katman kalkar */
function onPageImageLoad(page, img) {
  const p = app.pending.get(page);
  if (p && img.dataset.key && !img.dataset.key.startsWith(`${p.version}:`)) clearPending(page);
}

function onEditKey(e) {
  if (e.key === 'Enter') { e.preventDefault(); finishEdit(true); }
  else if (e.key === 'Escape') { e.preventDefault(); finishEdit(false); }
  else if (e.ctrlKey && !e.shiftKey && ['b', 'i', 'u'].includes(e.key.toLowerCase())) {
    e.preventDefault();
    toggleFmt({ b: 'bold', i: 'italic', u: 'underline' }[e.key.toLowerCase()]);
  }
}

/* ── Biçim çubuğu ─────────────────────────────────────────────────────────── */

function toggleFmt(key) {
  edit.fmt[key] = !edit.fmt[key];
  applyFormatToInput();
}

function refocus() { if (edit) edit.input.focus(); }

function showFormatBar() {
  const bar = $('fmt-bar');
  edit.input.parentElement.append(bar);    // sayfayla birlikte kaysın
  bar.classList.add('is-open');
  const orig = edit.span ? (edit.span.family || edit.span.font.split('+').pop()) : null;
  $('fmt-font').placeholder = orig ? `Orijinal — ${orig}` : 'Arial';
}

function hideFormatBar() {
  const bar = $('fmt-bar');
  bar.classList.remove('is-open');
  document.body.append(bar);                // sayfa katmanı silinse de kaybolmasın
}

function placeFormatBar() {
  const bar = $('fmt-bar'), s = edit.input.style;
  const top = parseFloat(s.top), left = parseFloat(s.left);
  const bh = bar.offsetHeight || 40;
  // Kutunun 8px üstünde; sayfanın tepesine çok yakınsa altında
  bar.style.top = `${top - bh - 8 >= 0 ? top - bh - 8 : top + parseFloat(s.height) + 8}px`;
  bar.style.left = `${Math.max(0, left)}px`;
}

function syncFormatBar() {
  const f = edit.fmt;
  $('fmt-font').value = f.family || '';
  $('fmt-size').value = String(f.size).replace('.', ',');
  $('fmt-bold').classList.toggle('is-active', f.bold);
  $('fmt-italic').classList.toggle('is-active', f.italic);
  $('fmt-underline').classList.toggle('is-active', f.underline);
  $('fmt-color').value = hex(f.color);
  for (const a of ['left', 'center', 'right']) $(`fmt-align-${a}`).classList.toggle('is-active', f.align === a);
  $('fmt-reset').disabled = sameFmt(f, edit.initial);
}

async function loadFontList() {
  if (fontsLoaded) return;
  fontsLoaded = true;
  const list = $('font-list');
  for (const fam of await api().system_fonts()) {
    const o = document.createElement('option');
    o.value = fam;
    list.append(o);
  }
}

function setFontFromInput() {
  if (!edit) return;
  const v = $('fmt-font').value.trim();
  const opts = [...$('font-list').options].map((o) => o.value);
  // Büyük/küçük harf farkıyla yazılmış olsa da listedeki adı kullan
  const hit = opts.find((o) => o.toLowerCase() === v.toLowerCase());
  edit.fmt.family = v ? (hit || edit.fmt.family) : (edit.span ? null : 'Arial');
  applyFormatToInput();
}

function setSizeFromInput() {
  if (!edit) return;
  const v = parseFloat($('fmt-size').value.replace(',', '.'));
  if (v > 0) edit.fmt.size = Math.min(400, Math.max(1, v));
  applyFormatToInput();
}

function stepSize(dir) {
  const cur = edit.fmt.size;
  const next = dir > 0 ? SIZES.find((s) => s > cur + 0.01) : [...SIZES].reverse().find((s) => s < cur - 0.01);
  edit.fmt.size = next || cur;
  applyFormatToInput();
}

function bindFormatBar() {
  const bar = $('fmt-bar');
  // Düğmeye basmak düzenleme kutusundan odağı çalmasın
  bar.querySelectorAll('button').forEach((b) => b.addEventListener('mousedown', (e) => e.preventDefault()));
  $('fmt-bold').addEventListener('click', () => toggleFmt('bold'));
  $('fmt-italic').addEventListener('click', () => toggleFmt('italic'));
  $('fmt-underline').addEventListener('click', () => toggleFmt('underline'));
  for (const a of ['left', 'center', 'right']) {
    $(`fmt-align-${a}`).addEventListener('click', () => { edit.fmt.align = a; applyFormatToInput(); });
  }
  $('fmt-size-down').addEventListener('click', () => stepSize(-1));
  $('fmt-size-up').addEventListener('click', () => stepSize(1));
  $('fmt-reset').addEventListener('click', () => { edit.fmt = { ...edit.initial }; applyFormatToInput(); });
  $('fmt-symbols').addEventListener('click', (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    showMenu(r.left, r.bottom + 4, SYMBOLS.map(([ch, name]) => ({
      icon: '', label: `${ch}   ${name}`, run: () => {
        const inp = edit.input;
        inp.setRangeText(ch, inp.selectionStart, inp.selectionEnd, 'end');
        layoutEditor();
      },
    })));
  });

  $('fmt-font').addEventListener('change', () => { setFontFromInput(); refocus(); });
  $('fmt-size').addEventListener('change', () => { setSizeFromInput(); refocus(); });
  $('fmt-color').addEventListener('input', (e) => {
    edit.fmt.color = parseInt(e.target.value.slice(1), 16);
    applyFormatToInput();
  });
  $('fmt-color').addEventListener('change', refocus);
  for (const id of ['fmt-font', 'fmt-size']) {
    $(id).addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); e.target.dispatchEvent(new Event('change')); }
      if (e.key === 'Escape') { e.preventDefault(); refocus(); }
    });
  }
  // Odak çubuktan dışarı (kutuya değil) giderse düzenleme uygulanır
  bar.addEventListener('focusout', (e) => {
    if (!edit) return;
    const to = e.relatedTarget;
    if (to && (to === edit.input || to.closest('#fmt-bar'))) return;
    finishEdit(true);
  });
}
