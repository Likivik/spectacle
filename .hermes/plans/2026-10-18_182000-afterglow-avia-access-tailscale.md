# afterglow-avia: доступ, tailscale, деплой

**Цель:** закрепить доступ с Serenity на afterglow-avia и починить шум KTailctl — сделать всё постоянным через один деплой хоста.

**Хост:** `afterglow-avia` — NixOS-моноблок солярия, KKM ATOL 30F + kkmserver 2.2.17.22 + PAX S300. Tailnet `oryx-galaxy.ts.net`, IP `100.92.209.16`, железо i3-6006U / 7.6 ГБ / SSD DEXP C100 256 ГБ.

**Тайм-бокс:** 30–50 мин на деплой (сборка на самой машине), +5–10 мин на пост-проверки. Если nixpkgs-ревизия не в кэше Hydra — до нескольких часов, тогда стоп и отдельное решение.

---

## Состояние на 2026-10-18 18:30 MSK

### Уже сделано

| Что | Где | Статус |
|---|---|---|
| Доступ Serenity → `likivik@afterglow-avia` | ключ дописан в `/etc/ssh/authorized_keys.d/likivik` (рантайм) | ✅ работает |
| То же декларативно | `modules/hosts/afterglow-avia/afterglow-avia.nix` — `hermes@serenity` в `openssh.authorizedKeys.keys` | ✅ в репе, ⏳ не задеплоено |
| KTailctl перестал спамить | `tailscale set --operator=solarium` (рантайм) | ✅ спам 0 (было ~24/мин) |
| То же декларативно | `afterglow-avia.nix` — `services.tailscale.extraUpFlags = lib.mkForce [ "--operator=solarium" "--accept-routes=true" ]` | ✅ в репе, ⏳ не задеплоено |

### Что диагностика показала

- **I/O в норме.** `/proc/pressure/io` = 5,1 % за 8 ч аптайма; `vmstat` wa 0–2 %, 92–95 % idle. Первые 60–86 % avg300 были артефактом собственного грепа по 509 МБ журнала.
- **Tailscale здоров, но старый:** 1.98.10, актуальная — 1.104.1 (2026-10-07). Прямой коннект, UDP ok, DERP Warsaw 33 мс.
- **Система отстала:** текущая генерация собрана 2026-07-30, ядро 6.18.40 против 6.18.55 во флоте.
- **Мусор:** `/var/lib/kkmserver/.atol/drivers10/logs/uem_bridge-KKT2.log` = **447 МБ**, не ротируется. `/var/log/epc` = 59 МБ.
- **`fwupd-refresh.timer`** каждые ~1 ч 20 мин падает по 60-секундному таймауту (lvfs metadata).
- **KTailctl 0.22.1** (актуальная 0.22.3) — версия не причина, причина была в `--operator`.

---

## План

### Task 1 — Прочитать изменения перед деплоем (2 мин)

```bash
jj diff modules/hosts/afterglow-avia/afterglow-avia.nix
```

Ожидаем ровно два блока: ключ `hermes@serenity` в `users.users.likivik.openssh.authorizedKeys.keys` и блок `extraUpFlags` с `--operator=solarium`.

⚠ В рабочей копии jj лежат **чужие незакоммиченные правки** (`.hermes/`, `notes/`, `research/`, `modules/users/likivik/dotfiles/git/config` + `.bak`). Они уедут в деплой вместе с нашими. Проверить, что это ок, либо разложить по отдельным изменениям через `jj new`.

### Task 2 — Dry-build (10–15 мин)

```bash
hostname -s                       # должно быть serenity
nix build .#nixosConfigurations.afterglow-avia.config.system.build.toplevel --dry-run
```

Ожидаем: эвалюация проходит, в списке будет собранное vs скачанное. Зафиксировать, меняется ли ядро (6.18.40 → 6.18.55) и версии ATOL-драйверов/kkmserver.

Стоп-условие: если в dry-run видно много `will be built` для kkmserver/ATOL — не деплоить, сначала проверить кэш Hydra.

### Task 3 — Проверка кэша Hydra (5 мин, только если Task 2 показал source-build)

```bash
nix run nixpkgs#hydra-check -- kkmserver
```

Если версии не совпадают с флейком → ожидать сборку из исходников, перенести деплой.

### Task 4 — Зафиксировать и запушить (2 мин)

```bash
jj describe -m "afterglow-avia: serenity ssh access + tailscale operator=solarium"
jj bookmark set dev -r @
jj git push --all
```

### Task 5 — Деплой (30–50 мин)

Запускать **с Serenity** (доступ теперь прямой):

```bash
nixos-rebuild switch --flake .#afterglow-avia \
  --build-host likivik@afterglow-avia \
  --target-host likivik@afterglow-avia \
  --elevate=sudo
```

⚠ Это НЕ serenity, поэтому `sudo systemd-run`-обёртка из AGENTS.md не нужна — она только для локального хоста. `--build-host` = `--target-host` = сама машина (каждый хост собирает свой клоужер).

⚠ **Солярий должен быть закрыт.** Бамп nixpkgs меняет ядро; `switch` активирует только userspace, модули ядра (в т.ч. USB/serial для PAX S300) подхватятся лишь после перезагрузки → хост в половинчатом состоянии до ребута.

### Task 6 — Перезагрузка (5 мин)

```bash
ssh likivik@afterglow-avia 'sudo systemctl reboot'
```

Затем дождаться возврата и проверить, что касса жива (Task 7). Если касса не поднялась — откат через GRUB на предыдущую генерацию.

### Task 7 — Пост-проверки (10 мин)

```bash
# доступ
ssh -o BatchMode=yes likivik@afterglow-avia 'hostname; whoami; sudo -n true && echo sudo-ok'

# tailscale
ssh likivik@afterglow-avia 'tailscale version; tailscale status | head -3; tailscale debug prefs | grep -i operator'
# ожидаем: 1.104.x, BackendState Running, OperatorUser = solarium

# шум в журнале (окно 2 мин)
ssh likivik@afterglow-avia 'sudo journalctl --since "2 min ago" | grep -c "profiles access denied"'
# ожидаем: 0

# касса
ssh likivik@afterglow-avia 'systemctl is-active kkmserver; systemctl --failed --no-pager'
# ожидаем: active, и никаких failed кроме известного fwupd-refresh

# ядро
ssh likivik@afterglow-avia 'uname -r'
```

### Task 8 — Мелкий мусор (отдельно, 10 мин)

1. Подрезать ATOL-лог и завести ротацию:
   ```bash
   ssh likivik@afterglow-avia 'sudo ls -la /var/lib/kkmserver/.atol/drivers10/logs/'
   # решение: truncate + logrotate-правило или настройка самого драйвера ATOL
   ```
2. `fwupd-refresh`: либо `services.fwupd.enable = false`, либо оставить (вреда нет, 60 с раз в час).
3. Опционально: поднять уровень логирования KTailctl (сейчас ~74 строки/мин обычного info).

---

## Файлы, которые меняются

- `modules/hosts/afterglow-avia/afterglow-avia.nix` — уже изменён (ключ + operator)

## Риски

| Риск | Митигация |
|---|---|
| Бамп ядра → нужен ребут, касса встаёт | только после закрытия солярия; откат через GRUB |
| Сборка из исходников на i3-6006U (часы) | Hydra-чек в Task 3 |
| Чужие незакоммиченные правки уедут в деплой | проверить `jj diff` в Task 1, при необходимости `jj new` |
| Обновление ATOL-драйвера ломает KKM | сверить версии в dry-run; при сомнении отложить |
| Потеря доступа, если ключ не применится | рантайм-ключ уже работает; NixOS-генерации позволяют откат |

## Открытые вопросы

1. Деплоим сегодня после 22:00 или откладываем до окна подлиннее?
2. Ребут кассы — согласован с владельцем солярия?
3. `fwupd` гасим или оставляем?
4. Чужие правки в рабочей копии jj — коммитить вместе или разделить?
