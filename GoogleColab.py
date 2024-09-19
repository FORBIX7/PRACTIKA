# Установка необходимых пакетов
import openai
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F
import nest_asyncio
import asyncio

# Применяем nest_asyncio для интеграции с существующим циклом событий
nest_asyncio.apply()

# Указываем ключи API и токен бота
OPENAI_API_KEY = "Your_token"
TELEGRAM_BOT_TOKEN = "Your_token"



# Устанавливаем ключ API для OpenAI
openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer("Привет! Я бот с искусственным интеллектом. Напиши мне что-нибудь!")

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_message(message: Message):
    user_message = message.text

    try:
        # Отправка запроса к OpenAI
        response = openai.ChatCompletion.create(
            model="davinci-002",
            messages=[
                {"role": "system", "content": "Ты ассистент."},
                {"role": "user", "content": user_message}
            ]
        )
        bot_response = response.choices[0].message['content']
        # Отправка ответа пользователю
        await message.answer(bot_response, parse_mode='HTML')
    except openai.error.RateLimitError as e:
        logger.error(f"RateLimitError: {e}")
        await message.answer("Извините, но я исчерпал лимит запросов. Пожалуйста, попробуйте позже.")
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        await message.answer("Произошла ошибка. Пожалуйста, попробуйте позже.")

# Запуск бота
async def main():
    # Удаление webhook, если он был установлен ранее
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

# Запуск асинхронного кода в интерактивной среде
if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())