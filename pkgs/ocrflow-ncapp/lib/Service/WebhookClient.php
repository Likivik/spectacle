<?php
/**
 * Thin HTTP client for the nc-ocr-flow webhook (runs on the same host, :8095).
 * Secret read from system config — never leaves the server.
 */
namespace OCA\OcrFlow\Service;

use OCP\IConfig;
use Psr\Log\LoggerInterface;

class WebhookClient {
    private IConfig $config;
    private LoggerInterface $logger;

    public function __construct(IConfig $config, LoggerInterface $logger) {
        $this->config = $config;
        $this->logger = $logger;
    }

    private function baseUrl(): string {
        return rtrim($this->config->getSystemValue('ocrflow_url', 'http://127.0.0.1:8095'), '/');
    }

    private function secret(): string {
        return (string)$this->config->getSystemValue('ocrflow_secret', '');
    }

    /**
     * Enqueue one file for OCR.
     * @return array ['status' => 'queued', 'jobId' => int] or ['status' => 'error', 'error' => string]
     */
    public function enqueue(string $ncPath, int $nodeId, string $engine = 'auto'): array {
        $payload = json_encode([
            'event' => [
                'class' => 'OCP\\Files\\Events\\Node\\NodeCreatedEvent',
                'node' => ['id' => $nodeId, 'path' => $ncPath],
            ],
            'rescan' => true,      // bypass recently_processed guard on the service side
            'engine' => $engine,
            'time' => time(),
        ]);

        $ch = curl_init($this->baseUrl() . '/webhook');
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'X-Webhook-Secret: ' . $this->secret(),
            ],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 30,
        ]);
        $resp = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr = curl_error($ch);
        curl_close($ch);

        if ($resp === false || $httpCode !== 200) {
            $this->logger->warning('ocrflow: webhook failed', [
                'path' => $ncPath, 'http' => $httpCode, 'curl' => $curlErr,
            ]);
            return ['status' => 'error', 'error' => "webhook unavailable (HTTP $httpCode)"];
        }

        $data = json_decode($resp, true);
        if (!is_array($data) || ($data['status'] ?? '') !== 'queued') {
            return ['status' => 'error', 'error' => 'unexpected webhook response: ' . substr($resp, 0, 200)];
        }

        return ['status' => 'queued', 'jobId' => $data['job_id'] ?? 0];
    }

    /**
     * Re-OCR a file from its pristine (first/original upload) version.
     * The webhook downloads that version, OCRs it, and writes the result back
     * to the current path as a new version — leaving the bad layer behind.
     * @return array ['status' => 'queued', 'jobId' => int] or error
     */
    public function rescanPristine(string $ncPath, int $nodeId, string $engine = 'auto'): array {
        return $this->postRescan($ncPath, $nodeId, $engine, 'pristine');
    }

    private function postRescan(string $ncPath, int $nodeId, string $engine, ?string $source): array {
        $payload = json_encode([
            'path' => $ncPath,
            'node_id' => $nodeId,
            'engine' => $engine === 'auto' ? null : $engine,
            'source' => $source,
            'time' => time(),
        ]);

        $ch = curl_init($this->baseUrl() . '/rescan');
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'X-Webhook-Secret: ' . $this->secret(),
            ],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 30,
        ]);
        $resp = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr = curl_error($ch);
        curl_close($ch);

        if ($resp === false || $httpCode !== 200) {
            $this->logger->warning('ocrflow: rescan failed', [
                'path' => $ncPath, 'http' => $httpCode, 'curl' => $curlErr,
            ]);
            return ['status' => 'error', 'error' => "webhook unavailable (HTTP $httpCode)"];
        }

        $data = json_decode($resp, true);
        if (!is_array($data) || ($data['status'] ?? '') !== 'queued') {
            return ['status' => 'error', 'error' => 'unexpected webhook response: ' . substr($resp, 0, 200)];
        }

        return ['status' => 'queued', 'jobId' => $data['job_id'] ?? 0];
    }

    /**
     * Enqueue every processable file under a folder ("" = whole storage).
     * Delegates to the webhook's /scan-all, which PROPFINDs the folder.
     * @return array ['enqueued' => int, 'skipped_ocrd' => int] or ['error' => string]
     */
    public function scanFolder(string $folder, ?string $engine = null): array {
        $payload = json_encode([
            'folder' => $folder,
            'engine' => $engine,
            'skip_ocrd' => true,
            'time' => time(),
        ]);

        $ch = curl_init($this->baseUrl() . '/scan-all');
        curl_setopt_array($ch, [
            CURLOPT_POST => true,
            CURLOPT_POSTFIELDS => $payload,
            CURLOPT_HTTPHEADER => [
                'Content-Type: application/json',
                'X-Webhook-Secret: ' . $this->secret(),
            ],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT => 30,
        ]);
        $resp = curl_exec($ch);
        $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $curlErr = curl_error($ch);
        curl_close($ch);

        if ($resp === false || $httpCode !== 200) {
            $this->logger->warning('ocrflow: scan-folder failed', [
                'folder' => $folder, 'http' => $httpCode, 'curl' => $curlErr,
            ]);
            return ['error' => "webhook unavailable (HTTP $httpCode)"];
        }

        $data = json_decode($resp, true);
        if (!is_array($data)) {
            return ['error' => 'unexpected webhook response: ' . substr($resp, 0, 200)];
        }

        return [
            'enqueued' => $data['enqueued'] ?? 0,
            'skipped_ocrd' => $data['skipped_ocrd'] ?? 0,
        ];
    }
}
