export default function (pi: any) {
  const hostname = process.env.HOSTNAME ?? process.env.HOST ?? "unknown";
  const interface_ = process.env.VSCODE_PID || process.env.VSCODE_INJECTION
    ? "IDE"
    : process.env.OPENCODE_APP
      ? "App"
      : process.stdout.isTTY
        ? "TUI"
        : "CLI";

  pi.on("session_start", async (_event: any, ctx: any) => {
    ctx.ui.notify(`System Context: ${hostname} (${interface_})`, "info");
  });

  pi.on("before_agent_start", async (_event: any, ctx: any) => {
    const systemContext = [
      "## System Context",
      `- Hostname: ${hostname}`,
      "- Platform: OMP",
      `- Interface: ${interface_}`,
    ].join("\n");
    return {
      message: {
        customType: "system-context",
        content: systemContext,
        display: false,
        attribution: "user",
      },
    };
  });
}
