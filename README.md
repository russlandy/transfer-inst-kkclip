# inst-trans

Telegram-бот, который в групповом чате с друзьями автоматически отвечает на
Instagram-ссылки их зеркальной версией — превью в Telegram подгружается, видео
проигрывается inline без открытия Instagram.

Конвертация — замена хоста: `instagram.com/<path>` → `<mirror>/<path>`.
В `.env` задаётся список зеркал (`TARGET_HOSTS`): первое — основная ссылка
(с превью), остальные — резервные, если у первой не подгрузилось. Если зеркало
перестало работать, достаточно поменять порядок в `TARGET_HOSTS` и перезапустить
сервис — код не трогаем.

Поддерживаемые пути: `/reel/`, `/tv/`, `/share/reel/`, `/share/`.
Известные зеркала: `kkclip.com`, `eeinstagram.com`, `ddinstagram.com`,
`kkinstagram.com`, `g.ddinstagram.com`.

## Стек

- Python 3.11+, [aiogram 3.x](https://docs.aiogram.dev/)
- structlog, pydantic-settings
- Деплой: systemd на Ubuntu/Debian (тот же VPS, что и teacher-helper)

## Локальный запуск

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

copy .env.example .env
# заполнить TELEGRAM_BOT_TOKEN и ALLOWED_CHAT_IDS

python -m inst_trans
```

### Как узнать chat_id

1. Создай бота через [@BotFather](https://t.me/BotFather), вставь токен в `.env`.
2. Запусти бота локально, добавь в нужный чат.
3. Напиши в чате `/chatid` — бот ответит id'шником чата. Скопируй в
   `ALLOWED_CHAT_IDS` и перезапусти.

## Деплой на VPS

Тот же сервер и схема, что у `teacher-helper`. Сначала bootstrap (если ещё
не делал — на VPS уже стоит ключ от teacher-helper, тогда шаг пропускается):

```powershell
$env:DEPLOY_PASS = "..."
python scripts\deploy_bootstrap.py <host> root
```

Затем установка:

```powershell
python scripts\deploy.py <host> root --git-url git@github.com:russlandy/inst-trans.git --branch main
```

Скрипт ставит сервис в `/opt/inst-trans`, заливает локальный `.env`, регистрирует
`inst-trans.service` в systemd и показывает статус + хвост journalctl.

Логи на сервере: `journalctl -u inst-trans -f`.

## Разработка

```bash
ruff check src/ tests/
ruff format src/ tests/
pytest
mypy src/
```

## Лицензия

MIT
