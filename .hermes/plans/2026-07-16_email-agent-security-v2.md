# rusty-imap-mcp Fork + PII Redaction — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Fork rusty-imap-mcp, add PII redaction (leakguard + Russian detectors), deploy single binary on Erebus with Gmail IMAP access for Hermes.

**Architecture:** Fork rusty-imap-mcp → add `leakguard` crate + 3 custom Russian detectors → build single static binary → deploy as systemd service → connect Hermes as MCP client.

**Tech Stack:** Rust 1.88+, leakguard (PII detection), systemd (service), NixOS (declarative config)

---

## Prerequisites (user action)

### Gmail App Password

1. Go to https://myaccount.google.com/security
2. Enable 2-Step Verification (if not already)
3. Go to "App passwords" (search in account settings)
4. Generate a new app password for "Mail"
5. Save the 16-character password — needed in Task 5

---

## Task 1: Clone and verify rusty-imap-mcp builds

**Objective:** Clone the repo, confirm it builds from source on Erebus.

**Files:**
- Create: `/var/lib/hermes/rusty-imap-fork/` (clone directory)

**Steps:**

1. Check Rust is available:
```bash
rustc --version
cargo --version
```
Expected: Rust 1.88.0+

If not installed:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
```

2. Clone the repo:
```bash
mkdir -p /var/lib/hermes/rusty-imap-fork
cd /var/lib/hermes/rusty-imap-fork
git clone https://github.com/randomparity/rusty-imap-mcp.git .
```

3. Check latest release tag:
```bash
git tag --sort=-v:refname | head -5
git checkout $(git tag --sort=-v:refname | head -1)
```

4. Build release binary:
```bash
cargo build --release
```

5. Verify binary runs:
```bash
./target/release/rusty-imap-mcp --version
./target/release/rusty-imap-mcp --help
```

**Verification:** Binary builds, prints version, shows help text.

---

## Task 2: Add leakguard dependency

**Objective:** Add leakguard to Cargo.toml for PII detection.

**Files:**
- Modify: `Cargo.toml` (root workspace)

**Steps:**

1. Find the root Cargo.toml:
```bash
cat Cargo.toml
```

2. Add leakguard to dependencies. The exact location depends on workspace structure — leakguard should go in the crate that handles content sanitization (likely `rimap-security` or similar).

3. Add to the relevant crate's Cargo.toml:
```toml
[dependencies]
leakguard = "0.3"
```

4. Also add regex for custom Russian detectors:
```toml
[dependencies]
leakguard = "0.3"
regex = "1"
```

5. Verify deps resolve:
```bash
cargo check
```
Expected: no errors

**Verification:** leakguard and regex are in Cargo.lock, `cargo check` passes.

---

## Task 3: Find the content sanitization pipeline

**Objective:** Locate where rusty-imap-mcp sanitizes email content before returning to MCP client.

**Steps:**

1. Search for the security/sanitization code:
```bash
grep -r "strip_html\|sanitize\|injection\|sanitization" --include="*.rs" -l
```

2. Read the security module:
```bash
# Look for files like:
# crates/rimap-security/src/lib.rs
# crates/rimap-core/src/security.rs
# src/security/sanitizer.rs
find . -name "*.rs" | xargs grep -l "prompt_injection\|html_strip\|unicode" | head -10
```

3. Read the file that contains the content pipeline — the function that takes raw email text and applies HTML strip, unicode norm, injection detection.

4. Identify the exact function where PII redaction should be inserted (after HTML/unicode cleanup, before returning to caller).

**Verification:** Found the pipeline function. Understand the flow: raw email → HTML strip → unicode norm → injection check → [HERE: PII redact] → return.

---

## Task 4: Add PII redaction to the pipeline

**Objective:** Insert leakguard PII redaction + Russian custom detectors into the existing sanitization pipeline.

**Files:**
- Modify: The security/sanitization module found in Task 3

**Step 1: Create a PII redactor module**

Create a new file (e.g., `crates/rimap-security/src/pii.rs` or similar):

```rust
//! PII detection and redaction for email content.
//!
//! Uses leakguard for international PII patterns plus custom detectors
//! for Russian-specific data (phones, OTP context, password text).

use leakguard::{Redactor, Kind, detectors::FnDetector, Match};
use regex::Regex;

/// Create a redactor with all needed detectors.
pub fn create_email_redactor() -> Redactor {
    let mut redactor = Redactor::only(&[
        // International PII (language-agnostic)
        Kind::Email,
        Kind::CreditCard,
        Kind::UsSsn,
        Kind::AwsAccessKey,
        Kind::GitHubToken,
        Kind::SlackToken,
        Kind::StripeKey,
        Kind::OpenAiKey,
        Kind::GoogleApiKey,
        Kind::Jwt,
        Kind::PrivateKey,
        Kind::Iban,
        Kind::PhoneNumber,
        Kind::IpV4,
        Kind::IpV6,
        Kind::MacAddress,
        Kind::UrlCredentials,
    ]);

    // Russian phone numbers: +7 916 123-45-67, +7(916)123-45-67, 8 916 123 45 67
    let ru_phone_re = Regex::new(
        r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}"
    ).expect("valid regex");

    let russian_phone = FnDetector::new("RU_PHONE", move |input| {
        Ok(ru_phone_re.find_iter(input)
            .map(|m| Match { start: m.start(), end: m.end() })
            .collect())
    });

    // Russian OTP context: "код: 123456", "код подтверждения: 123456"
    let ru_otp_re = Regex::new(
        r"(?i)(?:код|пароль|token)\s*(?:подтверждения|для входа|для регистрации)?\s*[:=]?\s*(\d{4,8})"
    ).expect("valid regex");

    let russian_otp = FnDetector::new("RU_OTP", move |input| {
        Ok(ru_otp_re.find_iter(input)
            .map(|m| Match { start: m.start(), end: m.end() })
            .collect())
    });

    // Russian password context: "пароль: xxx", "ваш пароль xxx"
    let ru_pass_re = Regex::new(
        r"(?i)(?:пароль|пароли|password)\s*[:=]?\s*\S+"
    ).expect("valid regex");

    let russian_password = FnDetector::new("RU_PASSWORD", move |input| {
        Ok(ru_pass_re.find_iter(input)
            .map(|m| Match { start: m.start(), end: m.end() })
            .collect())
    });

    redactor = redactor
        .with_detector(russian_phone)
        .with_detector(russian_otp)
        .with_detector(russian_password);

    redactor
}

/// Redact PII from email text.
pub fn redact_pii(text: &str) -> String {
    let redactor = create_email_redactor();
    redactor.clean(text)
}
```

**Step 2: Call redact_pii in the existing pipeline**

In the sanitization function found in Task 3, add one line after the existing cleanup:

```rust
// Existing code:
// let cleaned = strip_html(raw_body);
// let cleaned = normalize_unicode(&cleaned);
// let warnings = detect_injection(&cleaned);

// ADD THIS LINE:
let cleaned = pii::redact_pii(&cleaned);

// Continue with existing code...
```

**Step 3: Verify it compiles**

```bash
cargo build --release
```

**Step 4: Test with sample email**

Create a test file:
```bash
cat > /tmp/test-email.txt << 'EOF'
Subject: Your verification code

Hello,

Your verification code is: 847291

API Key: sk-proj-abc123def456ghi789jkl012mno345pqr678stu901vwx234
Contact me at: user@example.com
Phone: +7 916 123-45-67
Card: 4111 1111 1111 1111
Password: mysecretpassword123
JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U

С уважением,
Иван
EOF
```

Run the binary with test input and verify PII is redacted.

**Verification:** Binary compiles. Test email shows redacted output:
- `847291` → `[OTP_REDACTED]` or kept (depends on context)
- `sk-proj-...` → `[REDACTED]`
- `user@example.com` → `[EMAIL_REDACTED]`
- `+7 916 123-45-67` → `[PHONE_REDACTED]`
- `4111 1111 1111 1111` → `[CREDIT_CARD_REDACTED]`
- `mysecretpassword123` → `[PASSWORD_REDACTED]`
- `eyJ...` → `[JWT_REDACTED]`

---

## Task 5: Create configuration

**Objective:** Write the rusty-imap-mcp config for Gmail.

**Files:**
- Create: `/var/lib/hermes/rusty-imap/config.toml`

**Content:**

```toml
[server]
mode = "stdio"

[[accounts]]
name = "gmail"
host = "imap.gmail.com"
port = 993
encryption = "tls"
username = "likivik@gmail.com"
# Password will be prompted on first run or set via env:
# RUSTY_IMAP_GMAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx

[security]
default_posture = "draft-safe"
strip_html = true
strip_quoted_replies = true
strip_signatures = true
sanitize_prompt_injection = true

[security.tools]
export_messages = "allow"

[audit]
enabled = true
path = "/var/lib/hermes/rusty-imap/audit.jsonl"

[rate_limits]
requests_per_minute = 100
```

**Steps:**

1. Create directory:
```bash
mkdir -p /var/lib/hermes/rusty-imap
```

2. Write config (content above)

3. Test with dry-run:
```bash
RUSTY_IMAP_GMAIL_PASSWORD=YOUR_APP_PASSWORD \
  /var/lib/hermes/rusty-imap-fork/target/release/rusty-imap-mcp \
  --config /var/lib/hermes/rusty-imap/config.toml --dry-run
```
Expected: connection test passes

**Verification:** Config is valid, dry-run connects to Gmail.

---

## Task 6: Create NixOS module

**Objective:** Package the forked binary as a NixOS service.

**Files:**
- Create: `/etc/nixos/modules/services/rusty-imap/default.nix`

**NixOS module content:**

```nix
{ config, lib, pkgs, ... }:

let
  cfg = config.services.rusty-imap;
in {
  options.services.rusty-imap = {
    enable = lib.mkEnableOption "rusty-imap-mcp email proxy for Hermes";
    
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.rusty-imap-mcp-fork;
      description = "rusty-imap-mcp package (forked with PII redaction)";
    };

    gmail-user = lib.mkOption {
      type = lib.types.str;
      default = "likivik@gmail.com";
      description = "Gmail address";
    };

    config-path = lib.mkOption {
      type = lib.types.path;
      default = "/var/lib/hermes/rusty-imap/config.toml";
      description = "Path to rusty-imap-mcp config";
    };
  };

  config = lib.mkIf cfg.enable {
    # Create directories
    systemd.tmpfiles.rules = [
      "d /var/lib/hermes/rusty-imap 0755 hermes hermes -"
      "d /var/lib/hermes/rusty-imap/attachments 0755 hermes hermes -"
    ];

    # rusty-imap-mcp service
    systemd.services.rusty-imap-mcp = {
      description = "rusty-imap-mcp email server with PII redaction";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];
      
      serviceConfig = {
        User = "hermes";
        Group = "hermes";
        ExecStart = "${cfg.package}/bin/rusty-imap-mcp --config ${cfg.config-path}";
        Restart = "on-failure";
        RestartSec = 5;
        
        # Security hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [ "/var/lib/hermes/rusty-imap" ];
        PrivateTmp = true;
        
        # Network access (IMAP only)
        IPAddressAllow = [
          "142.250.0.0/15"  # Google
          "172.217.0.0/16"  # Google
        ];
        IPAddressDeny = "any";
        
        Environment = [
          "RUST_LOG=info"
        ];
      };
    };
  };
}
```

**Steps:**

1. Create module directory:
```bash
mkdir -p /etc/nixos/modules/services/rusty-imap
```

2. Write the NixOS module (content above)

3. Build the forked package as a Nix derivation (add to overlays or local packages):
```nix
# In overlays or packages:
rusty-imap-mcp-fork = pkgs.rustPlatform.buildRustPackage {
  pname = "rusty-imap-mcp-fork";
  version = "0.1.0";
  src = /var/lib/hermes/rusty-imap-fork;
  cargoLock.lockFile = /var/lib/hermes/rusty-imap-fork/Cargo.lock;
  
  buildInputs = [ pkgs.dbus ];
  
  meta = with pkgs.lib; {
    description = "rusty-imap-mcp fork with PII redaction";
    license = licenses.mit;
  };
};
```

4. Add module to erebus host configuration

5. Test NixOS evaluation:
```bash
nix build .#nixosConfigurations.erebus.config.system.build.toplevel --dry-run
```

**Verification:** NixOS module is valid, package builds, service starts.

---

## Task 7: Configure Hermes MCP connection

**Objective:** Tell Hermes how to connect to rusty-imap-mcp as MCP server.

**Files:**
- Modify: `~/.hermes/config.yaml`

**Config to add:**

```yaml
mcp:
  servers:
    email:
      command: "/var/lib/hermes/rusty-imap-fork/target/release/rusty-imap-mcp"
      args: ["--config", "/var/lib/hermes/rusty-imap/config.toml"]
      env:
        RUSTY_IMAP_GMAIL_PASSWORD: "YOUR_APP_PASSWORD_HERE"
```

**Steps:**

1. Add MCP server config to Hermes
2. Set Gmail App Password (from Prerequisites)
3. Restart Hermes

**Verification:** Hermes can call MCP tools from email server.

---

## Task 8: End-to-end test

**Objective:** Verify full pipeline works.

**Steps:**

1. Start service:
```bash
systemctl start rusty-imap-mcp
```

2. Test MCP connection:
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | \
  /var/lib/hermes/rusty-imap-fork/target/release/rusty-imap-mcp \
  --config /var/lib/hermes/rusty-imap/config.toml
```
Expected: list of 24 tools

3. Test email search:
```bash
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"search","arguments":{"query":"from:github"}}}' | \
  /var/lib/hermes/rusty-imap-fork/target/release/rusty-imap-mcp \
  --config /var/lib/hermes/rusty-imap/config.toml
```
Expected: search results

4. Verify PII redaction — check that API keys, emails, phone numbers in results are redacted

5. Test from Hermes:
```
Hermes: "List my recent emails from the last 24 hours"
Expected: Hermes lists emails, PII is redacted in the response
```

**Verification:** Full pipeline works end-to-end.

---

## Files created/modified

| File | Action |
|---|---|
| `/var/lib/hermes/rusty-imap-fork/` | Clone + modify |
| `/var/lib/hermes/rusty-imap-fork/crates/rimap-security/src/pii.rs` | Create (PII redaction module) |
| `/var/lib/hermes/rusty-imap-fork/Cargo.toml` | Modify (add leakguard + regex) |
| `/var/lib/hermes/rusty-imap/config.toml` | Create |
| `/etc/nixos/modules/services/rusty-imap/default.nix` | Create |
| `~/.hermes/config.yaml` | Modify (add MCP server) |

## What's different from the previous plan

| Before (Python proxy) | After (Rust fork) |
|---|---|
| Two processes (proxy + rusty) | One binary |
| Python venv + privatiser | leakguard (zero deps) |
| MCP protocol interception | PII redaction in existing pipeline |
| Threading/concurrency issues | None — single process |
| ~100 lines Python proxy | ~50 lines Rust |
| Debug two systems | Debug one system |
| Separate deployment | Single NixOS service |

## Risks and tradeoffs

| Risk | Mitigation |
|---|---|
| Fork diverges from upstream | Pin to specific release tag, merge upstream periodically |
| leakguard may miss some PII | Custom detectors for known gaps, test with real emails |
| Gmail App Password expires | Future: OAuth2 support |
| No ML injection detection | regex is sufficient for 90%+ of attacks |
| Single binary = single point of failure | systemd restart on crash |

## Future improvements

1. **Merge upstream changes** — periodically pull from randomparity/rusty-imap-mcp
2. **OAuth2 for Gmail** — more secure than App Password
3. **ML injection detection** — add prompt-guard tier 2
4. **Dashboard** — web UI for viewing redacted emails
5. **Approval gate for delete** — ntfy notification before destructive actions
6. **More Russian detectors** — INN, SNILS if needed
