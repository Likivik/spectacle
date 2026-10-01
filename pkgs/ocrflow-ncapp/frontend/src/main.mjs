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
import { registerFileAction, Node } from '@nextcloud/files'
import { translate as t, translatePlural as n } from '@nextcloud/l10n'

const OCRABLE_EXT = ['pdf', 'jpg', 'jpeg', 'png', 'webp', 'tiff', 'heic']

/**
 * @param {import('@nextcloud/files').Node} node
 * @return {boolean}
 */
function isOcrable(node) {
	if (!node || node.type !== Node.NodeType.File) return false
	const ext = (node.extension || node.basename.split('.').pop() || '').toLowerCase()
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
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify(body),
		})
		const data = await resp.json()
		// OCS wraps in { ocs: { data } }
		const payload = data?.ocs?.data ?? data
		const results = payload?.results ?? []
		const ok = results.filter(r => r.status === 'queued').length
		const bad = results.filter(r => r.status === 'error').length
		if (bad === 0) {
			OC.Notification.showTemporary(
				n('ocrflow',
					force ? 'File sent for re-OCR' : 'File sent for OCR',
					force ? '%n files sent for re-OCR' : '%n files sent for OCR', ok),
				{ type: 'success' }
			)
		} else {
			OC.Notification.showTemporary(
				t('ocrflow', 'OCR: %s sent, %s failed', [ok, bad]),
				{ type: 'error' }
			)
		}
	} catch (e) {
		console.error('[ocrflow] scan request failed', e)
		OC.Notification.showTemporary(t('ocrflow', 'Could not send for OCR'), { type: 'error' })
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
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify({ fileId, engine }),
		})
		const data = await resp.json()
		const payload = data?.ocs?.data ?? data
		if (payload?.error) {
			OC.Notification.showTemporary(t('ocrflow', 'Re-OCR failed: %s', [payload.error]), { type: 'error' })
			return
		}
		OC.Notification.showTemporary(t('ocrflow', 'File sent for re-OCR'), { type: 'success' })
	} catch (e) {
		console.error('[ocrflow] rescan-force failed', e)
		OC.Notification.showTemporary(t('ocrflow', 'Could not send for re-OCR'), { type: 'error' })
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
				'OCS-APIRequest': 'true',
			},
			body: JSON.stringify({ folder: folderPath, engine }),
		})
		const data = await resp.json()
		const payload = data?.ocs?.data ?? data
		if (payload?.error) {
			OC.Notification.showTemporary(t('ocrflow', 'Folder scan failed: %s', [payload.error]), { type: 'error' })
			return
		}
		const enq = payload?.enqueued ?? 0
		const skip = payload?.skipped_ocrd ?? 0
		OC.Notification.showTemporary(
			t('ocrflow', 'Folder queued for OCR: %s added, %s skipped (already OCR)', [enq, skip]),
			{ type: 'success' }
		)
	} catch (e) {
		console.error('[ocrflow] folder scan failed', e)
		OC.Notification.showTemporary(t('ocrflow', 'Could not scan folder'), { type: 'error' })
	}
}

// ---- NC 28+ Files API (@nextcloud/files ESM) ----

// Send to OCR: webhook decides whether OCR is actually needed
// (born-digital skip via pdf-inspector, recent-process guard).
// For deliberate re-OCRs, use the "Re-OCR anyway" action below.
registerFileAction({
	id: 'ocrflow-send',
	displayName: () => t('ocrflow', 'Send to OCR'),
	icon: () => 'icon-filetype-text',
	enabled: (nodes) => nodes.every(isOcrable),
	exec: async (node) => {
		await sendToOcr([node.fileid], 'auto', false)
		return null // stay in files list
	},
	execBulk: async (nodes) => {
		await sendToOcr(nodes.map(nd => nd.fileid), 'auto', false)
		return null
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
	icon: () => 'icon-history',
	enabled: (nodes) => nodes.length === 1 && nodes.every(isOcrable),
	exec: async (node) => {
		await sendRescanForce(node.fileid, 'auto')
		return null
	},
	order: -4,
})

// Scan an entire folder (single/multi-select on folders).
registerFileAction({
	id: 'ocrflow-scan-folder',
	displayName: () => t('ocrflow', 'Scan folder (OCR)'),
	icon: () => 'icon-folder',
	enabled: (nodes) =>
		nodes.length === 1 && nodes[0]?.type === Node.NodeType.Folder,
	exec: async (folder) => {
		const rel = folder.path.replace(/^\/+/, '') // "/Work/1-Аренда" → "Work/1-Аренда"
		await sendFolderToOcr(rel, 'auto')
		return null
	},
	order: -4,
})
