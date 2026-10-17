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
- **`config.php` holds the SMTP credential in plaintext** (mode 0640,
  `nextcloud:nextcloud`). Verified NOT present in the nix store, the system
  profile, the repo, or any log — this is how Nextcloud config works (it has no
  credential indirection), not a leak. Worth knowing before copying that file
  anywhere.
