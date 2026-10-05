<?php
/**
 * OCS controller: receives file IDs from the JS FileAction, resolves them to
 * NC-internal paths, and forwards to the nc-ocr-flow webhook service.
 * The webhook secret lives in system config — never exposed to the browser.
 */
namespace OCA\OcrFlow\Controller;

use OCA\OcrFlow\Service\FileStateService;
use OCA\OcrFlow\Service\StatsService;
use OCA\OcrFlow\Service\WebhookClient;
use OCP\AppFramework\Http\DataResponse;
use OCP\AppFramework\OCSController;
use OCP\Files\IRootFolder;
use OCP\IRequest;
use OCP\IUserSession;

class OcrController extends OCSController {
    private IRootFolder $rootFolder;
    private IUserSession $userSession;
    private WebhookClient $webhook;
    private StatsService $statsService;
    private FileStateService $fileStateService;

    public function __construct(
        string $appName,
        IRequest $request,
        IRootFolder $rootFolder,
        IUserSession $userSession,
        WebhookClient $webhook,
        StatsService $statsService,
        FileStateService $fileStateService,
    ) {
        parent::__construct($appName, $request);
        $this->rootFolder = $rootFolder;
        $this->userSession = $userSession;
        $this->webhook = $webhook;
        $this->statsService = $statsService;
        $this->fileStateService = $fileStateService;
    }

    /**
     * Read the raw request body (JSON) and decode it.
     * @return array<string, mixed>
     */
    private function parseBody(): array {
        $raw = (string)file_get_contents('php://input');
        $decoded = json_decode($raw, true);
        return is_array($decoded) ? $decoded : [];
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Body: { "fileIds": [123, 456], "engine": "google"|"tesseract"|"minimax", "force": bool? }
     * Returns: { results: [{ fileId, path, status, jobId?|error? }] }
     */
    public function scan(): DataResponse {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return new DataResponse(['results' => [], 'error' => 'not logged in']);
        }

        $body = $this->parseBody();
        $fileIds = $body['fileIds'] ?? [];
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'google', 'tesseract', 'minimax'], true)
            ? $body['engine'] ?? 'auto' : 'auto';
        // ``force`` is opt-in: the regular "Send to OCR" action leaves
        // it false (webhook decides whether OCR is needed); the
        // "Re-OCR anyway" action calls the dedicated /rescanForce
        // endpoint below with force=true.
        $force = filter_var($body['force'] ?? false, FILTER_VALIDATE_BOOLEAN);

        if (!is_array($fileIds) || count($fileIds) === 0) {
            return new DataResponse(['results' => [], 'error' => 'fileIds required']);
        }
        if (count($fileIds) > 100) {
            return new DataResponse(['results' => [], 'error' => 'too many files (max 100 per request)']);
        }

        $userFolder = $this->rootFolder->getUserFolder($userId);
        $results = [];

        foreach ($fileIds as $fileId) {
            $nodes = $userFolder->getById((int)$fileId);
            if (count($nodes) === 0) {
                $results[] = ['fileId' => $fileId, 'status' => 'error', 'error' => 'not found'];
                continue;
            }
            $node = $nodes[0];
            if ($node instanceof \OCP\Files\Folder) {
                $results[] = ['fileId' => $fileId, 'status' => 'error', 'error' => 'is a folder'];
                continue;
            }

            $relPath = $userFolder->getRelativePath($node->getPath());
            // NC-internal path format expected by the webhook: /<user>/files/<rel>
            $ncPath = '/' . $userId . '/files/' . ltrim($relPath, '/');

            $res = $this->webhook->enqueue($ncPath, (int)$fileId, $engine, $force);
            $results[] = array_merge(
                ['fileId' => $fileId, 'path' => $ncPath],
                $res
            );
        }

        return new DataResponse(['results' => $results]);
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * "Re-OCR anyway" action: deliberately re-OCR a single file, bypassing
     * the born-digital skip decision AND the recently-processed guard.
     *
     * Body: { "fileId": 123, "engine": "google"|"tesseract"|"minimax" }
     */
    public function rescanForce(): DataResponse {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return new DataResponse(['error' => 'not logged in']);
        }

        $body = $this->parseBody();
        $fileId = (int)($body['fileId'] ?? 0);
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'google', 'tesseract', 'minimax'], true)
            ? $body['engine'] ?? 'auto' : 'auto';

        if ($fileId <= 0) {
            return new DataResponse(['error' => 'fileId required']);
        }

        $userFolder = $this->rootFolder->getUserFolder($userId);
        $nodes = $userFolder->getById($fileId);
        if (count($nodes) === 0) {
            return new DataResponse(['error' => 'file not found']);
        }
        $node = $nodes[0];
        if ($node instanceof \OCP\Files\Folder) {
            return new DataResponse(['error' => 'is a folder']);
        }

        $relPath = $userFolder->getRelativePath($node->getPath());
        $ncPath = '/' . $userId . '/files/' . ltrim($relPath, '/');

        // force=true is the whole point of this endpoint.
        $res = $this->webhook->rescan($ncPath, $fileId, $engine, /*force=*/true);
        return new DataResponse(['job' => $res['body'] ?? null, 'force' => true]);
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Folder scan: forward the folder path to the webhook's /scan-all, which
     * PROPFINDs it and enqueues every processable file inside.
     * Body: { "folder": "Work/1-Аренда", "engine": ... } ("" = whole storage)
     */
    public function scanFolder(): DataResponse {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return new DataResponse(['error' => 'not logged in']);
        }

        $body = $this->parseBody();
        $folder = trim((string)($body['folder'] ?? ''));
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'google', 'tesseract', 'minimax'], true)
            ? $body['engine'] ?? 'auto' : 'auto';

        // Only allow folders inside this user's storage (no traversal)
        if ($folder !== '' && (str_contains($folder, '..') || str_starts_with($folder, '/'))) {
            return new DataResponse(['error' => 'invalid folder']);
        }

        return new DataResponse($this->webhook->scanFolder($folder, $engine === 'auto' ? null : $engine));
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Live OCR queue + history for the personal settings panel.
     * Proxies the nc-ocr-flow /status endpoint (the secret stays server-side).
     */
    public function status(): DataResponse {
        if ($this->userSession->getUser() === null) {
            return new DataResponse(['error' => 'not logged in']);
        }
        return new DataResponse($this->webhook->status(25));
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Aggregate OCR metrics for the personal settings panel:
     * files scanned / remaining / skipped and the per-engine breakdown.
     */
    public function stats(): DataResponse {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return new DataResponse(['error' => 'not logged in']);
        }
        return new DataResponse($this->statsService->collect($userId));
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Per-file OCR state for the Files actions: decides whether "Send to OCR"
     * or "Re-OCR anyway" is the right entry for each file.
     *
     * Body: { "fileIds": [123, 456] }
     * Returns: { states: { "<fileId>": { state, engine?, reason?, finished? } } }
     * where state ∈ never | queued | running | done | skipped | error | failed.
     */
    public function filestates(): DataResponse {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return new DataResponse(['states' => [], 'error' => 'not logged in']);
        }

        $body = $this->parseBody();

        // The Files actions ask for the whole map once per page load: they
        // must answer synchronously while the list renders, and a per-row
        // fetch always lands too late (the Files app memoises `enabled`).
        if (!empty($body['all'])) {
            return new DataResponse(['states' => $this->fileStateService->allStates()]);
        }

        $fileIds = $body['fileIds'] ?? [];
        if (!is_array($fileIds) || count($fileIds) === 0) {
            return new DataResponse(['states' => []]);
        }
        if (count($fileIds) > 200) {
            $fileIds = array_slice($fileIds, 0, 200);
        }

        return new DataResponse(['states' => $this->fileStateService->statesFor($userId, $fileIds)]);
    }
}
