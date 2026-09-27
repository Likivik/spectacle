<?php

declare(strict_types=1);

namespace OCA\OcrFlow\Service;

use OCA\OcrFlow\AppInfo\AppInfo;
use OCP\Http\Client\IClientService;
use OCP\IConfig;
use Psr\Log\LoggerInterface;

/**
 * Client for the nc-ocr-flow webhook service.
 *
 * Forwards "Send to OCR" / "Scan folder" calls to the FastAPI webhook
 * running on the same host, on port 8095 by default.
 */
final class WebhookClient
{
    public function __construct(
        private readonly IConfig $config,
        private readonly IClientService $clientService,
        private readonly LoggerInterface $logger,
    ) {}

    public function baseUrl(): string
    {
        $url = $this->config->getAppValue(AppInfo::APP_ID, 'webhook_url', '');
        if ($url === '') {
            $url = 'http://127.0.0.1:8095';
        }
        return rtrim($url, '/');
    }

    public function secret(): string
    {
        return $this->config->getAppValue(AppInfo::APP_ID, 'webhook_secret', '');
    }

    /**
     * Queue a single file (or folder, the webhook resolves) for OCR.
     *
     * @param string $ncPath   NC-internal path (e.g. /<user>/files/<rel>)
     * @param int    $nodeId   NC fileId (0 if unknown)
     * @param string $engine   google|tesseract|minimax|auto
     * @param bool   $force    bypass the born-digital skip decision AND
     *                         the recently-processed guard. The
     *                         "Re-OCR anyway" action sends force=true
     *                         so the user can deliberately re-OCR a
     *                         file we previously stamped or classified.
     */
    public function enqueue(
        string $ncPath,
        int $nodeId = 0,
        string $engine = 'auto',
        bool $force = false,
    ): array {
        $payload = [
            'event' => [
                'class' => 'OCP\\Files\\Events\\Node\\NodeWrittenEvent',
                'node' => [
                    'id'   => $nodeId,
                    'path' => $ncPath,
                ],
            ],
            'force' => $force,
        ];

        return $this->post('/webhook', $payload);
    }

    /**
     * Trigger an engine override re-OCR (panel action).
     *
     * @param bool $force bypass the born-digital skip decision
     */
    public function rescan(
        string $ncPath,
        int $nodeId,
        string $engine,
        bool $force = false,
    ): array {
        $payload = [
            'path'    => $ncPath,
            'node_id' => $nodeId,
            'engine'  => $engine,
            'force'   => $force,
        ];

        return $this->post('/rescan', $payload);
    }

    /**
     * Scan a folder: forward to the webhook's /scan-all, which PROPFINDs
     * the folder and enqueues every processable file inside.
     *
     * @param string $folder   relative folder path ("" = whole storage)
     * @param string|null $engine  google|tesseract|minimax; null → env
     */
    public function scanFolder(string $folder, ?string $engine = null): array
    {
        $payload = [
            'folder' => $folder,
        ];
        if ($engine !== null) {
            $payload['engine'] = $engine;
        }
        return $this->post('/scan-all', $payload);
    }

    /** Get the webhook's job-queue snapshot for the panel. */
    public function status(int $limit = 50): array
    {
        return $this->get('/status', ['limit' => $limit]);
    }

    private function post(string $path, array $payload): array
    {
        $url = $this->baseUrl() . $path;
        try {
            $client = $this->clientService->newClient();
            $resp = $client->post($url, [
                'headers' => $this->headers(),
                'body'    => json_encode($payload, JSON_THROW_ON_ERROR),
                'timeout' => 5,
            ]);
            return ['ok' => true, 'status' => $resp->getStatusCode(),
                    'body' => json_decode((string)$resp->getBody(), true)];
        } catch (\Throwable $e) {
            $this->logger->error('WebhookClient POST failed: ' . $e->getMessage(),
                ['url' => $url, 'payload' => $payload]);
            return ['ok' => false, 'error' => $e->getMessage()];
        }
    }

    private function get(string $path, array $query = []): array
    {
        $url = $this->baseUrl() . $path;
        if ($query) {
            $url .= '?' . http_build_query($query);
        }
        try {
            $client = $this->clientService->newClient();
            $resp = $client->get($url, [
                'headers' => $this->headers(),
                'timeout' => 5,
            ]);
            return ['ok' => true, 'status' => $resp->getStatusCode(),
                    'body' => json_decode((string)$resp->getBody(), true)];
        } catch (\Throwable $e) {
            $this->logger->error('WebhookClient GET failed: ' . $e->getMessage(),
                ['url' => $url]);
            return ['ok' => false, 'error' => $e->getMessage()];
        }
    }

    private function headers(): array
    {
        $h = [
            'Content-Type' => 'application/json',
            'Accept'       => 'application/json',
        ];
        $secret = $this->secret();
        if ($secret !== '') {
            $h['X-Webhook-Secret'] = $secret;
        }
        return $h;
    }
}