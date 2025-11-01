#!/usr/bin/env python3
"""
Скрипт установки AI News Aggregator
Автоматически устанавливает зависимости и настраивает проект
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_python_version():
    """Проверяет версию Python"""
    if sys.version_info < (3, 8):
        print("❌ Требуется Python 3.8 или выше")
        print(f"   Текущая версия: {sys.version}")
        return False
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True

def install_requirements():
    """Устанавливает зависимости из requirements.txt"""
    print("\n📦 Установка зависимостей...")
    
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("✅ Зависимости установлены успешно")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка установки зависимостей: {e}")
        return False

def create_directories():
    """Создает необходимые директории"""
    print("\n📁 Создание директорий...")
    
    directories = ["logs", "data"]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Директория {directory} создана")
    
    return True

def create_env_file():
    """Создает .env файл из примера"""
    print("\n⚙️ Настройка конфигурации...")
    
    if os.path.exists(".env"):
        print("✅ Файл .env уже существует")
        return True
    
    if os.path.exists("env.example"):
        try:
            shutil.copy("env.example", ".env")
            print("✅ Файл .env создан из env.example")
            print("⚠️ Не забудьте отредактировать .env файл с вашими API ключами!")
            return True
        except Exception as e:
            print(f"❌ Ошибка создания .env файла: {e}")
            return False
    else:
        print("❌ Файл env.example не найден")
        return False

def test_installation():
    """Тестирует установку"""
    print("\n🧪 Тестирование установки...")
    
    try:
        # Импортируем основные модули
        from utils.config import Config
        from utils.filters import NewsFilter
        from utils.telegram_sender import TelegramSender
        
        print("✅ Основные модули импортированы успешно")
        return True
    except ImportError as e:
        print(f"❌ Ошибка импорта модулей: {e}")
        return False

def show_next_steps():
    """Показывает следующие шаги"""
    print("\n" + "=" * 60)
    print("🎉 Установка завершена!")
    print("\n📋 Следующие шаги:")
    print("1. Отредактируйте файл .env с вашими API ключами")
    print("2. Запустите тест: python test_aggregator.py")
    print("3. Запустите агрегатор: python main.py")
    print("4. Для автоматического запуска: python scheduler.py")
    print("\n📚 Документация: README.md")
    print("=" * 60)

def main():
    """Основная функция установки"""
    print("🚀 Установка AI News Aggregator")
    print("=" * 40)
    
    steps = [
        ("Проверка Python", check_python_version),
        ("Создание директорий", create_directories),
        ("Установка зависимостей", install_requirements),
        ("Создание конфигурации", create_env_file),
        ("Тестирование", test_installation)
    ]
    
    for step_name, step_func in steps:
        print(f"\n{step_name}...")
        if not step_func():
            print(f"❌ Ошибка на этапе: {step_name}")
            sys.exit(1)
    
    show_next_steps()

if __name__ == "__main__":
    main()
