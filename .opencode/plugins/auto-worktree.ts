import { execSync } from "child_process"
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "fs"
import { join, resolve } from "path"

interface SessionEntry {
  worktreePath: string
  branch: string
  mainDir: string
  createdAt: number
}

type State = Record<string, SessionEntry>

const WORKTREE_REL = ["worktrees", "opencode"]
const STATE_FILE = "auto-worktree-state.json"

function git(cmd: string, cwd: string): string {
  return execSync(`git ${cmd}`, {
    cwd,
    encoding: "utf8",
    timeout: 10_000,
    stdio: ["pipe", "pipe", "pipe"],
  }).trim()
}

function branchExists(branch: string, dir: string): boolean {
  try {
    git(`show-ref --verify --quiet refs/heads/${branch}`, dir)
    return true
  } catch {
    return false
  }
}

function isLinkedWorktree(dir: string): boolean {
  try {
    const p = join(dir, ".git")
    return existsSync(p) && !statSync(p).isDirectory()
  } catch {
    return false
  }
}

function loadState(mainDir: string): State {
  const file = join(mainDir, ".opencode", STATE_FILE)
  try {
    if (existsSync(file)) return JSON.parse(readFileSync(file, "utf-8"))
  } catch {}
  return {}
}

function saveState(mainDir: string, state: State): void {
  const out = join(mainDir, ".opencode", STATE_FILE)
  const dir = join(mainDir, ".opencode")
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  writeFileSync(out, JSON.stringify(state, null, 2))
}

function removeWorktree(wtPath: string, branch: string, repoDir: string): void {
  if (existsSync(wtPath)) {
    try {
      execSync(`git worktree remove "${wtPath}" --force`, {
        cwd: repoDir,
        encoding: "utf8",
        timeout: 10_000,
        stdio: "pipe",
      })
    } catch {}
  }
  try { git("worktree prune", repoDir) } catch {}
  try { git(`branch -D "${branch}"`, repoDir) } catch {}
}

function currentBranch(dir: string): string {
  return git("rev-parse --abbrev-ref HEAD", dir)
}

function getMainDir(dir: string): string {
  try {
    const commonDir = git("rev-parse --git-common-dir", dir)
    return resolve(dir, commonDir, "..")
  } catch {
    return dir
  }
}

function isRealSessionId(id: string): boolean {
  return typeof id === "string" && id.startsWith("ses")
}

export const WorktreePlugin = async ({ client, directory }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.created") {
        const info = event.properties?.info
        if (!info?.id) return
        if (!isRealSessionId(info.id)) return
        if (isLinkedWorktree(directory)) return
        if (!client?.session?.fork || !client?.tui?.selectSession) return

        const sessionId: string = info.id
        const parentId: string | undefined = info.parentID
        const mainDir = getMainDir(directory)
        const state = loadState(mainDir)

        if (state[sessionId]) return

        // If this session is a child of an already-managed session, inherit the worktree.
        if (parentId && state[parentId]) {
          state[sessionId] = { ...state[parentId], createdAt: Date.now() }
          saveState(mainDir, state)
          return
        }

        const base = currentBranch(directory)
        const branch = `opencode/ses_${sessionId}`
        const wtPath = resolve(
          mainDir,
          ".opencode",
          ...WORKTREE_REL,
          `ses_${sessionId}`,
        )

        mkdirSync(resolve(wtPath, ".."), { recursive: true })

        try {
          if (branchExists(branch, mainDir)) {
            execSync(`git worktree add "${wtPath}" "${branch}"`, {
              cwd: mainDir,
              encoding: "utf8",
              timeout: 30_000,
              stdio: "pipe",
            })
          } else {
            execSync(
              `git worktree add -b "${branch}" "${wtPath}" "${base}"`,
              {
                cwd: mainDir,
                encoding: "utf8",
                timeout: 30_000,
                stdio: "pipe",
              },
            )
          }
        } catch (e) {
          console.error("auto-worktree: worktree add failed", e)
          return
        }

        // Save the entry for the original session BEFORE forking so child
        // session.created events can inherit it.
        state[sessionId] = {
          worktreePath: wtPath,
          branch,
          mainDir,
          createdAt: Date.now(),
        }
        saveState(mainDir, state)

        let forkResult: any
        try {
          forkResult = await client.session.fork({
            sessionID: sessionId,
            directory: wtPath,
          })
        } catch (e) {
          console.error("auto-worktree: fork failed", e)
          removeWorktree(wtPath, branch, mainDir)
          delete state[sessionId]
          saveState(mainDir, state)
          return
        }

        const newSessionId: string | undefined = forkResult?.data?.id
        if (!newSessionId) {
          console.error("auto-worktree: fork returned no session id, cleaning up")
          removeWorktree(wtPath, branch, mainDir)
          delete state[sessionId]
          saveState(mainDir, state)
          return
        }

        state[newSessionId] = {
          worktreePath: wtPath,
          branch,
          mainDir,
          createdAt: Date.now(),
        }
        saveState(mainDir, state)

        try {
          await client.tui.selectSession({ sessionID: newSessionId })
        } catch (e) {
          console.error("auto-worktree: selectSession failed", e)
        }
      }

      if (event.type === "session.deleted") {
        const sessionId: string | undefined =
          event.properties?.sessionID ?? event.properties?.info?.id
        if (!sessionId) return
        if (!isRealSessionId(sessionId)) return

        const mainDir = getMainDir(directory)
        const state = loadState(mainDir)
        let entry = state[sessionId]
        if (!entry) {
          entry = Object.values(state).find((e) => e.worktreePath === directory)
        }
        if (!entry) return

        try {
          git("add -A", entry.worktreePath)
          git('commit -m "WIP: auto-snapshot before worktree cleanup"', entry.worktreePath)
        } catch {}

        removeWorktree(entry.worktreePath, entry.branch, entry.mainDir)
        const keysToDelete = Object.keys(state).filter(
          (id) =>
            state[id].worktreePath === directory ||
            state[id].worktreePath === entry.worktreePath,
        )
        for (const k of keysToDelete) delete state[k]
        saveState(entry.mainDir, state)
      }
    },

    tool: {
      worktree_list: {
        description: "List all auto-managed worktrees with branch, path, and status.",
        args: {},
        async execute(_args, ctx) {
          const mainDir = getMainDir(ctx.directory)
          const state = loadState(mainDir)
          const entries = Object.entries(state)
          if (entries.length === 0) return "No auto-worktree sessions."
          return entries
            .map(([id, e]) => {
              const active = existsSync(e.worktreePath) ? "active" : "orphan"
              return `${id}  ${e.branch}  ${active}  ${e.worktreePath}`
            })
            .join("\n")
        },
      },
      worktree_finish: {
        description: "Commit changes and remove the current worktree. Use when done with this isolated session.",
        args: {},
        async execute(_args, ctx) {
          const mainDir = getMainDir(ctx.directory)
          const state = loadState(mainDir)
          const entry = Object.entries(state).find(
            ([_, e]) => e.worktreePath === ctx.directory,
          )
          if (!entry) return "Not in an auto-managed worktree."
          const [sessionId, e] = entry
          try {
            git("add -A", e.worktreePath)
            git('commit -m "WIP: snapshot before worktree cleanup"', e.worktreePath)
          } catch {}
          removeWorktree(e.worktreePath, e.branch, e.mainDir)
          delete state[sessionId]
          saveState(e.mainDir, state)
          return `Cleaned up worktree ${e.branch} (${e.worktreePath}).`
        },
      },
    },
  }
}
