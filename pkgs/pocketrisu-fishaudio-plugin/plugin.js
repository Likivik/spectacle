//@name fishaudio-controls
//@display-name Fish Audio Controls
//@api 3.0
//@version 0.1.0
// (No plugin args — TTS path is configured in PocketRisu's built-in provider;
//  this plugin only captures audio and exposes a controls panel.)
// (No update URL yet — repo not published.)

/* =====================================================================
   Fish Audio Controls — PocketRisu Plugin API 3.0
   --------------------------------------------------------------------
   Adds pause / resume / seek / volume / speed / re-play controls to
   PocketRisu's built-in TTS pipeline (any provider).

   How it works
   ------------
   PocketRisu pipes every TTS call through an `addTTSPostprocessor`
   hook. We hook that hook and capture the raw audio bytes per
   (message id, segment index) in an in-memory Map. A floating control
   panel within the plugin's own iframe exposes the queue + standard
   HTML5 audio controls.

   No proxy changes required. No source modifications. Fully reversible
   by uninstalling the plugin.

   Usage
   -----
   1. Install plugin (paste entire file into PocketRisu's Plugins
      → Import Plugin → From Text).
   2. Tap the 🎣 button in PocketRisu's chat menu (mobile) or the
      🎣 floating button top-right (desktop) — opens control panel.
   3. Configure your character's TTS to point at the Fish Audio proxy
      in PocketRisu's built-in character settings (OpenAI-compatible
      provider with Base URL = proxy URL, e.g.
      http://10.88.0.1:8099/v1).
   4. Hit 🔊 on any message. The captured audio shows up in the
      panel queue with a status badge "Captured TTS (N)".
   5. Use Play / Pause / Stop / Seek / Volume / Speed buttons.

   Tested against PocketRisu container
   ghcr.io/pocketrisu/pocketrisu:latest.
===================================================================== */

(async () => {
  if (typeof risuai === 'undefined') {
    console.error('[fishaudio-controls] risuai API not available');
    return;
  }

  const PLUGIN_NAME = 'fishaudio-controls';
  const log  = (...a) => console.log(`[${PLUGIN_NAME}]`, ...a);
  const err  = (...a) => console.error(`[${PLUGIN_NAME}]`, ...a);

  // ── Audio registry (lives in plugin iframe memory) ─────
  // Keyed by `${msgId}:${segIdx}`. Holds base64 audio + mime.
  const audioMap = new Map();
  let segCounter = 0;

  function storeAudio(msgId, segIdx, arrayBuffer, mimeType) {
    const bytes = new Uint8Array(arrayBuffer);
    let bin = '';
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    const b64 = btoa(bin);
    audioMap.set(`${msgId}:${segIdx}`, { b64, mimeType, msgId, segIdx });
    // Cap to last 24 (LRU eviction) — browser memory bound
    if (audioMap.size > 24) {
      const first = audioMap.keys().next().value;
      audioMap.delete(first);
    }
  }

  // Expose for the control panel to consume
  window._faControls = {
    getAudio:    (msgId, segIdx) => audioMap.get(`${msgId}:${segIdx}`),
    listAudio:   () => Array.from(audioMap.values()),
    removeAudio: (msgId, segIdx) => audioMap.delete(`${msgId}:${segIdx}`),
    clear:       () => audioMap.clear(),
  };

  // ── Native HTML5 Audio() instance ───────────────
  // Lives inside the iframe so we get full read/write access to
  // currentTime / paused / duration — none of which are exposed
  // across the sandbox boundary via getRootDocument().
  let audio = null;
  let currentItem = null;

  function ensureAudio() {
    if (audio) return audio;
    audio = new Audio();
    audio.preload = 'metadata';
    audio.volume = 0.8;
    audio.addEventListener('ended', () => {
      if (!currentItem) return;
      const items = window._faControls.listAudio();
      const idx = items.findIndex(
        (x) => `${x.msgId}:${x.segIdx}` === `${currentItem.msgId}:${currentItem.segIdx}`
      );
      const next = items[idx + 1];
      if (next) playItem(next);
    });
    audio.addEventListener('timeupdate', refreshTimeUI);
    audio.addEventListener('loadedmetadata', refreshTimeUI);
    audio.addEventListener('pause', () => { if (ui.bar) updatePlayBtn(false); });
    audio.addEventListener('play',  () => { if (ui.bar) updatePlayBtn(true);  });
    return audio;
  }

  function binToBlobUrl(b64, mimeType) {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([arr], { type: mimeType }));
  }

  async function playItem(item) {
    if (!item) return;
    const a = ensureAudio();
    if (a.src && a.src.startsWith('blob:')) URL.revokeObjectURL(a.src);
    a.src = binToBlobUrl(item.b64, item.mimeType);
    currentItem = { msgId: item.msgId, segIdx: item.segIdx };
    try { await a.play(); } catch (e) { err('play() failed', e?.message); }
    refreshPlaylistUI();
    updatePlayBtn(true);
  }

  // ── Control Panel UI ───────────────────────────────────
  // Built lazily on first user request. We keep a `ui` reference for
  // event handlers + state sync.
  let ui = null;

  function ensureUI() {
    if (ui) return ui;
    const doc = document;
    doc.head.appendChild(Object.assign(doc.createElement('style'), {
      textContent: `
        #fa-panel { color:#e0e0ea; font:13px/1.4 system-ui,-apple-system,sans-serif;
          padding:20px; max-width:600px; }
        #fa-panel .row { display:flex; align-items:center; gap:8px; margin-bottom:10px; }
        #fa-panel button { background:#2a2a3a; color:#fff; border:0; padding:6px 10px;
          border-radius:8px; cursor:pointer; font-size:12px; min-width:32px; }
        #fa-panel button:hover { background:#3a3a52; }
        #fa-panel button.primary { background:#5b6cff; }
        #fa-panel button.primary:hover { background:#6f80ff; }
        #fa-panel select, #fa-panel input[type=range] { flex:1; min-width:0; }
        #fa-panel .label { color:#9aa0b4; font-size:11px; }
        #fa-panel .time { font-variant-numeric:tabular-nums; min-width:80px;
          text-align:right; color:#cfd3e0; }
        #fa-panel .playlist { max-height:240px; overflow:auto;
          background:rgba(0,0,0,0.3); border-radius:6px; padding:4px 6px;
          font-size:11px; }
        #fa-panel .pl-item { display:flex; justify-content:space-between;
          align-items:center; padding:4px 6px; border-radius:4px; cursor:pointer; gap:6px; }
        #fa-panel .pl-item:hover { background:rgba(255,255,255,0.06); }
        #fa-panel .pl-item.active { background:rgba(91,108,255,0.25); }
        #fa-panel .pl-item .preview { flex:1; overflow:hidden;
          text-overflow:ellipsis; white-space:nowrap; }
        #fa-panel .badge { font-size:10px; background:#5b6cff;
          padding:1px 6px; border-radius:8px; }
      `,
    }));

    const root = doc.createElement('div');
    root.id = 'fa-panel';
    root.innerHTML = `
      <h2 style="margin-top:0;">🎣 Fish Audio Controls</h2>
      <p style="color:#9aa0b4;font-size:12px;margin:0 0 16px 0;">
        Captured TTS audio from PocketRisu's built-in provider.
        Tap any item to play. Use controls to pause / seek / replay.
      </p>
      <div class="row">
        <button class="primary" id="fa-play" disabled>▶</button>
        <button id="fa-stop" disabled>■</button>
        <button id="fa-prev" disabled>⏮</button>
        <button id="fa-next" disabled>⏭</button>
        <input type="range" id="fa-seek" min="0" max="100" value="0" step="0.1" disabled>
        <span class="time" id="fa-time">0:00 / 0:00</span>
      </div>
      <div class="row">
        <span class="label">vol</span>
        <input type="range" id="fa-vol" min="0" max="100" value="80">
        <span class="label">speed</span>
        <select id="fa-speed">
          <option value="0.5">0.5×</option>
          <option value="0.75">0.75×</option>
          <option value="1" selected>1.0×</option>
          <option value="1.25">1.25×</option>
          <option value="1.5">1.5×</option>
          <option value="2">2.0×</option>
        </select>
      </div>
      <h3 style="margin-top:18px;">
        Captured TTS (<span id="fa-pl-count">0</span>)
        <button id="fa-clear" style="margin-left:8px;font-size:11px;">Clear</button>
      </h3>
      <div class="playlist" id="fa-playlist"></div>
      <p style="color:#9aa0b4;font-size:11px;margin-top:14px;">
        Close this panel and trigger TTS again to capture more messages.
      </p>
    `;
    doc.body.appendChild(root);

    ui = {
      root,
      playBtn:  root.querySelector('#fa-play'),
      stopBtn:  root.querySelector('#fa-stop'),
      prevBtn:  root.querySelector('#fa-prev'),
      nextBtn:  root.querySelector('#fa-next'),
      seek:     root.querySelector('#fa-seek'),
      time:     root.querySelector('#fa-time'),
      vol:      root.querySelector('#fa-vol'),
      speed:    root.querySelector('#fa-speed'),
      playlist: root.querySelector('#fa-playlist'),
      plCount:  root.querySelector('#fa-pl-count'),
      clearBtn: root.querySelector('#fa-clear'),
    };

    ui.playBtn.addEventListener('click', async () => {
      const a = ensureAudio();
      if (!a.src) {
        const items = window._faControls.listAudio();
        if (items.length > 0) await playItem(items[items.length - 1]);
        return;
      }
      if (a.paused) { try { await a.play(); } catch {} updatePlayBtn(true); }
      else          { a.pause();                       updatePlayBtn(false); }
    });
    ui.stopBtn.addEventListener('click', () => {
      const a = ensureAudio();
      if (!a.src) return;
      a.pause(); a.currentTime = 0; updatePlayBtn(false);
    });
    ui.prevBtn.addEventListener('click', () => {
      const items = window._faControls.listAudio();
      const idx = currentItem ? items.findIndex(
        (x) => `${x.msgId}:${x.segIdx}` === `${currentItem.msgId}:${currentItem.segIdx}`) : -1;
      const prev = items[idx - 1];
      if (prev) playItem(prev);
    });
    ui.nextBtn.addEventListener('click', () => {
      const items = window._faControls.listAudio();
      const idx = currentItem ? items.findIndex(
        (x) => `${x.msgId}:${x.segIdx}` === `${currentItem.msgId}:${currentItem.segIdx}`) : -1;
      const next = items[idx + 1];
      if (next) playItem(next);
    });
    ui.seek.addEventListener('input', () => {
      const a = ensureAudio();
      try { a.currentTime = parseFloat(ui.seek.value); } catch {}
    });
    ui.vol.addEventListener('input', () => {
      const a = ensureAudio();
      try { a.volume = parseInt(ui.vol.value, 10) / 100; } catch {}
    });
    ui.speed.addEventListener('change', () => {
      const a = ensureAudio();
      try { a.playbackRate = parseFloat(ui.speed.value); } catch {}
    });
    ui.clearBtn.addEventListener('click', () => {
      window._faControls.clear();
      const a = ensureAudio();
      if (a.src && a.src.startsWith('blob:')) URL.revokeObjectURL(a.src);
      a.removeAttribute('src');
      a.load();
      currentItem = null;
      refreshPlaylistUI();
      updatePlayBtn(false);
    });

    setInterval(refreshPlaylistUI, 1500);
    return ui;
  }

  function refreshPlaylistUI() {
    if (!ui) return;
    const items = window._faControls.listAudio();
    ui.plCount.textContent = items.length;
    const enabled = items.length > 0;
    ui.playBtn.disabled = false;       // always: can resume last
    ui.stopBtn.disabled = !audio || !audio.src;
    ui.prevBtn.disabled = items.length < 2;
    ui.nextBtn.disabled = items.length < 2;
    ui.playlist.innerHTML = '';
    items.forEach((it) => {
      const div = document.createElement('div');
      div.className = 'pl-item';
      const id = `${it.msgId}:${it.segIdx}`;
      if (currentItem && `${currentItem.msgId}:${currentItem.segIdx}` === id) {
        div.classList.add('active');
      }
      const preview = document.createElement('span');
      preview.className = 'preview';
      preview.textContent = `seg ${it.segIdx} · ${(it.b64.length / 1024 * 0.75).toFixed(1)} KB`;
      const play = document.createElement('button');
      play.textContent = '▶';
      play.addEventListener('click', (e) => { e.stopPropagation(); playItem(it); });
      const del = document.createElement('button');
      del.textContent = '✕';
      del.addEventListener('click', (e) => {
        e.stopPropagation();
        window._faControls.removeAudio(it.msgId, it.segIdx);
        if (currentItem && currentItem.msgId === it.msgId && currentItem.segIdx === it.segIdx) {
          const a = ensureAudio();
          if (a.src && a.src.startsWith('blob:')) URL.revokeObjectURL(a.src);
          a.removeAttribute('src'); a.load(); currentItem = null;
        }
        refreshPlaylistUI();
      });
      div.appendChild(preview);
      div.appendChild(play);
      div.appendChild(del);
      div.addEventListener('click', () => playItem(it));
      ui.playlist.appendChild(div);
    });
    ui.playBtn.disabled = false;
  }

  function refreshTimeUI() {
    if (!ui || !audio) return;
    const ct = audio.currentTime || 0;
    const dur = isFinite(audio.duration) ? audio.duration : 0;
    ui.time.textContent = `${fmtTime(ct)} / ${fmtTime(dur)}`;
    if (!ui.seek.dataset.dragging && dur > 0) ui.seek.value = ct;
    ui.seek.disabled = dur <= 0;
  }

  function fmtTime(s) {
    if (!isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${String(sec).padStart(2, '0')}`;
  }

  function updatePlayBtn(playing) {
    if (!ui) return;
    ui.playBtn.textContent = playing ? '⏸' : '▶';
    ui.playBtn.dataset.state = playing ? 'playing' : 'paused';
  }

  // ── Open the panel (called from chat/floating button taps) ─
  let panelOpen = false;
  async function openControlPanel() {
    try { await risuai.showContainer('fullscreen'); } catch {}
    ensureUI();
    refreshPlaylistUI();
    panelOpen = true;
  }

  // ── Hooks ─────────────────────────────────────────

  // addTTSPostprocessor — capture every TTS audio buffer produced by PocketRisu.
  try {
    await risuai.addTTSPostprocessor(async (ctx) => {
      try {
        const char = await risuai.getCharacter();
        const msgId = char?.chat?.[char.chat?.length - 1]?.message_id
                   ?? char?.chatPage?.messageId
                   ?? `unknown-${Date.now()}`;
        const segIdx = segCounter++;
        storeAudio(msgId, segIdx, ctx.audio, ctx.mimeType || 'audio/mpeg');
        if (panelOpen && ui) refreshPlaylistUI();
      } catch (e) { err('postprocessor capture failed', e); }
      // Return void → original audio plays untouched.
    });
    log('addTTSPostprocessor registered');
  } catch (e) { err('addTTSPostprocessor failed (non-fatal)', e); }

  // addTTSPreprocessor — strip *action* / _emphasis_ markup before synthesis.
  try {
    await risuai.addTTSPreprocessor(async (ctx) => {
      if (ctx.ttsMode === 'openai' || ctx.ttsMode === 'fishspeech') {
        const cleaned = ctx.text
          .replace(/\*[^*]*\*/g, '')
          .replace(/_[^_]*_/g, '')
          .replace(/\s+/g, ' ')
          .trim();
        return { text: cleaned };
      }
    });
    log('addTTSPreprocessor registered');
  } catch (e) { err('addTTSPreprocessor failed (non-fatal)', e); }

  // ── UI entry points ───────────────────────────────

  await risuai.registerSetting(
    'Fish Audio Controls',
    async () => {
      try { await openControlPanel(); }
      catch (e) { err('panel open failed', e?.message); }
    },
  );

  await risuai.registerButton({
    name: 'Fish Audio Controls',
    icon: '🎣',
    iconType: 'html',
    location: 'chat',
    id: 'fa-open-panel',
  }, async () => {
    try { await openControlPanel(); }
    catch (e) { err('panel open failed', e?.message); }
  });

  log('initialized');
})();
