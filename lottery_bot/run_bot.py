#!/usr/bin/env python3
"""
Скрипт для запуска бота с дополнительными проверками
"""

import sys
from datetime import datetime

def check_python_version():
    """Проверка версии Python"""
    if sys.version_info < (3, 7):
        print("❌ Требуется Python 3.7 или выше")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def check_dependencies():
    """Проверка зависимостей"""
    try:
        import telegram
        print(f"✅ python-telegram-bot {telegram.__version__}")
        return True
    except ImportError as e:
        print(f"❌ Не установлена библиотека python-telegram-bot")
        print("Установите: pip install python-telegram-bot==13.7")
        return False

def check_token():
    """Проверка наличия токена"""
    # В реальном проекте токен лучше хранить в переменных окружения
    print("ℹ️  Токен проверяется в коде бота")
    return True

def check_database():
    """Проверка базы данных"""
    try:
        from database import Database
        db = Database()
        
        # Проверяем соединение
        test_result = db.get_participants_by_date("01.01.2025")
        print("✅ База данных доступна")
        
        # Проверяем целостность
        if db.check_database_integrity():
            print("✅ Целостность базы данных в порядке")
        else:
            print("⚠️  Возможны проблемы с целостностью базы данных")
            
        return True
    except Exception as e:
        print(f"❌ Проблема с базой данных: {e}")
        return False

def main():
    """Основная функция проверки и запуска"""
    print("=" * 50)
    print(f"Запуск Lottery Bot - {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}")
    print("=" * 50)
    
    # Выполняем проверки
    checks = [
        ("Версия Python", check_python_version),
        ("Зависимости", check_dependencies),
        ("Токен бота", check_token),
        ("База данных", check_database),
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        print(f"\n🔍 Проверка: {check_name}")
        if not check_func():
            all_passed = False
            print(f"❌ Проверка '{check_name}' не пройдена")
        else:
            print(f"✅ Проверка '{check_name}' пройдена")
    
    if not all_passed:
        print("\n❌ Не все проверки пройдены. Бот не может быть запущен.")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("✅ Все проверки пройдены успешно!")
    print("🚀 Запускаем бота...")
    print("=" * 50 + "\n")
    
    # Запускаем бота
    from bot import main as run_bot
    run_bot()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Бот остановлен пользователем")
        sys.exit(0)
    except Exception as e:
        print(f"\n\n❌ Критическая ошибка: {e}")
        sys.exit(1)