<?php
/**
 * Personal settings page: live OCR queue, scan metrics and history.
 *
 * Renders a server-side snapshot (works with JS disabled) and exposes the
 * queue/history/metrics to a small auto-refresher in the bundled JS
 * (frontend/src/main.mjs) which polls /apps/ocrflow/api/{status,stats}.
 */
namespace OCA\OcrFlow\Settings;

use OCA\OcrFlow\Service\StatsService;
use OCA\OcrFlow\Service\WebhookClient;
use OCP\AppFramework\Http\TemplateResponse;
use OCP\IConfig;
use OCP\IL10N;
use OCP\IUserSession;
use OCP\Settings\ISettings;

class Personal implements ISettings {
    public function __construct(
        private readonly IConfig $config,
        private readonly IL10N $l,
        private readonly IUserSession $userSession,
        private readonly WebhookClient $webhook,
        private readonly StatsService $statsService,
    ) {}

    public function getForm(): TemplateResponse {
        $status = $this->webhook->status(25);
        $data = ($status['ok'] ?? false) && is_array($status['body'] ?? null)
            ? $status['body'] : [];

        $uid = $this->userSession->getUser()?->getUID();
        $metrics = $uid !== null ? $this->statsService->collect($uid) : [];

        $parameters = [
            'service_ok' => (bool)($status['ok'] ?? false),
            'service_error' => $status['error'] ?? null,
            'queue_depth' => $data['queue_depth'] ?? 0,
            'queued' => $data['queued'] ?? [],
            'running' => $data['running'] ?? [],
            'history' => $data['history'] ?? [],
            'metrics' => $metrics,
            'my_uid' => $uid,
            'ocrflow_url' => $this->config->getSystemValue('ocrflow_url', 'http://127.0.0.1:8095'),
        ];
        return new TemplateResponse('ocrflow', 'personal', $parameters);
    }

    public function getSection(): string {
        return 'ocrflow';
    }

    public function getPriority(): int {
        return 50;
    }
}
