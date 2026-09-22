/* Masaüstü ↔ web farkları tek yerde. Arayüzün geri kalanı hangisinde çalıştığını bilmez.
 *
 * Masaüstü (app.py): pywebview köprüsü; Windows dosya pencereleri ve panosu Python'da.
 * Web (server.py): fetch('/api/…'); dosyalar yüklenir/indirilir, pano tarayıcıda.
 * Tüm fonksiyonlar köprü metotlarıyla aynı biçimde sonuç döner ({ ok, error, state, … })
 * ya da kullanıcı vazgeçtiyse null.
 */
'use strict';

const platform = IS_WEB ? webPlatform() : desktopPlatform();

function desktopPlatform() {
  return {
    openFile: () => api().open_dialog(),
    reopen: (result, password) => api().open_path(result.path, password),
    save: () => api().save(),
    saveAs: () => api().save_as(),
    addImage: (page) => api().add_image(page),
    afterCopy: () => {},                       // Python zaten Windows panosuna yazdı
    /** Panoda ne var (sağ tık menüsündeki "yapıştır" etiketi için; ucuz) */
    peekClipboard: () => api().clipboard_info(),
    readClipboard: () => api().clipboard_info(),
    pasteText: (page, x, y) => api().paste_text(page, x, y),
    pasteImage: (page, at) => api().paste_image(page, at),
  };
}

function webPlatform() {
  /** Gizli <input type=file> ile dosya seçtir; vazgeçilirse null */
  function pick(accept) {
    return new Promise((resolve) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = accept;
      input.addEventListener('change', () => resolve(input.files[0] || null));
      input.addEventListener('cancel', () => resolve(null));
      input.click();
    });
  }

  const toB64 = (blob) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);          // "data:image/png;base64,…" — Python öneki atar
    r.onerror = reject;
    r.readAsDataURL(blob);
  });

  async function readError(res) {
    try { const j = await res.json(); return j.detail || j.error || res.statusText; } catch (_) { return res.statusText; }
  }

  async function upload(file) {
    if (!file) return null;
    if (!/\.pdf$/i.test(file.name) && file.type !== 'application/pdf') {
      return { ok: false, error: 'Yalnız PDF dosyaları açılabilir.' };
    }
    toast('Yükleniyor…');
    const res = await fetch(`../upload?name=${encodeURIComponent(file.name)}`, { method: 'POST', body: file });
    if (!res.ok) return { ok: false, error: await readError(res) };
    return res.json();
  }

  async function download() {
    const a = document.createElement('a');
    a.href = '../download';
    a.download = (app.doc && app.doc.name) || 'belge.pdf';
    document.body.append(a);
    a.click();
    a.remove();
    // İndirme istek sırasında "kaydedilmedi" işaretini sıfırlar; durumu yenile
    await new Promise((r) => setTimeout(r, 400));
    return { ok: true, state: await api().get_state() };
  }

  /** Tarayıcı panosunu oku (sağ tık menüsü / Yapıştır düğmesi). Tarayıcı izin isteyebilir. */
  async function readClipboard() {
    try {
      if (navigator.clipboard.read) {
        for (const item of await navigator.clipboard.read()) {
          const type = item.types.find((t) => t.startsWith('image/'));
          if (type) return { kind: 'image', data: await toB64(await item.getType(type)) };
        }
      }
      const text = await navigator.clipboard.readText();
      return withStyle(await api().clipboard_info(text, false), text);
    } catch (_) {
      return { kind: null, denied: true };
    }
  }

  const withStyle = (info, text) => (info.kind === 'text' ? { ...info, text } : info);

  return {
    openFile: async () => upload(await pick('application/pdf,.pdf')),
    upload,
    async reopen(_result, password) {            // parolalı PDF: dosya yeniden gönderilmez
      const res = await fetch('../reopen', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                             body: JSON.stringify({ password }) });
      return res.ok ? res.json() : { ok: false, error: await readError(res) };
    },
    save: download,
    saveAs: download,
    async addImage(page) {
      const file = await pick('image/png,image/jpeg,image/gif,image/bmp,image/tiff');
      if (!file) return null;
      return api().add_image_data(page, await toB64(file));
    },
    async afterCopy(text) {
      try { await navigator.clipboard.writeText(text); } catch (_) {
        toast('Tarayıcı panoya yazma izni vermedi.');
      }
    },
    // Sağ tık her açıldığında izin sorulmasın: içerik ancak "yapıştır" seçilince okunur
    peekClipboard: async () => ({ kind: 'unknown' }),
    readClipboard,
    /** Ctrl+V: 'paste' olayı izin istemeden panoyu verir */
    async fromPasteEvent(e) {
      const file = [...e.clipboardData.files].find((f) => f.type.startsWith('image/'));
      if (file) return { kind: 'image', data: await toB64(file) };
      const text = e.clipboardData.getData('text/plain');
      return withStyle(await api().clipboard_info(text, false), text);
    },
    pasteText: (page, x, y, info) => api().paste_text(page, x, y, info.text),
    pasteImage: (page, at, info) => api().paste_image(page, at, info.data),
  };
}

/* ── Web: yükleme, sürükle-bırak, sayfadan ayrılma uyarısı, kaynak kod bağlantısı ── */

async function initWeb() {
  document.body.classList.add('is-web');
  $('btn-save').title = 'Bilgisayarına indir (Ctrl+S)';
  $('btn-save').querySelector('.label').textContent = 'İndir';
  $('btn-open').title = 'PDF yükle (Ctrl+O)';
  $('btn-open-empty').lastChild.textContent = 'PDF Yükle';

  const cfg = await (await fetch('../api/config')).json();
  $('web-note').replaceChildren(
    document.createTextNode(`Belgeniz yalnız bu oturumda tutulur, ${cfg.idleMinutes} dakika işlem yapılmazsa silinir. En fazla ${cfg.maxUploadMb} MB, ${cfg.maxPages} sayfa.`),
  );
  $('link-source').href = cfg.sourceUrl;
  $('link-source-top').href = cfg.sourceUrl;
  $('link-desktop').href = cfg.desktopUrl;
  $('link-selfhost').href = cfg.selfhostUrl;
  if (cfg.notice) {                          // herkese açık deneme kurulumu
    $('web-notice').textContent = cfg.notice;
    $('test-badge').hidden = false;
    $('test-badge').title = cfg.notice;
  } else {
    $('web-notice').remove();
  }

  // Sürükle-bırak (masaüstünde bunu pywebview yapıyor)
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', async (e) => {
    e.preventDefault();
    const file = [...(e.dataTransfer ? e.dataTransfer.files : [])].find((f) => /\.pdf$/i.test(f.name));
    if (!file) return;
    if (app.doc && app.doc.modified && !window.confirm('Açık belgedeki değişiklikler indirilmedi. Yine de yeni dosya açılsın mı?')) return;
    handleOpenResult(await serial(() => platform.upload(file)));
  });

  window.addEventListener('beforeunload', (e) => {
    if (app.doc && app.doc.modified) { e.preventDefault(); e.returnValue = ''; }
  });

  // Ctrl+V: tarayıcı izin sormadan panoyu 'paste' olayında verir
  document.addEventListener('paste', async (e) => {
    if (!app.doc || e.target.matches('input, textarea, [contenteditable="true"]')) return;
    e.preventDefault();
    usePasteInfo(await platform.fromPasteEvent(e));
  });
}
