<?php
/**
 * Serves the Files context-menu action JS as a content-type-correct response.
 *
 * Route: GET /apps/ocrflow/action-script
 *
 * Nextcloud's Util::addScript() emits /apps/<app>/<file>. For apps installed
 * via NixOS `services.nextcloud.extraApps`, static files under /apps/<app>/js
 * resolve on the filesystem and 404 — only ROUTES resolve (they're registered
 * by name, not URL→filesystem). Serving the action JS from a route therefore
 * sidesteps the extraApps static-file URL quirk, and works on any hosting.
 *
 * We extend plain Controller (not OCSController) so DataResponse returns raw
 * bytes rather than an OCS-<ocs> envelope, which would corrupt the script.
 */
namespace OCA\OcrFlow\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\DataResponse;
use OCP\IRequest;

class PageController extends Controller {
    public function __construct(string $appName, IRequest $request) {
        parent::__construct($appName, $request);
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     */
    public function actionScript(): DataResponse {
        $file = dirname(__DIR__, 2) . '/js/ocr-action.js';
        $js = file_exists($file) ? (string)file_get_contents($file) : '// ocr-action.js missing';
        $resp = new DataResponse($js, 200);
        $resp->setHeaders([
            'Content-Type' => 'application/javascript; charset=utf-8',
            'Cache-Control' => 'no-cache, no-store, must-revalidate',
        ]);
        return $resp;
    }
}