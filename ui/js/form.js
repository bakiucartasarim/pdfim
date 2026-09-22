/* Form & İmza modu — PDF form alanlarının üstünde doldurulabilir kutular, imza ve tarih.
 *
 * Alan kutuları sayfa katmanında durur; yalnız sayfa sürümü, yakınlaştırma ya da mod değişince
 * yeniden kurulur (her fare hareketinde değil — odak ve yazılan metin kaybolmasın). Bir değer
 * Python'a yazılınca sayfa yenilenir; o arada Tab ile geçilen alandaki odak ve henüz
 * gönderilmemiş yazı yeni kutulara taşınır.
 */
'use strict';

app.focusField = null;       // { page, xref } — yeniden kurulumdan sonra odak buraya döner

function formHint() {
  const n = formFieldCount();
  return n ? 'Alanlara tıklayıp doldurun · Tab: sonraki alan · İmza ve tarih ekleyebilirsiniz'
    : 'Bu sayfalarda form alanı yok · İmza ve tarih ekleyebilirsiniz';
}

function formFieldCount() {
  let n = 0;
  app.layers.forEach((e) => { if (e.data && e.data.fields) n += e.data.fields.length; });
  return n;
}

/* ── Alan kutuları ────────────────────────────────────────────────────────── */

function renderFields(i, layer) {
  let box = layer.querySelector(':scope > .fields');
  const d = layerData(i);
  const key = app.mode === 'form' && d ? `${d.version}:${k()}` : '';
  if (!key) { if (box) box.remove(); return; }
  if (box && box.dataset.key === key) return;

  // Henüz gönderilmemiş yazılar (Tab ile geçilip yazılmaya başlanmış alan) korunur
  const dirty = {};
  if (box) box.querySelectorAll('[data-xref]').forEach((el) => {
    if ('orig' in el.dataset && el.value !== el.dataset.orig) dirty[el.dataset.xref] = el.value;
  });
  if (box) box.remove();
  box = document.createElement('div');
  box.className = 'fields';
  box.dataset.key = key;
  layer.append(box);

  const kk = k();
  for (const f of d.fields) {
    const el = fieldControl(i, f);
    if (!el) continue;
    const [x0, y0, x1, y1] = f.rect;
    Object.assign(el.style, { left: `${x0 * kk}px`, top: `${y0 * kk}px`,
                              width: `${(x1 - x0) * kk}px`, height: `${(y1 - y0) * kk}px` });
    el.dataset.xref = f.xref;
    el.title = f.label || f.name;
    if (f.readonly) { el.disabled = true; el.classList.add('is-readonly'); }
    if (dirty[f.xref] !== undefined) el.value = dirty[f.xref];
    box.append(el);
    if (app.focusField && app.focusField.page === i && app.focusField.xref === f.xref) {
      el.focus({ preventScroll: true });
      if (el.setSelectionRange && el.value) el.setSelectionRange(el.value.length, el.value.length);
    }
  }
  renderInspector();          // alan sayısı / dolu sayısı
  updateStatus();
}

function fieldControl(page, f) {
  const commit = (value) => {
    mutate(() => api().set_field(page, f.xref, value)).then((r) => { if (r) toastField(f); });
  };
  const track = (el) => el.addEventListener('focus', () => { app.focusField = { page, xref: f.xref }; });

  if (f.type === 'text') {
    const el = document.createElement(f.multiline ? 'textarea' : 'input');
    el.className = 'fld fld-text';
    el.value = f.value || '';
    el.dataset.orig = el.value;
    if (f.maxlen) el.maxLength = f.maxlen;
    const h = (f.rect[3] - f.rect[1]) * k();
    const size = f.fontsize ? f.fontsize * k() : Math.min(h * 0.62, 14 * k());
    el.style.fontSize = `${Math.max(8, f.multiline ? Math.min(size, 12 * k()) : size)}px`;
    el.spellcheck = false;
    el.addEventListener('change', () => { if (el.value !== el.dataset.orig) commit(el.value); });
    el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !f.multiline) { e.preventDefault(); el.blur(); }
      if (e.key === 'Escape') { el.value = el.dataset.orig; el.blur(); }
    });
    track(el);
    return el;
  }
  if (f.type === 'checkbox' || f.type === 'radio') {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = `fld fld-${f.type}${f.checked ? ' is-checked' : ''}`;
    el.setAttribute('aria-pressed', f.checked);
    // Radyo düğmesi seçiliyken tekrar tıklamak kaldırmaz (PDF'teki davranış)
    el.addEventListener('click', () => {
      if (f.type === 'radio' && f.checked) return;
      commit(!f.checked);
    });
    track(el);
    return el;
  }
  if (f.type === 'combo' || f.type === 'list') {
    const el = document.createElement('select');
    el.className = 'fld fld-select';
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '—';
    el.append(blank);
    for (const o of f.options || []) {
      const opt = document.createElement('option');
      opt.value = o;
      opt.textContent = o;
      el.append(opt);
    }
    el.value = f.value || '';
    el.dataset.orig = el.value;
    el.addEventListener('change', () => commit(el.value));
    track(el);
    return el;
  }
  if (f.type === 'signature') {
    const el = document.createElement('button');
    el.type = 'button';
    el.className = 'fld fld-sign';
    el.innerHTML = '<span class="ms">signature</span><span>İmzala</span>';
    el.addEventListener('click', () => openSignature({ page, rect: f.rect }));
    return el;
  }
  return null;
}

function toastField(f) {
  toast(f.type === 'checkbox' || f.type === 'radio' ? 'İşaretlendi' : `${f.label || f.name || 'Alan'} dolduruldu`);
}

/* ── İşlemler ─────────────────────────────────────────────────────────────── */

function trDate() {
  const d = new Date();
  return `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}.${d.getFullYear()}`;
}

const formActions = {
  signature: () => openSignature(null),
  date() {
    const text = trDate();
    startPlacement({ text, size: 11, family: 'Arial', color: 0, bold: false },
      (i, x, y) => api().insert_text(i, x, y, text,
        { family: 'Arial', font: 'Arial', size: 11, bold: false, italic: false, color: 0 }),
      'Tarih eklendi');
  },
  async flatten() {
    if (!window.confirm('Form alanları sayfanın kalıcı parçası olacak ve artık değiştirilemeyecek.\n'
      + 'Doldurduğunuz değerler görünür kalır. Devam edilsin mi? (Geri al ile geri alınabilir)')) return;
    mutate(() => api().flatten_forms(), 'Form düzleştirildi');
  },
};

function bindForm() {
  document.querySelectorAll('#form-strip [data-fact]').forEach((b) =>
    b.addEventListener('click', () => formActions[b.dataset.fact]()));
}

/* ── Sağ panel ────────────────────────────────────────────────────────────── */

function renderFormInspector(body) {
  const fields = [];
  app.layers.forEach((e, page) => { if (e.data && e.data.fields) e.data.fields.forEach((f) => fields.push({ ...f, page })); });
  fields.sort((a, b) => a.page - b.page || a.rect[1] - b.rect[1]);
  const filled = fields.filter((f) => (f.type === 'checkbox' || f.type === 'radio' ? f.checked : f.value)).length;

  const list = document.createElement('div');
  list.className = 'field-list';
  for (const f of fields.slice(0, 60)) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'field-item';
    const v = f.type === 'checkbox' || f.type === 'radio' ? (f.checked ? '✓' : '') : (f.value || '');
    b.innerHTML = '<span class="field-name"></span><span class="field-val"></span>';
    b.querySelector('.field-name').textContent = f.label || f.name || f.type;
    b.querySelector('.field-val').textContent = v;
    b.addEventListener('click', () => focusField(f.page, f.xref));
    list.append(b);
  }

  body.append(
    section('Form alanları', fields.length
      ? [row('Görünen sayfalardaki alan', `${fields.length} · ${filled} dolu`), list]
      : [note('Görünen sayfalarda form alanı yok. İmza ya da tarih ekleyebilirsiniz.')]),
    actions([
      btn('signature', 'İmza ekle', formActions.signature, true),
      btn('calendar_today', 'Tarih', formActions.date),
    ]),
    note('Görsel imzadır; 5070 sayılı Elektronik İmza Kanunu kapsamında güvenli elektronik imza yerine geçmez.'),
  );
}

function focusField(page, xref) {
  scrollToPage(page, 'auto');
  requestAnimationFrame(() => {
    const el = app.pageEls[page] && app.pageEls[page].querySelector(`.fields [data-xref="${xref}"]`);
    if (el) { el.scrollIntoView({ block: 'center' }); el.focus({ preventScroll: true }); }
  });
}
