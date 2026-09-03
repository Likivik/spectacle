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
     * Body: { "fileIds": [123, 456], "engine": "auto"|"tesseract"|"vlm" }
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
        $engine = in_array($body['engine'] ?? 'auto', ['auto', 'tesseract', 'vlm'], true)
            ? $body['engine'] ?? 'auto' : 'auto';

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

            $res = $this->webhook->enqueue($ncPath, (int)$fileId, $engine);
            $results[] = array_merge(
                ['fileId' => $fileId, 'path' => $ncPath],
                $res
            );
        }

        return ['results' => $results];
    }
}
