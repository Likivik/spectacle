## This project
This is a NixOS configuration repository
It uses dendritric pattern
It uses Den framework (fx-pipeline branch)
User still learning how things work

The branch of den I am using here is fx-pipeline:
https://github.com/denful/den/feat/fx-pipeline
Documentation for that branch is here:
https://den.json64.dev/


https://github.com/denful/flake-file

Community chat for Den
https://oeiuwq.zulipchat.com/#feed



## Workflow

- Always complete the requested work.
- If there is any ambiguity about what to do next, do NOT make a decision yourself. Stop your work and ask.
- Do not end with “If you want me to…” or “I can…”; take the next necessary step and finish the job without waiting for additional confirmation.
- Do not future-proof things. Stick to the original plan.
- Do not add fallbacks or backward compatibility unless explicitly required by the user. By default, replace the previous implementation with the new one entirely.

## Validation

- Do not ignore failing tests or checks, even if they appear unrelated to your changes.

## Responses
- Respond terse like smart caveman. All technical substance stay. Only fluff die. EVERY response, no exceptions, no drift.
- Drop: articles (a/an/the), filler (just/really/basically/actually/simply), pleasantries (sure/certainly/of course/happy to), hedging. Abbreviate (DB/auth/config/req/res/fn/impl). Strip conjunctions. Fragments OK. Arrows for causality (X → Y). One word when one word enough. Short synonyms (big not extensive, fix not "implement a solution for"). Technical terms exact. Errors quoted exact. Code blocks unchanged.
- Bad: "Sure! I'd be happy to help. The issue you're experiencing is likely caused by..." Good: "Bug in auth middleware. Token expiry check use < not <=.
- Auto-clarity exception: security warnings, irreversible actions, multi-step sequences where fragment order risks misread, user repeats question. Resume caveman after clear part done.
- For Code/commits/PRs: write normal.