# aiogram 3 FSM — Best Practices for a Telegram Intake/Quiz Bot

Research compiled from official aiogram 3 docs, GitHub discussions/issues, DeepWiki,
and the aiogram_dialog docs (third-party companion library). Citations are inline
URLs; the full URL list is at the bottom.

## TL;DR (12 concrete recommendations)

1. **Define one `StatesGroup` per logical flow (e.g. `Intake`, `Quiz`), not one per step.**
   A `State` is a step *inside* a group. Separate flows must be separate groups so state
   filters don't accidentally cross-match. https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html

2. **Never mutate FSM state from outer middleware.** The FSM filter is resolved at
   middleware time and does not re-load mid-handler — changing state in middleware
   makes the filter "see" the old state for the current update. Detect the user
   property (e.g. registered/anonymous) in middleware and put it into handler data
   (`data["user"]`); gate routers with `MagicData(F.user)` / `MagicData(~F.user)`
   instead. https://github.com/aiogram/aiogram/discussions/1411

3. **Router-per-state (or router-per-flow) is the clean way to gate handlers.**
   Create one `Router()` per flow and use `@flow_router.message(Form.step)` /
   `@flow_router.callback_query(Form.step)` on its handlers. Attach the router to
   the dispatcher in the order you want priority. Do NOT rely on globally-scoped
   `@dp.message(...)` for state-bound handlers — you'll re-filter on every update
   and it gets messy fast. https://docs.aiogram.dev/en/latest/dispatcher/router.html

4. **Always provide a `/cancel` (and a `Cancel` button) that calls `await state.clear()`.**
   Guard it with `current_state = await state.get_state(); if current_state is None: return`
   so it no-ops outside an active flow. Without this, a stuck user is permanently wedged
   in the wrong state and only a Redis flush (or app restart with MemoryStorage) recovers
   them. https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html

5. **Use `MemoryStorage` only for dev/tests.** Docs explicitly warn: "not recommended
   for production in due to you will lose all data when your bot restarts."
   https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html

6. **Use `RedisStorage` in production.** It supports `state_ttl` and `data_ttl`
   (auto-expire abandoned flows), survives restarts and horizontal scaling, and pairs
   with `RedisEventIsolation` so per-user locks work across multiple bot instances.
   `RedisStorage.from_url("redis://...")` is the one-liner to wire it up.
   https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html
   https://deepwiki.com/aiogram/aiogram/5.4-event-isolation

7. **Use `SimpleEventIsolation` for single-process bots and `RedisEventIsolation`
   for multi-process.** `Dispatcher()` defaults to no isolation, which lets two
   concurrent updates for the same user race and corrupt `update_data`/`set_state`.
   Symptom in the wild: the bot "takes the first message and gets stuck" on rapid
   input. This is the #1 silent bug in naive aiogram 3 bots.
   https://github.com/aiogram/aiogram/issues/960
   https://deepwiki.com/aiogram/aiogram/5.4-event-isolation

8. **Per-user isolation comes from `FSMStrategy.USER_IN_CHAT` (the default), which
   scopes the `StorageKey` to `(bot_id, chat_id, user_id)`.** That's *storage key*
   isolation, not *processing* isolation. Storage key scoping prevents user A
   reading user B's state; event isolation prevents user A's two simultaneous
   updates from racing. You need both. Group chats need `USER_IN_TOPIC` to
   scope per forum topic.
   https://docs.aiogram.dev/en/latest/dispatcher/dispatcher.html
   https://deepwiki.com/aiogram/aiogram/5-finite-state-machine

9. **State filter is NOT applied by default in v3** (changed from v2). If a handler
   has no state filter, it fires regardless of state. Add explicit `StateFilter(state=None)`
   on "neutral" handlers (e.g. `/start`, `/help`) so they fire even mid-flow, or
   explicitly bind them with the relevant state. v2 docs/examples lie about this.
   https://docs.aiogram.dev/en/latest/migration_2_to_3.html
   https://github.com/aiogram/aiogram/issues/954

10. **For multi-step UIs with rich keyboards, prefer `aiogram_dialog` (third-party) or
    built-in `Scene`/`SceneWizard` over raw StatesGroup.** StatesGroup is best for
    linear text-question flows. Scene (added in v3.2) gives you isolated namespaces
    with enter/leave hooks, a back-stack via `wizard.goto`/`wizard.back`, and proper
    handling of cancellation. aiogram_dialog builds on top with declarative Windows,
    Buttons, transitions, and a stack — strictly less boilerplate for anything with
    a menu. The built-in Scene example shows the cancel/back as a reusable base class.
    https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/scene.html
    https://github.com/aiogram/aiogram/blob/dev-3.x/examples/scene.py
    https://aiogram-dialog.readthedocs.io/en/stable/quickstart/index.html

11. **Always pass an explicit `allowed_updates` to `start_polling`/`run_polling` if
    you handle `callback_query` or any non-message event.** aiogram v3 auto-discovers
    update types; if you only registered message handlers at startup, Telegram caches
    `allowed_updates=["message"]` server-side and your inline buttons silently stop
    working — and they stay broken even across bot token swaps. This is the single
    most-reported "stale button" bug and it isn't actually about FSM at all.
    https://github.com/aiogram/aiogram/discussions/1239
    https://stackoverflow.com/questions/78207499/telegram-bot-aiogram-3-doesnt-handle-inline-buttons-fsr

12. **Set TTLs (`state_ttl`, `data_ttl`) on `RedisStorage` and consider an
    auto-cancel handler.** Bots that people abandon mid-flow otherwise accumulate
    dead state forever. Combine `state_ttl=timedelta(minutes=30)` with an outer
    middleware that detects "stale" state (last interaction > N min via a
    timestamp you store in `state.update_data`) and prompts the user to resume
    or `/cancel`. https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html

## Pitfalls that break real bots (ranked by frequency in the wild)

- **No event isolation** → two rapid updates race, second `set_state` wins, first
  answer gets attached to wrong flow step. Fix: `events_isolation=SimpleEventIsolation()`
  in `Dispatcher(...)` or `RedisEventIsolation(...)` if multi-instance.
  https://github.com/aiogram/aiogram/issues/960
- **Mutating state in outer middleware** → state filter sees stale state for the
  current update. Fix: put the predicate into `data` and filter with `MagicData`.
  https://github.com/aiogram/aiogram/discussions/1411
- **Forgetting `allowed_updates` with `callback_query` handlers** → inline buttons
  mysteriously stop firing after a deploy. Fix: pass explicit `allowed_updates`.
  https://github.com/aiogram/aiogram/discussions/1239
- **StatesGroup for the whole bot instead of per-flow** → state filter on step 2 of
  flow A accidentally matches step 1 of flow B. Fix: one StatesGroup per flow.
  https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html
- **No `/cancel` handler** → user stuck after typing `/start` from inside an intake
  flow. Fix: always-on cancel that checks `await state.get_state() is not None`.
- **Storing the whole intake payload in `state.update_data` indefinitely** → data
  grows and, with MemoryStorage, is lost on restart. Fix: persist to DB on each
  step, keep only the minimal "current cursor" in FSM data.
- **`CallbackQuery.message` is `None`** (inline button from a notification or older
  Telegram client) — use `callback.message.edit_text(...)` defensively, or
  `await callback.answer("...")` and send a fresh message.
  https://docs.aiogram.dev/en/latest/migration_2_to_3.html
- **Reentrancy: user spams the same inline button while a handler is mid-await.**
  Without isolation, two coroutines run the same transition. Fix: `events_isolation`
  + idempotent handlers (check `await state.get_state()` after each `await`).
- **v2 muscle memory**: `state="*"`, `state=` kwarg, `@dp.callback_query_handler`,
  content_type filters. All gone in v3. Migration FAQ is the canonical reference.
  https://docs.aiogram.dev/en/latest/migration_2_to_3.html

## Storage decision matrix

| Scenario                          | Storage              | Isolation               | Why                                                |
|-----------------------------------|----------------------|-------------------------|----------------------------------------------------|
| Unit/integration tests            | `MemoryStorage`      | `DisabledEventIsolation`| Fast, no external deps                             |
| Local dev                         | `MemoryStorage`      | `SimpleEventIsolation`  | Sees race conditions before they hit prod          |
| Single-process prod               | `MemoryStorage`*     | `SimpleEventIsolation`  | * only if you tolerate restart loss; prefer Redis |
| Multi-process prod (gunicorn-like)| `RedisStorage`       | `RedisEventIsolation`   | Locks work across instances; TTL cleanup            |
| Forum-topic-scoped flows          | `RedisStorage`       | `RedisEventIsolation`   | Set `fsm_strategy=FSMStrategy.USER_IN_TOPIC`       |

## Sources

- FSM overview & usage: https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/index.html
- Storages: https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/storages.html
- Scenes: https://docs.aiogram.dev/en/latest/dispatcher/finite_state_machine/scene.html
- Router: https://docs.aiogram.dev/en/latest/dispatcher/router.html
- Dispatcher: https://docs.aiogram.dev/en/latest/dispatcher/dispatcher.html
- CallbackAnswer middleware: https://docs.aiogram.dev/en/v3.18.0/utils/callback_answer.html
- Migration FAQ: https://docs.aiogram.dev/en/latest/migration_2_to_3.html
- Discussion #1411 (state in middleware bug): https://github.com/aiogram/aiogram/discussions/1411
- Issue #960 (race conditions): https://github.com/aiogram/aiogram/issues/960
- Issue #954 (default state behavior): https://github.com/aiogram/aiogram/issues/954
- Discussion #1239 (allowed_updates stale buttons): https://github.com/aiogram/aiogram/discussions/1239
- Discussion #1486 (FSMStrategy + isolation): https://github.com/aiogram/aiogram/discussions/1486
- DeepWiki FSM: https://deepwiki.com/aiogram/aiogram/5-finite-state-machine
- DeepWiki Event Isolation: https://deepwiki.com/aiogram/aiogram/5.4-event-isolation
- Scene example: https://github.com/aiogram/aiogram/blob/dev-3.x/examples/scene.py
- aiogram_dialog quickstart: https://aiogram-dialog.readthedocs.io/en/stable/quickstart/index.html
- aiogram_dialog transitions: https://aiogram-dialog.readthedocs.io/en/stable/transitions/index.html
