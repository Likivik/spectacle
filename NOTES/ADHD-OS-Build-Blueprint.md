# ADHD-OS Build Blueprint — Our Stack

## Core Principle
"The goal is not to correct individuals with ADHD. They are not broken. The vision is to adjust the architectural environment around them." — ADHD-OS Whitepaper

## Four-Layer Architecture

### Layer 1: State Engine
- Models: energy, focus, stress, confidence, time perception
- Input: morning self-report (1-5 scale) or wearable data
- Triggers: reduced task exposure when state is low
- Our tool: Hermes cron prompt (daily check-in)

### Layer 2: Behavioural Layer
- Adapts task exposure based on state
- Shows ONLY today's tasks when state is low
- Full backlog visible only in high-capacity states
- Energy-based scheduling (tasks mapped to cognitive energy, not clock time)
- Our tool: AFFiNE daily view + Hermes task surfacing

### Layer 3: Reflection Layer
- Pattern detection (e.g., "low energy → admin avoidance")
- Weekly review + blind spot detection
- Agent maintains observations about user patterns
- Our tool: Hermes weekly cron + AFFiNE vault

### Layer 4: Guardrails
- Commitment caps (max N active projects)
- Spending alerts (financial impulsivity protection)
- Emotional state → reduced task exposure
- No streak-based shame mechanics
- Graceful degradation (missed days don't pile up)
- Our tool: Hermes alerts + AFFiNE limits

## Design Rules

1. **State variability is normative** — don't show 47 overdue tasks on a bad day
2. **Capture friction <5 seconds** — brain dump → AI sorts → vault
3. **No streak-based shame** — flexible habits, not rigid streaks
4. **Today view only** — backlog hidden until high-capacity state
5. **Energy-based scheduling** — tasks mapped to cognitive energy, not clock time
6. **Graceful degradation** — system forgives missed days
7. **User override always** — AI suggests, human decides
8. **Transparency** — all system logic explainable to user
9. **Harm reduction over productivity** — prevent overwhelm, not maximize output
10. **Non-exploitation** — no variable reward schedules, no shame mechanics

## Stack

| Layer | Tool | Purpose |
|---|---|---|
| Presentation | AFFiNE (self-hosted) | Vault, databases, kanban, daily notes |
| Processing | Hermes + LLM | State engine, task surfacing, patterns |
| Capture | AFFiNE mobile or voice | <5 second brain dump |
| Task execution | AFFiNE kanban + daily view | Same app, different views |
| Guardrails | Hermes cron + alerts | Caps, limits, emotional check-ins |
| Reflection | Hermes weekly review | Pattern detection, blind spots |

## ADHD-OS Agent Mapping (from whitepaper)

| Agent | Function | Our Implementation |
|---|---|---|
| Task Initiator | Overcome "Wall of Awful" | Hermes prompt: "What's the tiny next step?" |
| Decomposer | Break tasks into ≤10-min steps | Hermes prompt: "Break this down" |
| Body Double | Timed check-ins for accountability | Hermes cron: "How's it going?" |
| Time Calibrator | Correct time blindness | Hermes: "Last time this took X, estimate Y" |
| Focus Timer | Hyperfocus guardrails | Hermes cron: hard stop warnings |
| Catastrophe Check | Reality-test anxiety | Hermes: "What's the actual evidence?" |
| RSD Shield | Reframe perceived rejection | Hermes: "Alternative explanations?" |
| Motivation Engineer | Make boring tasks interesting | Hermes: "Gamify this task" |
| Pattern Analyst | Find correlations | Hermes weekly: "What patterns do you see?" |
| Reflector | Review plans for blind spots | Hermes weekly: "What's missing?" |

## References
- Whitepaper: https://gamma.app/docs/ADHD-OS-A-State-Aware-Behavioural-Operating-System-for-ADHD-g8iiaa8fdtqroab
- GitHub: https://github.com/vjdipaola/adhd-os
- Commercial: https://adhd-os.co.uk/
- Our note: NOTES/ADHD-OS.md
