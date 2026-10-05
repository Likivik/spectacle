<?php

declare(strict_types=1);

namespace OCA\OcrFlow\Service;

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
        // Written to config.php by config:system:set ocrflow_url (see
        // workflow-ocr default.nix); fall back to localhost.
        $url = $this->config->getSystemValue('ocrflow_url', '');
        if ($url === '') {
            $url = 'http://127.0.0.1:8095';
        }
        return rtrim($url, '/');
    }

    public function secret(): string
    {
        // config.php key is ocrflow_secret (config:system:set), NOT the
        // oc_appconfig webhook_secret.  getSystemValue reads config.php.
        return (string)$this->config->getSystemValue('ocrflow_secret', '');
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

    /**
     * Aggregate OCR metrics from the service's durable index
     * (scanned / skipped / per-engine breakdown).
     */
    public function stats(): array
    {
        return $this->get('/stats');
    }

    /**
     * Per-file OCR state (queued|running|done|skipped|error) for NC-internal
     * paths. Drives which Files action is offered for a file.
     *
     * Sent as repeated ``paths=`` params: FastAPI parses a list query that
     * way, and does not understand PHP's ``paths[0]=`` array notation.
     *
     * @param string[] $paths
     * @param bool $all  true → the whole index (keyed by NC path). Used by the
     *                   Files actions: they must know the state of every file
     *                   before the list renders, not just the visible rows.
     */
    public function states(array $paths = [], bool $all = false): array
    {
        if ($all) {
            return $this->getRaw('/states', 'all=1');
        }
        $paths = array_values(array_filter(
            array_map(static fn ($p) => (string)$p, $paths),
            static fn ($p) => $p !== ''
        ));
        if (count($paths) === 0) {
            return ['ok' => true, 'status' => 200, 'body' => ['states' => []]];
        }
        $query = implode('&', array_map(
            static fn ($p) => 'paths=' . rawurlencode($p),
            $paths
        ));
        return $this->getRaw('/states', $query);
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
        return $this->getRaw($path, $query ? http_build_query($query) : '');
    }

    /** GET with a pre-built query string (for repeated params). */
    private function getRaw(string $path, string $queryString = ''): array
    {
        $url = $this->baseUrl() . $path;
        if ($queryString !== '') {
            $url .= '?' . $queryString;
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