import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import sqlite3
import os
import openai
import requests
from io import BytesIO

# Замените на свои токены
BOT_TOKEN = 'YOUR_BOT_TOKEN'
OPENAI_API_KEY = 'YOUR_OPENAI_API_KEY'

# Инициализация OpenAI
openai.api_key = OPENAI_API_KEY

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация базы данных
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                  (user_id INTEGER PRIMARY KEY, username TEXT, tokens_used INTEGER)''')
conn.commit()

# Функция для регистрации пользователя
def register_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, tokens_used) VALUES (?, ?, 0)", 
                   (user_id, username))
    conn.commit()

# Функция для обновления использованных токенов
def update_tokens(user_id, tokens):
    cursor.execute("UPDATE users SET tokens_used = tokens_used + ? WHERE user_id = ?", (tokens, user_id))
    conn.commit()

# Функция для генерации ответа с помощью OpenAI
async def generate_response(prompt):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": prompt}
            ]
        )
        tokens_used = response['usage']['total_tokens']
        return response.choices[0].message['content'].strip(), tokens_used
    except Exception as e:
        logging.error(f"Error in OpenAI API call: {e}")
        return "Извините, произошла ошибка при обработке вашего запроса.", 0

# Функция для генерации изображения с помощью DALL-E
async def generate_image(prompt):
    try:
        response = openai.Image.create(
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        image_url = response['data'][0]['url']
        return image_url
    except Exception as e:
        logging.error(f"Error in DALL-E API call: {e}")
        return None

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    register_user(user_id, username)
    await state.clear()
    await message.answer("Привет! Я бот, использующий OpenAI. Я могу отвечать на ваши вопросы и генерировать изображения. Чем могу помочь?")
    update_tokens(user_id, 10)

# Обработчик текстовых сообщений
@dp.message(F.text)
async def handle_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text
    
    # Получаем текущий контекст
    context = await state.get_data()
    conversation = context.get('conversation', [])
    
    # Добавляем новое сообщение в контекст
    conversation.append(f"User: {text}")
    
    if "картинка" in text.lower() or "изображение" in text.lower():
        # Генерируем изображение
        image_url = await generate_image(text)
        if image_url:
            # Скачиваем изображение
            response = requests.get(image_url)
            img = BytesIO(response.content)
            # Отправляем изображение
            await message.answer_photo(photo=img, caption="Вот изображение, которое вы запросили:")
            response = "Я отправил вам запрошенное изображение."
            tokens_used = 50  # Примерная оценка токенов для генерации изображения
        else:
            response = "Извините, не удалось сгенерировать изображение."
            tokens_used = 10
    else:
        # Генерируем текстовый ответ
        response, tokens_used = await generate_response(text)
    
    # Добавляем ответ бота в контекст
    conversation.append(f"Bot: {response}")
    
    # Ограничиваем контекст последними 10 сообщениями
    conversation = conversation[-10:]
    
    # Сохраняем обновленный контекст
    await state.update_data(conversation=conversation)
    
    # Отправляем ответ
    await message.answer(response)
    
    # Обновляем токены
    update_tokens(user_id, tokens_used)

# Функция для запуска бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
