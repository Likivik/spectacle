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
    ],
];
