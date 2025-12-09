import logging
from config import config
import re
import sqlite3
import sys
import traceback
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    CallbackContext, ConversationHandler, CallbackQueryHandler 
)

from database import Database

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler('bot_errors.log', encoding='utf-8'
                            ),
        logging.StreamHandler(stream=sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
WAITING_FOR_NUMBER, WAITING_FOR_PHONE = range(2)

# Регулярное выражение для проверки номера лотереи
LOTTERY_NUMBER_PATTERN = re.compile(r'^\d{4}$')

# Регулярное выражение для проверки телефона (базовое)
PHONE_PATTERN = re.compile(r'^\+?[0-9\s\-\(\)]{5,20}$')

# Инициализация базы данных
db = Database()

# ID администратора 
ADMIN_ID = config.ADMIN_ID
TOKEN = config.BOT_TOKEN

MAX_INPUT_LENGTH = 100

def sanitize_text(text: str) -> str:
    """
    Очистка текста от потенциально опасных символов.
    Оставляет только буквы, цифры и некоторые безопасные символы.
    """
    if not text:
        return ""
    
    # Оставляем только безопасные символы (кириллица, латиница, цифры, некоторые знаки препинания)
    # Это более строгая проверка для максимальной безопасности
    safe_pattern = re.compile(r'[^a-zA-Zа-яА-ЯёЁ0-9\s\-_.,!?()@#%&*+=]')
    cleaned_text = safe_pattern.sub('', text)
    
    return cleaned_text.strip()

def start(update: Update, context: CallbackContext) -> int:
    """Обработка команды /start - начало регистрации"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("Пользователь не определен в update")
            # Отправляем сообщение даже если пользователь не определен
            try:
                update.message.reply_text(
                    "⚠️ Не удалось определить пользователя. Попробуйте позже или свяжитесь с администратором."
                )
            except:
                pass
            return ConversationHandler.END
        
        logger.info(f"Пользователь {user.id} ({user.username}) начал регистрацию")
        
        # Очищаем предыдущие данные пользователя
        if context.user_data:
            context.user_data.clear()
        
        # Создаем клавиатуру с кнопкой /start
        keyboard = [[KeyboardButton("/start")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        update.message.reply_text(
            f"Привет, {user.first_name}! ✨\n\n"
            "Я бот «7 канала Красноярск» для участия в\n"
            "розыгрыше призов от НЕТАЙНОГО САНТЫ!\n\n"
            "Для участия в розыгрыше:\n"
            "1. Отправь кодовое слово из эфира «7 канал Красноярск».\n"
            "2. Поделись своим контактным номером.\n",
            reply_markup=reply_markup
        )
        return WAITING_FOR_NUMBER
        
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}\n{traceback.format_exc()}")
        try:
            update.message.reply_text(
                "⚠️ Произошла ошибка при запуске. Попробуйте позже или нажмите /start для повторной попытки."
            )
        except:
            pass
        return ConversationHandler.END

def handle_start_button(update: Update, context: CallbackContext) -> int:
    """Обработка нажатия кнопки /start (или повторной команды /start)"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("Пользователь не определен")
            return ConversationHandler.END
        
        logger.info(f"Пользователь {user.id} нажал кнопку /start для повторной регистрации")
        
        # Очищаем предыдущие данные пользователя
        context.user_data.clear()
        
        # Создаем клавиатуру с кнопкой /start
        keyboard = [[KeyboardButton("/start")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        update.message.reply_text(
            f"Начнем заново! ✨\n\n"
            "Введите кодовое слово из эфира:\n",
            reply_markup=reply_markup
        )
        return WAITING_FOR_NUMBER
        
    except Exception as e:
        logger.error(f"Ошибка при обработке кнопки /start: {e}\n{traceback.format_exc()}")
        if update and update.message:
            update.message.reply_text("⚠️ Произошла ошибка. Попробуйте позже.")
        return ConversationHandler.END

def is_valid_kode_slovo(s: str) -> bool:
    """
    Проверяет, что кодовое слово содержит только безопасные символы.
    Разрешены: буквы (кириллица/латиница), цифры, пробелы (но они будут удалены).
    """
    if not s:
        return False
    
    # Проверяем, что строка состоит только из разрешенных символов
    allowed_pattern = re.compile(r'^[a-zA-Zа-яА-ЯёЁ0-9\s\-_.,!?()@#%&*+=]+$')
    return bool(allowed_pattern.match(s))

def handle_lottery_number(update: Update, context: CallbackContext) -> int:
    """Обработка введенного кодового слова"""
    try:
        if not update.message or not update.message.text:
            logger.error("Получено пустое сообщение")
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Получено пустое сообщение.\n"
                "Попробуйте еще раз или нажмите /start для начала:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_NUMBER
        
        user = update.effective_user
        raw_text = update.message.text.strip()
        
        # 1. Проверка длины (защита от слишком длинных сообщений)
        if len(raw_text) > MAX_INPUT_LENGTH:
            logger.warning(f"Пользователь {user.id} отправил слишком длинное сообщение: {len(raw_text)} символов")
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Сообщение слишком длинное.\n"
                f"Максимальная длина: {MAX_INPUT_LENGTH} символов.\n"
                "Попробуйте еще раз или нажмите /start для начала:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_NUMBER
        
        # 2. Очистка текста от потенциально опасных символов
        cleaned_text = sanitize_text(raw_text)
        
        # 3. Проверяем, если пользователь нажал кнопку /start
        if cleaned_text == "/start":
            return handle_start_button(update, context)
        
        # 4. Дополнительная проверка на SQL-инъекции и другие атаки
        # Проверяем наличие подозрительных последовательностей
        sql_keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'DROP', 'UNION', 'OR', 'AND']
        suspicious_patterns = ['--', ';', '/*', '*/', "'", '"', '`']
        
        upper_text = raw_text.upper()
        for keyword in sql_keywords:
            if keyword in upper_text:
                logger.warning(f"Пользователь {user.id} отправил подозрительный запрос с ключевым словом: {keyword}")
                
                # Создаем клавиатуру с кнопкой /start
                keyboard = [[KeyboardButton("/start")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "❌ Недопустимый ввод.\n"
                    "Попробуйте еще раз или нажмите /start для начала:",
                    reply_markup=reply_markup
                )
                return WAITING_FOR_NUMBER
        
        for pattern in suspicious_patterns:
            if pattern in raw_text:
                logger.warning(f"Пользователь {user.id} отправил подозрительный запрос с символом: {pattern}")
                
                # Создаем клавиатуру с кнопкой /start
                keyboard = [[KeyboardButton("/start")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "❌ Недопустимый ввод.\n"
                    "Попробуйте еще раз или нажмите /start для начала:",
                    reply_markup=reply_markup
                )
                return WAITING_FOR_NUMBER
        
        kode_slovo = cleaned_text
        
        # 5. Удаляем все пробелы, табуляции, переносы строк (но сохраняем для проверки длины)
        kode_slovo_without_spaces = re.sub(r'\s+', '', kode_slovo)
        
        # 6. Проверяем, что введено от 1 до 16 символов
        if len(kode_slovo_without_spaces) == 0:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Кодовое слово не может быть пустым.\n"
                "Попробуйте еще раз или нажмите /start для начала:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_NUMBER
        
        if len(kode_slovo_without_spaces) > 16:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            # Безопасно показываем длину (убираем escape)
            safe_length = str(len(kode_slovo_without_spaces))
            error_msg = f"❌ Кодовое слово должно содержать не более 16 символов (без учета пробелов). Вы ввели {safe_length} символов.\n"
            
            update.message.reply_text(
                f"{error_msg}"
                "Попробуйте еще раз или нажмите /start для начала:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_NUMBER
        
        # 7. Проверяем, что в строке есть хотя бы один печатный символ
        # (не только пробелы/табуляции)
        if not kode_slovo_without_spaces:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Кодовое слово должно содержать хотя бы один символ (буквы или цифры).\n"
                "Попробуйте еще раз или нажмите /start для начала:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_NUMBER
        
        logger.info(f"Пользователь {user.id} ввел кодовое слово: {kode_slovo_without_spaces}")
        
        # 8. Сохраняем кодовое слово в контексте пользователя
        context.user_data['kode_slovo'] = kode_slovo_without_spaces
        
        # 9. Создаем кнопки для отправки телефона и /start
        keyboard = [
            [KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)],
            [KeyboardButton("/start")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        
        # 10. Выводим кодовое слово пользователю (убираем escape)
        safe_display_kode = kode_slovo_without_spaces[:50]  # Ограничиваем длину для безопасности
        
        update.message.reply_text(
            f"Принимая участие в розыгрыше, вы подтверждаете свое ознакомление и согласие с условиями розыгрыша «Нетайный Санта», размещенными на сайте https://trk7.ru\n"
            "Победитель (получатель приза) идентифицируется по номеру телефона в сообщении с кодовым словом.\n\n"
            "Теперь поделитесь номером телефона, чтобы мы смогли связаться с вами в случае вашего выигрыша.\n"
            "Вы можете:\n"
            "1. Нажать кнопку '📱 Отправить мой номер телефона'\n"
            "2. Ввести номер вручную (например: +79123456789 или 89123456789)",
            reply_markup=reply_markup
        )
        
        return WAITING_FOR_PHONE
        
    except Exception as e:
        logger.error(f"Ошибка обработки кодового слова: {e}\n{traceback.format_exc()}")
        try:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "⚠️ Ошибка обработки кодового слова. Нажмите /start для начала заново:",
                reply_markup=reply_markup
            )
        except:
            pass
        return ConversationHandler.END

def sanitize_phone(phone: str) -> str:
    """
    Очистка номера телефона.
    Оставляет только цифры и символ + в начале.
    """
    if not phone:
        return ""
    
    # Удаляем все символы, кроме цифр и +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Если есть +, оставляем только один в начале
    if '+' in cleaned:
        # Удаляем все +, потом добавляем один в начало
        digits = cleaned.replace('+', '')
        cleaned = '+' + digits
    
    return cleaned

def handle_phone(update: Update, context: CallbackContext) -> int:
    """Обработка номера телефона с защитой"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("Пользователь не определен при обработке телефона")
            try:
                update.message.reply_text(
                    "❌ Не удалось определить пользователя. Нажмите /start для начала заново."
                )
            except:
                pass
            return ConversationHandler.END
        
        # Проверяем, если пользователь отправил /start
        if update.message.text:
            raw_text = update.message.text.strip()
            cleaned_text = sanitize_text(raw_text)
            if cleaned_text == "/start":
                return handle_start_button(update, context)
        
        # Получаем номер телефона
        phone = None
        if update.message.contact:
            # Контакт из Telegram уже безопасен
            phone = update.message.contact.phone_number
            logger.info(f"Пользователь {user.id} отправил контакт")
        elif update.message.text:
            phone_input = update.message.text.strip()
            
            # Проверка длины
            if len(phone_input) > 30:
                # Создаем кнопки
                keyboard = [
                    [KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)],
                    [KeyboardButton("/start")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "❌ Номер телефона слишком длинный.\n"
                    "Попробуйте еще раз или нажмите /start для начала заново:",
                    reply_markup=reply_markup
                )
                return WAITING_FOR_PHONE
            
            # Очистка ввода
            safe_phone_input = sanitize_text(phone_input)
            
            if not safe_phone_input:
                # Создаем кнопки
                keyboard = [
                    [KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)],
                    [KeyboardButton("/start")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "❌ Номер телефона не может быть пустым.\n"
                    "Попробуйте еще раз или нажмите /start для начала заново:",
                    reply_markup=reply_markup
                )
                return WAITING_FOR_PHONE
            
            # Нормализация телефона
            phone = sanitize_phone(safe_phone_input)
            
            # Проверяем, что после очистки номер валиден
            if not phone or len(phone) < 11:
                # Создаем кнопки
                keyboard = [
                    [KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)],
                    [KeyboardButton("/start")]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "❌ Номер телефона слишком короткий или неверный.\n"
                    "Примеры: +79123456789, 89123456789\n\n"
                    "Попробуйте еще раз или нажмите /start для начала заново:",
                    reply_markup=reply_markup
                )
                return WAITING_FOR_PHONE
            
            logger.info(f"Пользователь {user.id} ввел телефон: {phone}")
            
        else:
            # Создаем кнопки
            keyboard = [
                [KeyboardButton("📱 Отправить мой номер телефона", request_contact=True)],
                [KeyboardButton("/start")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Не удалось получить номер телефона.\n"
                "Попробуйте еще раз или нажмите /start для начала заново:",
                reply_markup=reply_markup
            )
            return WAITING_FOR_PHONE
        
        # Получаем сохраненное кодовое слово
        kode_slovo = context.user_data.get('kode_slovo')
        
        if not kode_slovo:
            logger.error(f"Пользователь {user.id}: кодовое слово не найдено в context.user_data")
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "⚠️ Сессия устарела. Нажмите /start для начала заново:",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        # Проверяем, не участвовал ли пользователь сегодня
        today = datetime.now().strftime("%d.%m.%Y")
        try:
            # Получаем существующую запись, если есть
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT kode_slovo, registration_time 
                FROM participants 
                WHERE user_id = ? AND date = ?
            ''', (user.id, today))
            
            existing = cursor.fetchone()
            conn.close()
            
            if existing:
                existing_kode = existing['kode_slovo'] if isinstance(existing, dict) else existing[0]
                existing_time = existing['registration_time'] if isinstance(existing, dict) else existing[1]
                
                logger.info(f"Пользователь {user.id} уже участвовал сегодня с кодовым словом {existing_kode}")
                
                # Создаем клавиатуру с кнопкой /start
                keyboard = [[KeyboardButton("/start")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    f"❌ Вы уже участвовали в розыгрыше сегодня!\n\n"
                    "Вы можете участвовать завтра снова!\n"
                    "Нажмите /start для участия в другом розыгрыше:",
                    reply_markup=reply_markup
                )
                return ConversationHandler.END
                
        except Exception as e:
            logger.error(f"Ошибка проверки участия пользователя: {e}\n{traceback.format_exc()}")
        
        # Сохраняем данные в базу
        try:
            db.save_participant(
                kode_slovo=kode_slovo,  # Изменено с lottery_number на kode_slovo
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                phone=phone
            )
            logger.info(f"Пользователь {user.id} успешно зарегистрирован с кодовым словом {kode_slovo}")
            
        except ValueError as e:
            # Обрабатываем ошибку "Вы уже участвовали сегодня"
            error_message = str(e)
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                f"❌ {error_message}\n\n"
                "Вы можете участвовать снова завтра!\n"
                "Нажмите /start для участия в другом розыгрыше:",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        except sqlite3.IntegrityError as e:
            # Обрабатываем ошибку уникального индекса
            logger.error(f"Ошибка уникальности при сохранении: {e}\n{traceback.format_exc()}")
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "❌ Вы уже участвовали в розыгрыше сегодня!\n\n"
                "Вы можете участвовать снова завтра!\n"
                "Нажмите /start для участия в другом розыгрыше:",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        except Exception as db_error:
            logger.error(f"Ошибка сохранения в БД: {db_error}\n{traceback.format_exc()}")
            
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "⚠️ Произошла ошибка при сохранении данных.\n"
                "Пожалуйста, попробуйте позже или свяжитесь с администратором.\n\n"
                "Нажмите /start для повторной попытки:",
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        # Убираем клавиатуру и отправляем подтверждение
        safe_kode_display = kode_slovo[:50]  # Ограничиваем длину для безопасности
        safe_phone_display = phone[:20]  # Ограничиваем длину телефона
        
        update.message.reply_text(
            f"Спасибо за ваше участие в розыгрыше «Нетайный Санта»!\n\n"
            f"Вы зарегистрированы в качестве участника!\n\n"
            f"Победитель и приз победителю (пользователю телефонного номера) - платеж в размере 1000 рублей передается в течение 48 часов с момента появления кодового слова ежедневного розыгрыша при условии ввода правильного кодового слова и идентификации победителя как физического лица.\n\n"
            f"Включай каждый будний день «7 канал Красноярск» с 18:30 до 20:00 и участвуй в игре «Нетайный Санта»!\n",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Очищаем данные
        context.user_data.clear()
        
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка обработки телефона: {e}\n{traceback.format_exc()}")
        try:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            update.message.reply_text(
                "⚠️ Произошла ошибка. Нажмите /start для начала заново:",
                reply_markup=reply_markup
            )
        except:
            pass
        return ConversationHandler.END
    
def handle_callback_query(update: Update, context: CallbackContext):
    """Обработчик нажатий на inline кнопки"""
    query = update.callback_query
    query.answer()
    
    callback_data = query.data
    
    try:
        # Обработка выбора даты
        if callback_data.startswith("list_date:"):
            date_str = callback_data.split(":")[1]
            
            # Получаем участников за указанную дату
            participants = db.get_participants_by_date(date_str)
            
            if not participants:
                query.edit_message_text(f"📭 На {date_str} участников нет.")
                return
            
            # Формируем список
            result = f"📋 Участники на {date_str}:\n\n"
            
            for participant in participants:
                # Преобразуем в словарь для безопасного доступа
                participant_dict = dict(participant) if not isinstance(participant, dict) else participant
                
                username = f"@{participant_dict.get('username', '')}" if participant_dict.get('username') else "нет username"
                result += f"{participant_dict.get('registration_time', '')} | {participant_dict.get('kode_slovo', '')} | {participant_dict.get('first_name', '')} ({username}) | {participant_dict.get('phone', '')}\n"
            
            # Добавляем статистику
            result += f"\n📊 Всего участников: {len(participants)}"
            
            # Создаем кнопку для возврата
            keyboard = [[InlineKeyboardButton("🔙 Назад к выбору даты", callback_data="back_to_dates")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Если сообщение слишком длинное, разбиваем на части
            if len(result) > 4000:
                query.edit_message_text("📋 Список участников:")
                
                parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
                for i, part in enumerate(parts):
                    if i == 0:
                        # Первую часть отправляем с кнопкой
                        context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=part,
                            reply_markup=reply_markup
                        )
                    else:
                        context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text=part
                        )
            else:
                query.edit_message_text(result, reply_markup=reply_markup)
        
        # Обработка возврата к выбору даты
        elif callback_data == "back_to_dates":
            # Получаем все уникальные даты из базы
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT DISTINCT date 
                FROM participants 
                ORDER BY date DESC
            ''')
            dates = cursor.fetchall()
            conn.close()
            
            if not dates:
                query.edit_message_text("📭 В базе нет данных об участниках.")
                return
            
            # Создаем кнопки с датами
            keyboard = []
            for i, date_row in enumerate(dates[:10]):
                date_dict = dict(date_row) if not isinstance(date_row, dict) else date_row
                date_str = date_dict.get('date', '')
                
                if not date_str:
                    continue
                    
                try:
                    date_obj = datetime.strptime(date_str, "%d.%m.%Y")
                    weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
                    display_date = f"{date_str} ({weekday})"
                except:
                    display_date = date_str
                
                keyboard.append([InlineKeyboardButton(
                    f"📅 {display_date}", 
                    callback_data=f"list_date:{date_str}"
                )])
            
            # Быстрые кнопки
            today = datetime.now().strftime("%d.%m.%Y")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
            
            keyboard.append([
                InlineKeyboardButton(f"📊 Сегодня ({today})", callback_data=f"list_date:{today}"),
                InlineKeyboardButton(f"📊 Вчера ({yesterday})", callback_data=f"list_date:{yesterday}")
            ])
            
            keyboard.append([InlineKeyboardButton(
                "📝 Ввести другую дату", 
                callback_data="enter_custom_date"
            )])
            
            keyboard.append([InlineKeyboardButton(
                "📈 Общая статистика", 
                callback_data="show_stats"
            )])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(
                "📋 Выберите дату для просмотра участников:\n\n"
                f"Найдено {len(dates)} дней с данными.",
                reply_markup=reply_markup
            )
        
        # Обработка ввода произвольной даты
        elif callback_data == "enter_custom_date":
            query.edit_message_text(
                "📝 Введите дату в формате DD.MM.YYYY:\n"
                "Например: 04.12.2025"
            )
            
            # Сохраняем состояние ожидания ввода даты
            context.user_data['waiting_for_date'] = True
            context.user_data['message_id'] = query.message.message_id
        
        # Обработка статистики
        elif callback_data == "show_stats":
            try:
                stats = db.get_database_stats()
                
                if not stats:
                    query.edit_message_text("❌ Не удалось получить статистику.")
                    return
                
                result = "📈 Общая статистика:\n\n"
                result += f"👥 Всего участников: {stats.get('total_participants', 0)}\n"
                result += f"📅 Дней с данными: {stats.get('unique_dates', 0)}\n"
                result += f"👤 Уникальных пользователей: {stats.get('unique_users', 0)}\n"
                result += f"📆 Первая запись: {stats.get('first_date', 'Нет данных')}\n"
                result += f"📆 Последняя запись: {stats.get('last_date', 'Нет данных')}\n\n"
                
                recent_dates = stats.get('recent_dates', [])
                if recent_dates:
                    result += "📊 Последние 5 дней:\n"
                    for date_stat in recent_dates:
                        date_str = date_stat.get('date', '')
                        count = date_stat.get('count', 0)
                        result += f"• {date_str}: {count} участников\n"
                
                # Кнопка возврата
                keyboard = [[InlineKeyboardButton("🔙 Назад к выбору даты", callback_data="back_to_dates")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                query.edit_message_text(result, reply_markup=reply_markup)
                
            except Exception as e:
                logger.error(f"Ошибка получения статистики: {e}")
                query.edit_message_text("❌ Ошибка при получении статистики.")
                
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}\n{traceback.format_exc()}")
        query.edit_message_text("⚠️ Произошла ошибка при обработке запроса.")

def list_participants(update: Update, context: CallbackContext):
    """Команда /list для администратора - показывает кнопки с датами"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("Пользователь не определен в команде /list")
            return
        
        # Проверяем, является ли пользователь админом
        if user.id != ADMIN_ID:
            logger.warning(f"Пользователь {user.id} попытался использовать команду /list без прав")
            update.message.reply_text("⛔ Эта команда только для администратора.")
            return
        
        # Если указана дата в аргументах - показываем список сразу
        if context.args:
            date_str = context.args[0]
            
            # Проверяем формат даты
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                update.message.reply_text(
                    "❌ Неверный формат даты!\n"
                    "Используйте: DD.MM.YYYY\n"
                    "Пример: /list 04.12.2025"
                )
                return
            
            logger.info(f"Администратор {user.id} запросил список за {date_str}")
            
            # Получаем участников за указанную дату
            try:
                participants = db.get_participants_by_date(date_str)
                
                if not participants:
                    update.message.reply_text(f"📭 На {date_str} участников нет.")
                    return
                
                # Формируем список
                result = f"📋 Участники на {date_str}:\n\n"
                
                for participant in participants:
                    participant_dict = dict(participant) if not isinstance(participant, dict) else participant
                    username = f"@{participant_dict.get('username', '')}" if participant_dict.get('username') else "нет username"
                    result += f"{participant_dict.get('registration_time', '')} | {participant_dict.get('kode_slovo', '')} | {participant_dict.get('first_name', '')} ({username}) | {participant_dict.get('phone', '')}\n"
                
                # Добавляем статистику
                result += f"\n📊 Всего участников: {len(participants)}"
                
                # Если сообщение слишком длинное, разбиваем на части
                if len(result) > 4000:
                    parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1:
                            part += f"\n\n(Часть {i+1} из {len(parts)})"
                        update.message.reply_text(part)
                else:
                    update.message.reply_text(result)
                    
            except Exception as db_error:
                logger.error(f"Ошибка получения данных из БД: {db_error}\n{traceback.format_exc()}")
                update.message.reply_text("⚠️ Произошла ошибка при получении данных из базы.")
            
            return
        
        # Если дата не указана - показываем кнопки с датами
        logger.info(f"Администратор {user.id} открыл меню выбора даты")
        
        # Получаем все уникальные даты из базы
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT date 
            FROM participants 
            ORDER BY date DESC
        ''')
        dates = cursor.fetchall()
        conn.close()
        
        if not dates:
            update.message.reply_text("📭 В базе нет данных об участниках.")
            return
        
        # Создаем кнопки с датами (максимум 10 последних дат)
        keyboard = []
        for i, date_row in enumerate(dates[:10]):
            date_dict = dict(date_row) if not isinstance(date_row, dict) else date_row
            date_str = date_dict.get('date', '')
            
            if not date_str:
                continue
                
            # Форматируем дату для красивого отображения
            try:
                date_obj = datetime.strptime(date_str, "%d.%m.%Y")
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
                display_date = f"{date_str} ({weekday})"
            except:
                display_date = date_str
            
            # Добавляем кнопку
            keyboard.append([InlineKeyboardButton(
                f"📅 {display_date}", 
                callback_data=f"list_date:{date_str}"
            )])
        
        # Добавляем кнопки для быстрого выбора
        today = datetime.now().strftime("%d.%m.%Y")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
        
        keyboard.append([
            InlineKeyboardButton(f"📊 Сегодня ({today})", callback_data=f"list_date:{today}"),
            InlineKeyboardButton(f"📊 Вчера ({yesterday})", callback_data=f"list_date:{yesterday}")
        ])
        
        # Добавляем кнопку для ввода произвольной даты
        keyboard.append([InlineKeyboardButton(
            "📝 Ввести другую дату", 
            callback_data="enter_custom_date"
        )])
        
        # Добавляем кнопку со статистикой
        keyboard.append([InlineKeyboardButton(
            "📈 Общая статистика", 
            callback_data="show_stats"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "📋 Выберите дату для просмотра участников:\n\n"
            f"Найдено {len(dates)} дней с данными.",
            reply_markup=reply_markup
        )
            
    except Exception as e:
        logger.error(f"Ошибка в команде /list: {e}\n{traceback.format_exc()}")
        if update and update.message:
            update.message.reply_text("⚠️ Произошла внутренняя ошибка при обработке команды.")
            
            
def handle_date_input(update: Update, context: CallbackContext):
    """Обработка ввода произвольной даты"""
    try:
        user = update.effective_user
        
        # Проверяем, ждем ли мы ввод даты
        if not context.user_data.get('waiting_for_date'):
            return
        
        # Проверяем права администратора
        if user.id != ADMIN_ID:
            logger.warning(f"Пользователь {user.id} попытался ввести дату без прав")
            return
        
        date_str = update.message.text.strip()
        
        # Проверяем формат даты
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            update.message.reply_text(
                "❌ Неверный формат даты!\n"
                "Используйте: DD.MM.YYYY\n"
                "Пример: 04.12.2025\n\n"
                "Попробуйте еще раз:"
            )
            return
        
        # Очищаем состояние
        context.user_data.pop('waiting_for_date', None)
        
        # Получаем участников за указанную дату
        participants = db.get_participants_by_date(date_str)
        
        if not participants:
            update.message.reply_text(f"📭 На {date_str} участников нет.")
            return
        
        # Формируем список
        result = f"📋 Участники на {date_str}:\n\n"
        
        for participant in participants:
            participant_dict = dict(participant) if not isinstance(participant, dict) else participant
            username = f"@{participant_dict.get('username', '')}" if participant_dict.get('username') else "нет username"
            result += f"{participant_dict.get('registration_time', '')} | {participant_dict.get('kode_slovo', '')} | {participant_dict.get('first_name', '')} ({username}) | {participant_dict.get('phone', '')}\n"
        
        # Добавляем статистику
        result += f"\n📊 Всего участников: {len(participants)}"
        
        # Если сообщение слишком длинное, разбиваем на части
        if len(result) > 4000:
            parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    part += f"\n\n(Часть {i+1} из {len(parts)})"
                update.message.reply_text(part)
        else:
            update.message.reply_text(result)
        
        # Удаляем сообщение с запросом даты, если знаем его ID
        message_id = context.user_data.get('message_id')
        if message_id:
            try:
                context.bot.delete_message(chat_id=update.effective_chat.id, message_id=message_id)
            except:
                pass
        
    except Exception as e:
        logger.error(f"Ошибка обработки ввода даты: {e}\n{traceback.format_exc()}")
        update.message.reply_text("⚠️ Произошла ошибка при обработке даты.")
        
        
def list_participants(update: Update, context: CallbackContext):
    """Команда /list для администратора - показывает кнопки с датами"""
    try:
        user = update.effective_user
        
        if not user:
            logger.error("Пользователь не определен в команде /list")
            return
        
        # Проверяем, является ли пользователь админом
        if user.id != ADMIN_ID:
            logger.warning(f"Пользователь {user.id} попытался использовать команду /list без прав")
            update.message.reply_text("⛔ Эта команда только для администратора.")
            return
        
        # Если указана дата в аргументах - показываем список сразу
        if context.args:
            date_str = context.args[0]
            
            # Проверяем формат даты
            try:
                datetime.strptime(date_str, "%d.%m.%Y")
            except ValueError:
                update.message.reply_text(
                    "❌ Неверный формат даты!\n"
                    "Используйте: DD.MM.YYYY\n"
                    "Пример: /list 04.12.2025"
                )
                return
            
            logger.info(f"Администратор {user.id} запросил список за {date_str}")
            
            # Получаем участников за указанную дату
            try:
                participants = db.get_participants_by_date(date_str)
                
                if not participants:
                    update.message.reply_text(f"📭 На {date_str} участников нет.")
                    return
                
                # Формируем список
                result = f"📋 Участники на {date_str}:\n\n"
                
                for participant in participants:
                    username = f"@{participant['username']}" if participant['username'] else "нет username"
                    result += f"{participant['registration_time']} | {participant['lottery_number']} | {participant['first_name']} ({username}) | {participant['phone']}\n"
                
                # Добавляем статистику
                result += f"\n📊 Всего участников: {len(participants)}"
                
                # Если сообщение слишком длинное, разбиваем на части
                if len(result) > 4000:
                    parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
                    for i, part in enumerate(parts):
                        if i == len(parts) - 1:
                            part += f"\n\n(Часть {i+1} из {len(parts)})"
                        update.message.reply_text(part)
                else:
                    update.message.reply_text(result)
                    
            except Exception as db_error:
                logger.error(f"Ошибка получения данных из БД: {db_error}\n{traceback.format_exc()}")
                update.message.reply_text("⚠️ Произошла ошибка при получении данных из базы.")
            
            return
        
        # Если дата не указана - показываем кнопки с датами
        logger.info(f"Администратор {user.id} открыл меню выбора даты")
        
        # Получаем все уникальные даты из базы
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT DISTINCT date 
            FROM participants 
            ORDER BY date DESC
        ''')
        dates = cursor.fetchall()
        conn.close()
        
        if not dates:
            update.message.reply_text("📭 В базе нет данных об участниках.")
            return
        
        # Создаем кнопки с датами (максимум 10 последних дат)
        keyboard = []
        for i, date_row in enumerate(dates[:10]):
            date_str = date_row['date']
            
            # Форматируем дату для красивого отображения
            try:
                date_obj = datetime.strptime(date_str, "%d.%m.%Y")
                weekday = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date_obj.weekday()]
                display_date = f"{date_str} ({weekday})"
            except:
                display_date = date_str
            
            # Добавляем кнопку
            keyboard.append([InlineKeyboardButton(
                f"📅 {display_date}", 
                callback_data=f"list_date:{date_str}"
            )])
        
        # Добавляем кнопки для быстрого выбора
        today = datetime.now().strftime("%d.%m.%Y")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
        
        keyboard.append([
            InlineKeyboardButton(f"📊 Сегодня ({today})", callback_data=f"list_date:{today}"),
            InlineKeyboardButton(f"📊 Вчера ({yesterday})", callback_data=f"list_date:{yesterday}")
        ])
        
        # Добавляем кнопку для ввода произвольной даты
        keyboard.append([InlineKeyboardButton(
            "📝 Ввести другую дату", 
            callback_data="enter_custom_date"
        )])
        
        # Добавляем кнопку со статистикой
        keyboard.append([InlineKeyboardButton(
            "📈 Общая статистика", 
            callback_data="show_stats"
        )])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "📋 Выберите дату для просмотра участников:\n\n"
            f"Найдено {len(dates)} дней с данными.",
            reply_markup=reply_markup
        )
            
    except Exception as e:
        logger.error(f"Ошибка в команде /list: {e}\n{traceback.format_exc()}")
        if update and update.message:
            update.message.reply_text("⚠️ Произошла внутренняя ошибка при обработке команды.")
            
def cancel(update: Update, context: CallbackContext) -> int:
    """Отмена регистрации"""
    try:
        user_id = update.effective_user.id if update.effective_user else "unknown"
        logger.info(f"Пользователь {user_id} отменил регистрацию")
        
        # Создаем клавиатуру с кнопкой /start
        keyboard = [[KeyboardButton("/start")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        update.message.reply_text(
            "Регистрация отменена.\n\n"
            "Нажмите /start для начала заново:",
            reply_markup=reply_markup
        )
        context.user_data.clear()
        return ConversationHandler.END
        
    except Exception as e:
        logger.error(f"Ошибка при отмене: {e}\n{traceback.format_exc()}")
        return ConversationHandler.END

def help_command(update: Update, context: CallbackContext):
    """Команда /help - справка"""
    try:
        user = update.effective_user
        
        # Создаем клавиатуру с кнопкой /start
        keyboard = [[KeyboardButton("/start")]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        help_text = (
            f"Правила розыгрыша «Нетайный Санта»  (далее «Розыгрыш» )\n\n"
            "Срок проведения розыгрыша — С 15 по 25 декабря 2025 года\n\n"
            "Порядок проведения Розыгрыша:\n"
            "В период с 15 по 25 декабря 2025 года по будням с 18:30 до 20:00 на телеканале «7 канал Красноярск» в любой момент на экране появляется  всплывающий баннер с кодовым словом. Победителем является первый участник, приславший указанное кодовое слово в телеграмм-бот «7 канала Красноярск» Санта7бот.\n"
            "Приз Победителю (пользователю телефонного номера) - платеж в размере 1000 рублей передается в течение 48 часов с момента  появления кодового слова ежедневного Розыгрыша при условии идентификации Победителя как физического лица.\n\n"
            "Один и тот же зритель может становится Победителем неоднократно.\n\n"
            "Среди всех Победителей за период Розыгрыша, будет случайным образом  выбран обладатель главного приза. Итоги розыгрыша главного приза – демонстрируются в вечернем выпуске новостей 31 декабря 2025 года.\n\n"
            "Принимая участие в Розыгрыше  путем направления кодового слова на указанный номер телефона-участник Розыгрыша, подтверждает свое согласие на участие в Розыгрыше, ознакомление и согласие с настоящими Правилами Розыгрыша во всех пунктах без каких-либо изъятий.\n\n"
            "Победитель (получатель приза) идентифицируется по реквизитам - номеру телефона с которого отправлено кодовое слово.\n\n"
            "Получатели призов берут на себя ответственность за оплату налогов и иные обязательства, связанные с получением призов, в соответствии с законодательством РФ: (ст. 217 НК РФ, в т.ч.- получение рекламных подарков (выигрышей), совокупная стоимость которых превышает 4 000,00 руб. за календарный год).  Принятием приза \n"
            "Победитель подтверждает уведомление  надлежащим образом о вышеуказанной обязанности.\n\n"
            "Розыгрыш не является лотереей либо иной игрой, основанной на риске, поэтому не требует обязательной регистрации или направления уведомления в соответствующие государственные органы.\n"
            "Организатор розыгрыша – редакция СМИ «7 канал Красноярск».\n\n"
            "Телефон для справок:** 2-900-333\n"
        )
        
        update.message.reply_text(help_text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /help: {e}\n{traceback.format_exc()}")
        if update and update.message:
            update.message.reply_text("⚠️ Произошла ошибка при показе справки.")
            
def error_handler(update: Update, context: CallbackContext):
    """Глобальный обработчик ошибок"""
    try:
        error = context.error
        
        # Логируем ошибку с деталями
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'user_id': update.effective_user.id if update and update.effective_user else None,
            'chat_id': update.effective_chat.id if update and update.effective_chat else None,
            'message_text': update.message.text if update and update.message else None
        }
        
        logger.error(f"Глобальная ошибка: {error_details}\n{traceback.format_exc()}")
        
        # Отправляем сообщение пользователю
        if update and update.message:
            try:
                # Создаем клавиатуру с кнопкой /start
                keyboard = [[KeyboardButton("/start")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    "⚠️ Произошла непредвиденная ошибка.\n"
                    "Пожалуйста, попробуйте позже.\n\n"
                    "Нажмите /start для начала заново:",
                    reply_markup=reply_markup
                )
            except:
                pass  # Не удалось отправить сообщение
        
        # Уведомляем администратора
        try:
            context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Произошла ошибка в боте:\n\n"
                     f"Тип: {type(error).__name__}\n"
                     f"Сообщение: {str(error)[:200]}\n"
                     f"Пользователь: {update.effective_user.id if update and update.effective_user else 'неизвестен'}"
            )
        except:
            logger.error("Не удалось уведомить администратора об ошибке")
            
    except Exception as e:
        logger.critical(f"Критическая ошибка в обработчике ошибок: {e}\n{traceback.format_exc()}")

def database_health_check():
    """Проверка работоспособности базы данных"""
    try:
        # Проверяем подключение к БД
        test_result = db.get_participants_by_date("01.01.2025")
        logger.info("Проверка базы данных: OK")
        return True
    except Exception as e:
        logger.error(f"Проверка базы данных: FAILED - {e}")
        return False

def main():
    """Запуск бота"""
    try:
        try:
            db.migrate_to_kode_slovo()
        except Exception as e:
            logger.warning(f"Миграция не удалась: {e}")
            
        # Проверяем базу данных перед запуском
        if not database_health_check():
            logger.error("База данных недоступна. Бот не может быть запущен.")
            return
        
        
        
        # Создаем Updater и Dispatcher
        updater = Updater(TOKEN, use_context=True)
        dispatcher = updater.dispatcher
        
        # Настраиваем ConversationHandler для регистрации
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', start)],
            states={
                WAITING_FOR_NUMBER: [
                    MessageHandler(Filters.text & ~Filters.command, handle_lottery_number),
                    MessageHandler(Filters.command, handle_start_button)  # Обработка /start из состояния
                ],
                WAITING_FOR_PHONE: [
                    MessageHandler(Filters.contact, handle_phone),
                    MessageHandler(Filters.text, handle_phone)  # Обрабатываем и текст и команды
                ],
            },
            fallbacks=[
                CommandHandler('cancel', cancel),
                CommandHandler('start', handle_start_button)  # Падение на /start
            ],
        )
        
        # Регистрируем обработчики команд
        dispatcher.add_handler(conv_handler)
        dispatcher.add_handler(CommandHandler("list", list_participants))
        dispatcher.add_handler(CommandHandler("help", help_command))
        
        dispatcher.add_handler(CallbackQueryHandler(handle_callback_query))
        dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_date_input))
        
        # Команда для проверки статуса бота (только для админа)
        def status_command(update: Update, context: CallbackContext):
            if update.effective_user.id == ADMIN_ID:
                # Создаем клавиатуру с кнопкой /start
                keyboard = [[KeyboardButton("/start")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                update.message.reply_text(
                    f"🤖 Статус бота:\n"
                    f"✅ Работает\n"
                    f"🕐 Время сервера: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                    f"👤 Админ ID: {ADMIN_ID}\n\n"
                    "Нажмите /start для тестирования регистрации:",
                    reply_markup=reply_markup
                )
        
        dispatcher.add_handler(CommandHandler("status", status_command))
        
        # Обработчик для команды /start вне ConversationHandler
        dispatcher.add_handler(CommandHandler("start", handle_start_button))
        
        # Глобальный обработчик ошибок
        dispatcher.add_error_handler(error_handler)
        
        # Запускаем бота
        updater.start_polling()
        logger.info("✅ Бот успешно запущен!")
        
        # Отправляем уведомление администратору о запуске
        try:
            # Создаем клавиатуру с кнопкой /start
            keyboard = [[KeyboardButton("/start")]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            
            updater.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"Нажмите /start для запуска регистрации:",
                reply_markup=reply_markup
            )
        except:
            logger.warning("Не удалось отправить уведомление администратору")
        
        updater.idle()
        
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}\n{traceback.format_exc()}")
        
        # Попытка уведомить администратора о падении бота
        try:
            import requests
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={
                    'chat_id': ADMIN_ID,
                    'text': f"❌ Бот упал с ошибкой:\n{str(e)[:100]}"
                },
                timeout=5
            )
        except:
            pass

if __name__ == '__main__':
    main()