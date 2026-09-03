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
}
