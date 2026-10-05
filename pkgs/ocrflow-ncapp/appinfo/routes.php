<?php
/**
 * OCR Flow — Nextcloud app routes.
 *
 * API endpoints (OCS, session-authenticated):
 *  - POST /api/scan          — send selected files/folder for OCR
 *  - POST /api/scan-folder   — scan every eligible file in a folder
 *  - POST /api/rescan-force  — force re-OCR even if stamped/classified no-OCR
 */
return [
    'routes' => [
        ['name' => 'ocr#scan', 'url' => '/api/scan', 'verb' => 'POST'],
        ['name' => 'ocr#scanFolder', 'url' => '/api/scan-folder', 'verb' => 'POST'],
        ['name' => 'ocr#rescanForce', 'url' => '/api/rescan-force', 'verb' => 'POST'],
        // GET /api/status — live queue + history (proxied from the OCR
        // service; used by the personal settings panel auto-refresher).
        ['name' => 'ocr#status', 'url' => '/api/status', 'verb' => 'GET'],
        // GET /api/stats — aggregate metrics (scanned/remaining/by engine).
        ['name' => 'ocr#stats', 'url' => '/api/stats', 'verb' => 'GET'],
        // POST /api/filestates — per-file OCR state, so the Files actions can
        // show exactly one of "Send to OCR" / "Re-OCR anyway".
        ['name' => 'ocr#filestates', 'url' => '/api/filestates', 'verb' => 'POST'],
    ],
];
