# lottery_bot/database.py
import sqlite3
import logging
from datetime import datetime
import traceback
from config import config
logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or config.DATABASE_PATH
        self.init_db()
    
    def get_connection(self):
        """Создание соединения с базой данных с обработкой ошибок"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Ошибка подключения к БД: {e}\n{traceback.format_exc()}")
            raise
    
    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Таблица участников
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,                    -- Дата в формате DD.MM.YYYY
                    kode_slovo TEXT NOT NULL,             -- Кодовое слово (до 16 символов)
                    user_id INTEGER NOT NULL,              -- ID пользователя Telegram
                    username TEXT,                         -- Username пользователя
                    first_name TEXT NOT NULL,              -- Имя пользователя
                    phone TEXT NOT NULL,                   -- Номер телефона
                    registration_time TEXT NOT NULL,       -- Время регистрации HH:MM:SS
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Индекс для быстрого поиска по дате
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_date 
                ON participants(date)
            ''')
            
            # Индекс для проверки уникальности (пользователь может участвовать только 1 раз в день)
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_user_date_unique 
                ON participants(user_id, date)
            ''')
            
            conn.commit()
            logger.info("✅ База данных успешно инициализирована")
            
            # Проверяем существующие данные
            cursor.execute('SELECT COUNT(*) as count FROM participants')
            count = cursor.fetchone()['count']
            logger.info(f"📊 В базе уже есть {count} записей")
            
            # Проверяем структуру таблицы
            cursor.execute("PRAGMA table_info(participants)")
            columns = cursor.fetchall()
            logger.info(f"Структура таблицы participants: {[col[1] for col in columns]}")
            
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка инициализации БД: {e}\n{traceback.format_exc()}")
            raise
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка при инициализации БД: {e}\n{traceback.format_exc()}")
            raise
        finally:
            if 'conn' in locals():
                conn.close()
    
    def save_participant(self, kode_slovo, user_id, username, first_name, phone):
        """Сохранение участника в базу данных"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            current_date = datetime.now().strftime("%d.%m.%Y")
            current_time = datetime.now().strftime("%H:%M:%S")

            # Проверяем, не участвовал ли пользователь сегодня
            cursor.execute('''
                SELECT id, kode_slovo, registration_time 
                FROM participants 
                WHERE user_id = ? AND date = ?
            ''', (user_id, current_date))

            existing = cursor.fetchone()

            if existing:
                logger.warning(f"Пользователь {user_id} уже участвовал сегодня "
                              f"(кодовое слово: {existing['kode_slovo']}, время: {existing['registration_time']})")
                raise ValueError(f"Вы уже участвовали в розыгрыше сегодня в {existing['registration_time']} с кодовым словом {existing['kode_slovo']}. Попробуйте завтра!")

            # Сохраняем участника
            cursor.execute('''
                INSERT INTO participants 
                (date, kode_slovo, user_id, username, first_name, phone, registration_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (current_date, kode_slovo, user_id, username, first_name, phone, current_time))

            conn.commit()
            logger.info(f"✅ Участник сохранен: {user_id}, кодовое слово: {kode_slovo}, время: {current_time}")

            return True

        except sqlite3.IntegrityError as e:
            logger.error(f"❌ Ошибка целостности данных при сохранении: {e}")
            if conn:
                conn.rollback()

            # Проверяем, это из-за уникальности или другой причины
            error_str = str(e)
            if "UNIQUE constraint failed" in error_str:
                # Пытаемся получить существующую запись
                try:
                    cursor.execute('''
                        SELECT kode_slovo, registration_time 
                        FROM participants 
                        WHERE user_id = ? AND date = ?
                    ''', (user_id, current_date))
                    existing = cursor.fetchone()
                    if existing:
                        raise ValueError(f"Вы уже участвовали в розыгрыше сегодня в {existing['registration_time']} с кодовым словом {existing['kode_slovo']}")
                    else:
                        raise ValueError("Вы уже участвовали в розыгрыше сегодня")
                except:
                    raise ValueError("Вы уже участвовали в розыгрыше сегодня")
            else:
                raise Exception(f"Ошибка сохранения в базу данных: {error_str}")

        except ValueError as e:
            # Пробрасываем уже обработанные ошибки
            raise e

        except Exception as e:
            logger.error(f"❌ Ошибка при сохранении участника: {e}\n{traceback.format_exc()}")
            if conn:
                conn.rollback()

            # Проверяем, если это ошибка уникальности
            if "UNIQUE constraint failed" in str(e):
                raise ValueError("Вы уже участвовали в розыгрыше сегодня")
            else:
                raise Exception(f"Ошибка сохранения в базу данных: {str(e)}")

        finally:
            if conn:
                conn.close()
    
    def get_participants_by_date(self, date):
        """Получение участников по дате"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем формат даты
            try:
                datetime.strptime(date, "%d.%m.%Y")
            except ValueError:
                raise ValueError("Неверный формат даты")
            
            cursor.execute('''
                SELECT date, kode_slovo, first_name, username, phone, registration_time
                FROM participants 
                WHERE date = ?
                ORDER BY registration_time
            ''', (date,))
            
            participants = cursor.fetchall()
            
            logger.info(f"📋 Запрошены участники за {date}: найдено {len(participants)} записей")
            
            return participants
            
        except ValueError as e:
            raise  # Пробрасываем ошибки валидации
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка SQLite при чтении: {e}\n{traceback.format_exc()}")
            raise Exception("Ошибка чтения из базы данных")
        except Exception as e:
            logger.error(f"❌ Неизвестная ошибка при чтении: {e}\n{traceback.format_exc()}")
            raise
        finally:
            if conn:
                conn.close()
    
    def can_user_participate_today(self, user_id):
        """Проверка, может ли пользователь участвовать сегодня"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            current_date = datetime.now().strftime("%d.%m.%Y")
            
            cursor.execute('''
                SELECT COUNT(*) as count 
                FROM participants 
                WHERE user_id = ? AND date = ?
            ''', (user_id, current_date))
            
            result = cursor.fetchone()
            can_participate = result['count'] == 0
            
            if not can_participate:
                logger.info(f"Пользователь {user_id} уже участвовал сегодня")
            else:
                logger.info(f"Пользователь {user_id} может участвовать сегодня")
            
            return can_participate
            
        except Exception as e:
            logger.error(f"Ошибка проверки участия пользователя: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def check_database_integrity(self):
        """Проверка целостности базы данных"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем целостность базы данных
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            if result[0] == "ok":
                logger.info("✅ Проверка целостности БД: OK")
                return True
            else:
                logger.error(f"❌ Проблемы с целостностью БД: {result[0]}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка проверки целостности БД: {e}\n{traceback.format_exc()}")
            return False
        finally:
            if conn:
                conn.close()
    
    def get_database_stats(self):
        """Получение статистики базы данных"""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Общая статистика
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_participants,
                    COUNT(DISTINCT date) as unique_dates,
                    COUNT(DISTINCT user_id) as unique_users,
                    MIN(date) as first_date,
                    MAX(date) as last_date
                FROM participants
            ''')
            
            stats_row = cursor.fetchone()
            
            if not stats_row:
                return None
            
            # Преобразуем в словарь для удобного доступа
            stats = dict(stats_row)
            
            # Статистика по датам
            cursor.execute('''
                SELECT 
                    date,
                    COUNT(*) as count,
                    GROUP_CONCAT(DISTINCT kode_slovo) as kode_slova
                FROM participants
                GROUP BY date
                ORDER BY date DESC
                LIMIT 5
            ''')
            
            recent_dates_rows = cursor.fetchall()
            recent_dates = []
            
            for row in recent_dates_rows:
                recent_dates.append(dict(row))
            
            return {
                'total_participants': stats.get('total_participants', 0) or 0,
                'unique_dates': stats.get('unique_dates', 0) or 0,
                'unique_users': stats.get('unique_users', 0) or 0,
                'first_date': stats.get('first_date', 'Нет данных') or 'Нет данных',
                'last_date': stats.get('last_date', 'Нет данных') or 'Нет данных',
                'recent_dates': recent_dates
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения статистики БД: {e}\n{traceback.format_exc()}")
            return None
        finally:
            if conn:
                conn.close()
    
    def migrate_to_kode_slovo(self):
        """Миграция данных из старого формата (если нужно)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            # Проверяем, существует ли колонка lottery_number
            cursor.execute("PRAGMA table_info(participants)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'lottery_number' in columns and 'kode_slovo' not in columns:
                logger.info("Начинаем миграцию данных из lottery_number в kode_slovo...")
                
                # Добавляем новую колонку
                cursor.execute('ALTER TABLE participants ADD COLUMN kode_slovo TEXT')
                
                # Копируем данные из lottery_number в kode_slovo
                cursor.execute('UPDATE participants SET kode_slovo = lottery_number')
                
                # Удаляем старую колонку (если нужно)
                # cursor.execute('ALTER TABLE participants DROP COLUMN lottery_number')
                
                conn.commit()
                logger.info("✅ Миграция данных завершена успешно")
                return True
            else:
                logger.info("Миграция не требуется: колонка kode_slovo уже существует или lottery_number отсутствует")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка миграции данных: {e}\n{traceback.format_exc()}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()