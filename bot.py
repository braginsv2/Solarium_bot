from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import CommandStart, Command
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputFile, ContentType
import asyncio
import cv2
from datetime import datetime
from dotenv import load_dotenv
import numpy as np
from io import BytesIO
import os
from PIL import Image
from pyzbar.pyzbar import decode, ZBarSymbol
import qrcode
import sqlite3

# Загрузка переменных окружения
load_dotenv()

SOLARIUM_ADDRESS = os.getenv('SOLARIUM_ADDRESS')
SOLARIUM_PHONE = os.getenv('SOLARIUM_PHONE')
SOLARIUM_SOCIAL = os.getenv('SOLARIUM_SOCIAL')

class RegistrationStates(StatesGroup):
    waiting_for_fullname = State()
    waiting_for_birthdate = State()
    waiting_for_phone = State()

class DetectQR(StatesGroup):
    waiting_for_id = State()
    waiting_for_minutes = State()

class MinDetectQR(StatesGroup):
    waiting_for_id = State()
    waiting_for_minutes = State()

class allSpam(StatesGroup):
    waiting_for_spam = State()
    waiting_for_compl = State()

class SolariumBot:
    def __init__(self, token: str):
        self.storage = MemoryStorage()
        self.bot = Bot(token=token)
        self.dp = Dispatcher(self.bot, storage=self.storage)
        self.admin_ids = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []
        self.pending_birth_date = {}
        
        # Инициализация базы данных
        self.init_db()
        
        # Регистрация обработчиков для aiogram 3.20
        self.dp.register_message_handler(self.start_handler, CommandStart())
        self.dp.register_message_handler(self.main_menu_handler, lambda message: message.text == "🔙 Вернуться в главное меню")
        self.dp.register_message_handler(self.registration_handler, lambda message: message.text == "📝 Регистрация")
        self.dp.register_message_handler(self.user_menu_handler, lambda message: message.text == "👤 Пользователь")
        self.dp.register_message_handler(self.admin_menu_handler, lambda message: message.text == "⚙️ Панель администратора")
        
        # Обработчики панели пользователя
        self.dp.register_message_handler(self.profile_handler, lambda message: message.text == "👤 Профиль")
        self.dp.register_message_handler(self.qr_handler, lambda message: message.text == "📱 QR-код")
        self.dp.register_message_handler(self.contact_handler, lambda message: message.text == "📞 Контакты")
        self.dp.register_message_handler(self.recommendations_handler, lambda message: message.text == "💡 Советы")
        self.dp.register_message_handler(self.help_user_handler, lambda message: message.text == "❓ Помощь")

        # Обработчики панели администратора
        self.dp.register_message_handler(self.add_minutes_handler, lambda message: message.text == "➕ Добавить минуты")
        self.dp.register_message_handler(self.minus_minutes_handler, lambda message: message.text == "➖ Списать минуты")
        #self.dp.register_message_handler(self.contact_handler, lambda message: message.text == "📊 Статистика")
        self.dp.register_message_handler(self.spam_handler, lambda message: message.text == "📢 Рассылка")
        #self.dp.register_message_handler(self.help_user_handler, lambda message: message.text == "🔒 Блокировка пользователя")
        #self.dp.register_message_handler(self.help_user_handler, lambda message: message.text == "🔓 Разблокировка пользователя")
        #self.dp.register_message_handler(self.help_user_handler, lambda message: message.text == "👤 Информация о пользователе")
        # Обработчики добавления минут
        self.dp.register_message_handler(self.add_detect, state=DetectQR.waiting_for_id, content_types=[ContentType.TEXT, ContentType.PHOTO])
        self.dp.register_message_handler(self.num_minutes, state=DetectQR.waiting_for_minutes)
        # Обработчики списания минут
        self.dp.register_message_handler(self.minus_detect, state=MinDetectQR.waiting_for_id, content_types=[ContentType.TEXT, ContentType.PHOTO])
        self.dp.register_message_handler(self.minus_num_minutes, state=MinDetectQR.waiting_for_minutes)
        # Обработчик рассылки минут
        self.dp.register_message_handler(self.spam, state=allSpam.waiting_for_spam)
        
        # Обработчики регистрации
        self.dp.register_message_handler(self.process_fullname, state=RegistrationStates.waiting_for_fullname)
        self.dp.register_message_handler(self.process_birthdate, state=RegistrationStates.waiting_for_birthdate)
        self.dp.register_message_handler(self.process_phone, state=RegistrationStates.waiting_for_phone)
    
    def init_db(self):
        """Инициализация базы данных SQLite"""
        self.conn = sqlite3.connect('solarium_bot.db')
        self.cursor = self.conn.cursor()
        
        # Создание таблицы пользователей, если она не существует
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            fullname TEXT,
            birthdate TEXT,
            phone TEXT,
            registration_date TEXT,
            number_minutes INT,
            total_minutes INT
                            
        )
        ''')
        self.conn.commit()
    
    async def close_db(self):
        """Закрытие соединения с базой данных"""
        self.conn.close()
    
    def user_exists(self, user_id: int) -> bool:
        """Проверяет, существует ли пользователь в базе данных"""
        self.cursor.execute('SELECT 1 FROM users WHERE user_id = ?', (user_id,))
        return self.cursor.fetchone() is not None
    
    def add_user(self, user_id: int, username: str, fullname: str, birthdate: str, phone: str):
        """Добавляет пользователя в базу данных"""
        registration_date = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        self.cursor.execute('''
        INSERT INTO users (user_id, username, fullname, birthdate, phone, registration_date, number_minutes, total_minutes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, fullname, birthdate, phone, registration_date, 0, 0))
        self.conn.commit()

    def find_white_square(self, image):
        """Находит белый квадрат на изображении и возвращает его ROI"""
        # Преобразуем в HSV для лучшего выделения белого
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        
        # Диапазон белого цвета в HSV
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])
        mask = cv2.inRange(hsv, lower_white, upper_white)
        
        # Морфологические операции
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # Находим контуры
        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # Ищем квадратные контуры
        squares = []
        for cnt in contours:
            # Аппроксимируем контур
            epsilon = 0.1 * cv2.arcLength(cnt, True)
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            
            # Ищем четырехугольники
            if len(approx) == 4:
                # Проверяем на квадратность
                area = cv2.contourArea(approx)
                x,y,w,h = cv2.boundingRect(approx)
                aspect_ratio = float(w)/h
                
                if 0.8 < aspect_ratio < 1.2 and area > 1000:  # Фильтр по размеру и форме
                    squares.append(approx)
        
        # Если нашли квадраты, берем самый большой
        if squares:
            largest_square = max(squares, key=cv2.contourArea)
            
            # Получаем повернутый прямоугольник
            rect = cv2.minAreaRect(largest_square)
            box = cv2.boxPoints(rect)
            box = box.astype(np.int32)
            
            # Вычисляем ширину и высоту ROI
            width = int(rect[1][0])
            height = int(rect[1][1])
            
            # Точки для перспективного преобразования
            src_pts = box.astype("float32")
            dst_pts = np.array([[0, height-1],
                            [0, 0],
                            [width-1, 0],
                            [width-1, height-1]], dtype="float32")
            
            # Перспективное преобразование
            M = cv2.getPerspectiveTransform(src_pts, dst_pts)
            warped = cv2.warpPerspective(image, M, (width, height))
            return warped
        
        return None  

    def decode_qr_from_roi(self, roi):
        """Декодирует QR-код из выделенной области"""
        # Улучшаем изображение
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Декодируем QR
        decoded = decode(thresh, symbols=[ZBarSymbol.QRCODE])
        if decoded:
            return decoded[0].data.decode('ascii')
        return None

    def get_main_keyboard(self, is_admin: bool = False):
        """Создание главной клавиатуры"""
        if is_admin:
            keyboard = [
                [KeyboardButton(text="👤 Пользователь")],
                [KeyboardButton(text="⚙️ Панель администратора")]
            ]
        else:
            keyboard = [
            [KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="📱 QR-код")],
            [KeyboardButton(text="📞 Контакты")],
            [KeyboardButton(text="💡 Советы")],
            [KeyboardButton(text="❓ Помощь")],
        ]
        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True
        )

    def get_user_keyboard(self, is_admin: bool = False):
        """Создание клавиатуры обычного пользователя"""
        if is_admin:
            keyboard = [
                [KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="📱 QR-код")],
                [KeyboardButton(text="📞 Контакты")],
                [KeyboardButton(text="💡 Советы")],
                [KeyboardButton(text="❓ Помощь")],
                [KeyboardButton(text="🔙 Вернуться в главное меню")]
            ]
            return ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True
            )
        else:
            keyboard = [
                [KeyboardButton(text="👤 Профиль")],
                [KeyboardButton(text="📱 QR-код")],
                [KeyboardButton(text="📞 Контакты")],
                [KeyboardButton(text="💡 Советы")],
                [KeyboardButton(text="❓ Помощь")],
            ]
            return ReplyKeyboardMarkup(
                keyboard=keyboard,
                resize_keyboard=True
            )
    
    

    def get_admin_keyboard(self):
        """Создание клавиатуры панели администратора"""
        keyboard = [
            [KeyboardButton(text="➕ Добавить минуты")],
            [KeyboardButton(text="➖ Списать минуты")],
            #[KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📢 Рассылка")],
            #[KeyboardButton(text="🔒 Блокировка пользователя")],
            #[KeyboardButton(text="🔓 Разблокировка пользователя")],
            #[KeyboardButton(text="👤 Информация о пользователе")],
            [KeyboardButton(text="🔙 Вернуться в главное меню")]
        ]
        return ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True
        )
    
    async def start_handler(self, message: types.Message):
        """Обработчик команды /start"""
        is_admin = message.from_user.id in self.admin_ids
        
        if self.user_exists(message.from_user.id):
            await message.answer(
                "С возвращением!",
                reply_markup=self.get_main_keyboard(is_admin)
            )
        else:
            await message.answer(
                "Добро пожаловать в бот солярия!",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="📝 Регистрация")]],
                    resize_keyboard=True
                    )
            )
    
    async def main_menu_handler(self, message: types.Message):
        """Обработчик возврата в главное меню"""
        is_admin = message.from_user.id in self.admin_ids
        await message.answer(
            "Главное меню:",
            reply_markup=self.get_main_keyboard(is_admin)
        )
    
    async def registration_handler(self, message: types.Message):
        """Обработчик начала регистрации"""
        if self.user_exists(message.from_user.id):
            await message.answer("Вы уже зарегистрированы!")
            return
        
        await message.answer(
            "Давайте начнем регистрацию. Введите ваше ФИО:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await RegistrationStates.waiting_for_fullname.set()
    
    async def process_fullname(self, message: types.Message, state: FSMContext):
        """Обработчик ввода ФИО"""
        if len(message.text.split()) >= 2:
            async with state.proxy() as data:
                data['fullname'] = message.text
            
            await message.answer("Отлично! Теперь введите вашу дату рождения в формате ДД.ММ.ГГГГ:")
            await RegistrationStates.next()
        else:
            await message.answer("Неверный формат. Пожалуйста, ФИО:")
            return
    
    async def process_birthdate(self, message: types.Message, state: FSMContext):
        """Обработчик ввода даты рождения"""
        try:
            birthdate = datetime.strptime(message.text, '%d.%m.%Y').date()
            async with state.proxy() as data:
                data['birthdate'] = birthdate.strftime('%d-%m-%Y')
            
            await message.answer("Отлично! Теперь отправьте ваш номер телефона:")
            await RegistrationStates.next()
        except ValueError:
            await message.answer("Неверный формат даты. Пожалуйста, введите дату в формате ДД.ММ.ГГГГ:")
    
    async def process_phone(self, message: types.Message, state: FSMContext):
        """Обработчик ввода телефона и завершение регистрации"""
        phone = message.text
        cleaned = ''.join(c for c in phone if c.isdigit() or c == '+')
        if len(cleaned) == 12 and cleaned.startswith('+7'):
            async with state.proxy() as data:
                fullname = data['fullname']
                birthdate = data['birthdate']
            
            # Сохраняем пользователя в базу данных
            self.add_user(
                user_id=message.from_user.id,
                username=message.from_user.username,
                fullname=fullname,
                birthdate=birthdate,
                phone=phone
            )
            
            await message.answer(
                "Регистрация завершена успешно!",
                reply_markup=self.get_main_keyboard(message.from_user.id in self.admin_ids)
            )
            await state.finish()
        else:
            await message.answer("Неверный формат телефона. Пожалуйста, введите номер телефона:")
            return
            
    
    async def user_menu_handler(self, message: types.Message):
        is_admin = message.from_user.id in self.admin_ids
        """Обработчик меню пользователя"""
        if not self.user_exists(message.from_user.id):
            await message.answer("Пожалуйста, сначала зарегистрируйтесь!")
            return
        
        await message.answer(
            "Меню пользователя:",
            reply_markup=self.get_user_keyboard(is_admin)
        )
    
    async def admin_menu_handler(self, message: types.Message):
        """Обработчик админского меню"""
        if message.from_user.id in self.admin_ids:
            await message.answer(
                "Панель администратора:",
                reply_markup=self.get_admin_keyboard()
            )
        else:
            await message.answer("У вас нет прав администратора!")

    async def profile_handler(self, message: types.Message):
        """Обработчик профиля пользователя"""
        is_admin = message.from_user.id in self.admin_ids
        self.cursor.execute('SELECT fullname, birthdate, phone, number_minutes, total_minutes FROM users WHERE user_id = ?', (message.from_user.id,))
        result = self.cursor.fetchone()
        profile_text = (
            f"👤 Профиль\n\n"
            f"ФИО: {result[0]}\n"
            f"Телефон: {result[2]}\n"
            f"Дата рождения: {result[1]}\n"
            f"Осталось минут: {result[3]} минут\n"
            f"Всего использовано минут: {result[4]} минут"
        )
        await message.answer(
                profile_text,
                reply_markup=self.get_user_keyboard(is_admin)
            )
        
    async def qr_handler(self, message: types.Message):
        is_admin = message.from_user.id in self.admin_ids
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(message.from_user.id)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        bio.name = 'qr.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        photo = InputFile(bio, filename='qr.png')

        # Отправляем QR-код
        await message.reply_photo(
            photo=photo,
            caption=f"Ваш QR-код для идентификации в солярии",
            reply_markup=self.get_user_keyboard(is_admin)
        )

    async def contact_handler(self, message: types.Message):
        """Показ контактной информации"""
        is_admin = message.from_user.id in self.admin_ids
        contact_text = (
            f"📞 Контактная информация\n\n"
            f"Адрес: {SOLARIUM_ADDRESS}\n"
            f"Телефон: {SOLARIUM_PHONE}\n"
            f"Социальные сети: {SOLARIUM_SOCIAL}"
        )
        await message.answer(
                contact_text,
                reply_markup=self.get_user_keyboard(is_admin)
            )

    async def recommendations_handler(self, message: types.Message):
        """Показ контактной информации"""
        is_admin = message.from_user.id in self.admin_ids
        recommendations_text = (
            "1. Начните с минимального времени (3-5 минут)\n"
            "2. Используйте специальные средства для загара\n"
            "3. Не загорайте чаще 2-3 раз в неделю\n"
            "4. Пейте больше воды до и после сеанса\n"
            "5. Используйте защитные очки\n"
            "6. Не загорайте натощак\n"
            "7. После сеанса нанесите увлажняющий крем"
        )
        await message.answer(
                recommendations_text,
                reply_markup=self.get_user_keyboard(is_admin)
            )
        
    async def help_user_handler(self, message: types.Message):
        """Показ контактной информации"""
        is_admin = message.from_user.id in self.admin_ids
        help_user_text = (
            "❓ Помощь по использованию бота\n\n"
            "1. Профиль - информация о вашем аккаунте\n"
            "2. QR-код - ваш идентификатор в солярии, его нужно показать администратору при посещении\n"
            "3. Контакты - информация о солярии\n"
            "4. Советы - рекомендации по загару\n"
        )
        await message.answer(
                help_user_text,
                reply_markup=self.get_user_keyboard(is_admin)
            )  

    async def add_minutes_handler(self, message: types.Message):

        await message.answer(
                "Введите ID Telegram или отправьте QR-код пользователя",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                    resize_keyboard=True
                    )
            ) 
        await DetectQR.waiting_for_id.set()
    async def add_detect(self, message: types.Message, state: FSMContext):
        if message.text == "🔙 Вернуться в главное меню":
            await state.finish()  # Сбрасываем состояние, если было
            await message.answer("Панель администратора:",
                            reply_markup=self.get_admin_keyboard()
                            )
        else:
            
            if message.text:
                try:
                    async with state.proxy() as data:
                        data['photo'] = message.text
                    if not self.user_exists(data["photo"]):
                        raise
                    await message.answer(
                        "Введите Количество минут, которое хотите добавить",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                            resize_keyboard=True
                            )
                    )
                    await DetectQR.next()
                except Exception as e:
                    await message.answer("Неверный ID")
            elif message.photo:
                
                # Получаем фото
                photo = message.photo[-1]
                file = await message.bot.get_file(photo.file_id)
                downloaded_file = await message.bot.download_file(file.file_path)
                
                # Конвертируем в numpy array
                img_array = np.frombuffer(downloaded_file.read(), dtype=np.uint8)
                image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                try:
                    # Читаем изображение
                    if image is None:
                        await message.answer("❌ Не удалось прочитать изображение. Попробуйте отправить фото еще раз.")
                        return
                    roi = self.find_white_square(image)
                    # Декодируем QR-код
                    telegram_id = self.decode_qr_from_roi(roi)
                    
                    if not telegram_id:
                        await message.answer("❌ QR-код не найден или нечитаем. Попробуйте отправить фото еще раз.")
                        return
                    
    
                    # Находим пользователя по Telegram ID
                    async with state.proxy() as data:
                        data['photo'] = telegram_id
                    if not self.user_exists(data["photo"]):
                        raise
                    await message.answer(
                        "Введите Количество минут, которое хотите добавить",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                            resize_keyboard=True
                            )
                    )
                    await DetectQR.next()
                except Exception as e:
                    print(f"Error: {e}")
                    await message.answer("❌ Произошла ошибка при обработке QR-кода. Попробуйте еще раз.")

    async def num_minutes(self, message: types.Message, state: FSMContext):
        try:
            if message.text == "🔙 Вернуться в главное меню":
                await state.finish()  # Сбрасываем состояние, если было
                await message.answer("Панель администратора:",
                                reply_markup=self.get_admin_keyboard()
                                )
            else:
                async with state.proxy() as data:
                    photo = data['photo']
                if self.user_exists(photo):
                    self.cursor.execute('''
                    SELECT number_minutes FROM users WHERE user_id = ? 
                    ''', (photo,))
                    result = self.cursor.fetchone()
                    self.cursor.execute('''
                    UPDATE users SET number_minutes = ? WHERE user_id = ? 
                    ''', (result[0]+int(message.text), int(photo)))
                    self.conn.commit()
                    await message.answer(
                        "Минуты добавлены",
                        reply_markup=self.get_admin_keyboard()
                    )
                    await state.finish()
                else:
                    raise
        except Exception as e:
            print(f"Error: {e}")
            await message.answer("Введите число", reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                    resize_keyboard=True
                    )
                )
    async def minus_minutes_handler(self, message: types.Message):

        await message.answer(
                "Введите ID Telegram или отправьте QR-код пользователя",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                    resize_keyboard=True
                    )
            ) 
        await MinDetectQR.waiting_for_id.set()
    async def minus_detect(self, message: types.Message, state: FSMContext):
        if message.text == "🔙 Вернуться в главное меню":
            await state.finish()  # Сбрасываем состояние, если было
            await message.answer("Панель администратора:",
                            reply_markup=self.get_admin_keyboard()
                            )
        else:
            if message.text:
                try:
                    async with state.proxy() as data:
                        data['photo'] = message.text
                    if not self.user_exists(data["photo"]):
                        raise
                    await message.answer(
                        "Введите Количество минут, которое хотите списать",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                            resize_keyboard=True
                            )
                    )
                    await MinDetectQR.next()
                except Exception as e:
                    await message.answer("Неверный ID")
            elif message.photo:
                
                # Получаем фото
                photo = message.photo[-1]
                file = await message.bot.get_file(photo.file_id)
                downloaded_file = await message.bot.download_file(file.file_path)
                
                # Конвертируем в numpy array
                img_array = np.frombuffer(downloaded_file.read(), dtype=np.uint8)
                image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                try:
                    # Читаем изображение
                    if image is None:
                        await message.answer("❌ Не удалось прочитать изображение. Попробуйте отправить фото еще раз.")
                        return
                    roi = self.find_white_square(image)
                    # Декодируем QR-код
                    telegram_id = self.decode_qr_from_roi(roi)
                    
                    if not telegram_id:
                        await message.answer("❌ QR-код не найден или нечитаем. Попробуйте отправить фото еще раз.")
                        return
                    
    
                    # Находим пользователя по Telegram ID
                    async with state.proxy() as data:
                        data['photo'] = telegram_id
                    if not self.user_exists(data["photo"]):
                        raise
                    await message.answer(
                        "Введите Количество минут, которое хотите списать",
                        reply_markup=ReplyKeyboardMarkup(
                            keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                            resize_keyboard=True
                            )
                    )
                    await MinDetectQR.next()
                except Exception as e:
                    print(f"Error: {e}")
                    await message.answer("❌ Произошла ошибка при обработке QR-кода. Попробуйте еще раз.")

    async def minus_num_minutes(self, message: types.Message, state: FSMContext):
        try:
            if message.text == "🔙 Вернуться в главное меню":
                await state.finish()  # Сбрасываем состояние, если было
                await message.answer("Панель администратора",
                                reply_markup=self.get_admin_keyboard()
                                )
            else:
                async with state.proxy() as data:
                    photo = data['photo']
                if self.user_exists(photo):
                    self.cursor.execute('''
                    SELECT number_minutes, total_minutes FROM users WHERE user_id = ? 
                    ''', (photo,))
                    result = self.cursor.fetchone()
                    if result[0]>=int(message.text):
                        self.cursor.execute('''
                        UPDATE users SET number_minutes = ?, total_minutes = ? WHERE user_id = ? 
                        ''', (result[0]-int(message.text),result[1]+int(message.text), int(photo)))
                        self.conn.commit()
                        await message.answer(
                            "Минуты списаны",
                            reply_markup=self.get_admin_keyboard()
                        )
                        await state.finish()
                    else: 
                        await message.answer("Недостаточно минут")
                        return
                else:
                    raise
        except Exception as e:
            await message.answer("Введите число", reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                    resize_keyboard=True
                    )
                )
    async def spam_handler(self, message: types.Message):
        
        await message.answer(
                "Введите сообщение для рассылки",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🔙 Вернуться в главное меню")]],
                    resize_keyboard=True
                    )
            ) 
        await allSpam.waiting_for_spam.set()

    async def spam(self, message: types.Message, state: FSMContext):
        if message.text == "🔙 Вернуться в главное меню":
            await state.finish()  # Сбрасываем состояние, если было
            await message.answer("Рассылка отменена",
                            reply_markup=self.get_admin_keyboard()
                            )
        else:
            self.cursor.execute("SELECT user_id FROM users")
            result = self.cursor.fetchone()
            for id in result:
                await self.bot.send_message(
                            chat_id=id,
                            text=message.text
                        )
            await message.answer("Рассылка отправлена",
                                reply_markup=self.get_admin_keyboard()
                                )
            await state.finish() 
async def main():
    # Инициализация бота
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        raise ValueError("Не указан TELEGRAM_BOT_TOKEN в .env файле")
    
    solarium_bot = SolariumBot(token)
    
    try:
        # Запуск бота
        await solarium_bot.dp.start_polling()
    finally:
        # Закрытие соединения с базой данных при завершении работы
        await solarium_bot.close_db()

if __name__ == '__main__':
    asyncio.run(main())
