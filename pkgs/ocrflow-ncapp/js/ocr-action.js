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
	 * POST selected files to the OCS endpoint.
	 * @param {number[]} fileIds
	 * @param {string} engine
	 */
	async function sendToOcr(fileIds, engine) {
		const url = OC.generateUrl('/apps/ocrflow/api/scan')
		try {
			const resp = await fetch(url, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					'requesttoken': OC.requestToken,
					'OCS-APIRequest': 'true',
				},
				body: JSON.stringify({ fileIds, engine }),
			})
			const data = await resp.json()
			// OCS wraps in { ocs: { data } }
			const payload = data?.ocs?.data ?? data
			const results = payload?.results ?? []
			const ok = results.filter(r => r.status === 'queued').length
			const bad = results.filter(r => r.status === 'error').length
			if (bad === 0) {
				OC.Notification.showTemporary(
					n('ocrflow', 'Файл отправлен на OCR', 'Файлов отправлено на OCR: %n', ok),
					{ type: 'success' }
				)
			} else {
				OC.Notification.showTemporary(
					t('ocrflow', 'OCR: отправлено {ok}, ошибок {bad}', { ok, bad }),
					{ type: 'error' }
				)
			}
		} catch (e) {
			console.error('[ocrflow] scan request failed', e)
			OC.Notification.showTemporary(t('ocrflow', 'Не удалось отправить на OCR'), { type: 'error' })
		}
	}

	// ---- NC 28+ Files API (viewer/cells) ----
	if (window.OCP?.Files?.registerFileAction) {
		OCP.Files.registerFileAction({
			id: 'ocrflow-send',
			displayName: () => t('ocrflow', 'Отправить на OCR'),
			icon: () => 'icon-filetype-text',
			// only files, not folders
			enabled: (nodes) => nodes.every(isOcrable),
			// single + bulk via the selection actions bar
			exec: async (file) => {
				await sendToOcr([file.fileid], 'auto')
				return null // stay in files list
			},
			execBulk: async (files) => {
				await sendToOcr(files.map(f => f.fileid), 'auto')
				return null
			},
			order: -5,
		})
	} else {
		console.warn('[ocrflow] OCP.Files.registerFileAction not available')
	}
})()
