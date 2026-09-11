#!/usr/bin/env python3
"""HR intake bot: @Likivik_Telegram_Assistant_Bot (aiogram 3 FSM).

Collects a candidate questionnaire, appends each completed form to
/var/lib/hr-bot/candidates.jsonl and notifies the owner (662542089).

Architecture:
  * engine.py — pure, framework-free logic (state transitions, validation,
    card building, persistence). Fully unit-tested without aiogram.
  * this module — thin aiogram 3 FSM wrapper: aiogram's StatesGroup handles
    per-user state isolation and route gating (a callback/message only fires
    in its registered state), which removes the hand-rolled step/guard bugs.
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, KeyboardButton, Message,
                           ReplyKeyboardMarkup, ReplyKeyboardRemove)

import engine

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hr-bot")

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DATA = "/var/lib/hr-bot/candidates.jsonl"


class Quiz(StatesGroup):
    pay = State()       # q1  (awaiting pay-format answer)
    exp = State()       # q2  (awaiting experience answer)
    contact = State()   # q3  (awaiting phone or telegram choice)
    extra = State()     # done — optional resume/about, /done to finish


def _q_kb(i):
    _, text, opts = engine.QUESTIONS[i]
    rows = [[InlineKeyboardButton(text=o, callback_data=str(i) + ":" + o)] for o in opts]
    rows.append([InlineKeyboardButton(text="✏️ Свой ответ", callback_data=str(i) + ":free")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _contact_kb():
    rows = [[
        InlineKeyboardButton(text="📱 По телефону", callback_data="contact:phone"),
        InlineKeyboardButton(text="✈️ В Telegram", callback_data="contact:tg"),
    ]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _notify(bot, text):
    await bot.send_message(engine.OWNER, text, parse_mode="HTML")


async def _do_finish(bot, message, state, pid):
    st = await state.get_data()
    engine.write_candidate(DATA, st, pid)
    try:
        await message.answer(
            "Спасибо! Анкета заполнена. Кирилл скоро свяжется с вами.\n"
            "Последним сообщением можете добавить что-то от себя или закинуть резюме (не обязательно).",
            reply_markup=ReplyKeyboardRemove())
    except Exception as e:
        log.warning("finish answer failed: %s", e)
    try:
        await _notify(bot, engine.make_card(st, pid))
    except Exception as e:
        log.warning("notify failed: %s", e)
    st["done"] = True
    await state.update_data(**st)
    await state.set_state(Quiz.extra)


# Dispatch setup
bot = Bot(TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Per-user inbound throttle (best-effort; full allowlist would defeat hiring).
_limiter = engine.RateLimiter(limit=10, window=60.0)


@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    # Throttle new intakes per user so a single account can't flood leads.
    if not _limiter.allow(m.from_user.id):
        await m.answer("Слишком много запросов. Подождите немного и попробуйте снова.")
        return
    st = engine.new_state(m.from_user.full_name, m.from_user.username or "")
    await state.set_data(st)
    await state.set_state(Quiz.pay)
    await m.answer(engine.VACANCY, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    i, text, _ = engine.QUESTIONS[0]
    await m.answer(text, reply_markup=_q_kb(0))


@dp.message(Command("cancel"))
async def cancel(m: Message, state: FSMContext):
    if await state.get_state() is not None:
        await state.clear()
        await m.answer("Отменено. Напишите /start, если захотите попробовать ещё раз.")
    else:
        await m.answer("Нечего отменять.")


# ── q1 (pay) ───────────────────────────────────────────────────────────
@dp.callback_query(Quiz.pay, F.data.startswith("0:"))
async def q1_answer(c: CallbackQuery, state: FSMContext):
    await c.answer()
    val = c.data.split(":", 1)[1]
    st = await state.get_data()
    if val == "free":
        await c.message.answer("Напишите ваш ответ следующим сообщением.")
        return  # stay in Quiz.pay; a free-text handler below advances
    engine.record_answer(st, "q1", val)
    await state.update_data(**st)
    await state.set_state(Quiz.exp)
    await c.message.answer("И второй вопрос:", )
    await c.message.answer(engine.QUESTIONS[1][1], reply_markup=_q_kb(1))


@dp.message(Quiz.pay, F.text)
async def q1_text(m: Message, state: FSMContext):
    st = await state.get_data()
    engine.record_answer(st, "q1", m.text)
    await state.update_data(**st)
    await state.set_state(Quiz.exp)
    await m.answer(engine.QUESTIONS[1][1], reply_markup=_q_kb(1))


# ── q2 (exp) ───────────────────────────────────────────────────────────
@dp.callback_query(Quiz.exp, F.data.startswith("1:"))
async def q2_answer(c: CallbackQuery, state: FSMContext):
    await c.answer()
    val = c.data.split(":", 1)[1]
    st = await state.get_data()
    if val == "free":
        await c.message.answer("Напишите ваш ответ следующим сообщением.")
        return
    engine.record_answer(st, "q2", val)
    await state.update_data(**st)
    await state.set_state(Quiz.contact)
    await c.message.answer(engine.CONTACT_PROMPT, reply_markup=_contact_kb())


@dp.message(Quiz.exp, F.text)
async def q2_text(m: Message, state: FSMContext):
    st = await state.get_data()
    engine.record_answer(st, "q2", m.text)
    await state.update_data(**st)
    await state.set_state(Quiz.contact)
    await m.answer(engine.CONTACT_PROMPT, reply_markup=_contact_kb())


# ── contact (q3) ───────────────────────────────────────────────────────
@dp.callback_query(Quiz.contact, F.data.startswith("contact:"))
async def q3_answer(c: CallbackQuery, state: FSMContext):
    await c.answer()
    st = await state.get_data()
    if c.data == "contact:phone":
        await c.message.answer(
            "Нажмите кнопку «📱 Поделиться номером» внизу — Telegram передаст номер одним нажатием.\n"
            "Или просто напишите номер текстом в формате +7XXXXXXXXXX.")
        await c.message.answer(
            "📱 Поделиться номером",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
                resize_keyboard=True, one_time_keyboard=True))
        return  # stay in Quiz.contact; contact/text handler below advances
    if c.data == "contact:tg":
        engine.record_answer(st, "q3", "только Telegram")
        await state.update_data(**st)
        await _do_finish(bot, c.message, state, c.from_user.id)


@dp.message(Quiz.contact, F.contact)
async def q3_contact(m: Message, state: FSMContext):
    st = await state.get_data()
    engine.record_answer(st, "q3", m.contact.phone_number)
    await state.update_data(**st)
    await _do_finish(bot, m, state, m.from_user.id)


@dp.message(Quiz.contact, F.text)
async def q3_text(m: Message, state: FSMContext):
    txt = m.text.strip()
    if not engine.is_valid_contact(txt):
        await m.answer(
            "Это не похоже на телефон или @username. Нажмите кнопку «📱 По телефону» "
            "или «✈️ В Telegram» выше, либо пришлите номер в формате +7...")
        return
    st = await state.get_data()
    engine.record_answer(st, "q3", txt)
    await state.update_data(**st)
    await _do_finish(bot, m, state, m.from_user.id)


# ── extra (done) — optional resume/about ───────────────────────────────
@dp.message(Quiz.extra, F.text)
async def extra_text(m: Message, state: FSMContext):
    st = await state.get_data()
    if m.text.strip() == "/done":
        await _do_close(bot, m, state, m.from_user.id)
        return
    engine.append_extra(st, m.text)
    await state.update_data(**st)
    await m.answer("Принято ✅ Кирилл получит это вместе с анкетой. "
                   "Ещё что-то добавить — пишите, /done — закончить.")


@dp.message(Quiz.extra, F.document)
async def extra_doc(m: Message, state: FSMContext):
    st = await state.get_data()
    d = m.document
    fname = d.file_name or "файл"
    engine.append_extra(st, f"[Резюме/файл: {fname}, file_id={d.file_id}]")
    await state.update_data(**st)
    await m.answer(f"Файл «{fname}» принят ✅ /done — закончить.")


async def _do_close(bot_, m, state, pid):
    st = await state.get_data()
    extra = st.get("extra", "").strip()
    if extra:
        try:
            await _notify(bot_, engine.make_extra_notice(st, pid))
        except Exception as e:
            log.warning("close notify failed: %s", e)
    await state.clear()
    await m.answer("Готово, спасибо!")
    log.info("closed %s", pid)


# Catch-all for any stray input while a valid user is mid-quiz
@dp.message()
async def unknown(m: Message, state: FSMContext):
    if m.from_user.id == engine.OWNER:
        return
    st = await state.get_data()
    if not st:
        await m.answer("Нажмите /start, чтобы откликнуться на вакансию.")
        return
    if not st.get("done") and (engine.answered_pay(st) or engine.answered_exp(st)):
        await m.answer("Ответьте на вопрос, нажав кнопку выше.")
    else:
        await m.answer("Нажмите /start, чтобы откликнуться на вакансию.")


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
