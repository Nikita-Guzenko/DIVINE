#!/usr/bin/env python3
"""
Telegram Channel Bot - отправка сообщений в канал
"""

import requests
import sys
from telegram_config import BOT_TOKEN, CHANNEL_ID


def send_message(text: str, parse_mode: str = "HTML") -> dict:
    """
    Отправить сообщение в канал

    Args:
        text: Текст сообщения (поддерживает HTML разметку)
        parse_mode: HTML или Markdown

    Returns:
        Ответ от Telegram API
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": parse_mode
    }

    response = requests.post(url, json=payload)
    result = response.json()

    if result.get("ok"):
        print(f"Сообщение отправлено в канал")
        return result
    else:
        print(f"Ошибка: {result.get('description')}")
        return result


def send_report(title: str, content: str) -> dict:
    """
    Отправить форматированный отчёт
    """
    message = f"<b>{title}</b>\n\n{content}"
    return send_message(message)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        send_message(text)
    else:
        print("Использование: python telegram_channel.py 'Текст сообщения'")
        print("Или импортируйте: from telegram_channel import send_message")
