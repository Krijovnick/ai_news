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
        """Отправляет сообщение в Telegram"""
        try:
            # Разбиваем длинные сообщения на части (лимит Telegram - 4096 символов)
            max_length = 3800  # Увеличиваем запас для полных заголовков
            if len(message) <= max_length:
                self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode=parse_mode,
                    disable_web_page_preview=True
                )
                self.logger.info("Сообщение успешно отправлено в Telegram")
                return True
            else:
                # Разбиваем на части
                parts = self._split_message(message, max_length)
                for i, part in enumerate(parts):
                    if i == 0:
                        part += "\n\n_Продолжение следует..._"
                    elif i == len(parts) - 1:
                        part = f"_Продолжение ({i+1}/{len(parts)})_\n\n" + part
                    else:
                        part = f"_Продолжение ({i+1}/{len(parts)})_\n\n" + part + "\n\n_Продолжение следует..._"
                    
                    self.bot.send_message(
                        chat_id=self.chat_id,
                        text=part,
                        parse_mode=parse_mode,
                        disable_web_page_preview=True
                    )
                
                self.logger.info(f"Сообщение разбито на {len(parts)} частей и отправлено в Telegram")
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
    
    def send_test_message(self) -> bool:
        """Отправляет тестовое сообщение"""
        test_message = "🤖 *AI News Aggregator*\n\nБот успешно запущен и готов к работе!"
        return self.send_message(test_message)
    
    def send_error_message(self, error_message: str) -> bool:
        """Отправляет сообщение об ошибке"""
        error_text = f"❌ *Ошибка в AI News Aggregator*\n\n{error_message}"
        return self.send_message(error_text)
    
    def send_summary(
        self,
        news_count: int,
        sources_used: list,
        errors: list = None,
        run_name: str = "AI News Aggregator",
    ) -> bool:
        """Отправляет сводку о работе агрегатора"""
        summary = f"📊 *Сводка работы {run_name}*\n\n"
        summary += f"📰 Найдено новостей: {news_count}\n"
        summary += f"🔍 Источники: {', '.join(sources_used)}\n"
        
        if errors:
            summary += f"\n⚠️ Ошибки: {len(errors)}\n"
            for error in errors[:3]:  # Показываем только первые 3 ошибки
                summary += f"• {error}\n"
        
        return self.send_message(summary)
