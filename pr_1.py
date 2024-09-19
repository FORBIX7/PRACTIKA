import openai
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram import F
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

# Инициализация OpenAI API
openai.api_key = os.getenv('OPENAI_API_KEY')

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=os.getenv('TELEGRAM_BOT_TOKEN'))
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def send_welcome(message: Message):
    await message.answer("Привет! Я бот с искусственным интеллектом. Напиши мне что-нибудь!")

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_message(message: Message):
    user_message = message.text

    # Отправка запроса к OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": user_message}
        ]
    )

    bot_response = response.choices[0].message['content']

    # Отправка ответа пользователю
    await message.answer(bot_response, parse_mode='HTML')

# Запуск бота
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
