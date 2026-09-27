<?php
/**
 * OCS API routes: /apps/ocrflow/api/scan
 */
return [
    'routes' => [
        ['name' => 'ocr#scan', 'url' => '/api/scan', 'verb' => 'POST'],
        ['name' => 'ocr#scanFolder', 'url' => '/api/scan-folder', 'verb' => 'POST'],
    ],
];
