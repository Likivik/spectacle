/**
 * OCR Flow — Files context menu action.
 *
 * Adds "Send to OCR" / "Re-OCR anyway" / "Scan folder (OCR)" to the
 * single-file and bulk-selection context menus.
 *
 * MUST be ESM (.mjs): NC 34 loads init scripts with type=module only for
 * .mjs files, and the modern Files FileAction API lives in the
 * '@nextcloud/files' ES module — there is NO window.OCP.Files global
 * anymore (a classic script gets "registerFileAction not available").
 * Loaded via Util::addInitScript('ocrflow', 'ocr-action') in Application::boot().
 *
 * API: POST /apps/ocrflow/api/scan         { fileIds: [...], engine, force? }
 *      POST /apps/ocrflow/api/rescan-force { fileId, engine }      (force=true)
 *      POST /apps/ocrflow/api/scan-folder  { folder, engine }
 * Auth: Nextcloud session cookie (CSRF token via OC.requestToken).
 */
import { registerFileAction } from '@nextcloud/files'
import { translate as t, translatePlural as n } from '@nextcloud/l10n'

const OCRABLE_EXT = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'tiff', 'heic']

/**
 * @param {import('@nextcloud/files').Node|Object} node
 * @return {boolean}
 */
function isOcrable(node) {
	if (!node) return false
	// Folders have no extension/mime, so keying off the extension inherently
	// excludes them — no reliance on node.type (which differed from the file
	// check). NB: node.extension is '.pdf' (WITH leading dot) in
	// @nextcloud/files v4, so strip it; basename fallback is dot-free.
	const ext = (node.extension || '.' + ((node.basename || '').split('.').pop() || '')).toLowerCase().replace(/^\./, '')
	return OCRABLE_EXT.includes(ext)
}

/**
 * POST a scan request for the given fileIds to the OCS endpoint.
 * @param {number[]} fileIds
 * @param {string} engine
 * @param {boolean} [force=false] when true, bypass the born-digital
 *   skip decision AND the recently-processed guard. Used by the
 *   "Re-OCR anyway" action.
 */
async function sendToOcr(fileIds, engine, force = false) {
	const url = OC.generateUrl('/apps/ocrflow/api/scan')
	const body = { fileIds, engine }
	if (force) body.force = true
	try {
		const resp = await fetch(url, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'requesttoken': OC.requestToken,
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify(body),
		})
		const data = await resp.json()
		// OCS wraps in { ocs: { data } }
		const payload = data?.ocs?.data ?? data
		const results = payload?.results ?? []
		// Each entry is { fileId, path, ok, status, body? } — `ok` is the
		// controller's own success flag (true when the webhook accepted the
		// job). Controller-side failures use status:'error'. Count both.
		const ok = results.filter(r => r.ok === true).length
		const bad = results.filter(r => r.ok !== true).length
		// Rely on Nextcloud's own action feedback: returning true makes the
		// Files app show "{displayName}: done"; false shows "...: failed".
		// (OC.Notification was removed in NC 28+, so we must not call it.)
		if (results.length > 0 && bad === 0) {
			return true
		}
		console.warn('[ocrflow] scan: %d ok, %d failed', ok, bad)
		return false
	} catch (e) {
		console.error('[ocrflow] scan request failed', e)
		return false
	}
}

/**
 * POST a force re-OCR for a single file to the rescan-force endpoint.
 * @param {number} fileId
 * @param {string} engine
 */
async function sendRescanForce(fileId, engine) {
	const url = OC.generateUrl('/apps/ocrflow/api/rescan-force')
	try {
		const resp = await fetch(url, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'requesttoken': OC.requestToken,
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify({ fileId, engine }),
		})
		const data = await resp.json()
		const payload = data?.ocs?.data ?? data
		if (payload?.error) {
			console.warn('[ocrflow] rescanned failed:', payload.error)
			return false
		}
		return true
	} catch (e) {
		console.error('[ocrflow] rescan-force failed', e)
		return false
	}
}

/**
 * POST a folder scan to the scan-folder endpoint.
 * @param {string} folderPath relative path, e.g. "Work/1-Аренда"
 * @param {string} engine
 */
async function sendFolderToOcr(folderPath, engine) {
	const url = OC.generateUrl('/apps/ocrflow/api/scan-folder')
	try {
		const resp = await fetch(url, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'requesttoken': OC.requestToken,
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify({ folder: folderPath, engine }),
		})
		const data = await resp.json()
		const payload = data?.ocs?.data ?? data
		if (payload?.error) {
			console.warn('[ocrflow] folder scan failed:', payload.error)
			return false
		}
		return true
	} catch (e) {
		console.error('[ocrflow] folder scan failed', e)
		return false
	}
}

// ---- NC 28+ Files API (@nextcloud/files ESM) ----
// FileActionData v4: icons are inline SVG STRINGS via iconSvgInline (a
// function returning an SVG), NOT css class names via `icon`. Using the
// legacy `icon:()=>'icon-...'` makes the bundled validator throw
// "Invalid iconSvgInline function" and no action registers. Bulk execution
// key is `execBatch`, not `execBulk`.

const OCR_ICON = `<svg viewBox="0 0 16 16" width="16" height="16" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M3 2h6l2 2h2a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z"/></svg>`
const OCR_FOLDER_ICON = `<svg viewBox="0 0 16 16" width="16" height="16" xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" d="M1.5 3A1.5 1.5 0 0 1 3 1.5h3l2 2h4.5A1.5 1.5 0 0 1 14 5v7.5a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 2 12.5v-9z"/></svg>`

// ---- Per-file OCR state ---------------------------------------------------
// Which action we offer ("Send to OCR" vs "Re-OCR anyway") depends on what
// already happened to the file, and `enabled()` must answer synchronously —
// so we keep a small cache of the OCR service's view of each file and
// prefetch it for the rows currently on screen.
const STATE_REFRESH = 60 * 1000
// A file we processed can still be poked by something outside our pipeline
// (sync clients, Nextcloud internals) right after we finish, so a change
// within this window is not treated as a user edit.
const MTIME_SLACK = 900
const stateCache = new Map() // fileId -> { state, finished, ts }

const nodeMtime = (node) => {
	const m = node?.mtime
	if (!m) return 0
	const t = m instanceof Date ? Math.floor(m.getTime() / 1000) : Number(m)
	return Number.isFinite(t) ? t : 0
}

const stateOf = (node) => {
	const id = node?.fileid
	if (id == null) return 'unknown'
	const hit = stateCache.get(String(id))
	if (!hit) return 'never' // the OCR service has never seen this file
	const st = hit.state
	if ((st === 'done' || st === 'skipped') && hit.finished) {
		const mt = nodeMtime(node)
		if (mt && mt > hit.finished + MTIME_SLACK) return 'never'
	}
	return st
}
const rememberState = (fileId, state, finished = null) => {
	if (fileId != null) stateCache.set(String(fileId), { state, finished, ts: Date.now() })
}
// States that mean "this file was already handled by us".
const STATE_DONE = ['done', 'skipped']
// States where "Send to OCR" is still the right (or only) entry.
const STATE_FRESH = ['never', 'failed', 'unknown', 'error']

// One call fetches every file the OCR service knows about (a bounded set —
// only files it has processed). It has to happen before the list renders:
// `enabled()` is evaluated once per row and the Files app memoises the
// result, so a late answer would never reach the menu.
async function refreshAllStates() {
	try {
		const resp = await fetch(OC.generateUrl('/apps/ocrflow/api/filestates'), {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
				'requesttoken': OC.requestToken,
			},
			body: JSON.stringify({ all: true }),
		})
		const data = await resp.json()
		const states = (data?.ocs?.data ?? data)?.states ?? {}
		const now = Date.now()
		for (const [id, rec] of Object.entries(states)) {
			const prev = stateCache.get(id)
			// Keep our optimistic "queued" until the service reports the job.
			if (prev?.state === 'queued' && now - prev.ts < 90 * 1000) continue
			stateCache.set(id, {
				state: rec?.state ?? 'never',
				finished: rec?.finished ?? null,
				ts: now,
			})
		}
	} catch (e) {
		console.warn('[ocrflow] state refresh failed', e)
	}
}

if (typeof document !== 'undefined') {
	refreshAllStates()
	window.setInterval(refreshAllStates, STATE_REFRESH)
}

// Send to OCR: webhook decides whether OCR is actually needed
// (born-digital skip via pdf-inspector, recent-process guard).
// For deliberate re-OCRs, use the "Re-OCR anyway" action below.
// NOTE v4 signature: enabled/exec/execBatch receive a single ActionContext
// object { nodes, view, folder, contents }, NOT the array. Destructure it.
registerFileAction({
	id: 'ocrflow-send',
	displayName: () => t('ocrflow', 'Send to OCR'),
	iconSvgInline: () => OCR_ICON,
	enabled: ({ nodes }) =>
		nodes.every(isOcrable)
		// Offer the plain action only while the file has not been handled by
		// us yet; for a finished file the "Re-OCR anyway" entry is correct.
		&& nodes.every((nd) => STATE_FRESH.includes(stateOf(nd))),
	exec: async ({ nodes }) => {
		// Return a real boolean: NC shows a generic "<action>: failed" toast
		// when exec rejects or resolves false; we already show our own toast.
		const ok = await sendToOcr([nodes[0].fileid], 'auto', false)
		if (ok === true) rememberState(nodes[0].fileid, 'queued')
		return ok
	},
	execBatch: async ({ nodes }) => {
		const ok = await sendToOcr(nodes.map(nd => nd.fileid), 'auto', false)
		if (ok === true) nodes.forEach(nd => rememberState(nd.fileid, 'queued'))
		return nodes.map(() => ok === true)
	},
	order: -5,
})

// Re-OCR anyway — bypass the born-digital skip and recently
// processed guards. Single-file only (deliberate re-OCR is
// intentionally low-volume to avoid accidentally re-OCRing
// large selections).
registerFileAction({
	id: 'ocrflow-reocr-force',
	displayName: () => t('ocrflow', 'Re-OCR anyway'),
	iconSvgInline: () => OCR_ICON,
	enabled: ({ nodes }) =>
		nodes.length === 1 && nodes[0]?.fileid != null && nodes.every(isOcrable)
		// Only for files we already processed — otherwise "Send to OCR" is
		// the right entry and this one just confuses the menu.
		&& STATE_DONE.includes(stateOf(nodes[0])),
	exec: async ({ nodes }) => {
		const ok = await sendRescanForce(nodes[0].fileid, 'auto')
		if (ok === true) rememberState(nodes[0].fileid, 'queued')
		return ok
	},
	order: -4,
})

// Scan an entire folder (single/multi-select on folders).
registerFileAction({
	id: 'ocrflow-scan-folder',
	displayName: () => t('ocrflow', 'Scan folder (OCR)'),
	iconSvgInline: () => OCR_FOLDER_ICON,
	enabled: ({ nodes }) =>
		nodes.length === 1 && nodes[0]?.type === 'folder',
	exec: async ({ nodes }) => {
		const rel = nodes[0].path.replace(/^\/+/, '') // "/Work/1-Аренда" → "Work/1-Аренда"
		return await sendFolderToOcr(rel, 'auto')
	},
	order: -4,
})

// ---- Personal settings panel auto-refresher -------------------------------
// This bundle is injected as an init script on every page. When the OCR Flow
// personal settings panel is on the page (#ocrflow-panel), poll the status
// route and re-render the queue + history tables in place. No-op elsewhere.
const panelBasename = (p) => String(p ?? '').split('/').pop()
const panelTime = (ts) => {
	if (!ts) return ''
	try { return new Date(Number(ts) * 1000).toLocaleString() } catch { return '' }
}
const panelRow = (cells) => {
	const tr = document.createElement('tr')
	for (const c of cells) {
		const td = document.createElement('td')
		td.textContent = c
		tr.appendChild(td)
	}
	return tr
}
const panelFill = (tableId, jobs, numCols, cellFn, emptyText = '') => {
	const tbody = document.querySelector(`#${tableId} tbody`)
	if (!tbody) return
	tbody.replaceChildren()
	if (!jobs.length) {
		tbody.appendChild(panelRow([emptyText, ...Array(numCols - 1).fill('')]))
		return
	}
	for (const j of jobs) tbody.appendChild(panelRow(cellFn(j)))
}
function renderPanel(body) {
	const depth = document.getElementById('ocrflow-queue-depth')
	if (depth) depth.textContent = String(body?.queue_depth ?? 0)

	const active = [...(body?.running ?? []), ...(body?.queued ?? [])]
	panelFill('ocrflow-active', active, 2, (j) => [panelBasename(j.path), j.status ?? ''], '—')
	panelFill('ocrflow-history', body?.history ?? [], 3, (j) => [panelBasename(j.path), j.status ?? '', panelTime(j.finished)], '—')
}
function renderMetrics(m) {
	if (!m) return
	const set = (id, v) => {
		const el = document.getElementById(id)
		if (el) el.textContent = String(v ?? '—')
	}
	set('ocrflow-m-scan', m.scanned)
	set('ocrflow-m-remaining', m.remaining)
	set('ocrflow-m-skip', m.skipped)
	set('ocrflow-m-total', m.total)
	const eng = document.getElementById('ocrflow-m-engines')
	if (eng) {
		const parts = Object.entries(m.byEngine || {}).map(([k, n]) => `${k} (${n})`)
		eng.textContent = parts.length ? parts.join(', ') : '—'
	}
}
async function pollPanel() {
	try {
		const resp = await fetch(OC.generateUrl('/apps/ocrflow/api/status'), {
			headers: {
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
				'requesttoken': OC.requestToken,
			},
		})
		const data = await resp.json()
		const payload = data?.ocs?.data ?? data
		renderPanel(payload?.body ?? payload)

		const sresp = await fetch(OC.generateUrl('/apps/ocrflow/api/stats'), {
			headers: {
				'Accept': 'application/json',
				'OCS-APIRequest': 'true',
				'requesttoken': OC.requestToken,
			},
		})
		const sdata = await sresp.json()
		renderMetrics(sdata?.ocs?.data ?? sdata)
	} catch (e) {
		// transient — the next tick retries
	}
}
if (typeof document !== 'undefined') {
	const startPanel = () => {
		const panel = document.getElementById('ocrflow-panel')
		if (!panel || panel.dataset.ocrflowStarted) return
		panel.dataset.ocrflowStarted = '1'
		pollPanel()
		setInterval(pollPanel, 5000)
	}
	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', startPanel)
	} else {
		startPanel()
	}
}
