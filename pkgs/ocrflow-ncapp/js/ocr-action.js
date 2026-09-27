/**
 * OCR Flow — Files context menu action.
 *
 * Adds "Send to OCR" to single-file context menus and bulk-selection actions
 * bar. NC 28+ Files FileAction API, vanilla JS (loaded via info.xml scripts).
 *
 * API: POST /apps/ocrflow/api/scan  { fileIds: [...], engine }
 * Auth: Nextcloud session cookie (CSRF token via OC.requestToken).
 */
(function () {
	'use strict'

	const APP_ID = 'ocrflow'

	/**
	 * @param {object} file the file object from NC
	 * @return {boolean}
	 */
	function isOcrable(file) {
		if (!file || file.type !== 'file') return false
		const ext = (file.extension || file.basename?.split('.').pop() || '').toLowerCase()
		return ['.pdf', '.jpg', '.jpeg', '.png', '.webp', '.tiff', '.heic'].includes('.' + ext)
	}

	/**
	 * POST a scan request for the given fileIds to the OCS endpoint.
	 * @param {number[]} fileIds
	 * @param {string} engine
	 * @param {string|null} source 'pristine' to re-OCR from the original upload
	 */
	async function sendToOcr(fileIds, source, engine) {
		const url = OC.generateUrl('/apps/ocrflow/api/scan')
		const body = { fileIds, engine }
		if (source) body.source = source
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
						// TRANSLATORS: the singular/plural is keyed off `ok` (count of queued files)
						n('ocrflow',
							source === 'pristine'
								? 'File sent for re-OCR (from original)'
								: 'File sent for OCR',
							source === 'pristine'
								? '%n files sent for re-OCR (from original)'
								: '%n files sent for OCR', ok),
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
	 * POST a folder-scan request (whole folder, not a file).
	 * @param {string} folderPath the NC path relative to the user's files, e.g. "Work/1-Аренда"
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

	// ---- NC 28+ Files API (viewer/cells) ----
	if (window.OCP?.Files?.registerFileAction) {
		OCP.Files.registerFileAction({
			id: 'ocrflow-send',
			displayName: () => t('ocrflow', 'Send to OCR'),
			icon: () => 'icon-filetype-text',
			// only files, not folders
			enabled: (nodes) => nodes.every(isOcrable),
			// single + bulk via the selection actions bar
			exec: async (file) => {
				await sendToOcr([file.fileid], null, 'auto')
				return null // stay in files list
			},
			execBulk: async (files) => {
				await sendToOcr(files.map(f => f.fileid), null, 'auto')
				return null
			},
			order: -5,
		})

		// Re-OCR a file from its original (pristine) upload — fixes bad text
		// layers by OCR-ing the first version and writing a new version back.
		OCP.Files.registerFileAction({
			id: 'ocrflow-reocr-pristine',
			displayName: () => t('ocrflow', 'Re-OCR from original'),
			icon: () => 'icon-history',
			enabled: (nodes) => nodes.every(isOcrable),
			exec: async (file) => {
				await sendToOcr([file.fileid], 'pristine', 'auto')
				return null
			},
			order: -4,
		})

		// Scan an entire folder (single/multi-select on folders).
		OCP.Files.registerFileAction({
			id: 'ocrflow-scan-folder',
			displayName: () => t('ocrflow', 'Scan folder (OCR)'),
			icon: () => 'icon-folder',
			enabled: (nodes) =>
				nodes.length === 1 && nodes[0]?.type === 'folder',
			exec: async (folder) => {
				const rel = folder.path.replace(/^\/+/, '') // "/Work/1-Аренда" → "Work/1-Аренда"
				await sendFolderToOcr(rel, 'auto')
				return null
			},
			order: -4,
		})
	} else {
		console.warn('[ocrflow] OCP.Files.registerFileAction not available')
	}
})()
