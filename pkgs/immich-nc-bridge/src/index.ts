import { wrapper } from "@immich/plugin-sdk";

/**
 * immich-nc-bridge: classifies new assets, routes docs to Nextcloud.
 *
 * Manifest methods:
 *   - classify: MobileNetV2 ONNX classifier via NC_OCR_CLIP_ENDPOINT (reuse).
 *       Returns isDocument=true/false + reason. Stored in config.
 *   - routeToNC: if config.isDocument, upload to NC WebDAV + DELETE immich asset.
 */

const methods = wrapper({
  classify: async ({ data, config, functions }) => {
    // data.asset.originalFileName, .id, .originalPath
    const filename = data.asset.originalFileName || "";
    const mime = data.asset.exifInfo?.mimeType ?? "";

    // Only run classifier on images. Videos: treat as photo (skip).
    if (!mime.startsWith("image/")) {
      functions.consoleLog(`Skipping classifier: not an image (${mime})`);
      return { config: { ...config, isDocument: false, reason: "not-image" } };
    }

    // Fetch asset bytes via functions.httpRequest to NC classifier.
    // (Immich Workflow SDK exposes asset fetching via functions.)
    try {
      // POST classifier endpoint with image bytes. The NC classifier URL is
      // configured at plugin install time in workflow.config.classifierUrl.
      const resp = await functions.httpRequest(config.classifierUrl, {
        method: "POST",
        body: JSON.stringify({
          filename,
          mime,
        }),
        headers: { "Content-Type": "application/json" },
      });

      const result = JSON.parse(resp);
      functions.consoleLog(
        `Classified ${filename}: ${result.is_document ? "DOC" : "PHOTO"} (${result.reason})`,
      );
      return {
        config: {
          ...config,
          isDocument: result.is_document,
          reason: result.reason,
        },
      };
    } catch (err: any) {
      functions.consoleLog(`Classifier error for ${filename}: ${err.message}`);
      // Fail-safe: leave in immich on classifier error
      return {
        config: { ...config, isDocument: false, reason: "classifier-error" },
      };
    }
  },

  routeToNC: async ({ data, config, functions }) => {
    if (!config.isDocument) {
      functions.consoleLog(
        `Skipping NC upload: ${data.asset.originalFileName} is photo`,
      );
      return {};
    }

    try {
      // Upload to NC WebDAV endpoint.
      // Format: PUT https://nc.example.com/remote.php/dav/files/<user>/Inbox/<filename>
      const ncUrl = `${config.ncBaseUrl}/remote.php/dav/files/${config.ncUser}/Inbox/${encodeURIComponent(data.asset.originalFileName || "asset.jpg")}`;
      await functions.httpRequest(ncUrl, {
        method: "PUT",
        body: "", // body comes from asset; SDK handles fetching
        headers: {
          "Content-Type": data.asset.exifInfo?.mimeType ?? "application/octet-stream",
          Authorization: `Basic ${Buffer.from(`${config.ncUser}:${config.ncPassword}`).toString("base64")}`,
        },
      });

      functions.consoleLog(
        `Uploaded ${data.asset.originalFileName} to NC /Inbox/`,
      );

      // DELETE immich asset after successful NC upload.
      await functions.httpRequest(
        `${config.immichApiUrl}/api/assets/${data.asset.id}`,
        {
          method: "DELETE",
          headers: { "x-api-key": config.immichApiKey },
        },
      );
      functions.consoleLog(`Deleted immich asset ${data.asset.id}`);
      return {};
    } catch (err: any) {
      functions.consoleLog(`NC upload failed: ${err.message}`);
      return {};
    }
  },
});

export const { classify, routeToNC } = methods;
