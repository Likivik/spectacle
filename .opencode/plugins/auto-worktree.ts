import { execSync } from "child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";

const STATE_FILE = "auto-worktree-state.json";
const WORKTREES_SUBDIR = join(".opencode", "worktrees", "opencode");

type SessionEntry = {
  worktreePath: string;
  branch: string;
  parentSessionId: string | null;
  createdAt: number;
};

type State = Record<string, SessionEntry>;

function run(cmd: string, cwd: string): string {
  return execSync(cmd, {
    cwd,
    encoding: "utf8",
    timeout: 10_000,
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function git(cmd: string, cwd: string): string {
  return run(`git ${cmd}`, cwd);
}

function loadState(dir: string): State {
  const file = join(dir, ".opencode", STATE_FILE);
  try {
    if (existsSync(file)) return JSON.parse(readFileSync(file, "utf-8"));
  } catch (e) {
    console.error("auto-worktree: failed to load state", e);
  }
  return {};
}

function saveState(dir: string, state: State): void {
  const out = join(dir, ".opencode", STATE_FILE);
  writeFileSync(out, JSON.stringify(state, null, 2));
}

function currentBranch(dir: string): string {
  return git("rev-parse --abbrev-ref HEAD", dir);
}

function branchExistsLocal(branch: string, dir: string): boolean {
  try {
    git(`show-ref --verify --quiet refs/heads/${branch}`, dir);
    return true;
  } catch {
    return false;
  }
}

function worktreeExists(wtPath: string, dir: string): boolean {
  try {
    return git("worktree list --porcelain", dir)
      .split("\n")
      .some((line) => line === `worktree ${wtPath}`);
  } catch {
    return false;
  }
}

function addWorktree(wtPath: string, branch: string, base: string, dir: string): void {
  mkdirSync(join(wtPath, ".."), { recursive: true });
  if (branchExistsLocal(branch, dir)) {
    git(`worktree add "${wtPath}" "${branch}"`, dir);
  } else {
    git(`worktree add -b "${branch}" "${wtPath}" "${base}"`, dir);
  }
}

function removeWorktree(wtPath: string, branch: string, dir: string): void {
  if (existsSync(wtPath)) {
    try {
      git(`worktree remove "${wtPath}" --force`, dir);
    } catch (e) {
      console.error("auto-worktree: worktree remove failed", e);
    }
  }
  try {
    git("worktree prune", dir);
  } catch {}
  if (branchExistsLocal(branch, dir)) {
    try {
      git(`branch -D "${branch}"`, dir);
    } catch (e) {
      console.error("auto-worktree: branch delete failed", e);
    }
  }
}

export const AutoWorktreePlugin = async ({ client, directory, worktree }) => {
  const isWorktreeSpawn = worktree?.includes("worktrees");

  if (!existsSync(join(directory, ".git"))) {
    return {};
  }

  return {
    "experimental.chat.system.transform": async (_input, output) => {
      if (isWorktreeSpawn) {
        output.system.push(
          "WORKTREE SESSION RULES (STRICT):\n" +
            "1) Your git operations are scoped to the current worktree branch — do not assume main repo state.\n" +
            "2) To clean up this session, call worktree_finish (worktree-manager plugin) or just delete the session; the worktree is removed automatically on session.deleted.\n" +
            "3) If a tool fails because the worktree was already cleaned up, stop and report — do not retry.",
        );
      }
    },

    event: async ({ event }) => {
      if (event.type === "session.deleted") {
        const sessionId: string | undefined =
          event.properties?.sessionID ?? event.properties?.info?.id;
        if (!sessionId) return;

        const state = loadState(directory);
        const entry = state[sessionId];
        if (!entry) return;

        removeWorktree(entry.worktreePath, entry.branch, directory);
        delete state[sessionId];

        if (entry.parentSessionId) {
          const parentEntry = state[entry.parentSessionId];
          if (parentEntry && !parentEntry.parentSessionId) {
            removeWorktree(
              parentEntry.worktreePath,
              parentEntry.branch,
              directory,
            );
            delete state[entry.parentSessionId];
          }
        }
        saveState(directory, state);
        return;
      }

      if (event.type !== "session.created") return;

      const info = event.properties?.info;
      if (!info?.id) return;

      const sessionId: string = info.id;
      const parentId: string | undefined = info.parentID;

      const state = loadState(directory);

      if (parentId && state[parentId]) {
        state[sessionId] = { ...state[parentId], createdAt: Date.now() };
        saveState(directory, state);
        return;
      }

      if (state[sessionId]) {
        const entry = state[sessionId];
        if (worktreeExists(entry.worktreePath, directory)) {
          return;
        }
        try {
          const base = currentBranch(directory);
          addWorktree(entry.worktreePath, entry.branch, base, directory);
          client.tui.showToast?.({
            body: {
              title: "Worktree Restored",
              message: `Re-attached ${entry.branch}`,
              variant: "success",
            },
          });
        } catch (e) {
          console.error("auto-worktree: resume restore failed", e);
          delete state[sessionId];
          saveState(directory, state);
        }
        return;
      }

      let base: string;
      try {
        base = currentBranch(directory);
      } catch (e) {
        console.error("auto-worktree: no branch in", directory, e);
        return;
      }

      const branch = `opencode/ses_${sessionId}`;
      const wtPath = join(directory, WORKTREES_SUBDIR, `ses_${sessionId}`);

      try {
        addWorktree(wtPath, branch, base, directory);
      } catch (e) {
        console.error("auto-worktree: worktree add failed", e);
        client.tui.showToast?.({
          body: {
            title: "Worktree Error",
            message: String(e instanceof Error ? e.message : e),
            variant: "error",
          },
        });
        return;
      }

      state[sessionId] = {
        worktreePath: wtPath,
        branch,
        parentSessionId: null,
        createdAt: Date.now(),
      };
      saveState(directory, state);

      let forkResult: any;
      try {
        forkResult = await (client as any).session.fork({
          sessionID: sessionId,
          directory: wtPath,
        });
      } catch (e) {
        console.error("auto-worktree: fork failed", e);
        removeWorktree(wtPath, branch, directory);
        delete state[sessionId];
        saveState(directory, state);
        return;
      }

      if (forkResult?.error || !forkResult?.data?.id) {
        const errMsg = JSON.stringify(forkResult?.error ?? "unknown");
        console.error("auto-worktree: fork error", errMsg);
        removeWorktree(wtPath, branch, directory);
        delete state[sessionId];
        saveState(directory, state);
        return;
      }

      const newSessionId: string = forkResult.data.id;

      try {
        await (client as any).session.update({
          sessionID: newSessionId,
          directory: wtPath,
          title: `[${branch}]`,
        });
      } catch (e) {
        console.error("auto-worktree: title update failed (non-fatal)", e);
      }

      try {
        await (client as any).tui.selectSession({
          sessionID: newSessionId,
          directory,
        });
      } catch (e) {
        console.error("auto-worktree: tui selectSession failed", e);
      }

      state[newSessionId] = {
        worktreePath: wtPath,
        branch,
        parentSessionId: sessionId,
        createdAt: Date.now(),
      };
      saveState(directory, state);

      client.tui.showToast?.({
        body: {
          title: "Worktree Ready",
          message: branch,
          variant: "success",
        },
      });
    },
  };
};
