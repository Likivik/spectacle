<?php
/**
 * Notification presenter for OCR Flow job outcomes.
 *
 * Notifications are created by the PollOcrStatus background job (the OCR
 * service is asynchronous — PHP only learns the outcome by polling /status).
 */
declare(strict_types=1);

namespace OCA\OcrFlow\Notification;

use OCP\IURLGenerator;
use OCP\L10N\IFactory;
use OCP\Notification\INotification;
use OCP\Notification\INotifier;
use OCP\Notification\UnknownNotificationException;

class Notifier implements INotifier {
    public function __construct(
        private readonly IFactory $factory,
        private readonly IURLGenerator $url,
    ) {}

    public function getID(): string {
        return 'ocrflow';
    }

    public function getName(): string {
        return $this->factory->get('ocrflow')->t('OCR Flow');
    }

    public function prepare(INotification $notification, string $languageCode): INotification {
        if ($notification->getApp() !== 'ocrflow') {
            throw new UnknownNotificationException();
        }

        $l = $this->factory->get('ocrflow', $languageCode);
        $params = $notification->getSubjectParameters();
        $file = (string)($params['file'] ?? '');

        switch ($notification->getSubject()) {
            case 'ocr_done':
                $notification->setParsedSubject($l->t('OCR finished: %s', [$file]));
                break;
            case 'ocr_failed':
                $reason = (string)($params['reason'] ?? '');
                $notification->setParsedSubject(
                    $reason !== ''
                        ? $l->t('OCR failed: %1$s (%2$s)', [$file, $reason])
                        : $l->t('OCR failed: %s', [$file])
                );
                break;
            default:
                throw new UnknownNotificationException();
        }

        $notification->setIcon($this->url->getAbsoluteURL($this->url->imagePath('core', 'filetypes/text.svg')));
        return $notification;
    }
}
