import type { Plugin } from "@opencode-ai/plugin";

// ===== Constants (mirroring Hermes mnemosyne-hermes plugin) =====

// prefetch: over-fetch 16, filter/dedup, cap 5
const RECALL_TOP_K = 16;
const RECALL_CAP = 5;

// sync_turn truncation (env: MNEMOSYNE_SYNC_TURN_USER_LIMIT / _ASSISTANT_LIMIT)
const USER_LIMIT = 500;
const ASSISTANT_LIMIT = 800;
const IDENTITY_LIMIT = 400;

// sync_turn importance
const USER_IMPORTANCE = "0.5";
const ASSISTANT_IMPORTANCE = "0.15";
const IDENTITY_IMPORTANCE = "0.85";

// sync_turn guards
const USER_MIN_LEN = 5;
const ASSISTANT_MIN_LEN = 10;

// auto-sleep: every 10 turns, if working-mem items > 50
const SLEEP_EVERY_N_TURNS = 10;
const SLEEP_THRESHOLD = 50;

// identity signals (case-insensitive substring, one per turn)
const IDENTITY_SIGNALS = [
  "feeling like",
  "imposter",
  "impostor",
  "barely know",
  "don't know my own",
  "don't even know how",
  "want them to feel",
  "i'm proud",
  "i feel like a",
  "i don't know how to",
];

// ===== Types =====

interface RecallRow {
  id: string;
  content: string;
  score: number;
  importance?: number;
  source?: string;
  timestamp?: string;
  veracity?: string;
}

// ===== Helpers =====

export async function doRecall($: any, query: string): Promise<string | null> {
  if (!query) return null;
  try {
    const raw = await $`nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne recall ${query} ${RECALL_TOP_K}`
      .quiet().text();
    const rows = parseRecallText(raw);
    const filtered = rows
      .filter(r => !r.content.startsWith("[ASSISTANT]"))
      .slice(0, RECALL_CAP);
    if (filtered.length === 0) return null;
    return formatContext(filtered);
  } catch {
    return null;
  }
}

export function parseRecallText(text: string): RecallRow[] {
  const results: RecallRow[] = [];
  const blocks = text.split(/\n\n+/);
  for (const block of blocks) {
    const row: Partial<RecallRow> = {};
    for (const line of block.split("\n")) {
      const m = line.match(/^\s+(\w+):\s*(.*)$/);
      if (!m) continue;
      const key = m[1].toLowerCase();
      const val = m[2].trim();
      if (key === "id") row.id = val;
      else if (key === "content") row.content = val;
      else if (key === "score") row.score = parseFloat(val) || 0;
      else if (key === "importance") row.importance = parseFloat(val);
      else if (key === "source") row.source = val;
      else if (key === "timestamp") row.timestamp = val;
      else if (key === "veracity") row.veracity = val;
    }
    if (row.id && row.content) {
      row.score = row.score ?? 0;
      results.push(row as RecallRow);
    }
  }
  return results;
}

export function formatContext(rows: RecallRow[]): string {
  const lines = rows.map(r => {
    const parts: string[] = [];
    if (r.importance !== undefined) {
      let tag = `(importance ${r.importance.toFixed(2)}`;
      if (r.source && r.source !== "conversation") tag += `, source ${r.source}`;
      tag += ")";
      parts.push(tag);
    }
    parts.push(r.content);
    return "  " + parts.join(" ");
  });
  return "## Mnemosyne Context\n" + lines.join("\n");
}

async function doRemember(
  $: any,
  content: string,
  source: string,
  importance: string,
  globalScope = false,
): Promise<void> {
  let oldVal: string | undefined;
  let wasSet = false;
  if (globalScope) {
    oldVal = process.env.MNEMOSYNE_DEFAULT_SCOPE;
    process.env.MNEMOSYNE_DEFAULT_SCOPE = "global";
    wasSet = true;
  }
  try {
    await $`nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne remember ${content} ${source} ${importance}`
      .quiet().text();
  } catch {
    // best-effort
  } finally {
    if (wasSet) {
      if (oldVal === undefined) delete process.env.MNEMOSYNE_DEFAULT_SCOPE;
      else process.env.MNEMOSYNE_DEFAULT_SCOPE = oldVal;
    }
  }
}

async function getWorkingCount($: any): Promise<number | null> {
  try {
    const raw = await $`nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne stats`
      .quiet().text();
    const m = raw.match(/Working memory:\s*(\d+)/);
    return m ? parseInt(m[1], 10) : null;
  } catch {
    return null;
  }
}

async function doSleep($: any): Promise<void> {
  try {
    await $`nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne sleep`
      .quiet().text();
  } catch {
    // best-effort
  }
}

export function matchIdentitySignal(userText: string): boolean {
  const lower = userText.toLowerCase();
  return IDENTITY_SIGNALS.some(s => lower.includes(s));
}

// ===== Plugin =====

const plugin: Plugin = async ({ $, client }) => {
  let lastUserText = "";
  let lastUserMessageID = "";
  let cachedContext: string | null = null;
  let turnCount = 0;
  // messageID -> partID -> text (overwrite semantics, per sentry-monitor pattern)
  const partsCache = new Map<string, Map<string, string>>();

  return {
    // 1. Capture user text + fire dynamic recall in background
    "chat.message": async (_input, output) => {
      const userParts = output.parts.filter(
        (p: any) => p.type === "text" && !p.synthetic,
      );
      lastUserText = userParts.map((p: any) => p.text).join("\n");
      lastUserMessageID = output.message.id;
      if (lastUserText) {
        doRecall($, lastUserText).then(ctx => {
          if (ctx) cachedContext = ctx;
        });
      }
    },

    // 2. Inject cached context into system prompt
    "experimental.chat.system.transform": async (_input, output) => {
      if (!cachedContext && lastUserText) {
        cachedContext = await doRecall($, lastUserText);
      }
      if (cachedContext) output.system.push(cachedContext);
    },

    event: async ({ event }) => {
      // 3. Cache text parts as they stream (overwrite, not delta)
      if (event.type === "message.part.updated") {
        const part = (event as any).properties?.part;
        if (part?.type === "text" && part.messageID) {
          let msgMap = partsCache.get(part.messageID);
          if (!msgMap) {
            msgMap = new Map();
            partsCache.set(part.messageID, msgMap);
          }
          msgMap.set(part.id, part.text ?? "");
        }
      }

      // 4. sync_turn equivalent — assistant message complete
      if (event.type === "message.updated") {
        const info = (event as any).properties?.info;
        if (info?.role !== "assistant") return;
        if (typeof info.time?.completed !== "number") return;

        const sessionID = info.sessionID;
        const assistantMessageID = info.id;

        // Assemble assistant text from cache
        let assistantText = "";
        const msgMap = partsCache.get(assistantMessageID);
        if (msgMap) {
          assistantText = [...msgMap.values()].join("\n\n");
        }

        // Fallback: fetch from SDK if cache miss
        if (!assistantText && client && sessionID) {
          try {
            const res = await client.session.messages({ path: { id: sessionID } });
            const list = (res.data ?? res) as Array<{ info: any; parts: any[] }>;
            const last = [...list].reverse().find(m => m.info?.role === "assistant");
            if (last) {
              assistantText = last.parts
                .filter((p: any) => p.type === "text")
                .map((p: any) => p.text)
                .join("\n\n");
            }
          } catch {
            // best-effort
          }
        }

        // Store [USER] (imp 0.5, [:500], guard len>5)
        if (lastUserText && lastUserText.length > USER_MIN_LEN) {
          await doRemember(
            $,
            `[USER] ${lastUserText.slice(0, USER_LIMIT)}`,
            "conversation",
            USER_IMPORTANCE,
          );
        }

        // Store [ASSISTANT] (imp 0.15, [:800], guard len>10)
        if (assistantText && assistantText.length > ASSISTANT_MIN_LEN) {
          await doRemember(
            $,
            `[ASSISTANT] ${assistantText.slice(0, ASSISTANT_LIMIT)}`,
            "conversation",
            ASSISTANT_IMPORTANCE,
          );
        }

        // Identity signal (imp 0.85, scope=global, [:400], one per turn)
        if (lastUserText && matchIdentitySignal(lastUserText)) {
          await doRemember(
            $,
            `[IDENTITY] ${lastUserText.slice(0, IDENTITY_LIMIT)}`,
            "identity",
            IDENTITY_IMPORTANCE,
            true,
          );
        }

        // Auto-sleep: every 10 turns, if working-mem > 50 items
        turnCount++;
        if (turnCount % SLEEP_EVERY_N_TURNS === 0) {
          const working = await getWorkingCount($);
          if (working !== null && working > SLEEP_THRESHOLD) {
            await doSleep($);
          }
        }

        // Cleanup caches for this turn
        partsCache.delete(assistantMessageID);
        if (lastUserMessageID) partsCache.delete(lastUserMessageID);
      }
    },

    // 5. Preserve context across compaction
    "experimental.session.compacting": async (_input, output) => {
      if (cachedContext) output.context.push(cachedContext);
    },
  };
};

export default { id: "mnemosyne-bridge", server: plugin };
