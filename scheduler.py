#!/usr/bin/env python3
"""
Планировщик задач для AI News Aggregator
Запускает агрегатор по расписанию
"""

import schedule
import time
import logging
import sys
import os
from datetime import datetime

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from main import AINewsAggregator
from utils.config import setup_logging

class NewsScheduler:
    """Планировщик для автоматического запуска агрегатора"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.aggregator = AINewsAggregator()
    
    def run_aggregator(self):
        """Запускает агрегатор новостей"""
        try:
            self.logger.info(f"Запуск агрегатора по расписанию: {datetime.now()}")
            self.aggregator.run()
        except Exception as e:
            self.logger.error(f"Ошибка при запуске агрегатора: {e}")
    
    def setup_schedule(self):
        """Настраивает расписание запуска"""
        # Ежедневно в 9:00
        schedule.every().day.at("09:00").do(self.run_aggregator)
        
        # Ежедневно в 18:00
        schedule.every().day.at("18:00").do(self.run_aggregator)
        
        # Каждые 6 часов (для тестирования)
        # schedule.every(6).hours.do(self.run_aggregator)
        
        self.logger.info("Расписание настроено:")
        self.logger.info("- Ежедневно в 09:00")
        self.logger.info("- Ежедневно в 18:00")
    
    def run(self):
        """Запускает планировщик"""
        self.logger.info("Запуск планировщика AI News Aggregator...")
        
        # Настраиваем расписание
        self.setup_schedule()
        
        # Запускаем один раз сразу для тестирования
        self.logger.info("Запуск агрегатора для тестирования...")
        self.run_aggregator()
        
        # Основной цикл планировщика
        self.logger.info("Планировщик запущен. Ожидание задач...")
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Проверяем каждую минуту
            except KeyboardInterrupt:
                self.logger.info("Планировщик остановлен пользователем")
                break
            except Exception as e:
                self.logger.error(f"Ошибка в планировщике: {e}")
                time.sleep(60)

def main():
    """Точка входа в планировщик"""
    # Настраиваем логирование
    logger = setup_logging()
    
    try:
        # Создаем и запускаем планировщик
        scheduler = NewsScheduler()
        scheduler.run()
        
    except KeyboardInterrupt:
        logger.info("Планировщик прерван пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка в планировщике: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
