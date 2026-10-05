<?php

declare(strict_types=1);

namespace OCA\OcrFlow\Service;

use OCP\Files\File;
use OCP\Files\IRootFolder;

/**
 * Per-file OCR state for the Files actions.
 *
 * "Send to OCR" and "Re-OCR anyway" are mutually exclusive: which one is
 * offered must depend on what already happened to the file. The OCR service
 * keeps the durable index, but only Nextcloud knows the live file — so an
 * index entry is trusted only while the file still looks the way the service
 * left it (same etag, or same size and not modified long after it finished).
 * Without that check a replaced file would keep hiding "Send to OCR".
 */
final class FileStateService
{
    /**
     * A processed file can still be touched by something outside our
     * pipeline right after we finish (desktop sync clients, Nextcloud
     * internals both rewrite it and shift mtime/etag). A modification within
     * this window is therefore not treated as a user edit.
     */
    private const MTIME_SLACK = 900;

    public function __construct(
        private readonly WebhookClient $webhook,
        private readonly IRootFolder $rootFolder,
    ) {
    }

    /**
     * Every file the OCR service knows about, keyed by Nextcloud file id —
     * a single cheap call so the Files actions can decide synchronously,
     * before the list renders. Freshness (has the file been replaced since?)
     * is judged on the client from the node's own mtime, which needs no
     * extra round trip and stays correct per row.
     *
     * @return array<string, array{state:string,finished:?int,engine:?string,reason:?string}>
     */
    public function allStates(): array
    {
        $svc = $this->webhook->states([], true);
        $records = $svc['body']['states'] ?? [];

        $out = [];
        foreach ($records as $path => $rec) {
            $nodeId = (int)($rec['node_id'] ?? 0);
            $status = (string)($rec['status'] ?? '');
            if ($nodeId <= 0 || $status === '') {
                continue;
            }
            $out[(string)$nodeId] = [
                'state' => $status,
                'finished' => isset($rec['finished']) ? (int)$rec['finished'] : null,
                'engine' => $rec['engine'] ?? null,
                'reason' => $rec['reason'] ?? null,
            ];
        }
        return $out;
    }

    /**
     * @param int[] $fileIds
     * @return array<int, array<string, mixed>> fileId → {state, engine?, reason?, finished?}
     */
    public function statesFor(string $userId, array $fileIds): array
    {
        $userFolder = $this->rootFolder->getUserFolder($userId);

        $meta = [];
        foreach ($fileIds as $fileId) {
            $fileId = (int)$fileId;
            if ($fileId <= 0) {
                continue;
            }
            try {
                $nodes = $userFolder->getById($fileId);
            } catch (\Throwable) {
                $nodes = [];
            }
            if (count($nodes) === 0) {
                continue;
            }
            $node = $nodes[0];
            if (!$node instanceof File) {
                continue;
            }
            $rel = ltrim((string)$userFolder->getRelativePath($node->getPath()), '/');
            if ($rel === '') {
                continue;
            }
            // The OCR service keys its index by the NC-internal path
            // ("/<uid>/files/<rel>") — the same form the webhook delivers.
            $key = '/' . $userId . '/files/' . $rel;
            $meta[$key] = [
                'fileId' => $fileId,
                'size' => (int)$node->getSize(),
                'mtime' => (int)$node->getMTime(),
                'etag' => (string)$node->getEtag(),
            ];
        }

        if (count($meta) === 0) {
            return [];
        }

        $res = $this->webhook->states(array_keys($meta));
        $records = $res['body']['states'] ?? [];
        if (!is_array($records)) {
            $records = [];
        }

        $out = [];
        foreach ($meta as $rel => $m) {
            $out[$m['fileId']] = $this->classify($m, $records[$rel] ?? null);
        }
        return $out;
    }

    /**
     * @param array{fileId:int,size:int,mtime:int,etag:string} $meta
     * @param array<string,mixed>|null $rec
     * @return array<string, mixed>
     */
    private function classify(array $meta, ?array $rec): array
    {
        if ($rec === null) {
            return ['state' => 'never'];
        }

        $status = (string)($rec['status'] ?? '');
        $base = [
            'engine' => $rec['engine'] ?? null,
            'reason' => $rec['reason'] ?? null,
            'finished' => isset($rec['finished']) ? (int)$rec['finished'] : null,
        ];

        if ($status === 'queued' || $status === 'running') {
            return ['state' => $status] + $base;
        }

        if (($status === 'done' || $status === 'skipped') && !$this->stillFresh($meta, $rec)) {
            // The user replaced or edited the file after we processed it.
            return ['state' => 'never', 'stale' => true] + $base;
        }

        return ['state' => $status !== '' ? $status : 'never'] + $base;
    }

    /**
     * Is the recorded outcome still about *this* content?
     *
     * Only the modification time is trusted for the negative case: a file
     * touched well after we finished was clearly replaced/edited since.
     * Size and etag are deliberately NOT used to declare a file stale — a
     * processed file gets rewritten/poked right after we finish, which
     * moves both without the content meaningfully changing. An exact etag
     * match is used the other way around, as proof of freshness.
     *
     * @param array{fileId:int,size:int,mtime:int,etag:string} $meta
     * @param array<string,mixed> $rec
     */
    private function stillFresh(array $meta, array $rec): bool
    {
        $recEtag = trim(str_replace('&quot;', '', (string)($rec['etag'] ?? '')), '"');
        $liveEtag = trim((string)$meta['etag'], '"');
        if ($recEtag !== '' && $liveEtag !== '' && $recEtag === $liveEtag) {
            return true;
        }

        $finished = (int)($rec['finished'] ?? 0);
        if ($finished > 0 && $meta['mtime'] > $finished + self::MTIME_SLACK) {
            return false;
        }

        return true;
    }
}
