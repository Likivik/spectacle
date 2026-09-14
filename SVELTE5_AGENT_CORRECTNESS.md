# Svelte 5 + SvelteKit — Agent-Correctness Research Report

**Purpose:** Distill the specific knowledge an AI agent needs to avoid Svelte 5 /
SvelteKit bugs when building the Spectacle stack: SvelteKit SPA mode
(`@sveltejs/adapter-static`, hash-based routing fallback), Svelte 5 runes
(`$state` / `$derived` / `$effect` / `$props` / `$bindable`), Vite, Tailwind v4
(CSS-first config via `@theme` in `app.css`), Vitest, and DOMPurify + marked for
markdown rendering. Backend is an Axum REST + SSE on the same origin behind a
Vite dev proxy. Build commands run via `nix develop -c npm run build`.

**Research date:** 2026-09-16. All URLs were live and verified.

---

## 1. Svelte 5 runes — gotchas that break AI-written code

### 1.1 `$state` — deep proxy semantics

- `$state(value)` declares a reactive cell. The Svelte compiler rewrites every
  read to `$.get(state)` and every write to `$.set(state)`. `$state` is a
  compiler keyword, not a runtime import: you cannot alias it, pass it around,
  or call it conditionally. (Source: <https://svelte.dev/docs/svelte/$state>,
  <https://fullstacksveltekit.com/blog/svelte-5-state-rune>)
- For plain objects and arrays, `$state` returns a **deep Proxy**. Mutations at
  any depth (`state.user.name = 'x'`, `arr.push(x)`) trigger fine-grained
  updates. (Source: <https://svelte.dev/docs/svelte/$state>)
- The proxy **stops at class instances**, `Object.create`-based objects, and
  native `Map` / `Set` / `Date` / `URL` (because they are class instances).
  For reactive equivalents, use `SvelteMap` / `SvelteSet` etc. from
  `svelte/reactivity`. (Source: <https://fullstacksveltekit.com/blog/svelte-5-state-rune>)
- **Destructuring detaches reactivity.** `let { name, age } = user` gives you
  plain values at the moment of destructure; the local bindings are not
  reactive. Two fixes: read through the proxy (`user.name`) everywhere, or pass
  a getter function (`() => user.name`). (Source: same)
- **ES module exports of `let` with `$state` will not work** — the compiler
  can only rewrite one file at a time, so importers see raw values. Two working
  patterns:
  1. Export an object whose *properties* you mutate (the binding itself is
     `const`); or
  2. Keep the state file-local and export a getter function.
  Best for app state: define a class with `$state` fields and export a
  `const` reference to the instance. (Source: <https://svelte.dev/docs/svelte/$state>)
- **`$state.raw(value)`** — opt out of the deep proxy. Use for large, immutable
  data (JSON API responses, config tables). Raw state cannot be mutated; it can
  only be reassigned. (Source: <https://svelte.dev/docs/svelte/$state>,
  <https://svelte.dev/docs/svelte/best-practices>)
- **`$state.snapshot(value)`** — returns a plain, detached copy. Use at API
  boundaries that can't accept proxies (`structuredClone`, `postMessage`,
  some serializers). The snapshot is *not* reactive: reading it does not
  register a dependency, mutating it does not update the original.
- **`$state.eager(value)`** — forces a synchronous read to avoid a one-frame
  scheduling lag (e.g. `aria-current` flicker on a click). Reach for this
  only when you can observe the lag — the docs explicitly warn to use it
  sparingly. (Source: <https://svelte.dev/docs/svelte/$state>)
- **Spread / `Object.keys` on a class with `$state` fields drop the reactive
  fields** because the fields are accessors on the prototype, not own
  properties. Spreading `{ ...todo }` loses `done` and `text`. Use
  `$state.snapshot` if you need a plain object. (Source:
  <https://fullstacksveltekit.com/blog/svelte-5-state-rune>)
- **Method references lose `this`.** If `toggle` is a class method and you
  write `<button onclick={instance.toggle}>`, `this` is undefined. Wrap in
  arrow, bind in constructor, or define as an arrow field (`toggle = () => {...}`).
- **Only declare `$state` for variables that should be reactive**; everything
  else should be a plain `const` / `let`. (Source:
  <https://svelte.dev/docs/svelte/best-practices>)

### 1.2 `$derived` vs `$effect` — when to use which

- **Default to `$derived` for computing values from state** (90% rule).
  `$derived(expression)` is for pure calculations: outputs a value, no side
  effects, memoised, recalculated only when its dependencies change.
  `$derived.by(() => {...})` is the form for complex logic. Deriveds are
  **writable** as of Svelte 5.25 (assign to them directly to override,
  useful for optimistic UI). (Sources:
  <https://svelte.dev/docs/svelte/$derived>,
  <https://svelte.dev/docs/svelte/best-practices>)
- **`$effect` is an escape hatch**, used for side effects only:
  analytics, syncing state to an external lib (D3), persisting to
  `localStorage`, network requests in response to state changes.
  (Source: <https://svelte.dev/docs/svelte/$effect>)
- **Never wrap effect body in `if (browser) {...}`** — effects don't run on
  the server at all. They run only after mount in the browser, after DOM
  updates have been applied. (Source:
  <https://svelte.dev/docs/svelte/best-practices>)
- **Avoid updating state inside `$effect`** — that creates update cycles.
  Link two reactive values with `$derived` and an `oninput` callback instead
  (the migration guide explicitly recommends this for "linked inputs"
  patterns). (Source: <https://svelte.dev/docs/svelte/$effect>)
- **The `state` object reference is not the dependency — its *properties*
  are.** `$effect(() => state)` won't re-run when `state.value` changes; you
  must read `state.value` inside the effect. Reading a `$derived` that
  returns a new object each time also re-runs the effect. (Source:
  <https://svelte.dev/docs/svelte/$effect>)
- **`untrack(() => ...)`** — exclude reads from the dependency set. Use when
  you must write inside an effect (e.g. `array.push` reads `length` first,
  which would otherwise create an infinite loop). (Source:
  <https://svelte.dev/docs/svelte/$effect>, GitHub issue sveltejs/svelte#16092)
- **`$effect.root(() => {...})`** creates a non-tracked scope for testing
  or programmatic effect trees outside a component. (Source:
  <https://svelte.dev/docs/svelte/testing>)
- **`$effect.pre(fn)`** runs *before* DOM updates (the old `beforeUpdate`
  hook). `$effect(fn)` runs *after*. (Source:
  <https://svelte.dev/docs/svelte/$effect>)
- **Push–pull reactivity** — when state changes, everything that depends on
  it is *notified* (push), but `$derived` values are not re-evaluated until
  they are *read* (pull). This is why deriveds are cheap to define and
  expensive to access in tight loops. (Source:
  <https://svelte.dev/docs/svelte/$derived>)
- **Diagnostic tool: `$inspect.trace(label)`** — drop into the first line of
  an effect / derived to log which dependency triggered an update.
  (Source: <https://svelte.dev/docs/svelte/best-practices>)

### 1.3 `$props` / `$bindable`

- `let { foo, bar = 'default' } = $props()` replaces `export let`. (Source:
  <https://next.svelte.dev/docs/svelte/v5-migration-guide>)
- **Bindable props are opt-in.** Wrap in `$bindable()`:
  `let { value = $bindable(0) } = $props()`. Without `$bindable`, a parent
  `bind:value` silently fails. (Source: <https://svelte.dev/docs/svelte/bind>,
  <https://next.svelte.dev/docs/svelte/v5-migration-guide>)
- If a bindable prop has a default and the parent uses `bind:`, the parent
  must pass a non-`undefined` value (otherwise a runtime error is thrown).
  This is a behavioural change from Svelte 4 (which reflected the default
  back to the parent).
- **Callbacks as props** replace `createEventDispatcher`. The child declares
  `let { onclick, onsubmit } = $props()`, the parent passes
  `onclick={handler}`. Forwarding event handlers via spread works:
  `<button {...$$props}>` becomes `<button {...rest}>` where `rest` is a
  separate destructuring. (Source: <https://svelte.dev/docs/svelte/v5-migration-guide>)

### 1.4 Snippets replacing slots

- `{#slot}` is replaced by `{#snippet name(args)}...{/snippet}` + `{@render
  name(args)}`. The default slot becomes the `children` snippet.
  - Child declares: `let { children, header } = $props()`
  - Child uses: `<header>{@render header?.()}</header>`
  - Parent uses: `<Layout>{#snippet header()}...{/snippet}</Layout>`
- `createRawSnippet(fn)` from `svelte` is the programmatic way to create a
  snippet for testing or dynamic composition. (Source:
  <https://vitest.dev/api/browser/svelte>)
- Slots still work in Svelte 5 (deprecated, not removed), but new code should
  use snippets. (Source: <https://svelte.dev/docs/svelte/v5-migration-guide>)

### 1.5 Event syntax: `onclick={...}` replaces `on:click={...}`

- Drop the colon: `<button onclick={handler}>`. Event modifiers (`|preventDefault`,
  `|stopPropagation`) are **gone** — handle inside the callback, or use the
  legacy helpers `preventDefault` / `stopPropagation` from `svelte/legacy`.
  (Source: <https://svelte.dev/docs/svelte/v5-migration-guide>)
- **`on:event` syntax still works for backwards compatibility** but is
  deprecated. Some `onevent` attributes are *delegated* — manually stopping
  propagation can prevent the delegated listener from running. (Source:
  same)
- **`onclick` no longer accepts a string** (e.g. `onclick="alert('x')"`). Only
  a function. (Source: same)
- Multiple handlers on one event: just call them in one function:
  `onclick={(e) => { a(e); b(e); }}`.

### 1.6 Mounting caveats

- `new Component({ target })`, `$set`, `$on`, `$destroy` are **gone**. Use
  `mount(Component, { target, props })` from `svelte` to mount imperatively;
  `unmount(component)` to tear down. (Source:
  <https://svelte.dev/docs/svelte/imperative-component-api>)
- For tests, prefer `render()` from `vitest-browser-svelte` (Browser Mode)
  or `@testing-library/svelte` (jsdom). Both internally use `mount()`.

### 1.7 Hydration and CSR-only SPA mode (prerender=false, ssr=false)

- **Default SvelteKit: SSR + hydrate.** Page options: `ssr`, `prerender`,
  `csr` are exported from `+page.js` / `+layout.js`. (Source:
  <https://svelte.dev/docs/kit/page-options>)
- **For a pure SPA via `adapter-static`** the documented pattern is:
  - Root layout: `export const ssr = false` (disables SSR for all pages).
  - In `svelte.config.js`: `adapter({ fallback: '200.html' })` (or
    `'index.html'`, `'404.html'` depending on host).
  - The fallback page is what the host serves when a path isn't prerendered.
    The static host must be configured to serve `200.html` (or whatever) for
    any unknown path — see Apache `.htaccess` snippet in docs. (Source:
    <https://svelte.dev/docs/kit/single-page-apps>,
    <https://svelte.dev/docs/kit/adapter-static>)
- **Subtle gotcha:** GitHub issue sveltejs/kit#13469 documents that with
  `adapter-static` and no `+page.server.js` / `+layout.server.js` /
  `+server.js`, **`ssr=false` is not strictly necessary** — the fallback
  mechanism produces a client-rendered app regardless. But you DO want
  `ssr=false` if your app mixes prerendered + dynamic routes. The official
  SPA docs still recommend `ssr=false` in the root layout for clarity.
  (Source: <https://github.com/sveltejs/kit/issues/13469>)
- **`+page.ts` and `+layout.ts` still execute on Node during the build** even
  with `ssr=false` and `prerender=false`, because SvelteKit needs to read
  the exports. Putting browser-only code (e.g. `new Worker()`) at module
  top level in those files throws at build time. Move browser-only code
  inside `load` functions or into the `+page.svelte` file itself. (Source:
  <https://github.com/sveltejs/kit/issues/11664>)
- **`trailingSlash` matters.** If your host doesn't rewrite `/a` →
  `/a.html`, set `trailingSlash: 'always'` in root layout to create
  `/a/index.html` files. (Source:
  <https://svelte.dev/docs/kit/adapter-static>)
- **`adapter-static` default `strict: true`** asserts that all pages were
  prerendered OR you set `fallback`. Set `strict: false` only if some pages
  are intentionally unreachable. (Source:
  <https://svelte.dev/docs/kit/adapter-static>)
- **Bundle strategy:** for truly portable SPAs (e.g. IPFS, single HTML
  embed), set `output.bundleStrategy: 'inline'` to inline JS + CSS into
  `index.html`. (Source:
  <https://sveltetalk.com/posts/sveltekit-hash-routing>)
- **`prerender: 'auto'`** for routes you want included in the server manifest
  even when prerendering (useful for `/blog/[slug]` where most posts are
  prebuilt but the long tail is dynamic). (Source:
  <https://svelte.dev/docs/kit/page-options>)

### 1.8 SPA-mode implications for our Axum/SSE stack

- No `+page.server.js` / `+layout.server.js` / `+server.js` allowed (no
  `+server.js` API routes) — backend lives on Axum, **all API/SSE calls
  must hit the same origin** as the static app. (Source:
  <https://svelte.dev/docs/kit/single-page-apps>)
- For SSE on the same origin, use `new EventSource('/api/events')` with
  relative URLs — works because Vite dev proxy AND production static
  hosting both forward `/api/*` to the backend.
- `goto()` (SvelteKit navigation) works in SPA mode but only updates the
  history; the host never sees the URL change unless `pushState` is in use.
  For hash routing, see §2.1.

---

## 2. SvelteKit static-adapter SPA specifics

### 2.1 Hash routing vs `pushState` fallback

- **Hash routing is supported** as of SvelteKit via
  `kit.router.type: 'hash'`. Configure in `svelte.config.js`:

  ```js
  kit: {
    adapter: adapter({ fallback: 'index.html' }),
    router: { type: 'hash' }
  }
  ```

  All routes become `/#/about` instead of `/about`. No server config
  needed — works on any static host, IPFS, embedded widgets, Electron.
  (Sources: <https://github.com/sveltejs/kit/issues/7443>,
  <https://sveltetalk.com/posts/sveltekit-hash-routing>,
  GitHub PR sveltejs/kit#13213)
- Hash routing **automatically disables SSR**. You cannot have
  `+page.server.js` / `+layout.server.js`. All data loading must be
  client-side. Progressive enhancement patterns (form actions) do not
  apply. (Source: <https://sveltetalk.com/posts/sveltekit-hash-routing>)
- If you stick with **default `pushState` routing**, the host must serve
  the fallback page for any path that doesn't match a file. Netlify does
  this automatically (it uses `_redirects`), Vercel uses its `routes`
  config, Apache needs `.htaccess`, IPFS needs special handling. The
  simplest portable choice is **hash routing**.
- For an Axum-backed SPA where the backend serves both `/api/*` and
  falls back to static files, hash routing eliminates the need to
  distinguish in the Axum router.

### 2.2 404 fallback page

- The `fallback` option in `adapter-static` accepts a filename; the host
  must serve that file for any unmatched path. Recommended names:
  - `200.html` — Surge, Netlify-style generic fallback
  - `404.html` — GitHub Pages, IPFS
  - `index.html` — single-HTML embedded app
  - Avoid `index.html` if your homepage is prerendered (conflict).
  (Source: <https://svelte.dev/docs/kit/adapter-static>,
  <https://svelte.dev/docs/kit/single-page-apps>)
- The fallback page contains **absolute asset paths** (`/foo.js`,
  not `./foo.js`) regardless of `paths.relative`. (Source: same)
- Apache example (from docs):

  ```apache
  <IfModule mod_rewrite.c>
    RewriteEngine On
    RewriteBase /
    RewriteRule ^200\.html$ - [L]
    RewriteCond %{REQUEST_FILENAME} !-f
    RewriteCond %{REQUEST_FILENAME} !-d
    RewriteRule . /200.html [L]
  </IfModule>
  ```

### 2.3 Dev proxy: Vite `server.proxy` for Axum API + SSE

- SvelteKit delegates dev-server proxying to **Vite**. Configure in
  `vite.config.ts`:

  ```ts
  import { defineConfig } from 'vite';
  import { sveltekit } from '@sveltejs/kit/vite';

  export default defineConfig({
    plugins: [sveltekit()],
    server: {
      proxy: {
        '/api': {
          target: 'http://localhost:8080',  // Axum
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/api/, ''),
        },
        '/events': {
          target: 'http://localhost:8080',
          ws: true,                          // SSE doesn't need ws,
          changeOrigin: true,                // but enable if Axum uses
        },                                   // WebSockets elsewhere
      },
    },
  });
  ```

  (Sources: <https://stackoverflow.com/questions/72753092/how-to-proxy-on-svelte-kit-in-dev-mode>,
  <https://vite.dev/config/server-options>)
- **`kit.vite.server.proxy` is documented under Vite, not SvelteKit.**
  SvelteKit's docs say "see Vite" (the proxy config is *passed through*
  to Vite). This is a frequent gotcha — agents grep `svelte.config.js`
  for `proxy` and find nothing. (Source:
  <https://github.com/sveltejs/kit/discussions/2778>)
- Key proxy options (extending `http-proxy-3`):
  - `target` — upstream URL (string).
  - `changeOrigin: true` — required when upstream uses virtual hosts
    (e.g. localhost:8080 with Host header). Almost always true.
  - `rewrite` — function `(path) => string` to strip a prefix.
  - `ws: true` — proxy WebSocket upgrades.
  - `bypass` — function `(req, res, options) => boolean | string` to
    short-circuit certain requests.
  - RegExp keys allowed: prefix with `^`. (Source:
    <https://vite.dev/config/server-options>)
- **SSE gotcha:** `EventSource` uses long-lived HTTP, which the proxy
  supports out of the box. But **don't set `ws: true`** for plain SSE —
  it's only for WebSocket upgrades.
- **Use relative URLs in the app**: `fetch('/api/...')` works in both
  dev (via proxy) and prod (same origin behind Axum fallback). Absolute
  URLs break when you switch between the two. (Source:
  <https://stackoverflow.com/questions/69173381/sveltekits-how-to-omit-host-address-in-fetch-url-under-proxy>)
- Vite warns: **"If you are using non-relative `base`, you must prefix
  each key with that `base`."** (Source:
  <https://vite.dev/config/server-options>)

### 2.4 Environment variables — `PUBLIC_` prefix, `$env/static/public`

- **In Vite land**: `import.meta.env.VITE_*` are exposed to client code
  at build time.
- **In SvelteKit**: `PUBLIC_*` (configurable via `kit.env.publicPrefix`)
  are exposed to client code via `$env/static/public` or
  `$env/dynamic/public`. **The `VITE_` prefix is a Vite convention but
  does NOT automatically work in SvelteKit** — SvelteKit uses `PUBLIC_`.
  (Source: <https://svelte.dev/docs/kit/$env-static-public>)
- `VITE_*` vars **are still accessible** in client code if you import
  them via `import.meta.env.VITE_FOO` (Vite handles this). But the
  SvelteKit-native way is `PUBLIC_FOO` + `import { PUBLIC_FOO } from
  '$env/static/public'`. Mixing the two in one codebase is a common
  agent mistake.
- For SvelteKit SPA mode specifically, `$env/static/public` is preferred
  because:
  - Static injection at build time enables dead-code elimination.
  - For prerendered pages, only `$env/static/*` work — `$env/dynamic/*`
    is not available.
  - `$env/static/public` works in prerendered AND CSR-only SPA builds.
    (Sources: <https://svelte.dev/docs/kit/$env-static-public>,
    <https://maier.tech/posts/environment-variables-in-sveltekit>)
- **Build-time only.** If you need runtime config (e.g. per-deployment
  backend URL), use `$env/dynamic/public` and pass through a `load`
  function — but `load` functions in pure-SPA mode are evaluated at
  build time too, so you'd need a server anyway. For Spectacle's Axum
  same-origin setup, no env vars should be needed for API URLs.
- As of SvelteKit 2.63, you can **opt into explicit env vars** by
  importing from `$app/env/private` and `$app/env/public` instead — both
  sets are still supported, the opt-in just makes the dependency
  explicit. (Source: <https://svelte.dev/docs/kit/environment-variables>)
- **`.env` files are loaded by Vite**, not SvelteKit directly. `VITE_*`
  and `PUBLIC_*` vars from `.env`, `.env.local`, `.env.production`, etc.
  follow Vite's normal precedence.

---

## 3. Testing runes components

### 3.1 Framework status (Sept 2026)

- **`@testing-library/svelte`** supports Svelte 3, 4, and 5. The
  integration needs the `svelteTesting` plugin from
  `@testing-library/svelte/vite` in your `vite.config.ts`. This plugin
  sets the `browser` resolve condition and auto-cleans up the DOM after
  each test (no manual `afterEach(cleanup)`). (Source:
  <https://blog.openreplay.com/test-svelte-5-components-vitest/>)
- **`vitest-browser-svelte`** is the new community package (Vitest
  Browser Mode + Playwright). It runs components in a real browser via
  Playwright, supports Svelte 5 runes natively, and uses Vitest locators
  (which auto-retry assertions until the DOM settles). Requires Vitest 4
  (Browser Mode exited experimental). (Sources:
  <https://vitest.dev/api/browser/svelte>,
  <https://blog.openreplay.com/test-svelte-5-components-vitest/>,
  <https://scottspence.com/posts/migrating-from-testing-library-svelte-to-vitest-browser-svelte>)
- **Old `@testing-library/svelte` + jsdom is being supplanted** because
  jsdom struggles with Svelte's reactivity — Scott Spence's migration
  post documents "weird errors or silently failing to detect reactivity
  changes." Use `vitest-browser-svelte` for new code if you can.
  (Source: <https://scottspence.com/posts/migrating-from-testing-library-svelte-to-vitest-browser-svelte>)

### 3.2 jsdom limitations with runes

- `vitest` + `jsdom` runs the Svelte compiler but executes the result
  in Node with a DOM stub. Effects schedule via `Promise.resolve()` /
  microtasks, which the test runner needs to **flush explicitly**.
- **Runes only execute after the Svelte compiler processes the file**
  (which only happens for files matching `*.svelte*`). A test file
  named `counter.test.js` cannot use `$state` — rename to
  `counter.svelte.test.js`. (Sources:
  <https://svelte.dev/docs/svelte/testing>,
  <https://blog.openreplay.com/test-svelte-5-components-vitest/>)
- **`$derived` does not recompute in jsdom by default** — you need
  `flushSync()` from `svelte` after mutating state, then read the
  derived value. The `derived` is "pull-based" — it only recomputes on
  read, but the read needs to happen after the update batch flushes.
- **`$effect` doesn't run unless wrapped in `$effect.root`** when the
  test isn't inside a mounted component. This is the canonical
  pattern:

  ```js
  test('Effect', () => {
    const cleanup = $effect.root(() => {
      let count = $state(0);
      let log = logger(() => count);
      flushSync();
      expect(log).toEqual([0]);
      count = 1;
      flushSync();
      expect(log).toEqual([0, 1]);
    });
    cleanup();
  });
  ```

  (Source: <https://github.com/sveltejs/svelte/blob/main/documentation/docs/07-misc/02-testing.md>)
- **Vitest environment must be set to `'browser'`** (not `'node'`) so
  runes actually run. If you see `$derived` returning the initial
  value forever, you forgot `environment: 'browser'` in `vitest.config.ts`
  or the `svelteTesting` plugin. (Source: GitHub issue sveltejs/svelte#17149)

### 3.3 `flushSync` and fake-timer pitfalls

- **Effects run async** (microtask-deferred). `flushSync()` from `svelte`
  flushes pending effects synchronously — use it after every state
  mutation that an effect should observe. Without it, the test
  races. (Source: <https://svelte.dev/docs/svelte/testing>)
- **Fake timers (`vi.useFakeTimers()`) conflict with `flushSync`**
  because Svelte's scheduler relies on `queueMicrotask` and Promise
  resolution. Patterns that work:
  - Use `vitest-browser-svelte` (real timers, real browser) — preferred
    for new code.
  - With jsdom + `@testing-library/svelte`, prefer real timers and
    explicit `flushSync()` calls rather than fake timers.
  - If you must use fake timers, call `vi.runAllTicks()` or
    `await Promise.resolve()` to drain microtasks after each
    `flushSync()`.
  (Source: GitHub issues sveltejs/svelte#16092, #17149, #18209)
- **Known Svelte 5.5x regression (svelte#18209)**: `$effect.pre` does
  not re-run on state change after `flushSync()` in tests, fixed in
  subsequent patches. Pin Svelte version if you hit it.
- **Worse: `flushSync` inside a render-phase effect can permanently
  kill reactivity** (svelte#18546) — only manifest in production, not
  in tests, but agent code that does this will silently break live
  apps. Avoid `flushSync()` inside `$effect.pre` / template effects.
- **Infinite-loop trap with `array.push` inside an `$effect`**
  (sveltejs/svelte#16092): the push reads `length` (registers a dep)
  and writes to it (invalidates the same dep). Either reassign the
  whole array or wrap the push in `untrack`.
- **Vitest version sensitivity**: sveltejs/svelte#16092 documents
  vitest 3.2.x regressions — pair specific Svelte + Vitest versions.
  Vitest 3.2.3 partially fixes things; pin explicitly in lockfile.

### 3.4 Component testing patterns

- **Test logic, not components, when possible.** Extract reactive
  logic into `.svelte.js` modules (which can use runes) and unit-test
  the module. The Svelte docs explicitly recommend this before
  writing component tests. (Source:
  <https://svelte.dev/docs/svelte/testing>)
- For Svelte 5 + `@testing-library/svelte`:
  - Use `render(Component, { props })` from
    `@testing-library/svelte/svelte5` (the Svelte 5 entry point).
  - `cleanup` is automatic via `svelteTesting` plugin — don't add
    `afterEach(cleanup)` manually.
  - Queries are by role / label (which forces accessibility).
  - After events that trigger runes updates, await microtask or call
    `flushSync()`.
- For `vitest-browser-svelte`:
  - All assertions are awaited: `await expect.element(loc).toBeVisible()`.
  - `await render(Component, props)` returns a `RenderResult` with
    locators + `rerender` + `unmount` + `container`.
  - Locators auto-retry — no manual `flushSync()` needed in browser mode.
  (Source: <https://vitest.dev/api/browser/svelte>)
- **Testing snippets:** wrap the snippet in a dummy component that
  exposes `{@render children?.()}` and assert on `data-testid`s, or
  use `createRawSnippet` to pass a programmatic snippet. (Source:
  same)
- **Testing events:** prefer `await userEvent.click(...)` (browser
  mode) over `fireEvent` (jsdom) for accurate event semantics. With
  `onclick={...}` (not `on:click`), the handler is just a property
  call — simpler to test in isolation.

---

## 4. Official agent-readable doc artifacts (llms.txt)

### 4.1 Svelte / SvelteKit (verified live 2026-09-16)

All serve `text/plain; charset=utf-8` with `Access-Control-Allow-Origin: *`
from Vercel CDN. Last-modified: Mon 14 Sep 2026.

| URL | Bytes | Content |
| --- | --- | --- |
| <https://svelte.dev/llms.txt> | 1,676 | Index of available files (small) |
| <https://svelte.dev/llms-full.txt> | 1,186,907 (~1.2 MB) | Full Svelte + SvelteKit docs |
| <https://svelte.dev/llms-medium.txt> | 837,205 | Abridged, examples removed |
| <https://svelte.dev/llms-small.txt> | 52,700 | Minimal, mostly reference |
| <https://svelte.dev/docs/svelte/llms.txt> | 480,261 | Svelte-only |
| <https://svelte.dev/docs/kit/llms.txt> | 588,648 | SvelteKit-only |
| <https://svelte.dev/docs/cli/llms.txt> | 200 | CLI only |
| <https://svelte.dev/docs/ai/llms.txt> | n/a | Svelte AI |
| <https://svelte.dev/docs/svelte/v5-migration-guide/llms.txt> | 200 | Svelte 4→5 migration guide |
| <https://svelte.dev/docs/svelte/best-practices/llms.txt> | 200 | Best-practices doc |

Discovery page: <https://svelte.dev/docs/llms>.

### 4.2 Tailwind CSS v4 — **does not exist officially**

- `https://tailwindcss.com/llms.txt` → **404 Not Found** (verified).
- `https://tailwindcss.com/llms-full.txt` → **404 Not Found** (verified).
- The Tailwind team is aware (tailwindlabs/tailwindcss discussion
  #18256) but as of mid-2026 has not shipped. They are gating an
  official llms.txt behind the "Insiders" sponsor tier
  (Cursor/Claude/AGENTS.md rules), and the public docs are source-available
  but not open-source — the team is cautious about redistribution.
  (Sources:
  <https://github.com/tailwindlabs/tailwindcss/discussions/18256>,
  <https://github.com/tailwindlabs/tailwindcss/discussions/14677>)
- **Workarounds for agents:**
  - Clone `tailwindlabs/tailwindcss.com` repo (MDX docs) and have the
    agent read individual files on demand. This is what
    [Lombiq/Tailwind-Agent-Skills](https://github.com/Lombiq/Tailwind-Agent-Skills)
    does — installs via `npx skills add Lombiq/Tailwind-Agent-Skills`,
    then runs `python scripts/sync_tailwind_docs.py --accept-docs-license`
    to populate `references/docs/`. The user explicitly accepts the
    upstream license.
  - Use [context7.com/websites/tailwindcss](https://context7.com/websites/tailwindcss)
    (third-party LLM-friendly docs index).
  - Individual pages on tailwindcss.com are Algolia-indexed and
    crawlable, so agents can use `web_fetch` per page.
- **For Tailwind v4 specifically, the things agents most often get wrong:**
  - Use `@import "tailwindcss";` not `@tailwind base; @tailwind components; @tailwind utilities;`.
  - Config is CSS-first via `@theme { --color-... }` in `app.css`,
    not JS in `tailwind.config.js`. (`tailwind.config.js` is optional
    in v4.)
  - No `content` array — v4 auto-detects sources.
  - `@apply` still works but is discouraged for new code.
  - Use `@theme` to declare custom design tokens; `@layer` for
    extending default layers; `@variant` for custom breakpoints.

### 4.3 Migration guides in llms format

- **Svelte 4 → 5**: <https://svelte.dev/docs/svelte/v5-migration-guide/llms.txt>
  (live, 200 OK). Covers `let` → `$state`, `$:` → `$derived` / `$effect`,
  `export let` → `$props`, `on:click` → `onclick`, slots → snippets, etc.
- **SvelteKit 1 → 2**: <https://svelte.dev/docs/kit/migrating-to-sveltekit-2/llms.txt>
  (live).
- **SvelteKit 2 → 3**: <https://svelte.dev/docs/kit/migrating-to-sveltekit-3/llms.txt>
  (live). Notes that `svelte.config.js` is removed — config moves to
  the `sveltekit()` Vite plugin options in `vite.config.js`. This
  affects Spectacle if you upgrade.
- **Pattern**: every docs page on svelte.dev has a `.llms.txt`
  counterpart appended to its URL (e.g.
  `/docs/svelte/$effect` → `/docs/svelte/$effect/llms.txt`). Confirmed
  for v5-migration-guide.

---

## 5. Accessibility (a11y) verification — Svelte-specific

### 5.1 What the Svelte compiler checks (compile-time)

There are ~30 `a11y_*` compiler warnings; full list at
<https://svelte.dev/docs/svelte/compiler-warnings>. Notable ones:

- **`a11y_missing_attribute`** — `<img>` without `alt`, `<a>` without
  `href`, etc.
- **`a11y_click_events_have_key_events`** — `onclick` on a
  non-interactive element with no `onkeyup` / `onkeydown` / `onkeypress`.
- **`a11y_no_static_element_interactions`** — click handler on `<div>`,
  `<span>` etc. with no `role`.
- **`a11y_no_noninteractive_element_interactions`** — handler on a
  `role="article"` etc. (non-interactive roles).
- **`a11y_label_has_associated_control`** — `<label>` with no `for`
  attribute and no wrapped `<input>`.
- **`a11y_media_has_caption`** — `<video>` without `<track>` for
  captions.
- **`a11y_missing_content`** — heading / anchor with no text content.
- **`a11y_positive_tabindex`** — `tabindex > 0`.
- **`a11y_autofocus`** — `autofocus` attribute is discouraged.
- **`a11y_aria_attributes`** — ARIA props on elements that don't
  support them (`meta`, `html`, `script`, `style`).
- **`a11y_incorrect_aria_attribute_type_*`** — wrong value type
  (boolean / integer / token / tristate / idlist).
- **`a11y_role_has_required_aria_props`** — role missing required
  ARIA.
- **`a11y_role_supports_aria_props_implicit`** — implicit role of
  element doesn't support the ARIA prop.
- **`a11y_unknown_role`** / `a11y_unknown_aria_attribute` — typos.
- **`a11y_no_redundant_roles`** — role duplicates implicit one.
- **`a11y_no_noninteractive_tabindex`** — tabindex on non-interactive.
- **`a11y_interactive_supports_focus`** — interactive role + handler
  without focusability.
- **`a11y_invalid_attribute`** — `href=""`, `href="#"`,
  `href="javascript:..."`.
- **`a11y_misplaced_role`** / `a11y_misplaced_scope`** — roles on
  elements that don't accept them.
- **`a11y_figcaption_index`** / `a11y_figcaption_parent`** — `<figcaption>`
  position rules.
- **`a11y_mouse_events_have_key_events`** — `onmouseover`/`onmouseout`
  need `onfocus`/`onblur`.
- **`a11y_distracting_elements`** — `<marquee>`, `<blink>`.
- **`a11y_img_redundant_alt`** — alt containing "image" / "picture".
- **`a11y_accesskey`** — discourage `accesskey`.

These run automatically at compile time (dev + build), can be elevated
to errors with `svelte-check --fail-on-warnings`, and surface as inline
editor hints via the Svelte VS Code extension.

### 5.2 What the compiler does **NOT** catch

(Condensed from Geoff Rich, "What Svelte's accessibility warnings won't
tell you" — <https://geoffrich.net/posts/svelte-a11y-limits/>.)

1. **Dynamic attribute values.** If `href={someVar}` and `someVar`
   could be `#` at runtime, the compiler can't know. No warning.
2. **Cross-component concerns.**
   - Heading-level skipping across components (e.g. `<h2>` in one,
     `<h4>` in another) — invisible to per-file static analysis.
   - Duplicate IDs in different components rendered simultaneously.
3. **Partial checks even for warnings it has.**
   - `a11y_label_has_associated_control` only requires the label to
     have `for=` or wrap an input. It does not verify an input with
     the matching `id` exists.
   - `a11y_invalid_attribute` only checks string-literal `href`s.
4. **CSS-only issues.**
   - Color contrast — text-on-background contrast ratios.
   - Focus visibility — focus ring color/contrast vs. background.
   - Touch target size (44x44 CSS pixels minimum).
5. **Things that need runtime / DOM checks.**
   - Is the alt text meaningful? Is the image decorative?
   - Is a custom dropdown/modal/combobox accessible by keyboard /
     screen reader / voice control?
   - Animation motion-sickness risk.
   - Live-region announcements actually happen.
   - Focus management on SPA route transitions.
   - Whether skipping navigation works as expected.
6. **Quality / intent.**
   - Whether a better semantic element exists (compiler warns about
     `a11y_no_static_element_interactions` but doesn't suggest a
     `<button>`).
   - Page structure for screen magnification users.
7. **WebAIM research**: 25–35% of WCAG errors are detectable by any
   automated tool. Svelte's compile-time checks are a subset of that.

### 5.3 Layers an agent should use (recommended stack)

1. **Compile-time**: Svelte's `a11y_*` warnings + `svelte-check
   --fail-on-warnings` in CI.
2. **Lint**: `eslint-plugin-svelte` extends the compiler rules.
3. **Component tests**: `@testing-library/svelte` queries (forces role
   / label queries by default — surfaces missing names) + `vitest-axe`
   (`toHaveNoViolations` matcher).
4. **End-to-end**: `@axe-core/playwright` against real routes.
5. **Manual**: keyboard pass + screen reader pass (the only way to
   confirm dialogs, live regions, focus traps actually work).

**Specifically for Spectacle's markdown rendering** (DOMPurify + marked):
the rendered HTML comes from user-edited markdown and can contain
arbitrary links / images / headings. Wrap DOMPurify with a config that
keeps ARIA-safe output; assert on rendered a11y with `vitest-axe` to
catch any heading-skip regressions across components.

---

## 6. Spectacle-specific implications (summary)

| Concern | Agent must know |
| --- | --- |
| SPA mode | `adapter-static` + `fallback` + `ssr=false` in root layout. `+page.ts` still evaluated at build — keep browser-only code inside `+page.svelte` or `load`. |
| Routing | Use `kit.router.type: 'hash'` for max portability (no host config). URLs become `/#/about`. |
| API/SSE | Same-origin. `fetch('/api/...')` with relative URLs. Vite dev proxy in `vite.config.ts` with `server.proxy`. |
| Env vars | Use `$env/static/public` + `PUBLIC_*`. `VITE_*` works for `import.meta.env` but is not the SvelteKit-native way. No runtime env changes in pure-SPA build. |
| State | Use `$state` only for reactive vars. Class fields with `$state` are accessors on the prototype — not own props (spread/`Object.keys` drop them). |
| Derived | Use `$derived` for computed values; `$effect` only for side effects (analytics, localStorage, external libs). |
| Bindable | Wrap in `$bindable()` for any prop the parent uses `bind:` on. |
| Events | `onclick={handler}` not `on:click={...}`. No modifiers — call `e.preventDefault()` in handler. |
| Slots | Use `{#snippet}` / `{@render}` not `<slot>`. |
| Testing | For Vitest + runes: file must be `*.svelte.test.ts`, wrap effects in `$effect.root`, call `flushSync()` after state changes. Prefer `vitest-browser-svelte` over `@testing-library/svelte` for Svelte 5. Avoid `array.push` inside `$effect` (use `untrack` or reassign). |
| Docs | `svelte.dev/llms-full.txt` (1.2 MB) — load on demand. `tailwindcss.com/llms.txt` does NOT exist — use Lombiq Tailwind Agent Skills or scrape tailwindcss.com repo. |
| A11y | `a11y_*` compiler warnings catch only static-markup issues (~30 rules). Combine with `vitest-axe` + manual keyboard/screen-reader pass. |
| Build command | `nix develop -c npm run build` runs Vite, which invokes `adapter-static`. Verify the `build/` directory contains the fallback page (e.g. `build/200.html` or `build/index.html`). |

---

## Sources

### Official Svelte / SvelteKit docs

- `$state` — <https://svelte.dev/docs/svelte/$state>
- `$derived` — <https://svelte.dev/docs/svelte/$derived>
- `$effect` — <https://svelte.dev/docs/svelte/$effect>
- Best practices — <https://svelte.dev/docs/svelte/best-practices>
- Compiler warnings — <https://svelte.dev/docs/svelte/compiler-warnings>
- Testing — <https://svelte.dev/docs/svelte/testing>
  (also <https://github.com/sveltejs/svelte/blob/main/documentation/docs/07-misc/02-testing.md>)
- v5 migration guide — <https://svelte.dev/docs/svelte/v5-migration-guide>
- `bind:` — <https://svelte.dev/docs/svelte/bind>
- `$env/static/public` — <https://svelte.dev/docs/kit/$env-static-public>
- Environment variables — <https://svelte.dev/docs/kit/environment-variables>
- Page options (ssr/prerender/csr) — <https://svelte.dev/docs/kit/page-options>
- Single-page apps — <https://svelte.dev/docs/kit/single-page-apps>
- `adapter-static` — <https://svelte.dev/docs/kit/adapter-static>
- Accessibility — <https://svelte.dev/docs/kit/accessibility>
- Docs for LLMs — <https://svelte.dev/docs/llms>
- Introducing runes (blog) — <https://svelte.dev/blog/runes>

### Tooling

- Vite `server.proxy` — <https://vite.dev/config/server-options>
- `vitest-browser-svelte` — <https://vitest.dev/api/browser/svelte>
- Testing Svelte 5 with Vitest (guide) — <https://blog.openreplay.com/test-svelte-5-components-vitest/>
- Migrating from testing-library to vitest-browser — <https://scottspence.com/posts/migrating-from-testing-library-svelte-to-vitest-browser-svelte>
- Tailwind llms.txt discussion — <https://github.com/tailwindlabs/tailwindcss/discussions/18256>
  and <https://github.com/tailwindlabs/tailwindcss/discussions/14677>
- Lombiq Tailwind Agent Skills — <https://github.com/Lombiq/Tailwind-Agent-Skills>

### GitHub issues (cited for known regressions)

- sveltejs/svelte#16092 — `$effect` testing broken with vitest 3.2.x; `array.push` in effect infinite loop
- sveltejs/svelte#17149 — `$state`/`$derived`/`$effect.root` behave incorrectly when vitest env is `node` not `browser`
- sveltejs/svelte#18209 — `$effect.pre` not re-run after `flushSync()` in tests (5.53.7 → 5.53.8 regression)
- sveltejs/svelte#18546 — `flushSync()` inside a render-phase effect can permanently kill the effect tree (production bug, not test-only)
- sveltejs/kit#11664 — `+page.ts` still executes on Node during build even with `ssr=false`/`prerender=false`
- sveltejs/kit#13469 — `ssr=false` not strictly necessary for pure-SPA via adapter-static (when no server-only files)
- sveltejs/kit#7443 — Original feature request for hash-based routing
- sveltejs/kit#13213 — Fix: allow dynamic routes with missing fallback in hash mode
- sveltejs/kit#2778 — Why is `kit.vite.server.proxy` not documented?

### SvelteKit router config

- Hash routing guide — <https://sveltetalk.com/posts/sveltekit-hash-routing>
- SO: proxy /api in SvelteKit — <https://stackoverflow.com/questions/72753092/how-to-proxy-on-svelte-kit-in-dev-mode>
- SO: omit host in fetch under proxy — <https://stackoverflow.com/questions/69173381/sveltekits-how-to-omit-host-address-in-fetch-url-under-proxy>

### Third-party deep dives

- Svelte 5 `$state` rune deep dive — <https://fullstacksveltekit.com/blog/svelte-5-state-rune>
- `$derived` vs `$effect` — <https://www.htmlallthethings.com/blog-posts/understanding-svelte-5-runes-derived-vs-effect>
- Svelte accessibility guide — <https://accessibility.build/guides/svelte-accessibility>
- Geoff Rich, "What Svelte's a11y warnings won't tell you" — <https://geoffrich.net/posts/svelte-a11y-limits/>
- Arc.dev, "Svelte 5 Runes migration guide" — <https://arc.dev/employer-blog/svelte-5-runes-migration-guide/>
- Svelte env vars (Maier) — <https://maier.tech/posts/environment-variables-in-sveltekit>