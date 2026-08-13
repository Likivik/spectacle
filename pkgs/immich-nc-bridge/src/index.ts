// immich-nc-bridge: placeholder. Real implementation requires Extism
// WASM SDK. See: https://github.com/immich-app/immich/tree/main/server/src/plugins

import fs from "node:fs/promises";
import path from "node:path";

interface AssetEvent {
  type: "AssetCreate";
  data: {
    id: string;
    originalFileName: string;
    originalPath: string;
  };
}

async function classify(assetPath: string): Promise<"document" | "photo"> {
  // TODO: wire to MobileNetV2 ONNX classifier via httpRequest host fn.
  return "photo";
}

export function handleEvent(payload: AssetEvent): Promise<void> {
  const { data } = payload;
  return fs.access(path.dirname(data.originalPath))
    .then(() => classify(data.originalPath))
    .then((kind) => {
      console.log(`[immich-nc-bridge] ${data.originalFileName}: ${kind}`);
    });
}