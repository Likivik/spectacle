<?php
/**
 * OCR metrics for the settings panel.
 *
 * Combines two sources:
 *  - the nc-ocr-flow service's durable index (files we OCR'd, split by
 *    engine, plus the ones we deliberately skipped),
 *  - Nextcloud itself for the denominator — the total number of OCR-able
 *    files in the user's space (only NC knows the file tree).
 *
 * The tree count is cached in app config for {TTL}s because searchByMime
 * walks the file cache and we don't want to do that on every panel poll.
 */
namespace OCA\OcrFlow\Service;

use OCP\Files\IRootFolder;
use OCP\IConfig;

class StatsService {
    /** Mimetypes the OCR pipeline can process (mirrors the frontend whitelist). */
    private const OCR_MIMES = [
        'application/pdf',
        'image/jpeg',
        'image/png',
        'image/webp',
        'image/tiff',
        'image/heic',
    ];

    private const TTL = 900; // seconds

    public function __construct(
        private readonly WebhookClient $webhook,
        private readonly IRootFolder $rootFolder,
        private readonly IConfig $config,
    ) {}

    /**
     * @return array<string, mixed>
     */
    public function collect(string $userId): array {
        $service = $this->webhook->stats();
        $body = is_array($service['body'] ?? null) ? $service['body'] : [];

        $scanned = (int)($body['scanned'] ?? 0);
        $skipped = (int)($body['skipped'] ?? 0);
        $total = $this->countOcrable($userId);

        return [
            'serviceOk' => (bool)($service['ok'] ?? false),
            'total' => $total,
            'scanned' => $scanned,
            'skipped' => $skipped,
            'remaining' => max(0, $total - $scanned - $skipped),
            'byEngine' => is_array($body['by_engine'] ?? null) ? $body['by_engine'] : [],
            'skipReasons' => is_array($body['skip_reasons'] ?? null) ? $body['skip_reasons'] : [],
        ];
    }

    private function countOcrable(string $userId): int {
        $key = 'ocrable_total_' . $userId;
        $cached = (string)$this->config->getAppValue('ocrflow', $key, '');
        if ($cached !== '') {
            $parts = explode(':', $cached, 2);
            if (count($parts) === 2 && (time() - (int)$parts[1]) < self::TTL) {
                return (int)$parts[0];
            }
        }

        $total = 0;
        try {
            $folder = $this->rootFolder->getUserFolder($userId);
            foreach (self::OCR_MIMES as $mime) {
                try {
                    $total += count($folder->searchByMime($mime));
                } catch (\Throwable $e) {
                    // a single mimetype failing must not blank the metric
                }
            }
        } catch (\Throwable $e) {
            return 0;
        }

        $this->config->setAppValue('ocrflow', $key, $total . ':' . time());
        return $total;
    }
}
