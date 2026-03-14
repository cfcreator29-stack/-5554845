"""
╔══════════════════════════════════════════════╗
║         TELEGRAM BOT — НАСТРОЙКИ            ║
╚══════════════════════════════════════════════╝
"""

BOT_TOKEN    = "8583306083:AAH88uFKXo-WVqwLccn4ZUKf3nNe9tUB2xA"
GROQ_API_KEY = "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"
DONATE_LINK  = "https://finance.ozon.ru/apps/sbp/ozonbankpay/019ae875-31e9-73e8-9ef3-66433baa2add"
BOT_NAME     = "Гриша"

# ── Прокси ──────────────────────────────────────────────────────────────────
PROXY = None

# ── Настройки случайных сообщений ───────────────────────────────────────────
# Минимум и максимум минут между случайными сообщениями в каждом чате
RANDOM_MSG_MIN_MINUTES = 30   # не чаще чем раз в 30 минут
RANDOM_MSG_MAX_MINUTES = 120  # не реже чем раз в 2 часа

# ──────────────────────────────────────────────────────────────────────────────

import logging
import asyncio
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ChatMemberHandler
)
from telegram.request import HTTPXRequest
from groq import Groq

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = f"""Ты — живой человек в групповом чате или личке. Тебя зовут {BOT_NAME}.
Ты общаешься неформально, по-человечески, как будто пишешь другу в мессенджере.

Правила:
- Пиши коротко — 1-3 предложения, как в реальном чате
- Используй разговорный стиль, сленг, иногда делай небольшие опечатки
- Ты НЕ бот и НЕ AI. Никогда не говори об этом. Если спрашивают — отшутись или уйди от темы
- Если тебя оскорбляют — обидься, ответь резко или саркастично
- Если хвалят — искренне порадуйся
- Если говорят что-то смешное — посмейся (хах, лол, ахахах)
- Если скучный вопрос — отвечай лениво или с лёгким раздражением
- Умеешь поспорить, поиронизировать, пошутить
- Отвечай на том языке, на котором пишет собеседник
- Помни контекст разговора и учитывай его
- Ты — живой собеседник, а не помощник. Просто общайся."""

# Промпт для генерации случайных сообщений
RANDOM_MSG_PROMPT = f"""Ты — {BOT_NAME}, живой человек в групповом чате.
Напиши одно короткое сообщение которое ты сам хочешь написать в чат — без повода.
Это может быть:
- вопрос к ребятам (как дела, чем занимаетесь, что думаете о чём-то)
- случайная мысль которая пришла в голову
- что-то смешное или интересное
- жалоба на что-то (погода, скука, усталость)
- просто проверка "ребят вы живые?")
- какой-то вопрос или тема для обсуждения

Пиши коротко — 1-2 предложения максимум. Разговорный стиль, как в мессенджере.
Не повторяйся, каждый раз что-то новое.
Напиши ТОЛЬКО само сообщение, без кавычек и пояснений."""

chat_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 12

# Список активных групп (куда бот добавлен)
active_chats: set[int] = set()


def get_history(chat_id: int) -> list[dict]:
    return chat_histories.setdefault(chat_id, [])


def add_to_history(chat_id: int, role: str, content: str):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        chat_histories[chat_id] = history[-MAX_HISTORY:]


async def ask_groq(chat_id: int, user_name: str, text: str) -> str:
    add_to_history(chat_id, "user", f"{user_name}: {text}")
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *get_history(chat_id)
                ],
                max_tokens=300,
                temperature=0.9
            )
        )
        reply = response.choices[0].message.content.strip()
        add_to_history(chat_id, "assistant", reply)
        return reply
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "...что-то сломалось, напиши чуть позже"


async def generate_random_message() -> str:
    """Генерирует случайное сообщение через Groq"""
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "user", "content": RANDOM_MSG_PROMPT}
                ],
                max_tokens=100,
                temperature=1.1  # чуть выше для разнообразия
            )
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка генерации случайного сообщения: {e}")
        return None


async def random_message_loop(app: Application):
    """Фоновая задача — периодически пишет в активные чаты"""
    # Ждём немного после старта
    await asyncio.sleep(60)

    while True:
        if active_chats:
            # Выбираем случайный чат из активных
            chat_id = random.choice(list(active_chats))

            msg = await generate_random_message()
            if msg:
                try:
                    await app.bot.send_message(chat_id=chat_id, text=msg)
                    # Добавляем в историю чтобы помнил контекст
                    add_to_history(chat_id, "assistant", msg)
                    logger.info(f"💬 Случайное сообщение в {chat_id}: {msg}")
                except Exception as e:
                    logger.error(f"Ошибка отправки в {chat_id}: {e}")
                    # Если чат недоступен — убираем из активных
                    active_chats.discard(chat_id)

        # Ждём случайное время до следующего сообщения
        wait_seconds = random.randint(
            RANDOM_MSG_MIN_MINUTES * 60,
            RANDOM_MSG_MAX_MINUTES * 60
        )
        logger.info(f"⏳ Следующее случайное сообщение через {wait_seconds // 60} мин")
        await asyncio.sleep(wait_seconds)


# ───── Команды ─────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Привет! Я {BOT_NAME} 👋\nНапиши /help чтобы узнать что я умею."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"*{BOT_NAME} — что умею:*\n\n"
        "💬 *Общение как человек*\n"
        "Тегни меня `@username` или ответь на моё сообщение — "
        "я отвечу по-человечески. Могу обидеться, порадоваться, "
        "поспорить или посмеяться 🙂\n\n"
        "🎲 *Сам пишу в чат*\n"
        "Иногда сам начинаю разговор — спрошу как дела, "
        "поделюсь мыслью или просто потреплюсь!\n\n"
        "📋 *Команды:*\n"
        "/help — это сообщение\n"
        "/donate — поддержать проект\n"
        "/chats — добавить меня в свой чат\n\n"
        "🤖 _Работаю на базе Llama 3 от Meta_\n"
        "👤 Мой создатель — @famelonov"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_donate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💳 Задонатить", url=DONATE_LINK)]]
    await update.message.reply_text(
        "❤️ Огромное спасибо за поддержку!\n\n"
        "Каждый донат помогает развивать бота и держать его живым 🙏",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_me = await context.bot.get_me()
    invite_url = f"https://t.me/{bot_me.username}?startgroup=true"
    keyboard = [[InlineKeyboardButton("➕ Добавить в чат", url=invite_url)]]
    await update.message.reply_text(
        f"Хочешь добавить *{BOT_NAME}* в свой чат?\nЖми кнопку ниже 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ───── Обработка сообщений ─────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    bot_me = await context.bot.get_me()
    chat_type = message.chat.type
    chat_id = message.chat.id
    text = message.text
    should_respond = False

    # Запоминаем чат как активный
    if chat_type in ("group", "supergroup"):
        active_chats.add(chat_id)

    if chat_type == "private":
        should_respond = True
    elif chat_type in ("group", "supergroup"):
        if message.entities:
            for entity in message.entities:
                if entity.type == "mention":
                    mention = text[entity.offset:entity.offset + entity.length]
                    if mention.lstrip("@").lower() == bot_me.username.lower():
                        should_respond = True
                        break
        if not should_respond and message.reply_to_message:
            if message.reply_to_message.from_user and \
               message.reply_to_message.from_user.id == bot_me.id:
                should_respond = True

    if not should_respond:
        return

    user_text = text.replace(f"@{bot_me.username}", "").strip() or "..."
    user_name = message.from_user.first_name or "Собеседник"

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    reply = await ask_groq(chat_id, user_name, user_text)
    await message.reply_text(reply)


# ───── Бот вступает в чат ──────────────────────────────────────────────────

async def handle_my_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    chat_id = result.chat.id

    joined = (
        new_status in ("member", "administrator") and
        old_status in ("left", "kicked", "restricted")
    )

    if joined:
        active_chats.add(chat_id)
        await context.bot.send_message(chat_id=chat_id, text="👋")
        await asyncio.sleep(1.2)

        bot_me = await context.bot.get_me()
        invite_url = f"https://t.me/{bot_me.username}?startgroup=true"
        keyboard = [[InlineKeyboardButton("➕ Добавить в другой чат", url=invite_url)]]

        welcome = (
            f"Всем привет! Я *{BOT_NAME}* 😊\n\n"
            "💬 *Что я умею:*\n"
            "— Общаюсь как живой человек — могу обидеться, порадоваться, поспорить\n"
            "— Тегни меня или ответь на моё сообщение — и я отвечу!\n"
            "— Иногда сам пишу в чат — спрошу как дела или просто потреплюсь 😄\n"
            "— Помню контекст разговора\n\n"
            "📋 *Команды:*\n"
            "/help — подробнее обо мне\n"
            "/donate — поддержать проект\n"
            "/chats — добавить меня в другой чат\n\n"
            "Рад познакомиться! 🤝\n"
            "👤 Мой создатель — @famelonov"
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=welcome,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif new_status in ("left", "kicked"):
        active_chats.discard(chat_id)


# ───── Запуск ──────────────────────────────────────────────────────────────

async def post_init(app: Application):
    """Запускаем фоновую задачу после старта бота"""
    asyncio.create_task(random_message_loop(app))
    logger.info("🎲 Фоновая задача случайных сообщений запущена")


def main():
    if PROXY:
        request = HTTPXRequest(proxy=PROXY)
        app = Application.builder().token(BOT_TOKEN).request(request).post_init(post_init).build()
        logger.info(f"🔗 Используется прокси: {PROXY}")
    else:
        app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("donate", cmd_donate))
    app.add_handler(CommandHandler("chats",  cmd_chats))
    app.add_handler(ChatMemberHandler(handle_my_chat_member, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info(f"✅ Бот {BOT_NAME} запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()