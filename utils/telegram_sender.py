import logging
from telegram import Bot
from telegram.error import TelegramError
from utils.config import Config

class TelegramSender:
    """Класс для отправки сообщений в Telegram"""
    
    def __init__(self):
        self.config = Config()
        self.bot = Bot(token=self.config.TELEGRAM_BOT_TOKEN)
        self.chat_id = self.config.TELEGRAM_CHAT_ID
        self.logger = logging.getLogger(__name__)
    
    def send_message(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Отправляет сообщение в Telegram. parse_mode=None — без разметки."""
        try:
            kwargs = {
                "chat_id": self.chat_id,
                "text": message,
                "disable_web_page_preview": True,
            }
            if parse_mode:
                kwargs["parse_mode"] = parse_mode

            max_length = 3800
            if len(message) <= max_length:
                self.bot.send_message(**kwargs)
                self.logger.info("Сообщение успешно отправлено в Telegram")
                return True

            parts = self._split_message(message, max_length)
            for part in parts:
                part_kwargs = dict(kwargs)
                part_kwargs["text"] = part
                self.bot.send_message(**part_kwargs)

            self.logger.info("Сообщение разбито на %s частей и отправлено в Telegram", len(parts))
            return True

        except TelegramError as e:
            self.logger.error(f"Ошибка при отправке сообщения в Telegram: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Неожиданная ошибка при отправке в Telegram: {e}")
            return False
    
    def _split_message(self, message: str, max_length: int) -> list:
        """Разбивает сообщение на части"""
        parts = []
        lines = message.split('\n')
        current_part = ""
        
        for line in lines:
            # Если добавление строки не превысит лимит
            if len(current_part + line + '\n') <= max_length:
                current_part += line + '\n'
            else:
                # Сохраняем текущую часть и начинаем новую
                if current_part:
                    parts.append(current_part.strip())
                current_part = line + '\n'
        
        # Добавляем последнюю часть
        if current_part:
            parts.append(current_part.strip())
        
        return parts
