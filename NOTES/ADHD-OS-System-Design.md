# ADHD-OS System Design — Our Build

## Core Principle
"A concrete pathway when there's no time or strength to think."

## Architecture

### Layer 1: Capture (2-second, always available)
| Method | How | Where it goes |
|---|---|---|
| Voice note | Tap → speak → done | Inbox in AFFiNE |
| Quick text | Widget on phone homescreen | Inbox in AFFiNE |
| Telegram bot | Message @your_bot with task | Inbox in AFFiNE |
| Email auto-scan | Hermes reads inbox, extracts tasks | Inbox in AFFiNE |
| Desktop | AFFiNE quick capture shortcut | Inbox in AFFiNE |

Everything lands in ONE Inbox. No thinking about where to put it. AI sorts it later.

### Layer 2: Processing (Hermes does the thinking)
| What | When | How |
|---|---|---|
| Sort inbox | Every few hours | AI reads Inbox, creates proper notes (task/event/project) |
| Deduplicate | On sort | AI checks if similar task already exists |
| Surface today | Every morning | AI picks 3-5 tasks based on state + priorities |
| Remind | Cron-based | "You said you'd do X — still relevant?" |
| Weekly review | Sunday evening | AI summarizes what got done, what's stale, patterns |

### Layer 3: Presentation (AFFiNE — what you see)
| View | Purpose |
|---|---|
| Today | The only view on bad days — 3-5 tasks max |
| Inbox | Everything unsorted (AI handles it) |
| Projects | Kanban per project (rental, solarium, coding, home) |
| Calendar | Time-based view of deadlines and events |
| Daily note | Auto-generated each morning with tasks + context |

### Layer 4: Guardrails (prevents the mess)
| Rule | What it does |
|---|---|
| Max 5 active tasks | Hard cap — can't add more without completing one |
| Stale task review | If untouched for 14 days → AI asks "still relevant?" |
| Bad day mode | State = low → system shows only 1-2 micro-tasks |
| No overdue shame | Overdue tasks don't pile up — reviewed and rescheduled/archived |
| Commitment cap | Max 2-3 active projects at once |

## Integration
| Source | What it does |
|---|---|
| Email | Hermes scans for action items, adds to Inbox |
| Telegram | Bot captures tasks, reads chat for context |
| Calendar | Syncs events, shows time blocks |
| Call recordings | Transcribed → AI extracts action items |
| GF's solarium | Separate workspace in AFFiNE, shared view |

## Bad Day Mode
When in crisis/stress/depression:
- System shows ONLY today's 1-2 easiest tasks
- Everything else is hidden
- AI says: "Just do this one thing. That's enough."
- No deadlines, no overdue, no guilt
- When you come back → system gently resurfaces what matters

## Projects
1. **Rental management** (main job) — reactive + proactive
2. **Solarium software** (GF's business) — build Yclients competitor
3. **Coding business/job** — personal apps + freelance
4. **Home** — cleaning, cooking, cats

## Phase 1 (Must Have)
- [ ] Deploy AFFiNE on erebus
- [ ] Set up Telegram capture bot
- [ ] Build Hermes morning briefing prompt
- [ ] Test "2-second capture → AI sort → daily view" loop
- [ ] Delete AppFlowy

## Phase 2 (Nice to Have)
- [ ] Email auto-scan
- [ ] Call recording transcription
- [ ] Pattern detection
- [ ] GF shared workspace
- [ ] Calendar integration
- [ ] Weekly auto-review

## References
- ADHD-OS Whitepaper: NOTES/ADHD-OS.md
- Build Blueprint: NOTES/ADHD-OS-Build-Blueprint.md
- Knowledge Management: NOTES/Knowledge-management.md
