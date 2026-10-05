<?php
/**
 * Admin settings template for OCR Flow (Settings → Administration → Server).
 * @var array $_
 * @var \OCP\IL10N $l
 */
?>
<div class="section">
    <h2><?php p($l->t('OCR Flow')); ?></h2>
    <p class="settings-hint">
        <?php p($l->t('Files action that sends documents to the nc-ocr-flow service for OCR.')); ?>
    </p>

    <p>
        <label for="ocrflow-url"><?php p($l->t('OCR service URL')); ?></label>
        <input type="text" id="ocrflow-url" name="ocrflow_url"
               value="<?php p($_['ocrflow_url']); ?>" placeholder="http://127.0.0.1:8095" />
    </p>
    <p class="settings-hint">
        <?php p($l->t('The shared webhook secret is stored in the server configuration (ocrflow_secret) and is never rendered here.')); ?>
    </p>
</div>
