# Open questions — nc-ocr-flow

Recorded 2026-10-17, at Kirill's request ("write down these 2 questions to figure
out later"). Not blocking anything; both are about how this subsystem is
configured and tested.

## 1. occ on NixOS: can we configure Nextcloud entirely through occ, and switch to it for everything?

What we know so far (2026-10-17):

- The NixOS `services.nextcloud` module exposes `occ` as
  `/run/current-system/sw/bin/nextcloud-occ`, a generated wrapper that
  `cd`s into the Nextcloud store path and — when `requiresRuntimeSystemdCredentials`
  is true and there is no `CREDENTIALS_DIRECTORY` — re-executes itself through
  `systemd-run --property=LoadCredential=...` so Nextcloud can read its secrets
  (db password, smtp, etc.) via `nix_read_secret()`.
- Consequence: the wrapper only works from a context where `systemd-run` is
  permitted. It **fails** as a non-root user over plain ssh
  ("Failed to start transient service unit: Access denied"), and it **works** as
  root (`sudo -n nextcloud-occ ...`). Inside a unit that already has a
  `CREDENTIALS_DIRECTORY`, it inherits it instead.
- So `occ` is usable declaratively today (e.g. `config:system:set` from
  `nextcloud-setup.postStart`), but "switch to occ for everything" needs a
  decision about *which* unit runs the commands and how credentials reach them.

Open sub-questions:
- Which of our current direct actions have an occ equivalent, and which do not?
  (Known gaps as of NC 34.0.4: no `occ workflows:delete` — only `workflows:list`;
  no `occ webhook_listeners:add` — only `webhook_listeners:list`.)
- Should the oneshots that need occ run as root (so the wrapper can `systemd-run`)
  or load the same credential set themselves so a direct `php occ` works?
- Does running occ from a `nextcloud`-user oneshot break when the wrapper tries
  `systemd-run`?

## 2. Is what we test equal to what we deploy? (dev = prod parity)

Are the test environment and the deployed service actually equivalent — fonts,
shared libraries, native dependencies (pymupdf/onnxruntime/tesseract), the Python
interpreter, env vars, and the config defaults?

Why it matters here specifically:

- The local test suite already has one known divergence: `test_orientation.py::
  TestDetectOrientation::test_takes_pp_lcnet_when_confident` fails locally because
  the PP-LCNet ONNX model file is absent, and passes in CI. That is a real
  dev≠prod gap in the test harness, not just noise.
- `pymupdf` needs `LD_LIBRARY_PATH` (libstdc++) to import outside the service
  environment — found the hard way when probing files on the box.
- Fonts matter for OCR output: the service sets `NC_OCR_FONT_PATH`; a test run
  without the same font set can produce different embedded text.
- Engines differ by credentials: Google Vision (deployed, `NC_OCR_ENGINE=google`)
  vs tesseract/minimax paths that CI may exercise with different dependencies.

Open sub-questions:
- Do we bundle/require every native dependency the deployed venv has, or does CI
  silently skip tests that need them?
- Should the CI job run inside the same closure as the deployed service (e.g.
  `nix build` the service env and run pytest against it) instead of a host venv?
- Which tests are credential-gated and therefore never exercised in CI?

## Findings from the 2026-10-17 quality/security pass

- **`occ admin-delegation:show` does not list our delegation**, although it is
  in effect. `Show.php` only walks the sections returned by
  `IAdminSettings::getAdminSections()`, and the Webhooks page declares its own
  section (`webhook_listeners-admin`), which that call never returns — so
  delegated *app* settings are invisible to it. Audit the delegation instead in
  `oc_authorized_groups` (ours is `1|ocr-webhooks|OCA\WebhookListeners\Settings\Admin`,
  written by `IAuthorizedGroupService::create()`), in the admin UI, or simply by
  the fact that `nc-ocr-register-webhook` fails loudly if the delegation is gone.
- **Nextcloud writes the full request headers of a FAILED webhook call into
  `nextcloud.log`, including `X-Webhook-Secret`.** Nothing we control suppresses
  it. Treat the secret as compromised whenever a dispatch failure is
  investigated, rotate it, and scrub the log.
- **`nextcloud/admin-password` (sops) is a first-install bootstrap secret, not a
  credential store — and it is SUPPOSED to diverge from the live admin
  password.** The NixOS module is explicit: "The password is set only in the
  initial setup of Nextcloud by the systemd service `nextcloud-setup.service`".
  It is consumed once, by the installer, through the `adminpass` credential.
  Nothing reads it at runtime: the OCR units no longer load it (`occ status`
  succeeds with only `mail_smtppassword` present, so it was provably unread) and
  the live `config.php` contains no `adminpass` entry. `scripts/deploy-poweredge.sh`
  generates it when it creates the secrets file and prints it during bootstrap,
  and it is the value a from-scratch reinstall would apply — so keep it.
  Do NOT "refresh" it to the live admin password (that would put a real admin
  credential in the repo), and do NOT delete it unless you also set
  `adminuser = null` + `adminpassFile = null` (the module permits disabling
  initial admin creation on Nextcloud >= 32, and asserts the two must match),
  accepting a manual admin-creation step on any reinstall.
- **The SMTP credential in `config.php` is the module's deliberate design.** It
  asserts that `services.nextcloud.settings.mail_smtppassword` "must not be
  used, as it puts the password into the world-readable nix store", so the value
  is resolved through `nix_read_secret` and rendered into `config.php` (mode
  0640, `nextcloud:nextcloud`) instead. Verified absent from the nix store, the
  system profile, the repo and every log.
- **The SMTP secret is read per PHP request, and a stale literal in `config.php`
  is a decoy.** Two files are in play:
  - `override.config.php` (rendered by the module, linked by tmpfiles) holds
    `'mail_smtppassword' => nix_read_secret('mail_smtppassword')` — an
    expression, evaluated from `$CREDENTIALS_DIRECTORY` on every request. This
    is the value in use, so **a rotation takes effect without a restart** and no
    `restartUnits` is needed.
  - `config.php` (mode 0640, `nextcloud:nextcloud`) holds a stale **literal**,
    because Nextcloud serialises its merged config whenever it persists config
    (`nextcloud-setup` runs `occ upgrade` and
    `occ config:system:delete trusted_domains`). It is shadowed:
    `override.config.php` is applied last via `array_replace_recursive`.
  Do not conclude from the literal that a rotation needs a re-render — and note
  the stale literal does leave a copy of the (possibly old) key in that file, so
  do not copy it anywhere. Verified: the key is NOT in the nix store, the system
  profile, the repo, or any log.

## Open work on the OCR pipeline (recorded 2026-10-18)

- **Uploads during a service restart: FIXED by the startup catch-up pass.**
  The gap was real — a file that arrives while the unit restarts (every deploy
  that changes the source rebuilds the venv, ~1-2 min) never reaches us, and
  nothing recorded it. Two live end-to-end attempts were lost this way on
  2026-10-18.
  Note the original wording was wrong on one point: `webhook_server.py` *does*
  reconcile at import (`_reconcile_startup` / `_reconcile_stale_startup`), it
  just cannot help here — both only look at index rows, and a file whose
  webhook died has no row at all.
  Fix (`catch_up_missed_files`, run once at startup in a daemon thread, plus
  `POST /catch-up`): keep a watermark of the last webhook actually received
  (settings key `_last_webhook_at`, advanced at the top of `/webhook`), then
  PROPFIND the root with `getlastmodified` and enqueue only entries modified after
  it. Bounded by `NC_OCR_CATCHUP_MAX` (default 200, newest first), clamped to
  `NC_OCR_CATCHUP_MAX_AGE` (default 7 days), and a missing watermark means a
  fresh install and does nothing. `NC_OCR_CATCHUP=0` disables it. Never the
  full walk `/scan-all` would have done, and it cannot double-bill: candidates
  go through the same `_path_in_flight` guard as the webhook.
- **The two PHP scripts: DONE** (#88). 10 PHPUnit tests / 60 assertions under
  `modules/aspects/server/workflow-ocr/tests/`, running as the
  `php tests (workflow-ocr)` CI job. Note for whoever adds the next CI job: the
  repo allows only GitHub-owned actions plus `DeterminateSystems/nix-installer-action`,
  and an unlisted `uses:` fails the entire run at startup, not just the job.
  Both scripts were written to be testable — `ocsRequest()` is `protected` so a
  stub OCS server can be injected — and the suite now exercises idempotent
  registration, secret rotation, poison/self-heal, disable + post-condition and
  mixed-failure aggregation.
- **Nextcloud rate-limits the service's WebDAV reads** — 429 on the `localhost`
  request stream under bursty traffic; clears within minutes. Since the retry
  ordering fix (#84) that now leaves a queued retry with backoff instead of
  losing the file, so it is no longer data loss, but a large first-time batch
  can still stall. Do not upload in a loop while testing.
- **TODO (deferred by decision, not by doubt): make the restart-gap drill a
  repeatable gate.** The catch-up pass (#87 + #90) is proven by hand: stop
  `nc-ocr-webhook`, upload one PDF via WebDAV with the service credentials,
  hold the unit down ~150 s (shorter windows prove nothing — NC dispatches via
  a background job that simply runs after the restart), start the unit, require
  `checked=N enqueued=1` and exactly one new `jobs` row. Deliberately NOT wired
  into CI now: the hosted runner cannot reach a live Nextcloud, and a local
  version adds several minutes to every iteration while the app is still moving
  fast. **Do it when nc-ocr-flow moves to its own repository**, where the suite
  can own its own throwaway Nextcloud (container + `occ` bootstrap) and treat
  the outage drill as a first-class test instead of a manual ritual.
  The manual procedure and the 150 s figure are the specification for it.
- **Image branch behaviour (settled 2026-10-19).** A folder of images is NOT
  converted blindly: `classify()` (MobileNetV3-Small) gates document vs photo,
  and 12/12 WhatsApp photos in a render folder came back `photo` → skipped,
  untouched. Three decisions after that review:
  1. **The classifier now fails closed.** It used to default to `is_document=True`
     on any error, which meant a missing/broken ONNX model would convert and
     delete every image in every folder on the next `/scan-all`. Now it raises
     `ClassifierUnavailable` → the job errors with the reason and NOTHING is
     converted or deleted. Fix `NC_OCR_MOBILENET_MODEL` and restart.
  2. **Name collisions no longer skip.** If `name.pdf` exists, the OCR'd image
     uploads as `name (1).pdf` (up to 50), and the pre-existing PDF is never
     touched. Skip only if every candidate is taken or PROPFIND fails.
  3. **`NC_OCR_KEEP_SOURCE_IMAGE=1`** keeps the source image beside the PDF
     (marked `source_image_kept`); off by default. Conversion is lossless anyway
     — see `nc-ocr-extract` — so this is about folder shape, not data safety.
  Screenshots still count as documents (correct: the Vodokanal screenshot
  converted), and the image's own EXIF survives inside the PDF either way.
