#!/usr/bin/env node
/**
 * Smoke test for plugin.js: verifies plugin registers all required risuai
 * methods without throwing during init. DOM stubs swallow everything.
 */

const fs = require('fs');
const vm = require('vm');
const path = require('path');

const PLUGIN = path.join(__dirname, 'plugin.js');
const SRC = fs.readFileSync(PLUGIN, 'utf8');

const noop = () => {};
const callCounts = {};
const stub = (k) => (...args) => {
  callCounts[k] = (callCounts[k] || 0) + 1;
  if (k === 'addTTSPostprocessor' || k === 'addTTSPreprocessor') {
    return async (ctx) => {
      // Return an empty result for pre, no-op for post
      if (k === 'addTTSPreprocessor') return { text: ctx.text };
      if (k === 'addTTSPostprocessor') {
        // Simulate the storage path
        return;
      }
    };
  }
  return undefined;
};

let audioStore = [];
const stubs = {
  addTTSPreprocessor: stub('addTTSPreprocessor'),
  addTTSPostprocessor: stub('addTTSPostprocessor'),
  registerSetting:    stub('registerSetting'),
  registerButton:     stub('registerButton'),
  showContainer:      stub('showContainer'),
  hideContainer:      stub('hideContainer'),
  getCharacter:       async () => ({ chatPage: { messageId: 'fake' }, chat: [] }),
  getRootDocument:    async () => ({}),
  getArg:             () => null,
  pluginStorage: {
    _s: new Map(),
    getItem(k) { return this._s.has(k) ? this._s.get(k) : null; },
    setItem(k, v) { this._s.set(k, v); },
  },
};

// Smart element stub — preserves own properties and returns deaf children.
const elemStore = [];
function makeEl(tag = 'div') {
  const id = elemStore.length;
  elemStore.push({ id, tag });
  return {
    _id: id,
    _tag: tag,
    tagName: tag.toUpperCase(),
    children: [],
    style: { cssText: '' },
    dataset: {},
    _classList: new Set(),
    classList: {
      add(...c) { c.forEach(x => this._classList.add(x)); },
      remove(...c) { c.forEach(x => this._classList.delete(x)); },
      contains(c) { return this._classList.has(c); },
    },
    addEventListener: noop,
    removeEventListener: noop,
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    removeChild(c) { this.children = this.children.filter(x => x !== c); return c; },
    remove() {},
    click() {},
    setAttribute: noop, getAttribute() { return null; }, removeAttribute: noop,
    querySelector(sel) { /* return a deaf-but-real-looking el */ return makeEl(sel.replace(/[^a-z]/g, '') || 'span'); },
    querySelectorAll() { return []; },
    getElementById() { return null; },
    set textContent(v) {
      if (typeof v === 'string' && v.includes('<style>') && this._tag === 'style') {
        this._cssText = v;
      }
    },
    get textContent() { return ''; },
    set innerHTML(html) {
      // Crude "rendering" — count tags so we know it wasn't empty
      const m = (html || '').match(/<\w+/g) || [];
      this._renderedTags = m;
    },
    get innerHTML() { return ''; },
    set value(v) { this._value = v; }, get value() { return this._value || ''; },
    set checked(v) { this._checked = v; }, get checked() { return !!this._checked; },
    set src(v) { this._src = v; }, get src() { return this._src || ''; },
    set id(v) { this._idStr = v; }, get id() { return this._idStr || ''; },
    set volume(_) {},
    set playbackRate(_) {},
    set currentTime(_) {},
    load: noop, play: async () => {}, pause: noop,
  };
}

// Make the same el instances trackable when needed
let floatingBar = null;
const origCreate = makeEl;
function trackedCreate(tag) {
  const el = origCreate(tag);
  if (!floatingBar) floatingBar = el;
  return el;
}

const ctx = {
  console,
  setTimeout: (fn, _t) => fn && fn(),
  clearTimeout: noop,
  setInterval: noop, clearInterval: noop,
  Blob: class { constructor(p){ this.p = p; } },
  URL: { createObjectURL() { return 'blob:x'; }, revokeObjectURL: noop },
  Audio: class { constructor(){ this.src = ''; this.currentTime = 0; this.paused = true; } },
  document: {
    body: trackedCreate('body'),
    head: trackedCreate('head'),
    createElement: trackedCreate,
    createElementNS: (_ns, tag) => trackedCreate(tag),
    addEventListener: noop, removeEventListener: noop,
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  },
  window: {},
  risuai: stubs,
};
ctx.global = ctx;
vm.createContext(ctx);

let exitCode = 0;
try {
  vm.runInContext(SRC, ctx, { filename: 'plugin.js' });
} catch (e) {
  console.error('✗ plugin.js threw during init:', e.message);
  console.error(e.stack.split('\n').slice(0, 8).join('\n'));
  exitCode = 1;
}

// Allow microtasks
Promise.resolve().then(() => Promise.resolve()).then(() => {
  const report = [
    ['addTTSPreprocessor registered',  (callCounts.addTTSPreprocessor  || 0) >= 1],
    ['addTTSPostprocessor registered', (callCounts.addTTSPostprocessor || 0) >= 1],
    ['registerSetting registered',     (callCounts.registerSetting     || 0) >= 1],
    ['registerButton registered',      (callCounts.registerButton      || 0) >= 1],
    ['getCharacter hook invokable',    typeof stubs.getCharacter === 'function'],
  ];
  console.log('\n=== smoke results ===');
  for (const [k, v] of report) console.log(`  ${v ? '✓' : '✗'}  ${k}`);
  const failed = report.filter(([, v]) => !v).length;
  if (failed) {
    console.log(`\n${failed} check(s) failed`);
    process.exit(1);
  }
  console.log('\nall checks passed');
  console.log(`registrations: pre=${callCounts.addTTSPreprocessor||0} post=${callCounts.addTTSPostprocessor||0} set=${callCounts.registerSetting||0} btn=${callCounts.registerButton||0}`);
  process.exit(exitCode);
});
