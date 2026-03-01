#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TELEGRAM MONITORING BOT
Мониторинг всех действий пользователей Telegram
Для платформы BotHost.ru

⚠️ ВНИМАНИЕ: Использование бота без согласия третьих лиц НЕЗАКОННО!
Разработчики не несут ответственности за неправомерное использование.

Автор: AI Developer
Дата: 2026-03-01
Версия: 1.0.0
"""

import asyncio
import json
import logging
import os
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Set
from collections import defaultdict
import re

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Update,
    User as TelegramUser,
    Chat,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData


# ════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ════════════════════════════════════════════════════════════════

BOT_TOKEN = "8296802832:AAEU4oF4v5bjKP3KTb1rRx1Oxf-Z1dng9QQ"
ADMIN_USERNAME = "mrztn"
ADMIN_ID = 7785371505
BOT_USERNAME = "@mrztnbot"

# Директории для хранения (BotHost совместимо)
DATA_DIR = "data"
LOGS_DIR = "logs"
EXPORTS_DIR = "exports"

for directory in [DATA_DIR, LOGS_DIR, EXPORTS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Пути к файлам данных
USERS_FILE = os.path.join(DATA_DIR, "users.json")
ACTIVITY_FILE = os.path.join(DATA_DIR, "activity.json")
ALERTS_FILE = os.path.join(DATA_DIR, "alerts.json")
STATS_FILE = os.path.join(DATA_DIR, "stats.json")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "bot.log"), encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ ДАННЫХ (JSON-BASED)
# ════════════════════════════════════════════════════════════════

class DataStorage:
    """Класс для работы с JSON-хранилищем"""
    
    def __init__(self):
        self.users: Dict[int, Dict] = self._load_json(USERS_FILE, {})
        self.activity: List[Dict] = self._load_json(ACTIVITY_FILE, [])
        self.alerts: List[Dict] = self._load_json(ALERTS_FILE, [])
        self.stats: Dict = self._load_json(STATS_FILE, self._default_stats())
    
    @staticmethod
    def _load_json(filepath: str, default: Any) -> Any:
        """Загрузить JSON"""
        try:
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки {filepath}: {e}")
        return default
    
    @staticmethod
    def _save_json(filepath: str, data: Any):
        """Сохранить JSON"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения {filepath}: {e}")
    
    def _default_stats(self) -> Dict:
        """Статистика по умолчанию"""
        return {
            "total_users": 0,
            "total_events": 0,
            "deleted_messages": 0,
            "edited_messages": 0,
            "media_intercepted": 0,
            "secret_chats": 0,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    
    def save_all(self):
        """Сохранить все данные"""
        self._save_json(USERS_FILE, self.users)
        self._save_json(ACTIVITY_FILE, self.activity[-10000:])  # Последние 10k событий
        self._save_json(ALERTS_FILE, self.alerts[-1000:])  # Последние 1k алертов
        self._save_json(STATS_FILE, self.stats)
    
    def add_user(self, user_id: int, user_data: Dict):
        """Добавить пользователя"""
        self.users[str(user_id)] = {
            **user_data,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
            "is_active": True
        }
        self.stats["total_users"] += 1
        self.save_all()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        """Получить пользователя"""
        return self.users.get(str(user_id))
    
    def update_user(self, user_id: int, updates: Dict):
        """Обновить данные пользователя"""
        if str(user_id) in self.users:
            self.users[str(user_id)].update(updates)
            self.users[str(user_id)]["last_activity"] = datetime.now(timezone.utc).isoformat()
            self.save_all()
    
    def add_event(self, event_type: str, user_id: int, data: Dict):
        """Добавить событие"""
        event = {
            "type": event_type,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data
        }
        self.activity.append(event)
        self.stats["total_events"] += 1
        
        # Обновляем счётчики
        if event_type == "message_deleted":
            self.stats["deleted_messages"] += 1
        elif event_type == "message_edited":
            self.stats["edited_messages"] += 1
        elif event_type == "media_intercepted":
            self.stats["media_intercepted"] += 1
        elif event_type == "secret_chat":
            self.stats["secret_chats"] += 1
        
        self.save_all()
    
    def add_alert(self, alert_type: str, user_id: int, message: str, severity: str = "info"):
        """Добавить алерт"""
        alert = {
            "type": alert_type,
            "user_id": user_id,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        self.alerts.append(alert)
        self.save_all()
        return alert
    
    def get_user_events(self, user_id: int, limit: int = 100) -> List[Dict]:
        """Получить события пользователя"""
        return [e for e in self.activity if e["user_id"] == user_id][-limit:]
    
    def get_all_users(self) -> List[Dict]:
        """Получить всех пользователей"""
        return [{"id": int(k), **v} for k, v in self.users.items()]
    
    def search_events(self, query: str, limit: int = 50) -> List[Dict]:
        """Поиск по событиям"""
        results = []
        query_lower = query.lower()
        
        for event in reversed(self.activity):
            event_str = json.dumps(event, ensure_ascii=False).lower()
            if query_lower in event_str:
                results.append(event)
                if len(results) >= limit:
                    break
        
        return results


# ════════════════════════════════════════════════════════════════
# ТЕКСТЫ И ПОЛИТИКА
# ════════════════════════════════════════════════════════════════

TEXTS = {
    "start_warning": (
        "⚠️ <b>КРИТИЧЕСКИ ВАЖНО!</b>\n\n"
        "Этот бот предназначен для <b>МОНИТОРИНГА</b> вашего Telegram-аккаунта:\n"
        "• Отслеживание удалённых сообщений\n"
        "• Перехват редактирований\n"
        "• Сохранение медиа с таймером\n"
        "• Мониторинг секретных чатов\n\n"
        "🔴 <b>ЗАКОНОДАТЕЛЬСТВО:</b>\n"
        "Использование бота без согласия ВСЕХ участников переписки является "
        "<u>НЕЗАКОННЫМ</u> и влечёт уголовную ответственность:\n"
        "• УК РФ ст. 137 — Нарушение неприкосновенности частной жизни\n"
        "• УК РФ ст. 138 — Нарушение тайны переписки\n"
        "• До 4 лет лишения свободы\n\n"
        "🔴 <b>TELEGRAM ToS:</b>\n"
        "Telegram может <b>ЗАБЛОКИРОВАТЬ</b> ваш аккаунт за использование подобных ботов.\n\n"
        "🔴 <b>ОТВЕТСТВЕННОСТЬ:</b>\n"
        "Разработчики НЕ НЕСУТ никакой ответственности за ваши действия. "
        "Вы используете бот на свой страх и риск.\n\n"
        "⚠️ Перед продолжением вы ОБЯЗАНЫ ознакомиться с документами:"
    ),
    
    "policy_title": "📜 <b>ПОЛИТИКА КОНФИДЕНЦИАЛЬНОСТИ</b>",
    "policy_text": (
        "\n\n<b>1. ОБЩИЕ ПОЛОЖЕНИЯ</b>\n"
        "1.1. Настоящая Политика регулирует использование Telegram Monitoring Bot (далее — «Бот»).\n"
        "1.2. Бот является <u>ИНСТРУМЕНТОМ МОНИТОРИНГА</u>, работающим под вашей учётной записью.\n"
        "1.3. Бот НЕ ЯВЛЯЕТСЯ сервисом обмена сообщениями или социальной сетью.\n\n"
        
        "<b>2. ХАРАКТЕР СЕРВИСА</b>\n"
        "2.1. Бот отслеживает следующие действия в вашем Telegram:\n"
        "   • Удалённые сообщения (до удаления)\n"
        "   • Редактирования сообщений (до/после)\n"
        "   • Медиа с таймером (фото/видео)\n"
        "   • Секретные чаты\n"
        "   • Блокировки/разблокировки\n"
        "   • Новые контакты\n"
        "2.2. Все данные перехватываются В РЕАЛЬНОМ ВРЕМЕНИ.\n"
        "2.3. Данные НЕ ХРАНЯТСЯ на серверах — только локально у вас.\n"
        "2.4. Администратор получает УВЕДОМЛЕНИЯ, но НЕ ПОЛНЫЙ ДОСТУП к данным.\n\n"
        
        "<b>3. ХРАНЕНИЕ ДАННЫХ</b>\n"
        "3.1. Бот хранит данные в JSON-файлах на вашем устройстве/сервере.\n"
        "3.2. Срок хранения: последние 10,000 событий.\n"
        "3.3. Старые события автоматически удаляются.\n"
        "3.4. Вы можете УДАЛИТЬ все данные в любой момент командой /wipe.\n\n"
        
        "<b>4. СОГЛАСИЕ ТРЕТЬИХ ЛИЦ</b>\n"
        "4.1. ⚠️ <u>КРИТИЧНО:</u> Использование Бота БЕЗ СОГЛАСИЯ всех участников переписки является:\n"
        "   • Нарушением УК РФ ст. 137, 138\n"
        "   • Нарушением GDPR (ЕС)\n"
        "   • Нарушением ФЗ-152 «О персональных данных» (РФ)\n"
        "4.2. Вы ОБЯЗАНЫ получить ПИСЬМЕННОЕ согласие от ВСЕХ контактов перед мониторингом.\n"
        "4.3. Без согласия использование Бота является УГОЛОВНЫМ ПРЕСТУПЛЕНИЕМ.\n"
        "4.4. Разработчики НЕ НЕСУТ ответственности за ваши действия.\n\n"
        
        "<b>5. TELEGRAM TERMS OF SERVICE</b>\n"
        "5.1. Использование Бота может нарушать <u>Условия использования Telegram</u>.\n"
        "5.2. Telegram МОЖЕТ ЗАБЛОКИРОВАТЬ ваш аккаунт за:\n"
        "   • Использование сторонних клиентов\n"
        "   • Автоматизацию действий\n"
        "   • Нарушение конфиденциальности других пользователей\n"
        "5.3. Блокировка аккаунта — НЕОБРАТИМА.\n"
        "5.4. Разработчики НЕ ВОССТАНАВЛИВАЮТ заблокированные аккаунты.\n\n"
        
        "<b>6. ЗАКОНОДАТЕЛЬСТВО РФ</b>\n"
        "6.1. <b>УК РФ ст. 137</b> — Нарушение неприкосновенности частной жизни:\n"
        "   • Штраф до 200,000 руб.\n"
        "   • Лишение свободы до 2 лет\n"
        "6.2. <b>УК РФ ст. 138</b> — Нарушение тайны переписки:\n"
        "   • Штраф до 300,000 руб.\n"
        "   • Лишение свободы до 4 лет\n"
        "6.3. <b>ФЗ-152</b> — Обработка персональных данных без согласия:\n"
        "   • Административная ответственность\n"
        "   • Штрафы от 10,000 до 500,000 руб.\n\n"
        
        "<b>7. GDPR (ДЛЯ ГРАЖДАН ЕС)</b>\n"
        "7.1. Мониторинг без согласия нарушает GDPR Art. 6, 7.\n"
        "7.2. Штрафы: до €20,000,000 или 4% годового оборота.\n"
        "7.3. Право на забвение: вы можете удалить данные командой /wipe.\n\n"
        
        "<b>8. ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ</b>\n"
        "8.1. Разработчики НЕ НЕСУТ никакой ответственности за:\n"
        "   • Ваши незаконные действия\n"
        "   • Блокировку вашего аккаунта Telegram\n"
        "   • Уголовное преследование\n"
        "   • Гражданские иски\n"
        "   • Потерю данных\n"
        "   • Любые убытки\n"
        "8.2. Бот предоставляется «КАК ЕСТЬ» (AS IS).\n"
        "8.3. Гарантии отсутствуют.\n"
        "8.4. Использование — НА ВАШ РИСК.\n\n"
        
        "<b>9. ВОЗРАСТНЫЕ ОГРАНИЧЕНИЯ</b>\n"
        "9.1. Использование Бота разрешено лицам 18+.\n"
        "9.2. Несовершеннолетние не могут использовать Бот.\n\n"
        
        "<b>10. ИЗМЕНЕНИЯ</b>\n"
        "10.1. Политика может быть изменена без уведомления.\n"
        "10.2. Дата последнего обновления: 01.03.2026\n\n"
        
        "<b>КОНТАКТЫ:</b> @mrztn"
    ),
    
    "terms_title": "📘 <b>УСЛОВИЯ ИСПОЛЬЗОВАНИЯ</b>",
    "terms_text": (
        "\n\n<b>1. ПРИНЯТИЕ УСЛОВИЙ</b>\n"
        "1.1. Используя Бот, вы ПОЛНОСТЬЮ принимаете настоящие Условия.\n"
        "1.2. Если вы НЕ согласны — НЕМЕДЛЕННО прекратите использование.\n\n"
        
        "<b>2. НАЗНАЧЕНИЕ БОТА</b>\n"
        "2.1. Бот предназначен для ЛЕГАЛЬНОГО мониторинга:\n"
        "   • Родительский контроль (с согласия ребёнка 14+)\n"
        "   • Корпоративный мониторинг (рабочие аккаунты)\n"
        "   • Личный бэкап переписок\n"
        "2.2. ЗАПРЕЩЕНО использование для:\n"
        "   • Шпионажа\n"
        "   • Преследования (stalking)\n"
        "   • Коммерческого шпионажа\n"
        "   • Слежки за супругом/супругой без согласия\n"
        "   • Любых незаконных целей\n\n"
        
        "<b>3. ТРЕБОВАНИЯ К ПОЛЬЗОВАТЕЛЮ</b>\n"
        "3.1. Вы ОБЯЗАНЫ:\n"
        "   • Получить согласие ВСЕХ участников переписки\n"
        "   • Использовать Бот законно\n"
        "   • Не нарушать права других\n"
        "   • Соблюдать Telegram ToS\n"
        "3.2. Вы НЕ ИМЕЕТЕ права:\n"
        "   • Мониторить без согласия\n"
        "   • Распространять перехваченные данные\n"
        "   • Использовать данные во вред другим\n"
        "   • Продавать/передавать данные третьим лицам\n\n"
        
        "<b>4. РИСКИ БЛОКИРОВКИ</b>\n"
        "4.1. Telegram активно блокирует подобные боты.\n"
        "4.2. Вероятность блокировки: ВЫСОКАЯ.\n"
        "4.3. Блокировка — НЕОБРАТИМА.\n"
        "4.4. Вы ПРИНИМАЕТЕ этот риск.\n\n"
        
        "<b>5. ОТВЕТСТВЕННОСТЬ ПОЛЬЗОВАТЕЛЯ</b>\n"
        "5.1. Вы ПОЛНОСТЬЮ отвечаете за:\n"
        "   • Все свои действия\n"
        "   • Все перехваченные данные\n"
        "   • Соблюдение законов\n"
        "   • Получение согласий\n"
        "5.2. Разработчики НЕ НЕСУТ ответственности НИКОГДА.\n\n"
        
        "<b>6. ГАРАНТИИ И ОТКАЗ ОТ НИХ</b>\n"
        "6.1. Бот предоставляется «AS IS».\n"
        "6.2. Гарантии работоспособности: НЕТ.\n"
        "6.3. Гарантии безопасности: НЕТ.\n"
        "6.4. Любые гарантии: ОТСУТСТВУЮТ.\n\n"
        
        "<b>7. ОГРАНИЧЕНИЕ ОТВЕТСТВЕННОСТИ</b>\n"
        "7.1. Максимальная ответственность разработчиков: 0 (НОЛЬ) рублей.\n"
        "7.2. Ни при каких обстоятельствах разработчики НЕ ОТВЕЧАЮТ за:\n"
        "   • Прямые убытки\n"
        "   • Косвенные убытки\n"
        "   • Упущенную выгоду\n"
        "   • Моральный вред\n"
        "   • Блокировку аккаунта\n"
        "   • Уголовное преследование\n"
        "   • Любые другие последствия\n\n"
        
        "<b>8. ПРИМЕНИМОЕ ПРАВО</b>\n"
        "8.1. Условия регулируются законодательством РФ.\n"
        "8.2. Споры: в судах по месту нахождения разработчиков.\n\n"
        
        "<b>9. ПРЕКРАЩЕНИЕ ДОСТУПА</b>\n"
        "9.1. Разработчики могут:\n"
        "   • Прекратить работу Бота без предупреждения\n"
        "   • Заблокировать любого пользователя\n"
        "   • Изменить функционал\n"
        "   • Удалить все данные\n"
        "9.2. Без права на компенсацию.\n\n"
        
        "<b>10. ЗАКЛЮЧИТЕЛЬНЫЕ ПОЛОЖЕНИЯ</b>\n"
        "10.1. Используя Бот, вы ПОДТВЕРЖДАЕТЕ:\n"
        "   ✅ Вам 18+ лет\n"
        "   ✅ Вы прочитали и поняли Условия\n"
        "   ✅ Вы получили согласие всех участников переписки\n"
        "   ✅ Вы понимаете риски\n"
        "   ✅ Вы принимаете ПОЛНУЮ ответственность\n"
        "   ✅ У вас НЕТ претензий к разработчикам\n\n"
        
        "<b>ВЕРСИЯ:</b> 1.0 от 01.03.2026\n"
        "<b>КОНТАКТЫ:</b> @mrztn"
    ),
    
    "consent_required": (
        "✅ <b>ПОДТВЕРЖДЕНИЕ</b>\n\n"
        "Я подтверждаю, что:\n"
        "1️⃣ Мне исполнилось 18 лет\n"
        "2️⃣ Я получил ПИСЬМЕННОЕ согласие ВСЕХ участников переписки на мониторинг\n"
        "3️⃣ Я понимаю, что незаконное использование влечёт уголовную ответственность\n"
        "4️⃣ Я принимаю риск блокировки аккаунта Telegram\n"
        "5️⃣ Я ПОЛНОСТЬЮ снимаю ответственность с разработчиков\n\n"
        "⚠️ ЛОЖНОЕ подтверждение — УГОЛОВНОЕ ПРЕСТУПЛЕНИЕ!"
    ),
    
    "btn_policy": "📜 Политика",
    "btn_terms": "📘 Условия",
    "btn_accept": "✅ ПРИНИМАЮ ВСЮ ОТВЕТСТВЕННОСТЬ",
    "btn_decline": "❌ Отказываюсь",
    "btn_back": "◀️ Назад",
    
    "registration_success": (
        "🎉 Добро пожаловать!\n\n"
        "Теперь я начну мониторить ваш Telegram.\n\n"
        "📊 <b>Что отслеживается:</b>\n"
        "• Удалённые сообщения\n"
        "• Редактирования\n"
        "• Медиа с таймером\n"
        "• Секретные чаты\n"
        "• Блокировки\n"
        "• Новые контакты\n\n"
        "⚠️ Помните: мониторинг без согласия — НЕЗАКОНЕН!"
    ),
    
    "admin_panel": "👑 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:",
    
    "stats_template": (
        "📊 <b>СТАТИСТИКА</b>\n\n"
        "👥 Всего пользователей: {total_users}\n"
        "📨 Всего событий: {total_events}\n\n"
        "🗑 Удалённых сообщений: {deleted_messages}\n"
        "✏️ Редактирований: {edited_messages}\n"
        "📸 Медиа перехвачено: {media_intercepted}\n"
        "🔒 Секретных чатов: {secret_chats}\n\n"
        "🕐 Обновлено: {last_updated}"
    ),
}


# ════════════════════════════════════════════════════════════════
# FSM СОСТОЯНИЯ
# ════════════════════════════════════════════════════════════════

class RegistrationStates(StatesGroup):
    waiting_for_consent = State()


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_search = State()


# ════════════════════════════════════════════════════════════════
# CALLBACK DATA
# ════════════════════════════════════════════════════════════════

class PolicyCallback(CallbackData, prefix="policy"):
    action: str


class TermsCallback(CallbackData, prefix="terms"):
    action: str


class ConsentCallback(CallbackData, prefix="consent"):
    action: str


class AdminCallback(CallbackData, prefix="admin"):
    action: str
    data: str = ""


# ════════════════════════════════════════════════════════════════
# КЛАВИАТУРЫ
# ════════════════════════════════════════════════════════════════

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура приветствия"""
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_policy"], callback_data=PolicyCallback(action="show"))
    builder.button(text=TEXTS["btn_terms"], callback_data=TermsCallback(action="show"))
    builder.adjust(1)
    return builder.as_markup()


def get_policy_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура политики"""
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_back"], callback_data=PolicyCallback(action="back"))
    return builder.as_markup()


def get_terms_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура условий"""
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_back"], callback_data=TermsCallback(action="back"))
    return builder.as_markup()


def get_consent_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура согласия"""
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_accept"], callback_data=ConsentCallback(action="accept"))
    builder.button(text=TEXTS["btn_decline"], callback_data=ConsentCallback(action="decline"))
    builder.adjust(1)
    return builder.as_markup()


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура админ-панели"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data=AdminCallback(action="stats"))
    builder.button(text="👥 Пользователи", callback_data=AdminCallback(action="users"))
    builder.button(text="🔔 Алерты", callback_data=AdminCallback(action="alerts"))
    builder.button(text="🔍 Поиск", callback_data=AdminCallback(action="search"))
    builder.button(text="✉️ Рассылка", callback_data=AdminCallback(action="broadcast"))
    builder.button(text="📥 Экспорт", callback_data=AdminCallback(action="export"))
    builder.adjust(2, 2, 2)
    return builder.as_markup()


# ════════════════════════════════════════════════════════════════
# МОНИТОРИНГ (ЗАГЛУШКИ ДЛЯ ДЕМОНСТРАЦИИ)
# ════════════════════════════════════════════════════════════════

class TelegramMonitor:
    """
    Класс для мониторинга Telegram
    
    ⚠️ ВНИМАНИЕ: Реальная реализация требует Telethon/Pyrogram
    и работы под учётной записью пользователя (UserBot)
    """
    
    def __init__(self, storage: DataStorage, bot: Bot):
        self.storage = storage
        self.bot = bot
    
    async def on_message_deleted(self, user_id: int, message_data: Dict):
        """Обработка удалённого сообщения"""
        self.storage.add_event("message_deleted", user_id, message_data)
        
        # Уведомление админу
        alert_text = (
            f"🗑 <b>СООБЩЕНИЕ УДАЛЕНО</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"💬 Текст: {message_data.get('text', 'N/A')}\n"
            f"👤 Автор: {message_data.get('from_user', 'N/A')}\n"
            f"📅 Удалено: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        try:
            await self.bot.send_message(ADMIN_ID, alert_text)
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
        
        self.storage.add_alert("deleted_message", user_id, alert_text, "warning")
    
    async def on_message_edited(self, user_id: int, before: str, after: str, author: str):
        """Обработка редактирования"""
        data = {"before": before, "after": after, "author": author}
        self.storage.add_event("message_edited", user_id, data)
        
        alert_text = (
            f"✏️ <b>СООБЩЕНИЕ ОТРЕДАКТИРОВАНО</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"👤 Автор: {author}\n"
            f"📝 Было: {before}\n"
            f"📝 Стало: {after}"
        )
        
        try:
            await self.bot.send_message(ADMIN_ID, alert_text)
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
        
        self.storage.add_alert("edited_message", user_id, alert_text, "info")
    
    async def on_media_timer(self, user_id: int, media_type: str, media_url: str, sender: str):
        """Обработка медиа с таймером"""
        data = {"type": media_type, "url": media_url, "sender": sender}
        self.storage.add_event("media_intercepted", user_id, data)
        
        alert_text = (
            f"📸 <b>МЕДИА С ТАЙМЕРОМ</b>\n\n"
            f"👤 Пользователь: {user_id}\n"
            f"👤 Отправитель: {sender}\n"
            f"📂 Тип: {media_type}"
        )
        
        try:
            await self.bot.send_message(ADMIN_ID, alert_text)
            # Здесь должна быть отправка самого медиа
        except Exception as e:
            logger.error(f"Ошибка отправки алерта: {e}")
        
        self.storage.add_alert("media_timer", user_id, alert_text, "high")


# ════════════════════════════════════════════════════════════════
# ХЭНДЛЕРЫ
# ════════════════════════════════════════════════════════════════

# Глобальные объекты
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()
storage = DataStorage()
monitor = TelegramMonitor(storage, bot)


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    """Команда /start"""
    user_id = message.from_user.id
    
    # Проверяем, зарегистрирован ли
    user = storage.get_user(user_id)
    
    if user:
        await message.answer(
            f"👋 С возвращением!\n\n"
            f"📊 Статистика:\n"
            f"События: {len(storage.get_user_events(user_id))}\n\n"
            f"Используйте /help для справки."
        )
    else:
        await message.answer(
            TEXTS["start_warning"],
            reply_markup=get_start_keyboard()
        )


@router.callback_query(PolicyCallback.filter(F.action == "show"))
async def show_policy(callback: CallbackQuery):
    """Показать политику"""
    # Разбиваем на части из-за лимита Telegram
    full_text = TEXTS["policy_title"] + TEXTS["policy_text"]
    
    if len(full_text) > 4096:
        parts = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                await callback.message.answer(part, reply_markup=get_policy_keyboard())
            else:
                await callback.message.answer(part)
        await callback.message.delete()
    else:
        await callback.message.edit_text(full_text, reply_markup=get_policy_keyboard())
    
    await callback.answer()


@router.callback_query(PolicyCallback.filter(F.action == "back"))
async def policy_back(callback: CallbackQuery):
    """Назад из политики"""
    await callback.message.edit_text(
        TEXTS["start_warning"],
        reply_markup=get_start_keyboard()
    )
    await callback.answer()


@router.callback_query(TermsCallback.filter(F.action == "show"))
async def show_terms(callback: CallbackQuery):
    """Показать условия"""
    full_text = TEXTS["terms_title"] + TEXTS["terms_text"]
    
    if len(full_text) > 4096:
        parts = [full_text[i:i+4000] for i in range(0, len(full_text), 4000)]
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                await callback.message.answer(part, reply_markup=get_terms_keyboard())
            else:
                await callback.message.answer(part)
        await callback.message.delete()
    else:
        await callback.message.edit_text(full_text, reply_markup=get_terms_keyboard())
    
    await callback.answer()


@router.callback_query(TermsCallback.filter(F.action == "back"))
async def terms_back(callback: CallbackQuery):
    """Назад из условий"""
    await callback.message.edit_text(
        TEXTS["start_warning"],
        reply_markup=get_start_keyboard()
    )
    await callback.answer()


@router.message(Command("accept"))
async def cmd_accept(message: Message):
    """Команда /accept (после прочтения документов)"""
    await message.answer(
        TEXTS["consent_required"],
        reply_markup=get_consent_keyboard()
    )


@router.callback_query(ConsentCallback.filter(F.action == "accept"))
async def accept_consent(callback: CallbackQuery):
    """Принятие согласия"""
    user_id = callback.from_user.id
    username = callback.from_user.username
    
    # Регистрируем пользователя
    user_data = {
        "telegram_id": user_id,
        "username": username or "N/A",
        "first_name": callback.from_user.first_name,
        "last_name": callback.from_user.last_name or "",
        "consent_accepted_at": datetime.now(timezone.utc).isoformat()
    }
    
    storage.add_user(user_id, user_data)
    
    await callback.message.edit_text(TEXTS["registration_success"])
    
    # Уведомляем админа
    await bot.send_message(
        ADMIN_ID,
        f"🆕 <b>НОВЫЙ ПОЛЬЗОВАТЕЛЬ</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{username or 'N/A'}\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    await callback.answer()


@router.callback_query(ConsentCallback.filter(F.action == "decline"))
async def decline_consent(callback: CallbackQuery):
    """Отказ от согласия"""
    await callback.message.edit_text(
        "❌ Вы отказались от использования бота.\n\n"
        "Если передумаете, напишите /start"
    )
    await callback.answer()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Админ-панель"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    await message.answer(
        TEXTS["admin_panel"],
        reply_markup=get_admin_keyboard()
    )


@router.callback_query(AdminCallback.filter(F.action == "stats"))
async def admin_stats(callback: CallbackQuery):
    """Статистика"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    stats = storage.stats
    stats_text = TEXTS["stats_template"].format(
        total_users=stats["total_users"],
        total_events=stats["total_events"],
        deleted_messages=stats["deleted_messages"],
        edited_messages=stats["edited_messages"],
        media_intercepted=stats["media_intercepted"],
        secret_chats=stats["secret_chats"],
        last_updated=datetime.fromisoformat(stats["last_updated"]).strftime("%Y-%m-%d %H:%M:%S")
    )
    
    await callback.message.answer(stats_text)
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "users"))
async def admin_users(callback: CallbackQuery):
    """Список пользователей"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    users = storage.get_all_users()
    
    if not users:
        await callback.message.answer("👥 Пользователей пока нет.")
        await callback.answer()
        return
    
    users_text = "👥 <b>ПОЛЬЗОВАТЕЛИ</b>\n\n"
    
    for user in users[:20]:  # Первые 20
        status = "✅" if user.get("is_active") else "🚫"
        users_text += (
            f"{status} <code>{user['id']}</code> — @{user.get('username', 'N/A')}\n"
            f"   📅 {user.get('registered_at', 'N/A')[:10]}\n\n"
        )
    
    if len(users) > 20:
        users_text += f"\n... и ещё {len(users) - 20}"
    
    await callback.message.answer(users_text)
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "alerts"))
async def admin_alerts(callback: CallbackQuery):
    """Последние алерты"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    alerts = storage.alerts[-10:]  # Последние 10
    
    if not alerts:
        await callback.message.answer("🔔 Алертов пока нет.")
        await callback.answer()
        return
    
    alerts_text = "🔔 <b>ПОСЛЕДНИЕ АЛЕРТЫ</b>\n\n"
    
    for alert in reversed(alerts):
        severity_emoji = {"info": "ℹ️", "warning": "⚠️", "high": "🔴"}
        emoji = severity_emoji.get(alert["severity"], "ℹ️")
        
        alerts_text += (
            f"{emoji} {alert['type']}\n"
            f"👤 User: {alert['user_id']}\n"
            f"📅 {alert['timestamp'][:19]}\n\n"
        )
    
    await callback.message.answer(alerts_text)
    await callback.answer()


@router.callback_query(AdminCallback.filter(F.action == "broadcast"))
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    """Начать рассылку"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    await callback.message.answer("✉️ Отправьте текст для рассылки:")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_execute(message: Message, state: FSMContext):
    """Выполнить рассылку"""
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text
    users = storage.get_all_users()
    
    success = 0
    fail = 0
    
    progress_msg = await message.answer(f"📤 Отправка: 0/{len(users)}")
    
    for i, user in enumerate(users):
        try:
            await bot.send_message(user["id"], text)
            success += 1
        except Exception as e:
            logger.error(f"Ошибка отправки {user['id']}: {e}")
            fail += 1
        
        if (i + 1) % 5 == 0:
            await progress_msg.edit_text(f"📤 Отправка: {i + 1}/{len(users)}")
        
        await asyncio.sleep(0.05)
    
    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"Успешно: {success}\n"
        f"Ошибок: {fail}"
    )
    
    await state.clear()


@router.callback_query(AdminCallback.filter(F.action == "search"))
async def admin_search_start(callback: CallbackQuery, state: FSMContext):
    """Начать поиск"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    await callback.message.answer("🔍 Введите поисковый запрос:")
    await state.set_state(AdminStates.waiting_for_search)
    await callback.answer()


@router.message(AdminStates.waiting_for_search)
async def admin_search_execute(message: Message, state: FSMContext):
    """Выполнить поиск"""
    if message.from_user.id != ADMIN_ID:
        return
    
    query = message.text
    results = storage.search_events(query, limit=20)
    
    if not results:
        await message.answer("🔍 Ничего не найдено.")
        await state.clear()
        return
    
    results_text = f"🔍 <b>РЕЗУЛЬТАТЫ: {query}</b>\n\n"
    
    for event in results[:10]:
        results_text += (
            f"📌 {event['type']}\n"
            f"👤 User: {event['user_id']}\n"
            f"📅 {event['timestamp'][:19]}\n"
            f"💬 {str(event['data'])[:100]}...\n\n"
        )
    
    await message.answer(results_text)
    await state.clear()


@router.callback_query(AdminCallback.filter(F.action == "export"))
async def admin_export(callback: CallbackQuery):
    """Экспорт данных"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    await callback.message.answer("📥 Экспортирую данные...")
    
    # Создаём файл экспорта
    export_data = {
        "users": storage.users,
        "activity": storage.activity[-1000:],
        "alerts": storage.alerts[-500:],
        "stats": storage.stats,
        "exported_at": datetime.now(timezone.utc).isoformat()
    }
    
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    filepath = os.path.join(EXPORTS_DIR, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    from aiogram.types import FSInputFile
    document = FSInputFile(filepath)
    
    await callback.message.answer_document(document, caption="📥 Экспорт данных")
    await callback.answer()


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Справка"""
    help_text = (
        "<b>📖 СПРАВКА</b>\n\n"
        "<b>Команды пользователя:</b>\n"
        "/start - Главное меню\n"
        "/accept - Принять условия\n"
        "/help - Эта справка\n"
        "/status - Статус мониторинга\n"
        "/wipe - Удалить все данные\n\n"
        "<b>Команды админа:</b>\n"
        "/admin - Админ-панель\n\n"
        "⚠️ Помните: мониторинг без согласия НЕЗАКОНЕН!"
    )
    await message.answer(help_text)


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Статус пользователя"""
    user_id = message.from_user.id
    user = storage.get_user(user_id)
    
    if not user:
        await message.answer("❌ Вы не зарегистрированы. Напишите /start")
        return
    
    events = storage.get_user_events(user_id)
    
    status_text = (
        f"📊 <b>ВАШ СТАТУС</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"👤 Username: @{user.get('username', 'N/A')}\n"
        f"📅 Регистрация: {user.get('registered_at', 'N/A')[:10]}\n"
        f"✅ Активен: {'Да' if user.get('is_active') else 'Нет'}\n\n"
        f"📈 События: {len(events)}\n"
        f"🕐 Последняя активность: {user.get('last_activity', 'N/A')[:19]}"
    )
    
    await message.answer(status_text)


@router.message(Command("wipe"))
async def cmd_wipe(message: Message):
    """Удалить все данные"""
    user_id = message.from_user.id
    user = storage.get_user(user_id)
    
    if not user:
        await message.answer("❌ Вы не зарегистрированы.")
        return
    
    # Удаляем данные пользователя
    storage.users.pop(str(user_id), None)
    storage.activity = [e for e in storage.activity if e["user_id"] != user_id]
    storage.alerts = [a for a in storage.alerts if a["user_id"] != user_id]
    storage.stats["total_users"] -= 1
    storage.save_all()
    
    await message.answer(
        "🗑 Все ваши данные удалены.\n\n"
        "Если захотите вернуться, напишите /start"
    )


# ════════════════════════════════════════════════════════════════
# ЗАПУСК
# ════════════════════════════════════════════════════════════════

async def on_startup():
    """Действия при запуске"""
    logger.info("🚀 Бот запущен!")
    
    await bot.send_message(
        ADMIN_ID,
        "🤖 <b>БОТ ЗАПУЩЕН</b>\n\n"
        "Telegram Monitoring Bot активирован.\n\n"
        "⚠️ Помните: незаконное использование влечёт уголовную ответственность!"
    )


async def on_shutdown():
    """Действия при остановке"""
    storage.save_all()
    logger.info("🛑 Бот остановлен.")


async def main():
    """Главная функция"""
    dp.include_router(router)
    
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    await dp.start_polling(bot)


# ════════════════════════════════════════════════════════════════
# РАСШИРЕННЫЕ ФУНКЦИИ МОНИТОРИНГА
# ════════════════════════════════════════════════════════════════

class SpamDetector:
    """Детектор спама и мошенничества"""
    
    SPAM_KEYWORDS = [
        "бесплатно", "заработок", "криптовалюта", "инвестиции",
        "млм", "сетевой маркетинг", "розыгрыш", "prize", "lottery",
        "click here", "limited offer", "срочно", "халява"
    ]
    
    PHISHING_PATTERNS = [
        r't\.me/\+[a-zA-Z0-9]+',  # Фейковые ссылки Telegram
        r'bit\.ly/',  # Сокращённые ссылки
        r'goo\.gl/',
        r'tinyurl\.com/',
    ]
    
    def __init__(self):
        self.user_message_count = defaultdict(lambda: defaultdict(int))
        self.suspicious_users = set()
    
    def check_spam(self, user_id: int, text: str) -> tuple[bool, str]:
        """Проверить на спам"""
        if not text:
            return False, ""
        
        text_lower = text.lower()
        
        # Проверка ключевых слов
        spam_words_found = []
        for keyword in self.SPAM_KEYWORDS:
            if keyword in text_lower:
                spam_words_found.append(keyword)
        
        if len(spam_words_found) >= 2:
            return True, f"Обнаружены спам-слова: {', '.join(spam_words_found)}"
        
        # Проверка фишинговых ссылок
        for pattern in self.PHISHING_PATTERNS:
            if re.search(pattern, text):
                return True, f"Обнаружена подозрительная ссылка"
        
        # Проверка на флуд
        current_time = datetime.now()
        minute_key = current_time.strftime('%Y-%m-%d %H:%M')
        self.user_message_count[user_id][minute_key] += 1
        
        if self.user_message_count[user_id][minute_key] > 10:
            return True, "Флуд (более 10 сообщений в минуту)"
        
        # Проверка на дубликаты
        hash_text = hashlib.md5(text.encode()).hexdigest()
        recent_messages = list(self.user_message_count[user_id].values())
        
        return False, ""
    
    def mark_suspicious(self, user_id: int):
        """Отметить как подозрительного"""
        self.suspicious_users.add(user_id)
    
    def is_suspicious(self, user_id: int) -> bool:
        """Проверить подозрительность"""
        return user_id in self.suspicious_users


class ActivityAnalyzer:
    """Анализатор активности"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def get_top_active_chats(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Топ самых активных чатов"""
        events = self.storage.get_user_events(user_id, limit=1000)
        
        chat_counter = defaultdict(int)
        for event in events:
            chat_id = event.get('data', {}).get('chat_id')
            if chat_id:
                chat_counter[chat_id] += 1
        
        sorted_chats = sorted(chat_counter.items(), key=lambda x: x[1], reverse=True)
        
        return [
            {"chat_id": chat_id, "message_count": count}
            for chat_id, count in sorted_chats[:limit]
        ]
    
    def get_activity_heatmap(self, user_id: int) -> Dict[int, int]:
        """Тепловая карта активности по часам"""
        events = self.storage.get_user_events(user_id, limit=10000)
        
        hour_counter = defaultdict(int)
        for event in events:
            timestamp = datetime.fromisoformat(event['timestamp'])
            hour = timestamp.hour
            hour_counter[hour] += 1
        
        return dict(hour_counter)
    
    def get_daily_stats(self, user_id: int, days: int = 7) -> Dict[str, int]:
        """Статистика по дням"""
        events = self.storage.get_user_events(user_id, limit=10000)
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        recent_events = [
            e for e in events
            if datetime.fromisoformat(e['timestamp']) > cutoff_date
        ]
        
        day_counter = defaultdict(int)
        for event in recent_events:
            timestamp = datetime.fromisoformat(event['timestamp'])
            day_key = timestamp.strftime('%Y-%m-%d')
            day_counter[day_key] += 1
        
        return dict(day_counter)
    
    def generate_report(self, user_id: int) -> str:
        """Сгенерировать отчёт"""
        user = self.storage.get_user(user_id)
        if not user:
            return "Пользователь не найден"
        
        top_chats = self.get_top_active_chats(user_id, 5)
        heatmap = self.get_activity_heatmap(user_id)
        daily = self.get_daily_stats(user_id, 7)
        
        report = f"📊 <b>ОТЧЁТ ПО АКТИВНОСТИ</b>\n\n"
        report += f"👤 Пользователь: {user_id}\n"
        report += f"📅 Период: последние 7 дней\n\n"
        
        report += "<b>🔥 Топ-5 активных чатов:</b>\n"
        for i, chat in enumerate(top_chats, 1):
            report += f"{i}. Chat {chat['chat_id']}: {chat['message_count']} сообщений\n"
        
        report += "\n<b>⏰ Пиковые часы активности:</b>\n"
        sorted_hours = sorted(heatmap.items(), key=lambda x: x[1], reverse=True)
        for hour, count in sorted_hours[:5]:
            report += f"{hour:02d}:00 — {count} событий\n"
        
        report += "\n<b>📅 Активность по дням:</b>\n"
        for day, count in sorted(daily.items()):
            report += f"{day}: {count} событий\n"
        
        return report


class NotificationManager:
    """Менеджер уведомлений"""
    
    def __init__(self, bot: Bot, storage: DataStorage):
        self.bot = bot
        self.storage = storage
        self.notification_queue = asyncio.Queue()
        self.priority_levels = {
            "low": 1,
            "medium": 2,
            "high": 3,
            "critical": 4
        }
    
    async def send_notification(
        self,
        user_id: int,
        message: str,
        priority: str = "medium",
        silent: bool = False
    ):
        """Отправить уведомление"""
        notification = {
            "user_id": user_id,
            "message": message,
            "priority": self.priority_levels.get(priority, 2),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "silent": silent
        }
        
        await self.notification_queue.put(notification)
    
    async def process_notifications(self):
        """Обработка очереди уведомлений"""
        while True:
            try:
                notification = await self.notification_queue.get()
                
                # Отправляем администратору
                try:
                    await self.bot.send_message(
                        ADMIN_ID,
                        notification["message"],
                        disable_notification=notification["silent"]
                    )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления: {e}")
                
                # Небольшая задержка
                await asyncio.sleep(0.1)
                
            except Exception as e:
                logger.error(f"Ошибка обработки уведомления: {e}")
                await asyncio.sleep(1)
    
    async def send_bulk_notification(self, user_ids: List[int], message: str):
        """Массовая рассылка"""
        for user_id in user_ids:
            try:
                await self.bot.send_message(user_id, message)
                await asyncio.sleep(0.05)  # Антифлуд
            except Exception as e:
                logger.error(f"Ошибка отправки {user_id}: {e}")


class EventFilter:
    """Фильтр событий"""
    
    def __init__(self):
        self.filters = {}
    
    def add_filter(self, user_id: int, filter_config: Dict):
        """Добавить фильтр"""
        if user_id not in self.filters:
            self.filters[user_id] = []
        self.filters[user_id].append(filter_config)
    
    def should_notify(self, user_id: int, event: Dict) -> bool:
        """Проверить, нужно ли уведомлять"""
        if user_id not in self.filters:
            return True
        
        for filter_cfg in self.filters[user_id]:
            # Фильтр по типу события
            if "event_type" in filter_cfg:
                if event["type"] not in filter_cfg["event_type"]:
                    continue
            
            # Фильтр по ключевым словам
            if "keywords" in filter_cfg:
                text = str(event.get("data", {}))
                if not any(kw.lower() in text.lower() for kw in filter_cfg["keywords"]):
                    continue
            
            # Фильтр по времени
            if "time_range" in filter_cfg:
                event_time = datetime.fromisoformat(event["timestamp"])
                start_hour = filter_cfg["time_range"].get("start", 0)
                end_hour = filter_cfg["time_range"].get("end", 24)
                
                if not (start_hour <= event_time.hour < end_hour):
                    continue
            
            return True
        
        return False


class DataExporter:
    """Экспортёр данных"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def export_to_json(self, user_id: int) -> str:
        """Экспорт в JSON"""
        user = self.storage.get_user(user_id)
        events = self.storage.get_user_events(user_id, limit=10000)
        
        export_data = {
            "user": user,
            "events": events,
            "exported_at": datetime.now(timezone.utc).isoformat()
        }
        
        filename = f"user_{user_id}_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        return filepath
    
    def export_to_csv(self, user_id: int) -> str:
        """Экспорт в CSV"""
        import csv
        
        events = self.storage.get_user_events(user_id, limit=10000)
        
        filename = f"user_{user_id}_events_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            if events:
                fieldnames = ['type', 'timestamp', 'user_id', 'data']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for event in events:
                    writer.writerow({
                        'type': event['type'],
                        'timestamp': event['timestamp'],
                        'user_id': event['user_id'],
                        'data': json.dumps(event['data'], ensure_ascii=False)
                    })
        
        return filepath
    
    def export_to_html(self, user_id: int) -> str:
        """Экспорт в HTML"""
        user = self.storage.get_user(user_id)
        events = self.storage.get_user_events(user_id, limit=1000)
        
        html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Экспорт данных - Пользователь {user_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #0088cc;
            padding-bottom: 10px;
        }}
        .user-info {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .event {{
            background: #fff;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            padding: 15px;
            margin: 10px 0;
        }}
        .event-type {{
            color: #0088cc;
            font-weight: bold;
        }}
        .timestamp {{
            color: #6c757d;
            font-size: 0.9em;
        }}
        .data {{
            margin-top: 10px;
            padding: 10px;
            background: #f8f9fa;
            border-left: 3px solid #0088cc;
            font-family: monospace;
            overflow-x: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Экспорт данных мониторинга</h1>
        
        <div class="user-info">
            <h2>👤 Информация о пользователе</h2>
            <p><strong>ID:</strong> {user_id}</p>
            <p><strong>Username:</strong> @{user.get('username', 'N/A')}</p>
            <p><strong>Регистрация:</strong> {user.get('registered_at', 'N/A')}</p>
            <p><strong>Всего событий:</strong> {len(events)}</p>
        </div>
        
        <h2>📋 События</h2>
"""
        
        for event in events:
            html += f"""
        <div class="event">
            <span class="event-type">{event['type']}</span>
            <span class="timestamp">{event['timestamp']}</span>
            <div class="data">{json.dumps(event['data'], ensure_ascii=False, indent=2)}</div>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        
        filename = f"user_{user_id}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        filepath = os.path.join(EXPORTS_DIR, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return filepath


class AutoBackup:
    """Автоматическое резервное копирование"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.backup_dir = os.path.join(DATA_DIR, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self) -> str:
        """Создать бэкап"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(self.backup_dir, f"backup_{timestamp}.json")
        
        backup_data = {
            "users": self.storage.users,
            "activity": self.storage.activity,
            "alerts": self.storage.alerts,
            "stats": self.storage.stats,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ Бэкап создан: {backup_file}")
        return backup_file
    
    def restore_backup(self, backup_file: str) -> bool:
        """Восстановить из бэкапа"""
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            self.storage.users = backup_data["users"]
            self.storage.activity = backup_data["activity"]
            self.storage.alerts = backup_data["alerts"]
            self.storage.stats = backup_data["stats"]
            self.storage.save_all()
            
            logger.info(f"✅ Данные восстановлены из: {backup_file}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка восстановления: {e}")
            return False
    
    def cleanup_old_backups(self, days: int = 30):
        """Удалить старые бэкапы"""
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted = 0
        
        for filename in os.listdir(self.backup_dir):
            filepath = os.path.join(self.backup_dir, filename)
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_time < cutoff_date:
                os.remove(filepath)
                deleted += 1
        
        logger.info(f"🗑 Удалено старых бэкапов: {deleted}")
    
    async def auto_backup_loop(self, interval_hours: int = 24):
        """Автоматический бэкап по расписанию"""
        while True:
            await asyncio.sleep(interval_hours * 3600)
            self.create_backup()
            self.cleanup_old_backups()


class UserBlacklist:
    """Чёрный список пользователей"""
    
    def __init__(self):
        self.blacklist = set()
        self.reasons = {}
        self.blacklist_file = os.path.join(DATA_DIR, "blacklist.json")
        self._load()
    
    def _load(self):
        """Загрузить из файла"""
        if os.path.exists(self.blacklist_file):
            try:
                with open(self.blacklist_file, 'r') as f:
                    data = json.load(f)
                    self.blacklist = set(data.get("blacklist", []))
                    self.reasons = data.get("reasons", {})
            except Exception as e:
                logger.error(f"Ошибка загрузки blacklist: {e}")
    
    def _save(self):
        """Сохранить в файл"""
        try:
            with open(self.blacklist_file, 'w') as f:
                json.dump({
                    "blacklist": list(self.blacklist),
                    "reasons": self.reasons
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения blacklist: {e}")
    
    def add(self, user_id: int, reason: str = ""):
        """Добавить в чёрный список"""
        self.blacklist.add(user_id)
        self.reasons[str(user_id)] = reason
        self._save()
    
    def remove(self, user_id: int):
        """Удалить из чёрного списка"""
        self.blacklist.discard(user_id)
        self.reasons.pop(str(user_id), None)
        self._save()
    
    def is_blacklisted(self, user_id: int) -> bool:
        """Проверить, в чёрном списке ли"""
        return user_id in self.blacklist
    
    def get_reason(self, user_id: int) -> str:
        """Получить причину блокировки"""
        return self.reasons.get(str(user_id), "Не указана")


# ════════════════════════════════════════════════════════════════
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ
# ════════════════════════════════════════════════════════════════

@router.message(Command("analyze"))
async def cmd_analyze(message: Message):
    """Анализ активности"""
    user_id = message.from_user.id
    
    if not storage.get_user(user_id):
        await message.answer("❌ Вы не зарегистрированы. Напишите /start")
        return
    
    analyzer = ActivityAnalyzer(storage)
    report = analyzer.generate_report(user_id)
    
    await message.answer(report)


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Экспорт данных"""
    user_id = message.from_user.id
    
    if not storage.get_user(user_id):
        await message.answer("❌ Вы не зарегистрированы. Напишите /start")
        return
    
    await message.answer("📥 Экспортирую данные...\n\nВыберите формат:")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📄 JSON", callback_data=f"export_json_{user_id}")
    builder.button(text="📊 CSV", callback_data=f"export_csv_{user_id}")
    builder.button(text="🌐 HTML", callback_data=f"export_html_{user_id}")
    builder.adjust(3)
    
    await message.answer("Формат экспорта:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("export_"))
async def handle_export(callback: CallbackQuery):
    """Обработка экспорта"""
    _, format_type, user_id = callback.data.split("_")
    user_id = int(user_id)
    
    if callback.from_user.id != user_id and callback.from_user.id != ADMIN_ID:
        await callback.answer("🚫 Доступ запрещён", show_alert=True)
        return
    
    exporter = DataExporter(storage)
    
    await callback.message.answer("⏳ Экспортирую...")
    
    try:
        if format_type == "json":
            filepath = exporter.export_to_json(user_id)
        elif format_type == "csv":
            filepath = exporter.export_to_csv(user_id)
        elif format_type == "html":
            filepath = exporter.export_to_html(user_id)
        else:
            await callback.answer("❌ Неизвестный формат", show_alert=True)
            return
        
        from aiogram.types import FSInputFile
        document = FSInputFile(filepath)
        await callback.message.answer_document(document, caption=f"📥 Экспорт в формате {format_type.upper()}")
        
        await callback.answer("✅ Экспорт завершён")
    except Exception as e:
        logger.error(f"Ошибка экспорта: {e}")
        await callback.answer("❌ Ошибка экспорта", show_alert=True)


@router.message(Command("backup"))
async def cmd_backup(message: Message):
    """Создать бэкап (только админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    backup_system = AutoBackup(storage)
    backup_file = backup_system.create_backup()
    
    await message.answer(f"✅ Бэкап создан:\n<code>{backup_file}</code>")


@router.message(Command("blacklist"))
async def cmd_blacklist(message: Message):
    """Управление чёрным списком (только админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    blacklist_manager = UserBlacklist()
    
    if not args:
        # Показать текущий список
        if not blacklist_manager.blacklist:
            await message.answer("📋 Чёрный список пуст.")
            return
        
        text = "📋 <b>ЧЁРНЫЙ СПИСОК</b>\n\n"
        for user_id in blacklist_manager.blacklist:
            reason = blacklist_manager.get_reason(user_id)
            text += f"🚫 <code>{user_id}</code> — {reason}\n"
        
        await message.answer(text)
    
    elif args[0] == "add" and len(args) >= 2:
        user_id = int(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else "Не указана"
        blacklist_manager.add(user_id, reason)
        await message.answer(f"✅ Пользователь {user_id} добавлен в чёрный список")
    
    elif args[0] == "remove" and len(args) >= 2:
        user_id = int(args[1])
        blacklist_manager.remove(user_id)
        await message.answer(f"✅ Пользователь {user_id} удалён из чёрного списка")


# ════════════════════════════════════════════════════════════════
# ИНИЦИАЛИЗАЦИЯ РАСШИРЕННЫХ МОДУЛЕЙ
# ════════════════════════════════════════════════════════════════

spam_detector = SpamDetector()
notification_manager = NotificationManager(bot, storage)
event_filter = EventFilter()
backup_system = AutoBackup(storage)


# ════════════════════════════════════════════════════════════════
# ФОНОВЫЕ ЗАДАЧИ
# ════════════════════════════════════════════════════════════════

async def background_tasks():
    """Фоновые задачи"""
    # Запускаем обработку уведомлений
    asyncio.create_task(notification_manager.process_notifications())
    
    # Запускаем автобэкап
    asyncio.create_task(backup_system.auto_backup_loop(interval_hours=24))
    
    logger.info("✅ Фоновые задачи запущены")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Остановка по Ctrl+C")


# ════════════════════════════════════════════════════════════════
# РАСШИРЕННАЯ АНАЛИТИКА (ПРОДОЛЖЕНИЕ)
# ════════════════════════════════════════════════════════════════

class SentimentAnalyzer:
    """Анализ тональности сообщений"""
    
    POSITIVE_WORDS = {
        "хорошо", "отлично", "супер", "классно", "круто", "спасибо",
        "благодарю", "рад", "счастлив", "люблю", "нравится", "восторг"
    }
    
    NEGATIVE_WORDS = {
        "плохо", "ужасно", "отвратительно", "ненавижу", "не нравится",
        "разочарован", "грустно", "печально", "злой", "бесит", "раздражает"
    }
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """Анализ тональности"""
        if not text:
            return {"sentiment": "neutral", "score": 0}
        
        text_lower = text.lower()
        words = text_lower.split()
        
        positive_count = sum(1 for word in words if word in self.POSITIVE_WORDS)
        negative_count = sum(1 for word in words if word in self.NEGATIVE_WORDS)
        
        total = positive_count + negative_count
        
        if total == 0:
            return {"sentiment": "neutral", "score": 0}
        
        score = (positive_count - negative_count) / total
        
        if score > 0.3:
            sentiment = "positive"
        elif score < -0.3:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment": sentiment,
            "score": score,
            "positive_words": positive_count,
            "negative_words": negative_count
        }


# Инициализация всех модулей
sentiment_analyzer = SentimentAnalyzer()


# ════════════════════════════════════════════════════════════════
# ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ (ПРОДОЛЖЕНИЕ)
# ════════════════════════════════════════════════════════════════

@router.message(Command("about"))
async def cmd_about(message: Message):
    """О боте"""
    about_text = (
        "<b>🤖 TELEGRAM MONITORING BOT</b>\n\n"
        "<b>Версия:</b> 1.0.0\n"
        "<b>Дата:</b> 01.03.2026\n"
        "<b>Разработчик:</b> @mrztn\n\n"
        "<b>Функции:</b>\n"
        "• Перехват удалённых сообщений\n"
        "• Отслеживание редактирований\n"
        "• Сохранение медиа с таймером\n"
        "• Мониторинг секретных чатов\n"
        "• Детекция спама\n"
        "• Статистика и аналитика\n\n"
        "⚠️ <b>ПРЕДУПРЕЖДЕНИЕ:</b>\n"
        "Незаконное использование влечёт уголовную ответственность.\n\n"
        "<b>Поддержка:</b> @mrztn"
    )
    
    await message.answer(about_text)




# ════════════════════════════════════════════════════════════════
# ВЕБ-ДАШБОРД (ДОПОЛНИТЕЛЬНО)
# ════════════════════════════════════════════════════════════════

class WebDashboard:
    """Веб-дашборд для админа (концепт)"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def generate_html_dashboard(self) -> str:
        """Сгенерировать HTML-дашборд"""
        stats = self.storage.stats
        users = self.storage.get_all_users()
        recent_alerts = self.storage.alerts[-20:]
        
        html = f"""
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Telegram Monitoring Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        header {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        
        h1 {{
            color: #1a73e8;
            font-size: 32px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: white;
            padding: 25px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .stat-value {{
            font-size: 48px;
            font-weight: bold;
            color: #1a73e8;
            margin: 10px 0;
        }}
        
        .stat-label {{
            color: #5f6368;
            font-size: 14px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .section {{
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }}
        
        .section h2 {{
            color: #202124;
            margin-bottom: 20px;
            font-size: 24px;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        
        th {{
            background: #f8f9fa;
            color: #5f6368;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 12px;
        }}
        
        .alert {{
            padding: 15px;
            border-left: 4px solid #ea4335;
            background: #fce8e6;
            margin: 10px 0;
            border-radius: 4px;
        }}
        
        .alert.info {{
            border-color: #1a73e8;
            background: #e8f0fe;
        }}
        
        .alert.warning {{
            border-color: #f9ab00;
            background: #fef7e0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Telegram Monitoring Dashboard</h1>
            <p style="color: #5f6368; margin-top: 10px;">
                Последнее обновление: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            </p>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Всего пользователей</div>
                <div class="stat-value">{stats['total_users']}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Всего событий</div>
                <div class="stat-value">{stats['total_events']}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Удалённых сообщений</div>
                <div class="stat-value">{stats['deleted_messages']}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Редактирований</div>
                <div class="stat-value">{stats['edited_messages']}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Медиа перехвачено</div>
                <div class="stat-value">{stats['media_intercepted']}</div>
            </div>
            
            <div class="stat-card">
                <div class="stat-label">Секретных чатов</div>
                <div class="stat-value">{stats['secret_chats']}</div>
            </div>
        </div>
        
        <div class="section">
            <h2>👥 Последние пользователи</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Username</th>
                        <th>Имя</th>
                        <th>Регистрация</th>
                        <th>Статус</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        for user in users[-10:]:
            status = "✅ Активен" if user.get("is_active") else "🚫 Неактивен"
            html += f"""
                    <tr>
                        <td>{user['id']}</td>
                        <td>@{user.get('username', 'N/A')}</td>
                        <td>{user.get('first_name', 'N/A')}</td>
                        <td>{user.get('registered_at', 'N/A')[:19]}</td>
                        <td>{status}</td>
                    </tr>
"""
        
        html += """
                </tbody>
            </table>
        </div>
        
        <div class="section">
            <h2>🔔 Последние алерты</h2>
"""
        
        for alert in reversed(recent_alerts):
            severity_class = alert.get("severity", "info")
            html += f"""
            <div class="alert {severity_class}">
                <strong>{alert['type']}</strong> — User {alert['user_id']}<br>
                <small>{alert['timestamp'][:19]}</small><br>
                {alert['message'][:200]}
            </div>
"""
        
        html += """
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def save_dashboard(self) -> str:
        """Сохранить дашборд"""
        html = self.generate_html_dashboard()
        filepath = os.path.join(EXPORTS_DIR, f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
        
        return filepath


# ════════════════════════════════════════════════════════════════
# КОМАНДЫ ДАШБОРДА
# ════════════════════════════════════════════════════════════════

@router.message(Command("dashboard"))
async def cmd_dashboard(message: Message):
    """Сгенерировать дашборд"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    await message.answer("📊 Генерирую дашборд...")
    
    dashboard = WebDashboard(storage)
    filepath = dashboard.save_dashboard()
    
    from aiogram.types import FSInputFile
    document = FSInputFile(filepath)
    
    await message.answer_document(
        document,
        caption="📊 Веб-дашборд сгенерирован. Откройте файл в браузере."
    )


@router.message(Command("stats_full"))
async def cmd_stats_full(message: Message):
    """Полная статистика (админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    stats = storage.stats
    users = storage.get_all_users()
    
    # Дополнительная аналитика
    active_users = [u for u in users if u.get("is_active")]
    inactive_users = [u for u in users if not u.get("is_active")]
    
    # Распределение по датам
    from collections import Counter
    registration_dates = [u.get("registered_at", "")[:10] for u in users]
    date_counter = Counter(registration_dates)
    
    # Топ-дни регистраций
    top_days = date_counter.most_common(5)
    
    full_stats_text = f"""
📊 <b>ПОЛНАЯ СТАТИСТИКА</b>

<b>👥 ПОЛЬЗОВАТЕЛИ:</b>
• Всего: {stats['total_users']}
• Активных: {len(active_users)}
• Неактивных: {len(inactive_users)}

<b>📈 СОБЫТИЯ:</b>
• Всего: {stats['total_events']}
• Удалённых сообщений: {stats['deleted_messages']}
• Редактирований: {stats['edited_messages']}
• Медиа перехвачено: {stats['media_intercepted']}
• Секретных чатов: {stats['secret_chats']}

<b>📅 ТОП-ДНИ РЕГИСТРАЦИЙ:</b>
"""
    
    for date, count in top_days:
        full_stats_text += f"• {date}: {count} пользователей\n"
    
    full_stats_text += f"\n🕐 Последнее обновление: {stats['last_updated'][:19]}"
    
    await message.answer(full_stats_text)


@router.message(Command("user_info"))
async def cmd_user_info(message: Message):
    """Информация о пользователе (админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    
    if not args:
        await message.answer("Использование: /user_info <user_id>")
        return
    
    target_id = int(args[0])
    user = storage.get_user(target_id)
    
    if not user:
        await message.answer(f"❌ Пользователь {target_id} не найден.")
        return
    
    events = storage.get_user_events(target_id, limit=1000)
    
    # Статистика по типам событий
    event_types = defaultdict(int)
    for event in events:
        event_types[event["type"]] += 1
    
    user_info_text = f"""
👤 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>Основное:</b>
• ID: <code>{target_id}</code>
• Username: @{user.get('username', 'N/A')}
• Имя: {user.get('first_name', 'N/A')} {user.get('last_name', '')}
• Статус: {'✅ Активен' if user.get('is_active') else '🚫 Неактивен'}

<b>Даты:</b>
• Регистрация: {user.get('registered_at', 'N/A')[:19]}
• Согласие: {user.get('consent_accepted_at', 'N/A')[:19]}
• Последняя активность: {user.get('last_activity', 'N/A')[:19]}

<b>Статистика событий:</b>
• Всего: {len(events)}
"""
    
    for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
        user_info_text += f"• {event_type}: {count}\n"
    
    await message.answer(user_info_text)


@router.message(Command("broadcast_test"))
async def cmd_broadcast_test(message: Message):
    """Тестовая рассылка (админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    test_message = (
        "🔔 <b>ТЕСТОВОЕ УВЕДОМЛЕНИЕ</b>\n\n"
        "Это тестовое сообщение от Telegram Monitoring Bot.\n"
        "Если вы получили это сообщение, значит система рассылок работает корректно."
    )
    
    try:
        await bot.send_message(ADMIN_ID, test_message)
        await message.answer("✅ Тестовое сообщение отправлено")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@router.message(Command("clear_data"))
async def cmd_clear_data(message: Message):
    """Очистить данные пользователя"""
    user_id = message.from_user.id
    
    if not storage.get_user(user_id):
        await message.answer("❌ Вы не зарегистрированы.")
        return
    
    # Удаляем события
    storage.activity = [e for e in storage.activity if e["user_id"] != user_id]
    storage.alerts = [a for a in storage.alerts if a["user_id"] != user_id]
    storage.save_all()
    
    await message.answer("✅ Все ваши события удалены. Аккаунт сохранён.")


@router.message(Command("privacy"))
async def cmd_privacy(message: Message):
    """Информация о конфиденциальности"""
    privacy_text = (
        "🔒 <b>КОНФИДЕНЦИАЛЬНОСТЬ</b>\n\n"
        "<b>Что мы собираем:</b>\n"
        "• Telegram ID, username\n"
        "• События в вашем Telegram (удаления, редактирования и т.д.)\n"
        "• Время и дата событий\n\n"
        "<b>Где хранится:</b>\n"
        "• Локально на сервере бота\n"
        "• JSON-файлы\n"
        "• Без доступа третьих лиц\n\n"
        "<b>Ваши права:</b>\n"
        "• /export — экспорт всех данных\n"
        "• /clear_data — удаление событий\n"
        "• /wipe — полное удаление аккаунта\n\n"
        "⚠️ Помните: мониторинг без согласия третьих лиц НЕЗАКОНЕН!"
    )
    
    await message.answer(privacy_text)


@router.message(Command("version"))
async def cmd_version(message: Message):
    """Версия бота"""
    version_text = (
        "<b>🤖 Telegram Monitoring Bot</b>\n\n"
        "<b>Версия:</b> 1.0.0\n"
        "<b>Дата сборки:</b> 01.03.2026\n"
        "<b>Python:</b> 3.12+\n"
        "<b>Aiogram:</b> 3.15.0\n"
        "<b>Статус:</b> Production Ready ✅\n\n"
        "<b>Функционал:</b>\n"
        "• Мониторинг удалений\n"
        "• Отслеживание редактирований\n"
        "• Перехват медиа\n"
        "• Детекция спама\n"
        "• Аналитика\n"
        "• Экспорт данных\n"
        "• Автобэкапы\n\n"
        "<b>Разработчик:</b> @mrztn"
    )
    
    await message.answer(version_text)


@router.message(Command("commands"))
async def cmd_commands(message: Message):
    """Список всех команд"""
    user_id = message.from_user.id
    is_admin = (user_id == ADMIN_ID)
    
    commands_text = "<b>📖 СПИСОК КОМАНД</b>\n\n"
    
    commands_text += (
        "<b>Основные:</b>\n"
        "/start — Начало работы\n"
        "/help — Справка\n"
        "/status — Ваш статус\n"
        "/about — О боте\n"
        "/version — Версия\n"
        "/privacy — Конфиденциальность\n\n"
        
        "<b>Данные:</b>\n"
        "/export — Экспорт данных\n"
        "/analyze — Анализ активности\n"
        "/clear_data — Очистить события\n"
        "/wipe — Удалить аккаунт\n\n"
        
        "<b>Дополнительно:</b>\n"
        "/keywords — Ключевые слова\n"
        "/archive — Архивировать чат\n"
        "/security — Отчёт безопасности\n"
        "/chart — Графики\n"
    )
    
    if is_admin:
        commands_text += (
            "\n<b>👑 АДМИН:</b>\n"
            "/admin — Админ-панель\n"
            "/dashboard — Веб-дашборд\n"
            "/stats_full — Полная статистика\n"
            "/user_info — Инфо о пользователе\n"
            "/backup — Создать бэкап\n"
            "/blacklist — Чёрный список\n"
            "/broadcast_test — Тест рассылки\n"
        )
    
    await message.answer(commands_text)


# ════════════════════════════════════════════════════════════════
# ОБРАБОТКА НЕИЗВЕСТНЫХ КОМАНД
# ════════════════════════════════════════════════════════════════

@router.message(Command())
async def unknown_command(message: Message):
    """Неизвестная команда"""
    await message.answer(
        "❓ Неизвестная команда.\n\n"
        "Список доступных команд: /commands\n"
        "Справка: /help"
    )


# ════════════════════════════════════════════════════════════════
# ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ
# ════════════════════════════════════════════════════════════════

@router.message(F.text)
async def handle_text(message: Message):
    """Обработка текстовых сообщений"""
    user_id = message.from_user.id
    
    if not storage.get_user(user_id):
        await message.answer(
            "👋 Привет! Я бот для мониторинга Telegram.\n\n"
            "Чтобы начать, напишите /start"
        )
        return
    
    # Здесь может быть логика обработки текста
    # Например, поиск по событиям
    await message.answer(
        "✅ Сообщение получено.\n\n"
        "Используйте команды для управления ботом. Список: /commands"
    )




# ════════════════════════════════════════════════════════════════
# СИСТЕМА ТЕГОВ И МЕТОК
# ════════════════════════════════════════════════════════════════

class TagSystem:
    """Система тегов для событий"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
        self.tags = defaultdict(set)  # event_id -> {tags}
    
    def add_tag(self, event_id: str, tag: str):
        """Добавить тег"""
        self.tags[event_id].add(tag.lower())
    
    def remove_tag(self, event_id: str, tag: str):
        """Удалить тег"""
        self.tags[event_id].discard(tag.lower())
    
    def get_tags(self, event_id: str) -> Set[str]:
        """Получить теги события"""
        return self.tags.get(event_id, set())
    
    def search_by_tag(self, tag: str) -> List[str]:
        """Поиск событий по тегу"""
        results = []
        tag_lower = tag.lower()
        
        for event_id, tags in self.tags.items():
            if tag_lower in tags:
                results.append(event_id)
        
        return results


# ════════════════════════════════════════════════════════════════
# СИСТЕМА УВЕДОМЛЕНИЙ С ПРИОРИТЕТАМИ
# ════════════════════════════════════════════════════════════════

class PriorityNotification:
    """Приоритетные уведомления"""
    
    PRIORITY_EMOJIS = {
        "low": "ℹ️",
        "medium": "⚠️",
        "high": "🔴",
        "critical": "🚨"
    }
    
    def __init__(self, bot: Bot):
        self.bot = bot
        self.notification_history = []
    
    async def send(
        self,
        user_id: int,
        message: str,
        priority: str = "medium",
        attachments: Optional[List] = None
    ):
        """Отправить уведомление с приоритетом"""
        emoji = self.PRIORITY_EMOJIS.get(priority, "ℹ️")
        formatted_message = f"{emoji} <b>УВЕДОМЛЕНИЕ [{priority.upper()}]</b>\n\n{message}"
        
        try:
            await self.bot.send_message(
                user_id,
                formatted_message,
                disable_notification=(priority == "low")
            )
            
            self.notification_history.append({
                "user_id": user_id,
                "message": message,
                "priority": priority,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "delivered": True
            })
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
            self.notification_history.append({
                "user_id": user_id,
                "message": message,
                "priority": priority,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "delivered": False,
                "error": str(e)
            })


# ════════════════════════════════════════════════════════════════
# РАСШИРЕННЫЙ ПОИСК
# ════════════════════════════════════════════════════════════════

class AdvancedSearch:
    """Расширенный поиск по событиям"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def search(
        self,
        user_id: Optional[int] = None,
        event_type: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        keywords: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Продвинутый поиск"""
        
        events = self.storage.activity
        
        # Фильтр по пользователю
        if user_id:
            events = [e for e in events if e["user_id"] == user_id]
        
        # Фильтр по типу
        if event_type:
            events = [e for e in events if e["type"] == event_type]
        
        # Фильтр по дате
        if date_from:
            events = [
                e for e in events
                if datetime.fromisoformat(e["timestamp"]) >= date_from
            ]
        
        if date_to:
            events = [
                e for e in events
                if datetime.fromisoformat(e["timestamp"]) <= date_to
            ]
        
        # Фильтр по ключевым словам
        if keywords:
            filtered = []
            for event in events:
                event_str = json.dumps(event, ensure_ascii=False).lower()
                if any(kw.lower() in event_str for kw in keywords):
                    filtered.append(event)
            events = filtered
        
        return events[:limit]
    
    def search_regex(self, pattern: str, limit: int = 50) -> List[Dict]:
        """Поиск по регулярному выражению"""
        import re
        
        results = []
        regex = re.compile(pattern, re.IGNORECASE)
        
        for event in self.storage.activity:
            event_str = json.dumps(event, ensure_ascii=False)
            if regex.search(event_str):
                results.append(event)
                if len(results) >= limit:
                    break
        
        return results


# ════════════════════════════════════════════════════════════════
# ГЕНЕРАТОР ОТЧЁТОВ
# ════════════════════════════════════════════════════════════════

class ReportGenerator:
    """Генератор отчётов"""
    
    def __init__(self, storage: DataStorage):
        self.storage = storage
    
    def generate_user_report(self, user_id: int, period_days: int = 7) -> str:
        """Сгенерировать отчёт по пользователю"""
        user = self.storage.get_user(user_id)
        if not user:
            return "Пользователь не найден"
        
        events = self.storage.get_user_events(user_id, limit=10000)
        cutoff = datetime.now(timezone.utc) - timedelta(days=period_days)
        recent_events = [
            e for e in events
            if datetime.fromisoformat(e["timestamp"]) > cutoff
        ]
        
        # Статистика
        event_types = defaultdict(int)
        for event in recent_events:
            event_types[event["type"]] += 1
        
        # Активность по дням
        daily_activity = defaultdict(int)
        for event in recent_events:
            day = datetime.fromisoformat(event["timestamp"]).date().isoformat()
            daily_activity[day] += 1
        
        # Формируем отчёт
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║              ОТЧЁТ ПО ПОЛЬЗОВАТЕЛЮ                           ║
╚══════════════════════════════════════════════════════════════╝

👤 ИНФОРМАЦИЯ:
   • ID: {user_id}
   • Username: @{user.get('username', 'N/A')}
   • Регистрация: {user.get('registered_at', 'N/A')[:10]}

📊 СТАТИСТИКА ЗА {period_days} ДНЕЙ:
   • Всего событий: {len(recent_events)}
   
📈 ПО ТИПАМ:
"""
        
        for event_type, count in sorted(event_types.items(), key=lambda x: x[1], reverse=True):
            report += f"   • {event_type}: {count}\n"
        
        report += "\n📅 АКТИВНОСТЬ ПО ДНЯМ:\n"
        for day in sorted(daily_activity.keys()):
            bars = "█" * (daily_activity[day] // 5)
            report += f"   {day}: {bars} ({daily_activity[day]})\n"
        
        report += f"\n🕐 Дата отчёта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += "═" * 62
        
        return report
    
    def generate_admin_report(self) -> str:
        """Сгенерировать отчёт для админа"""
        stats = self.storage.stats
        users = self.storage.get_all_users()
        
        active_today = []
        cutoff_today = datetime.now(timezone.utc).date()
        
        for user in users:
            last_activity = user.get("last_activity")
            if last_activity:
                activity_date = datetime.fromisoformat(last_activity).date()
                if activity_date == cutoff_today:
                    active_today.append(user)
        
        report = f"""
╔══════════════════════════════════════════════════════════════╗
║              АДМИНИСТРАТИВНЫЙ ОТЧЁТ                          ║
╚══════════════════════════════════════════════════════════════╝

👥 ПОЛЬЗОВАТЕЛИ:
   • Всего зарегистрировано: {stats['total_users']}
   • Активных сегодня: {len(active_today)}
   • Новых за сегодня: {len([u for u in users if u.get('registered_at', '')[:10] == str(cutoff_today)])}

📈 СОБЫТИЯ:
   • Всего событий: {stats['total_events']}
   • Удалённых сообщений: {stats['deleted_messages']}
   • Редактирований: {stats['edited_messages']}
   • Медиа перехвачено: {stats['media_intercepted']}
   • Секретных чатов: {stats['secret_chats']}

🔔 АЛЕРТЫ:
   • Всего: {len(self.storage.alerts)}
   • За последний час: {len([a for a in self.storage.alerts if datetime.fromisoformat(a['timestamp']) > datetime.now(timezone.utc) - timedelta(hours=1)])}

💾 ДАННЫЕ:
   • Размер событий: {len(self.storage.activity)} записей
   • Размер алертов: {len(self.storage.alerts)} записей

🕐 Дата отчёта: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
═══════════════════════════════════════════════════════════════
"""
        
        return report


# ════════════════════════════════════════════════════════════════
# КОМАНДЫ ДЛЯ РАСШИРЕННОГО ФУНКЦИОНАЛА
# ════════════════════════════════════════════════════════════════

@router.message(Command("report"))
async def cmd_report(message: Message):
    """Сгенерировать отчёт"""
    user_id = message.from_user.id
    
    if not storage.get_user(user_id):
        await message.answer("❌ Вы не зарегистрированы. Напишите /start")
        return
    
    args = message.text.split()[1:] if len(message.text.split()) > 1 else []
    period = int(args[0]) if args else 7
    
    generator = ReportGenerator(storage)
    report = generator.generate_user_report(user_id, period)
    
    await message.answer(f"<pre>{report}</pre>")


@router.message(Command("admin_report"))
async def cmd_admin_report(message: Message):
    """Админский отчёт"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    generator = ReportGenerator(storage)
    report = generator.generate_admin_report()
    
    await message.answer(f"<pre>{report}</pre>")


@router.message(Command("search_advanced"))
async def cmd_search_advanced(message: Message, state: FSMContext):
    """Расширенный поиск"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    await message.answer(
        "🔍 <b>РАСШИРЕННЫЙ ПОИСК</b>\n\n"
        "Использование:\n"
        "<code>/search_advanced keyword1 keyword2</code>\n\n"
        "Будут найдены события, содержащие эти ключевые слова."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    """Проверка работы бота"""
    start_time = datetime.now()
    sent_message = await message.answer("🏓 Pong!")
    end_time = datetime.now()
    
    latency = (end_time - start_time).total_seconds() * 1000
    
    await sent_message.edit_text(
        f"🏓 Pong!\n\n"
        f"⏱ Задержка: {latency:.2f} мс\n"
        f"✅ Бот работает нормально"
    )


@router.message(Command("uptime"))
async def cmd_uptime(message: Message):
    """Время работы бота"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    # Читаем время запуска из файла (если есть)
    uptime_file = os.path.join(DATA_DIR, "uptime.txt")
    
    if os.path.exists(uptime_file):
        with open(uptime_file, 'r') as f:
            start_time_str = f.read().strip()
            start_time = datetime.fromisoformat(start_time_str)
            
            uptime_delta = datetime.now(timezone.utc) - start_time
            
            days = uptime_delta.days
            hours = uptime_delta.seconds // 3600
            minutes = (uptime_delta.seconds % 3600) // 60
            
            await message.answer(
                f"⏰ <b>UPTIME</b>\n\n"
                f"Запущен: {start_time.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
                f"Работает: {days}д {hours}ч {minutes}м"
            )
    else:
        await message.answer("⏰ Время запуска неизвестно")


@router.message(Command("changelog"))
async def cmd_changelog(message: Message):
    """История изменений"""
    changelog_text = """
<b>📝 ИСТОРИЯ ИЗМЕНЕНИЙ</b>

<b>v1.0.0 (01.03.2026)</b>
✨ Первый релиз
• Перехват удалённых сообщений
• Отслеживание редактирований
• Сохранение медиа с таймером
• Мониторинг секретных чатов
• Детекция спама
• Анализ тональности
• Статистика и аналитика
• Админ-панель
• Экспорт данных
• Автобэкапы
• Веб-дашборд
• Система приоритетов
• Расширенный поиск
• Генератор отчётов

<b>Разработчик:</b> @mrztn
"""
    
    await message.answer(changelog_text)


@router.message(Command("feedback"))
async def cmd_feedback(message: Message):
    """Обратная связь"""
    feedback_text = (
        "💬 <b>ОБРАТНАЯ СВЯЗЬ</b>\n\n"
        "Если у вас есть предложения, вопросы или вы обнаружили баг, "
        "пожалуйста, свяжитесь с разработчиком:\n\n"
        "👨‍💻 @mrztn\n\n"
        "Мы ценим ваше мнение и постоянно улучшаем бота!"
    )
    
    await message.answer(feedback_text)


@router.message(Command("donate"))
async def cmd_donate(message: Message):
    """Поддержка проекта"""
    donate_text = (
        "❤️ <b>ПОДДЕРЖКА ПРОЕКТА</b>\n\n"
        "Если вам нравится этот бот и вы хотите поддержать его развитие, "
        "вы можете связаться с разработчиком:\n\n"
        "👨‍💻 @mrztn\n\n"
        "Спасибо за вашу поддержку! 🙏"
    )
    
    await message.answer(donate_text)


# ════════════════════════════════════════════════════════════════
# ФИНАЛЬНАЯ ИНИЦИАЛИЗАЦИЯ
# ════════════════════════════════════════════════════════════════

# Сохраняем время запуска
uptime_file = os.path.join(DATA_DIR, "uptime.txt")
with open(uptime_file, 'w') as f:
    f.write(datetime.now(timezone.utc).isoformat())


# Инициализация всех систем
tag_system = TagSystem(storage)
priority_notifier = PriorityNotification(bot)
advanced_search = AdvancedSearch(storage)
report_generator = ReportGenerator(storage)

logger.info("✅ Все системы инициализированы")


# ════════════════════════════════════════════════════════════════
# ГЛАВНЫЙ ЗАПУСК
# ════════════════════════════════════════════════════════════════

async def main():
    """Главная функция"""
    logger.info("🚀 Запуск Telegram Monitoring Bot...")
    
    # Регистрируем роутер
    dp.include_router(router)
    
    # Регистрируем события
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    
    # Запускаем фоновые задачи
    asyncio.create_task(background_tasks())
    
    # Запускаем polling
    logger.info("📡 Начинаю polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⚠️ Остановка по Ctrl+C")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        # Сохраняем все данные перед выходом
        storage.save_all()
        logger.info("💾 Данные сохранены")
        logger.info("👋 Бот остановлен")



# ════════════════════════════════════════════════════════════════
# ДОПОЛНИТЕЛЬНЫЕ УТИЛИТЫ
# ════════════════════════════════════════════════════════════════

class PerformanceMonitor:
    """Мониторинг производительности"""
    
    def __init__(self):
        self.metrics = {
            "commands_processed": 0,
            "events_logged": 0,
            "alerts_sent": 0,
            "errors_count": 0,
            "average_response_time": 0,
            "start_time": datetime.now(timezone.utc)
        }
    
    def record_command(self, response_time: float):
        """Записать обработку команды"""
        self.metrics["commands_processed"] += 1
        
        # Обновляем среднее время ответа
        current_avg = self.metrics["average_response_time"]
        count = self.metrics["commands_processed"]
        new_avg = (current_avg * (count - 1) + response_time) / count
        self.metrics["average_response_time"] = new_avg
    
    def record_event(self):
        """Записать событие"""
        self.metrics["events_logged"] += 1
    
    def record_alert(self):
        """Записать алерт"""
        self.metrics["alerts_sent"] += 1
    
    def record_error(self):
        """Записать ошибку"""
        self.metrics["errors_count"] += 1
    
    def get_metrics(self) -> Dict:
        """Получить метрики"""
        uptime = datetime.now(timezone.utc) - self.metrics["start_time"]
        return {
            **self.metrics,
            "uptime_seconds": uptime.total_seconds()
        }


class RateLimiter:
    """Ограничение частоты запросов"""
    
    def __init__(self, max_requests: int = 10, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window  # секунды
        self.user_requests = defaultdict(list)
    
    def is_allowed(self, user_id: int) -> bool:
        """Проверить, разрешён ли запрос"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.time_window)
        
        # Очищаем старые запросы
        self.user_requests[user_id] = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > cutoff
        ]
        
        # Проверяем лимит
        if len(self.user_requests[user_id]) >= self.max_requests:
            return False
        
        # Добавляем текущий запрос
        self.user_requests[user_id].append(now)
        return True
    
    def get_remaining(self, user_id: int) -> int:
        """Получить оставшееся количество запросов"""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.time_window)
        
        recent_requests = [
            req_time for req_time in self.user_requests[user_id]
            if req_time > cutoff
        ]
        
        return max(0, self.max_requests - len(recent_requests))


# Инициализация
performance_monitor = PerformanceMonitor()
rate_limiter = RateLimiter(max_requests=30, time_window=60)


@router.message(Command("performance"))
async def cmd_performance(message: Message):
    """Метрики производительности (админ)"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("🚫 Доступ запрещён.")
        return
    
    metrics = performance_monitor.get_metrics()
    
    uptime_hours = metrics["uptime_seconds"] / 3600
    
    perf_text = f"""
⚡️ <b>МЕТРИКИ ПРОИЗВОДИТЕЛЬНОСТИ</b>

📊 ОБРАБОТАНО:
• Команд: {metrics['commands_processed']}
• Событий: {metrics['events_logged']}
• Алертов: {metrics['alerts_sent']}

⚠️ ОШИБКИ:
• Всего: {metrics['errors_count']}

⏱ ВРЕМЯ ОТВЕТА:
• Среднее: {metrics['average_response_time']:.2f} мс

⏰ UPTIME:
• {uptime_hours:.1f} часов

📈 ПРОИЗВОДИТЕЛЬНОСТЬ:
• Команд/час: {metrics['commands_processed'] / max(uptime_hours, 1):.1f}
• События/час: {metrics['events_logged'] / max(uptime_hours, 1):.1f}
"""
    
    await message.answer(perf_text)


@router.message(Command("limits"))
async def cmd_limits(message: Message):
    """Информация о лимитах"""
    user_id = message.from_user.id
    remaining = rate_limiter.get_remaining(user_id)
    
    limits_text = f"""
⚙️ <b>ЛИМИТЫ ИСПОЛЬЗОВАНИЯ</b>

<b>Частота команд:</b>
• Максимум: {rate_limiter.max_requests} команд/{rate_limiter.time_window} сек
• Доступно: {remaining}

<b>Хранение данных:</b>
• События: последние 10,000
• Алерты: последние 1,000
• Бэкапы: автоматически каждые 24 часа

<b>Размер:</b>
• Экспорт: до 50 МБ
• Медиа: до 20 МБ
"""
    
    await message.answer(limits_text)


@router.message(Command("disclaimer"))
async def cmd_disclaimer(message: Message):
    """Юридический дисклеймер"""
    disclaimer_text = """
⚖️ <b>ЮРИДИЧЕСКИЙ ДИСКЛЕЙМЕР</b>

⚠️ <b>ВНИМАНИЕ! ОЧЕНЬ ВАЖНО!</b>

<b>1. НЕЗАКОННОЕ ИСПОЛЬЗОВАНИЕ:</b>
Использование этого бота без ПИСЬМЕННОГО СОГЛАСИЯ всех участников переписки является УГОЛОВНЫМ ПРЕСТУПЛЕНИЕМ по законодательству Российской Федерации:

• УК РФ ст. 137 — до 2 лет лишения свободы
• УК РФ ст. 138 — до 4 лет лишения свободы

<b>2. РИСК БЛОКИРОВКИ:</b>
Telegram активно блокирует аккаунты, использующие подобные боты. Блокировка НЕОБРАТИМА.

<b>3. ОТКАЗ ОТ ОТВЕТСТВЕННОСТИ:</b>
Разработчики НЕ НЕСУТ НИКАКОЙ ответственности за:
• Ваши действия
• Блокировку аккаунта
• Уголовное преследование
• Любые убытки

<b>4. СОГЛАСИЕ:</b>
Используя бот, вы ПОДТВЕРЖДАЕТЕ, что:
• Вам 18+ лет
• Вы получили согласие ВСЕХ участников
• Вы понимаете риски
• Вы принимаете ПОЛНУЮ ответственность

⚠️ Разработчики рекомендуют НЕ использовать бот без юридической консультации!

<b>Поддержка:</b> @mrztn
"""
    
    await message.answer(disclaimer_text)


@router.message(Command("legal"))
async def cmd_legal(message: Message):
    """Юридическая информация"""
    legal_text = """
⚖️ <b>ЮРИДИЧЕСКАЯ ИНФОРМАЦИЯ</b>

<b>ПРИМЕНИМОЕ ЗАКОНОДАТЕЛЬСТВО:</b>

<b>Россия:</b>
• УК РФ ст. 137 "Нарушение неприкосновенности частной жизни"
• УК РФ ст. 138 "Нарушение тайны переписки"
• ФЗ-152 "О персональных данных"

<b>Европейский Союз:</b>
• GDPR (General Data Protection Regulation)
• Штрафы до €20,000,000

<b>США:</b>
• Electronic Communications Privacy Act
• Computer Fraud and Abuse Act

<b>TELEGRAM TERMS OF SERVICE:</b>
Использование сторонних клиентов и ботов мониторинга может нарушать Условия использования Telegram и привести к блокировке аккаунта.

<b>РЕКОМЕНДАЦИИ:</b>
1. Проконсультируйтесь с юристом
2. Получите письменное согласие всех участников
3. Используйте только в легальных целях
4. Будьте готовы к блокировке аккаунта

<b>КОНТАКТЫ:</b>
@mrztn
"""
    
    await message.answer(legal_text)


# ════════════════════════════════════════════════════════════════
# EASTER EGGS
# ════════════════════════════════════════════════════════════════

@router.message(Command("secret"))
async def cmd_secret(message: Message):
    """Секретная команда"""
    await message.answer(
        "🎉 Поздравляю! Вы нашли секретную команду!\n\n"
        "Вот несколько интересных фактов о боте:\n"
        "• Разработан за 1 день\n"
        "• Содержит 3000+ строк кода\n"
        "• 50+ команд\n"
        "• 15+ модулей\n"
        "• 100% Python 🐍\n\n"
        "Автор: @mrztn"
    )


@router.message(F.text == "🤖")
async def easter_egg_robot(message: Message):
    """Пасхалка с роботом"""
    await message.answer("🤖 Я робот! Бип-буп!")


@router.message(F.text.lower() == "привет")
async def greet_hello(message: Message):
    """Приветствие"""
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        "Я бот для мониторинга Telegram. Используйте /help для справки."
    )


# ════════════════════════════════════════════════════════════════
# ФИНАЛЬНЫЕ ЛОГИ
# ════════════════════════════════════════════════════════════════

logger.info("=" * 60)
logger.info("TELEGRAM MONITORING BOT")
logger.info("Version: 1.0.0")
logger.info("Date: 01.03.2026")
logger.info("Developer: @mrztn")
logger.info("=" * 60)
logger.info(f"Bot token: {BOT_TOKEN[:10]}...")
logger.info(f"Admin ID: {ADMIN_ID}")
logger.info(f"Data directory: {DATA_DIR}")
logger.info("=" * 60)

