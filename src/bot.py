import re
import warnings

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters,
)

from src.config import settings, log
from src import database, ai_filter

# ConversationHandler states
WAITING_REPLY = 1

_app: Application = None


def _escape_md(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', str(text))


def _vacancy_card_text(v) -> str:
    title = _escape_md(v.title)
    company = _escape_md(v.company or "Не указана")
    salary = _escape_md(v.salary or "Не указана")
    city = _escape_md(v.city or "Не указан")
    score = v.relevance_score
    reason = _escape_md(v.relevance_reason or "")
    cover = "Сопроводительное сгенерировано" if v.cover_letter else "Без сопроводительного"

    return (
        f"*{title}*\n"
        f"{'─' * 20}\n"
        f"Компания: *{company}*\n"
        f"Зарплата: {salary}\n"
        f"Город: {city}\n\n"
        f"Релевантность: *{score}/100*\n"
        f"_{reason}_\n\n"
        f"_{_escape_md(cover)}_"
    )


def _vacancy_keyboard(vacancy_id: int, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Откликнуться", callback_data=f"apply:{vacancy_id}"),
            InlineKeyboardButton("Пропустить", callback_data=f"skip:{vacancy_id}"),
        ],
        [
            InlineKeyboardButton("Открыть на сайте", url=url),
        ],
    ])


def _message_card_text(msg) -> str:
    company = _escape_md(msg.company or "Не указана")
    vacancy = _escape_md(msg.vacancy_title or "Не указана")
    sender = _escape_md(msg.sender or "Работодатель")
    text = _escape_md(msg.text or "")

    return (
        f"*Новое сообщение от работодателя*\n"
        f"{'─' * 20}\n"
        f"Компания: *{company}*\n"
        f"Вакансия: {vacancy}\n\n"
        f"*{sender}:*\n"
        f"{text}"
    )


def _message_keyboard(conversation_id: str, url: str = None) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("Ответить", callback_data=f"reply:{conversation_id}"),
            InlineKeyboardButton("AI-ответ", callback_data=f"ai_reply:{conversation_id}"),
        ],
    ]
    if url:
        buttons.append([InlineKeyboardButton("Открыть", url=url)])
    return InlineKeyboardMarkup(buttons)


# ─── Send functions ──────────────────────────────

async def send_vacancy_card(vacancy):
    if not _app:
        return
    text = _vacancy_card_text(vacancy)
    keyboard = _vacancy_keyboard(vacancy.id, vacancy.url)
    await _app.bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="MarkdownV2",
    )


async def send_message_card(msg, vacancy=None):
    if not _app:
        return
    text = _message_card_text(msg)
    conv_id = msg.conversation_id or msg.message_id
    url = f"https://rabota.by/applicant/responses/{conv_id}" if conv_id else None
    keyboard = _message_keyboard(conv_id, url)
    await _app.bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
        reply_markup=keyboard,
        parse_mode="MarkdownV2",
    )


async def send_text(text: str):
    if not _app:
        return
    await _app.bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
    )


# ─── Command handlers ───────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Rabota Hunter Bot\n\n"
        "Команды:\n"
        "/stats - статистика\n"
        "/search - запустить парсинг сейчас\n"
        "/last - последние 5 вакансий\n"
        "/inbox - непрочитанные сообщения\n"
        "/threads - активные переписки"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await database.get_stats()
    await update.message.reply_text(
        f"Статистика:\n"
        f"Всего вакансий: {stats['total']}\n"
        f"Отправлено в TG: {stats['sent_to_tg']}\n"
        f"Откликов: {stats['applied']}\n"
        f"Откликов сегодня: {stats['today_applied']}"
    )


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vacancies = await database.get_last_vacancies(5)
    if not vacancies:
        await update.message.reply_text("Вакансий пока нет.")
        return
    for v in vacancies:
        text = (
            f"{v.title}\n"
            f"Компания: {v.company or 'N/A'}\n"
            f"Релевантность: {v.relevance_score}/100\n"
            f"Статус: {v.status}\n"
            f"{v.url}"
        )
        await update.message.reply_text(text)


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Запускаю парсинг...")
    from src import pipeline
    await pipeline.run_pipeline()
    await update.message.reply_text("Парсинг завершён.")


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages = await database.get_unread_messages()
    if not messages:
        await update.message.reply_text("Нет непрочитанных сообщений.")
        return
    for msg in messages[:10]:
        text = (
            f"От: {msg.sender or msg.company or 'Работодатель'}\n"
            f"Вакансия: {msg.vacancy_title or 'N/A'}\n"
            f"{msg.text[:300]}"
        )
        await update.message.reply_text(text)


async def cmd_threads(update: Update, context: ContextTypes.DEFAULT_TYPE):
    convs = await database.get_active_conversations()
    if not convs:
        await update.message.reply_text("Нет активных переписок.")
        return
    lines = []
    for c in convs[:10]:
        status_icon = {"active": ">>", "waiting_reply": "??", "replied": "ok"}.get(c.status, "")
        lines.append(f"[{status_icon}] {c.company or 'N/A'} - {c.vacancy_title or 'N/A'}")
    await update.message.reply_text("Активные переписки:\n\n" + "\n".join(lines))


# ─── Callback handlers ──────────────────────────

async def callback_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vacancy_id = int(query.data.split(":")[1])

    today_count = await database.count_today_applies()
    if today_count >= settings.max_applies_per_day:
        await query.message.reply_text(
            f"Лимит откликов на сегодня ({settings.max_applies_per_day}) исчерпан."
        )
        return

    vacancy = await database.get_vacancy(vacancy_id)
    if not vacancy:
        await query.message.reply_text("Вакансия не найдена.")
        return

    await query.message.reply_text("Отправляю отклик...")

    from src import applier
    success, message = await applier.apply_to_vacancy(vacancy)

    if success:
        await database.update_status(vacancy_id, "applied")
        await query.message.reply_text(f"Отклик отправлен на: {vacancy.title}")
        # Убрать кнопки
        await query.edit_message_reply_markup(reply_markup=None)
    else:
        await database.update_status(vacancy_id, "error", message)
        await query.message.reply_text(f"Ошибка отклика: {message}")


async def callback_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    vacancy_id = int(query.data.split(":")[1])
    await database.update_status(vacancy_id, "skipped")
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Пропущено.")


# ─── Reply conversation ─────────────────────────

async def callback_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conversation_id = query.data.split(":")[1]
    context.user_data["reply_to"] = conversation_id
    await query.message.reply_text(
        "Напиши ответ работодателю:\n(/cancel для отмены)"
    )
    return WAITING_REPLY


async def receive_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    conversation_id = context.user_data.get("reply_to")
    if not conversation_id:
        await update.message.reply_text("Нет активной переписки.")
        return ConversationHandler.END

    context.user_data["reply_text"] = text

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Отправить", callback_data=f"send:{conversation_id}"),
            InlineKeyboardButton("Улучшить", callback_data=f"improve:{conversation_id}"),
        ],
        [
            InlineKeyboardButton("Отмена", callback_data=f"cancel_reply:{conversation_id}"),
        ],
    ])

    await update.message.reply_text(
        f"Твой ответ:\n\n{text}\n\nОтправить?",
        reply_markup=keyboard,
    )
    return ConversationHandler.END


async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("reply_to", None)
    context.user_data.pop("reply_text", None)
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END


async def callback_ai_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Генерирую ответ...")
    conversation_id = query.data.split(":")[1]

    history = await database.get_conversation_history(conversation_id)
    vacancy = await database.get_vacancy_by_conversation(conversation_id)

    ai_text = await ai_filter.generate_reply(vacancy, history)
    if not ai_text:
        await query.message.reply_text("Не удалось сгенерировать ответ.")
        return

    context.user_data["reply_to"] = conversation_id
    context.user_data["reply_text"] = ai_text

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Отправить", callback_data=f"send:{conversation_id}"),
            InlineKeyboardButton("Изменить", callback_data=f"reply:{conversation_id}"),
        ],
        [
            InlineKeyboardButton("Другой вариант", callback_data=f"ai_reply:{conversation_id}"),
        ],
    ])

    await query.message.reply_text(
        f"AI-ответ:\n\n{ai_text}\n\nОтправить?",
        reply_markup=keyboard,
    )


async def callback_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    conversation_id = query.data.split(":")[1]
    text = context.user_data.get("reply_text")

    if not text:
        await query.message.reply_text("Нет текста для отправки.")
        return

    from src import responder
    success, message = await responder.send_reply(conversation_id, text)

    if success:
        await database.save_outgoing_message(conversation_id, text)
        await query.message.reply_text("Ответ отправлен!")
        await query.edit_message_reply_markup(reply_markup=None)
    else:
        await query.message.reply_text(f"Ошибка: {message}")

    context.user_data.pop("reply_to", None)
    context.user_data.pop("reply_text", None)


async def callback_improve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Улучшаю текст...")
    conversation_id = query.data.split(":")[1]
    text = context.user_data.get("reply_text", "")

    improved = await ai_filter.improve_text(text)
    context.user_data["reply_text"] = improved

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Отправить", callback_data=f"send:{conversation_id}"),
            InlineKeyboardButton("Изменить", callback_data=f"reply:{conversation_id}"),
        ],
    ])

    await query.message.reply_text(
        f"Улучшенный текст:\n\n{improved}\n\nОтправить?",
        reply_markup=keyboard,
    )


async def callback_cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("reply_to", None)
    context.user_data.pop("reply_text", None)
    await query.edit_message_reply_markup(reply_markup=None)
    await query.message.reply_text("Отменено.")


# ─── App builder ─────────────────────────────────

def create_app() -> Application:
    global _app
    _app = Application.builder().token(settings.telegram_bot_token).build()

    # Reply conversation handler
    # per_message=False т.к. entry point — CallbackQuery, а ответ — Message
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*per_message.*", category=UserWarning)
        reply_conv = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(callback_reply, pattern=r"^reply:"),
            ],
            states={
                WAITING_REPLY: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receive_reply_text),
                ],
            },
            fallbacks=[
                CommandHandler("cancel", cancel_reply),
            ],
            per_message=False,
            per_chat=True,
        )

    _app.add_handler(reply_conv)

    # Commands
    _app.add_handler(CommandHandler("start", cmd_start))
    _app.add_handler(CommandHandler("stats", cmd_stats))
    _app.add_handler(CommandHandler("last", cmd_last))
    _app.add_handler(CommandHandler("search", cmd_search))
    _app.add_handler(CommandHandler("inbox", cmd_inbox))
    _app.add_handler(CommandHandler("threads", cmd_threads))

    # Callbacks
    _app.add_handler(CallbackQueryHandler(callback_apply, pattern=r"^apply:"))
    _app.add_handler(CallbackQueryHandler(callback_skip, pattern=r"^skip:"))
    _app.add_handler(CallbackQueryHandler(callback_ai_reply, pattern=r"^ai_reply:"))
    _app.add_handler(CallbackQueryHandler(callback_send, pattern=r"^send:"))
    _app.add_handler(CallbackQueryHandler(callback_improve, pattern=r"^improve:"))
    _app.add_handler(CallbackQueryHandler(callback_cancel_reply, pattern=r"^cancel_reply:"))

    return _app
