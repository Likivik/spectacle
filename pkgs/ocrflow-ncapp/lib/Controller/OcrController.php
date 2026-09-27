<?php
/**
 * OCS controller: receives file IDs from the JS FileAction, resolves them to
 * NC-internal paths, and forwards to the nc-ocr-flow webhook service.
 * The webhook secret lives in system config — never exposed to the browser.
 */
namespace OCA\OcrFlow\Controller;

use OCA\OcrFlow\Service\WebhookClient;
use OCP\AppFramework\OCSController;
use OCP\Files\IRootFolder;
use OCP\IRequest;
use OCP\IUserSession;

class OcrController extends OCSController {
    private IRootFolder $rootFolder;
    private IUserSession $userSession;
    private WebhookClient $webhook;

    public function __construct(
        string $appName,
        IRequest $request,
        IRootFolder $rootFolder,
        IUserSession $userSession,
        WebhookClient $webhook,
    ) {
        parent::__construct($appName, $request);
        $this->rootFolder = $rootFolder;
        $this->userSession = $userSession;
        $this->webhook = $webhook;
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Body: { "fileIds": [123, 456], "engine": "google"|"tesseract"|"minimax", "source": "pristine"? }
     * Returns: { results: [{ fileId, path, status, jobId?|error? }] }
     */
    public function scan(): array {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return ['results' => [], 'error' => 'not logged in'];
        }

        $body = json_decode($this->request->getParam('body', '{}'), true)
            ?? $this->request->getParams();
        $fileIds = $body['fileIds'] ?? [];
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'google', 'tesseract', 'minimax'], true)
            ? $body['engine'] ?? 'auto' : 'auto';
        $source = ($body['source'] ?? null) === 'pristine' ? 'pristine' : null;

        if (!is_array($fileIds) || count($fileIds) === 0) {
            return ['results' => [], 'error' => 'fileIds required'];
        }
        if (count($fileIds) > 100) {
            return ['results' => [], 'error' => 'too many files (max 100 per request)'];
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

            if ($source === 'pristine') {
                // node_id = NC fileId is required to address the versions DAV node
                $res = $this->webhook->rescanPristine($ncPath, (int)$fileId, $engine);
            } else {
                $res = $this->webhook->enqueue($ncPath, (int)$fileId, $engine);
            }
            $results[] = array_merge(
                ['fileId' => $fileId, 'path' => $ncPath],
                $res
            );
        }

        return ['results' => $results];
    }

    /**
     * @NoCSRFRequired
     * @NoAdminRequired
     *
     * Folder scan: forward the folder path to the webhook's /scan-all, which
     * PROPFINDs it and enqueues every processable file inside.
     * Body: { "folder": "Work/1-Аренда", "engine": ... } ("" = whole storage)
     */
    public function scanFolder(): array {
        $userId = $this->userSession->getUser()?->getUID();
        if ($userId === null) {
            return ['error' => 'not logged in'];
        }

        $body = json_decode($this->request->getParam('body', '{}'), true)
            ?? $this->request->getParams();
        $folder = trim((string)($body['folder'] ?? ''));
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'google', 'tesseract', 'minimax'], true)
            ? $body['engine'] ?? 'auto' : 'auto';

        // Only allow folders inside this user's storage (no traversal)
        if ($folder !== '' && (str_contains($folder, '..') || str_starts_with($folder, '/'))) {
            return ['error' => 'invalid folder'];
        }

        return $this->webhook->scanFolder($folder, $engine === 'auto' ? null : $engine);
    }
}
