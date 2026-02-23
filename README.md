# DIVINE Recruiting Automation

Автоматизация рекрутинга CDL Team Drivers для Divine Enterprises.

## Quick Start

```bash
cd ~/Desktop/DIVINE
source venv/bin/activate
cd scripts

# Обработать новых CDL кандидатов
python run.py process

# Отправить pre-screening emails (когда будет корп. почта)
python run.py screen

# Проверить ответы на pre-screening
python run.py check-replies

# Список готовых к звонку (Team OK)
python run.py list --status "Team OK"

# Синхронизировать в Google Sheet
python run.py sync
```

## Workflow

```
1. process      → кандидаты в базе (статус: New)
2. screen       → отправка pre-screening (статус: Screening)
3. check-replies → парсинг ответов (статус: Team OK / Solo Only)
4. list --status "Team OK" → список готовых к team driving
5. Звоним только "Team OK"
6. sync         → синхронизация в Google Sheet
```

## Команды

| Команда | Описание |
|---------|----------|
| `python run.py process` | Обработать новых CDL кандидатов из Gmail |
| `python run.py process --all` | Обработать ВСЕХ кандидатов |
| `python run.py screen` | Отправить pre-screening всем New |
| `python run.py screen --id 15` | Отправить конкретному кандидату |
| `python run.py check-replies` | Проверить ответы на pre-screening |
| `python run.py sync` | Синхронизировать в Google Sheet |
| `python run.py stats` | Показать статистику |
| `python run.py list` | Список последних кандидатов |
| `python run.py list -n 50` | Список последних 50 |
| `python run.py list --status "Team OK"` | Фильтр по статусу |
| `python run.py search "John"` | Поиск по имени/email/телефону |

## Архитектура

```
Gmail (CareerPlug notifications)
        ↓
    Playwright (scraping)
        ↓
    SQLite Database (быстро, надёжно)
        ↓
    Pre-screening Email → ответ → Team OK / Solo Only
        ↓
    Звонок только "Team OK"
        ↓
    Google Sheet (для работы и Divine)
```

## Структура файлов

```
DIVINE/
├── venv/                     # Python окружение
├── scripts/
│   ├── config.py             # Credentials
│   ├── run.py                # Главный скрипт
│   ├── database.py           # SQLite база
│   ├── email_sender.py       # Отправка писем + парсинг ответов
│   ├── careerplug_scraper.py # Scraping CareerPlug
│   ├── google_sheets.py      # Sync с Google Sheet
│   └── google_credentials.json
├── data/
│   ├── candidates.db         # SQLite база
│   └── candidates.csv        # Backup CSV
├── templates/
│   ├── candidate_email.md    # Шаблон IntelliApp письма
│   └── prescreening_email.md # Шаблон pre-screening
└── README.md
```

## Google Sheet

**URL:** https://docs.google.com/spreadsheets/d/1mJoB8KQY7lOYWu8ONFUXZq9JYilpQPA0CVwYHOQeRBg

**Колонки:**
1. Date Called
2. Applicant Name
3. Phone Number
4. Call Status
5. Comment
6. Call Back Number
7. Class A Experience
8. Open to Team Driving?
9. Reason for Switching
10. Days on Road
11. Expected Home Time
12. 53' Temp exp
13. Doubles/Triples
14. Tanker
15. Hazmat
16. W-2 or 1099

## Статусы кандидатов

- `New` — новый, не обработан
- `Screening` — отправлен pre-screening email, ждём ответ
- `Team OK` — готов к team driving, звоним!
- `Solo Only` — хочет работать solo, не подходит
- `Done` — позвонили
- `Sent link` — отправили IntelliApp
- `No answer` — не ответил
- `Not interested` — не заинтересован

## Credentials

**Gmail (для уведомлений):**
- Email: nguzen@gmail.com
- App Password: в config.py

**CareerPlug:**
- Login: nguzen@gmail.com
- Password: в config.py

**Google Sheets:**
- Service Account: divine-bot@divine-bot-482110.iam.gserviceaccount.com
- Credentials: scripts/google_credentials.json

## Divine Enterprises

- HR Manager: Irina Lazebnaia
- Email: irina@divinetrans.com
- Phone: (916) 781-7200 Ext. 238
- Address: 3555 Cincinnati Ave., Rocklin, CA 95765

## Контракт

- База: $1,200/мес (включая SMM)
- За команду: $760
- Цель: 5 команд/мес = $5,000

## IntelliApp

Все кандидаты должны заполнить заявку:
https://intelliapp.driverapponline.com/c/divinetrans

## Pre-screening Email

**Блокер:** Ждём корпоративную почту Divine.

Когда получишь email от Divine:
1. Обнови `config.py`:
   ```python
   USE_DIVINE_EMAIL = True
   DIVINE_EMAIL = "nikita@divinetrans.com"
   DIVINE_EMAIL_PASSWORD = "password"
   DIVINE_IMAP_SERVER = "mail.divinetrans.com"
   DIVINE_SMTP_SERVER = "mail.divinetrans.com"
   ```
2. Запусти `python run.py screen`
