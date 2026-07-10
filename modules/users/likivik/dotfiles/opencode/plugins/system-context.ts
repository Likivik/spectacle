import type { Plugin } from "@opencode-ai/plugin";

const hostname =
  globalThis.process?.env?.HOSTNAME ??
  globalThis.process?.env?.HOST ??
  "unknown";

const interface_ = (() => {
  if (process.env.VSCODE_PID || process.env.VSCODE_INJECTION) return "IDE";
  if (process.env.OPENCODE_APP) return "App";
  if (process.stdout.isTTY) return "TUI";
  return "CLI";
})();

const contextBlock = [
  "## System Context",
  `- Hostname: ${hostname}`,
  "- Platform: Opencode",
  `- Interface: ${interface_}`,
  "",
].join("\n");

export const SystemContextPlugin: Plugin = async () => {
  return {
    "experimental.chat.system.transform": async (_input, output) => {
      if (output.system.length === 0) return;
      if (output.system[0].includes("## System Context")) return;
      output.system[0] = `${output.system[0]}\n\n${contextBlock}`;
    },
  };
};
