# Brief: propose a best-practice way to manage Hermes Agent under Nix config

**Type:** research + proposal. **Do not implement yet** — the deliverable is a written
proposal with options, a recommendation, and a migration path.

## Read first

- `/Storage/Git/spectacle/AGENTS.md` — repo rules (jj VCS, hosts, deploy flow, the
  "research latest best practices first" rule).
- The `hermes-agent` skill (`skill_view(name='hermes-agent')`) and its
  `references/configuration.md`.
- `https://hermes-agent.nousresearch.com/docs/llms.txt` — the authoritative index of
  every Hermes feature; start any "does Hermes support X?" question there.
- The `nixos-fleet-operations` and `nixos-secrets-ops` skills — the fleet's existing
  aspect/sops conventions.

## The situation

Hermes Agent has been running on this fleet as an **empirical setup** — installed
first, made to work second. It works, but the management is inconsistent:

- Hermes is a **Nix-managed artifact** (`/nix/store/vlkvynbpginvwy3yzhvnbgz39fr3gaz7-hermes-agent-0.0.0/…`,
  reporting `Hermes Agent v0.21.7 (2026.9.24) · upstream 71d34bad`), yet its own
  tooling reports `⚠ install out of sync (ffmpeg: not installed or outdated;
  ripgrep: not installed or outdated) — this nix-managed install must rebuild the
  artifact to fix`. Filed as **Likivik/spectacle#82**.
- Much of the operational surface is **hand-managed outside Nix**: `~/.hermes/config.yaml`
  is written imperatively by `hermes config set`, secrets live in `~/.hermes/.env`,
  and ad-hoc `systemd-run --user` units have accumulated (most recently
  `pylon-cdp.service` and `pylon-webdev.service`, created 2026-10-18 to keep a
  Chromium CDP endpoint and a wasm dev server alive across a gateway restart).
- So the state that matters (config, secrets, sessions, skills, memory, browser
  wiring) is split between Nix, hand-edited files, and runtime state — with no
  single place that says what the intended configuration *is*.

The question: **what is the best-practice way to manage this under the Nix config,
and what would the migration look like?**

## Questions the proposal must answer

1. **Upstream packaging.** Does Hermes publish a Nix flake / NixOS module /
   home-manager module? What do the upstream docs and repo recommend for NixOS?
   Cite what you find; if there is nothing official, say so plainly and look at how
   other people do it (blog posts, other flakes, the `nixos-fleet-operations`
   patterns already in this repo).
2. **The core tension — declarative vs. self-writing config.** Hermes writes its own
   config (`hermes config set`), and the skill's hard invariant says never hand-edit
   `config.yaml` because a stray indent breaks the live gateway. Nix wants the file
   to be a generated, read-only artifact. How do best-practice setups reconcile
   this? Options to evaluate at minimum:
   - Nix generates `config.yaml` read-only; all runtime mutation goes through a
     documented, reviewed path (e.g. change the Nix source and redeploy).
   - Nix seeds a baseline; a separate mutable overlay holds runtime deltas.
   - Nix owns the package + units + secrets, and config stays imperative but is
     backed up / tracked.
   For each: what breaks, what the failure modes are, and how `hermes config set`
   (and any other self-writing surface — skins, pets, plugins) behaves.
3. **Secrets.** The fleet already uses sops-nix. How should Hermes' `.env`
   (`~/.hermes/.env` — API keys, `HERMES_HOME`, service URLs) be handled
   declaratively without the keys ending up in the store? Note the hard invariant:
   **secrets in `.env`, settings in `config.yaml`.**
4. **State that must NOT be declarative.** `~/.hermes/state.db` (SQLite session
   store), `~/.hermes/sessions/`, skills, memory, cron state, kanban. Which of these
   are runtime state to leave alone, which are configuration to own, and how do
   backups/restores work? (The Nextcloud version-history incident in this fleet's
   history is a reminder that destructive state operations need a rollback story.)
5. **Multi-host and profiles.** The fleet is Serenity (where the agent runs),
   Erebus (edit-only, gateway masked), Traversal (off-tailnet), Poweredge. Hermes
   supports profiles (`~/.hermes/profiles/<name>/`). How should the module express
   per-host and per-profile differences, and should Erebus' masked gateway be
   expressed in Nix rather than hand-managed?
6. **Upgrades and pinning.** How is the Hermes version currently pinned, how should
   it be, and what is the upgrade flow (including the existing note that a nixpkgs
   bump changes the kernel and needs a reboot)?
7. **Service supervision.** The gateway/dashboard/graphiti user units, linger, and
   the user bus. Which of these should be declarative Nix units, and how do
   transient `systemd-run --user` helpers (like `pylon-cdp`) fit — are they
   legitimate, or should they be real units?
8. **What "done" looks like.** A concrete end state: which files become
   Nix-generated, which stay mutable, how a change is made and deployed, and how
   someone verifies the host matches the declared state.

## Constraints

- **Do not break the running gateway.** Agents must not restart it from their own
  cgroup — see the deploy hazard in `AGENTS.md`. Any restart is the user's action.
- The repo uses **jj**, not git. Never create git worktrees.
- Do not put secrets or key material in the Nix store.
- Follow the repo's rule: research current best practice first, cite sources, and do
  not rely on memory of how things used to be done.

## Deliverable

A markdown proposal (write it to `.hermes/plans/<date>-hermes-nix-management.md` in
the spectacle repo) containing:

- Current state, established by inspection — with commands and real output, not
  assumption.
- The options, each with trade-offs and failure modes.
- A recommendation, with reasoning.
- A migration path: ordered, reversible steps, each verifiable, with the risky ones
  called out.
- Explicit list of what you could not determine and what you would need to.

Report back a short summary plus the file path. Do not implement the migration in
this session.
