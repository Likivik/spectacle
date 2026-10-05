<?php
/**
 * Polls the nc-ocr-flow /status endpoint and raises a Nextcloud notification
 * (bell + mobile push) when a job finishes (done) or fails (error).
 *
 * The OCR service is asynchronous, so this is how the app learns outcomes.
 * Job ids already notified are tracked in app config (last_notified_job_id)
 * so a job is never announced twice.
 */
declare(strict_types=1);

namespace OCA\OcrFlow\BackgroundJob;

use OCA\OcrFlow\Service\WebhookClient;
use OCP\AppFramework\Utility\ITimeFactory;
use OCP\BackgroundJob\IJob;
use OCP\BackgroundJob\TimedJob;
use OCP\IConfig;
use OCP\Notification\IManager as INotificationManager;
use Psr\Log\LoggerInterface;

class PollOcrStatus extends TimedJob {
    private const LAST_ID_KEY = 'last_notified_job_id';

    public function __construct(
        ITimeFactory $time,
        private readonly WebhookClient $webhook,
        private readonly IConfig $config,
        private readonly INotificationManager $notifications,
        private readonly LoggerInterface $logger,
    ) {
        parent::__construct($time);
        // NC cron runs on a timer; 120s keeps notifications timely without
        // hammering the service.
        $this->setInterval(120);
        $this->setTimeSensitivity(IJob::TIME_INSENSITIVE);
    }

    protected function run($argument): void {
        $res = $this->webhook->status(50);
        if (!($res['ok'] ?? false)) {
            return;
        }
        $history = $res['body']['history'] ?? [];
        if (!is_array($history)) {
            return;
        }

        $last = (int)$this->config->getAppValue('ocrflow', self::LAST_ID_KEY, '0');
        $maxSeen = $last;

        foreach ($history as $job) {
            if (!is_array($job)) {
                continue;
            }
            $id = (int)($job['id'] ?? 0);
            if ($id <= $last) {
                continue;
            }
            $maxSeen = max($maxSeen, $id);

            $status = (string)($job['status'] ?? '');
            if ($status !== 'done' && $status !== 'error') {
                continue; // queued/running/skipped → nothing to announce
            }

            $path = (string)($job['path'] ?? '');
            $uid = $this->uidFromPath($path);
            if ($uid === null) {
                continue;
            }

            try {
                $notification = $this->notifications->createNotification();
                $notification
                    ->setApp('ocrflow')
                    ->setUser($uid)
                    ->setDateTime(new \DateTime())
                    ->setObject('ocrflow_job', (string)$id)
                    ->setSubject(
                        $status === 'done' ? 'ocr_done' : 'ocr_failed',
                        [
                            'file' => basename($path),
                            'path' => $path,
                            'reason' => (string)($job['reason'] ?? $job['error'] ?? ''),
                        ]
                    );
                $this->notifications->notify($notification);
            } catch (\Throwable $e) {
                $this->logger->warning(
                    'ocrflow: failed to raise notification for job ' . $id . ': ' . $e->getMessage(),
                    ['app' => 'ocrflow']
                );
            }
        }

        if ($maxSeen !== $last) {
            $this->config->setAppValue('ocrflow', self::LAST_ID_KEY, (string)$maxSeen);
        }
    }

    /** Map an NC-internal path (/<uid>/files/<rel>) to its owner uid. */
    private function uidFromPath(string $path): ?string {
        if (preg_match('#^/([^/]+)/files/#', $path, $m) === 1) {
            return $m[1];
        }
        return null;
    }
}
