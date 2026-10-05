<?php
/**
 * Personal settings template: OCR metrics + queue + scan history.
 *
 * A server-rendered snapshot; #ocrflow-panel is picked up by the bundled
 * auto-refresher (frontend/src/main.mjs) which polls
 * /apps/ocrflow/api/{status,stats} and re-renders in place.
 *
 * @var array $_     template parameters
 * @var \OCP\IL10N $l
 */
$metrics = is_array($_['metrics'] ?? null) ? $_['metrics'] : [];
$byEngine = is_array($metrics['byEngine'] ?? null) ? $metrics['byEngine'] : [];
$skipReasons = is_array($metrics['skipReasons'] ?? null) ? $metrics['skipReasons'] : [];

$names = static function (array $jobs): array {
    $out = [];
    foreach ($jobs as $j) {
        $p = (string)($j['path'] ?? '');
        $out[] = [
            'name' => $p === '' ? '' : basename($p),
            'status' => (string)($j['status'] ?? ''),
            'finished' => $j['finished'] ?? null,
        ];
    }
    return $out;
};
$active = array_merge(
    $names(is_array($_['running'] ?? null) ? $_['running'] : []),
    $names(is_array($_['queued'] ?? null) ? $_['queued'] : []),
);
$history = array_reverse($names(is_array($_['history'] ?? null) ? $_['history'] : []));
$fmt = static function ($ts): string {
    if (!$ts) {
        return '';
    }
    try {
        return (new \DateTime('@' . (int)$ts))->format('Y-m-d H:i');
    } catch (\Throwable $e) {
        return '';
    }
};
?>
<div id="ocrflow-panel" class="section">
    <h2><?php p($l->t('OCR Flow')); ?></h2>
    <p class="settings-hint">
        <?php p($l->t('OCR pipeline metrics for this instance. Counts come from the OCR service index; the total is every PDF/image in your files.')); ?>
    </p>

    <h3><?php p($l->t('Metrics')); ?></h3>
    <table class="grid" id="ocrflow-metrics">
        <thead>
            <tr>
                <th><?php p($l->t('Scanned')); ?></th>
                <th><?php p($l->t('Not scanned yet')); ?></th>
                <th><?php p($l->t('Skipped')); ?></th>
                <th><?php p($l->t('OCR-able total')); ?></th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td id="ocrflow-m-scan"><?php p($metrics['scanned'] ?? '—'); ?></td>
                <td id="ocrflow-m-remaining"><?php p($metrics['remaining'] ?? '—'); ?></td>
                <td id="ocrflow-m-skip"><?php p($metrics['skipped'] ?? '—'); ?></td>
                <td id="ocrflow-m-total"><?php p($metrics['total'] ?? '—'); ?></td>
            </tr>
        </tbody>
    </table>
    <p class="settings-hint">
        <?php p($l->t('By engine:')); ?>
        <span id="ocrflow-m-engines"><?php
            $parts = [];
            foreach ($byEngine as $eng => $n) {
                $parts[] = $eng . ' (' . (int)$n . ')';
            }
            p($parts ? implode(', ', $parts) : $l->t('no data yet'));
        ?></span>
    </p>
    <?php if ($skipReasons): ?>
    <p class="settings-hint">
        <?php p($l->t('Skipped because:')); ?>
        <span id="ocrflow-m-skipwhy"><?php
            $parts = [];
            foreach ($skipReasons as $r => $n) {
                $parts[] = $r . ' (' . (int)$n . ')';
            }
            p(implode(', ', $parts));
        ?></span>
    </p>
    <?php endif; ?>

    <h3><?php p($l->t('In progress')); ?></h3>
    <p class="settings-hint">
        <?php p($l->t('Queue depth:')); ?> <span id="ocrflow-queue-depth"><?php p($_['queue_depth'] ?? 0); ?></span>
    </p>
    <table class="grid" id="ocrflow-active">
        <thead><tr><th><?php p($l->t('File')); ?></th><th><?php p($l->t('Status')); ?></th></tr></thead>
        <tbody>
        <?php if (!$active): ?>
            <tr><td colspan="2"><?php p($l->t('Nothing in progress.')); ?></td></tr>
        <?php else: foreach ($active as $row): ?>
            <tr><td><?php p($row['name']); ?></td><td><?php p($row['status']); ?></td></tr>
        <?php endforeach; endif; ?>
        </tbody>
    </table>

    <h3><?php p($l->t('History')); ?></h3>
    <table class="grid" id="ocrflow-history">
        <thead><tr><th><?php p($l->t('File')); ?></th><th><?php p($l->t('Status')); ?></th><th><?php p($l->t('Finished')); ?></th></tr></thead>
        <tbody>
        <?php if (!$history): ?>
            <tr><td colspan="3"><?php p($l->t('No scans yet.')); ?></td></tr>
        <?php else: foreach ($history as $row): ?>
            <tr><td><?php p($row['name']); ?></td><td><?php p($row['status']); ?></td><td><?php p($fmt($row['finished'])); ?></td></tr>
        <?php endforeach; endif; ?>
        </tbody>
    </table>
</div>
