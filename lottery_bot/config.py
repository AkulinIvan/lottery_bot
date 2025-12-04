# lottery_bot/config.py
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Конфигурация бота
class Config:
    # Токен бота
    BOT_TOKEN = os.getenv('BOT_TOKEN')
    
    # ID администратора
    ADMIN_ID = int(os.getenv('ADMIN_ID'))
    
    # Путь к базе данных
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'lottery.db')
    
    # Настройки логирования
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    DEBUG_MODE = os.getenv('DEBUG_MODE', 'False').lower() == 'true'
    
    @classmethod
    def validate(cls):
        """Проверка конфигурации"""
        errors = []
        
        if not cls.BOT_TOKEN or cls.BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
            errors.append("BOT_TOKEN не настроен в .env файле")
        
        if not cls.ADMIN_ID or cls.ADMIN_ID == 0:
            errors.append("ADMIN_ID не настроен в .env файле")
        
        if errors:
            raise ValueError(f"Ошибки конфигурации: {', '.join(errors)}")
        
        return True

# Экземпляр конфигурации
config = Config()