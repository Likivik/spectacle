"""Pure, framework-free logic for the HR intake quiz.

No aiogram imports here on purpose: every function works on plain dicts, so
it is unit-testable without a token, network, or the aiogram dependency (and
therefore also runs in the nix flake-check python quickly).

The aiogram layer (hr_bot.py) is a thin FSM wrapper over these functions.
State shape (the "data" dict stored in FSM context):
  {
    "name": str, "username": str, "started": float,
    "answers": {"q1": str, "q2": str, ...},   # q1/q2 answered; q3 added at contact
    "extra": str,                               # optional resume/about, done phase
    "done": bool,
  }
"""

import html
import json
import os
import re
import time
from collections import deque

OWNER = 662542089

VACANCY = (
    "🏢 <b>Менеджер проекта «Счётчики тепла»</b> · удалённо · СПб\n\n"
    "Цель: чтобы в помещениях стояли счётчики тепла и РСО принимали "
    "показания. Работа из дома — звонки, переписка, согласования.\n\n"
    "<b>Что делать:</b>\n"
    "📞 звонить в УК — согласовать установку (список и контакты готов)\n"
    "🔧 найти монтажников, согласовать время и цену\n"
    "📨 заявки в ТеплоЭнерго / ГУП ТЭК / ТГК-1 — пломбировка и ввод\n"
    "📊 вести таблицу по помещениям, напоминать службам о себе\n\n"
    "<b>Оплата:</b> от 10 000 ₽ за проект + по времени, по договорённости. "
    "Самозанятость — плюс. Если пойдёт хорошо — продолжим.\n\n"
    "3 коротких вопроса — минута. Поехали 👇"
)

# (qid, text, choices)
QUESTIONS = [
    ("q1", "Оплата: проект от 10 000 ₽, далее по затраченному времени и усилиям — подходит такой формат?",
     ["Да, подходит", "Хочу фиксированную оплату", "Обсудим"]),
    ("q2", "Был ли у вас опыт звонков и договорённостей с УК, ЖЭК, ТСЖ или ресурсоснабжающими организациями (ТеплоЭнерго, ГУП ТЭК, ТГК-1)?",
     ["Да, был", "Не было, но разберусь"]),
]

CONTACT_PROMPT = (
    "Как с вами лучше связаться?\n\n"
    "И если хотите — следующим сообщением дополните о себе "
    "или пришлите резюме (файлом или текстом). Это необязательно."
)


def new_state(name, username):
    return {
        "name": name,
        "username": username or "",
        "started": time.time(),
        "answers": {},
        "extra": "",
        "done": False,
    }


def is_done(st) -> bool:
    return bool(st.get("done"))


def answered_pay(st) -> bool:
    return "q1" in st.get("answers", {})


def answered_exp(st) -> bool:
    return "q2" in st.get("answers", {})


def answers_complete(st) -> bool:
    """All required questions (q1..q2) answered."""
    a = st.get("answers", {})
    return all(q in a for q, _, _ in QUESTIONS)


def record_answer(st, qid, value) -> None:
    """Record one answered question (q1/q2 from buttons or free-text)."""
    st.setdefault("answers", {})[qid] = value


_phone_re = re.compile(r"^\+?\d[\d\s()\-]{8,}$")


def is_valid_contact(text: str) -> bool:
    t = text.strip()
    if t.startswith("@") and len(t) > 1:
        return True
    digits = re.sub(r"[^\d]", "", t)
    return bool(_phone_re.match(t)) and len(digits) >= 10


def make_card(st, pid) -> str:
    a = st.get("answers", {})
    name = st.get("name", "")
    uname = ("@" + st["username"]) if st.get("username") else ""
    phone = a.get("q3", "")
    if phone and phone != "только Telegram":
        contact_line = f"Связь: 📞 {phone}"
    else:
        contact_line = "Связь: ✈️ Telegram (этот чат)"
    return (
        "📋 <b>АНКЕТА КАНДИДАТА</b>\n"
        f"Имя: {html.escape(name)} {html.escape(uname)} (tg_id {pid})\n"
        f"Оплата: {html.escape(str(a.get('q1', '—')))}\n"
        f"Опыт с УК/РСО: {html.escape(str(a.get('q2', '—')))}\n"
        f"{html.escape(contact_line)}"
    )


def make_record(st, pid) -> dict:
    return {
        "ts": time.time(),
        "tg_id": pid,
        "name": st.get("name", ""),
        "username": st.get("username", ""),
        "answers": st.get("answers", {}),
    }


def write_candidate(data_path, st, pid) -> None:
    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    # 0600: candidate phones/names are PII — never world-readable.
    fd = os.open(data_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(json.dumps(make_record(st, pid), ensure_ascii=False) + "\n")


def make_extra_notice(st, pid) -> str:
    """Owner alert for the resume/extra payload. HTML-escaped — this goes
    into a parse_mode=HTML message, and both the display name and the extra
    (which includes user text AND uploaded file_name, both attacker-controlled)
    must never render as markup/HREFs in the owner's DM."""
    name = st.get("name", "")
    extra = st.get("extra", "").strip()
    safe = html.escape(f"📎 От кандидата {name}:"[:600]) + "\n\n" + html.escape(extra[:3500])
    return safe


def append_extra(st, text_or_fragment) -> None:
    st["extra"] = (st.get("extra", "") + "\n" + text_or_fragment).strip()


class RateLimiter:
    """Per-user sliding-window throttle (in-memory, best-effort)."""

    def __init__(self, limit: int = 8, window: float = 60.0):
        self.limit = limit
        self.window = window
        self._hits = {}  # user -> deque[timestamps]

    def allow(self, user, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        q = self._hits.setdefault(user, deque())
        # drop old timestamps outside the window
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True

