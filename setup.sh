#!/usr/bin/env bash
# Разовая настройка Barometer на своей машине.
# Использование:  ./setup.sh <api_id> <api_hash>
set -euo pipefail

cd "$(dirname "$0")"

if [ $# -lt 2 ]; then
    echo "Использование: ./setup.sh <api_id> <api_hash>"
    echo "Ключи берутся на my.telegram.org → API development tools."
    exit 1
fi

echo "==> Виртуальное окружение"
python3 -m venv .venv
# Системный setuptools в Debian ломается на сборке pyaes — обновляем в venv.
.venv/bin/pip install --quiet --upgrade pip setuptools wheel
.venv/bin/pip install --quiet -r requirements.txt

echo "==> Файл .env"
if [ -f .env ]; then
    echo "    .env уже существует, не трогаю"
else
    cp .env.example .env
    sed -i.bak "s/^TELEGRAM_API_ID=.*/TELEGRAM_API_ID=$1/" .env
    sed -i.bak "s/^TELEGRAM_API_HASH=.*/TELEGRAM_API_HASH=$2/" .env
    rm -f .env.bak
    echo "    ключи записаны (файл в .gitignore)"
fi

echo "==> Вход в Telegram"
echo "    Сейчас будет запрошен номер телефона и код из Telegram."
set -a; . ./.env; set +a
.venv/bin/python -m barometer login status || true

cat <<'HINT'

Дальше:

  .venv/bin/python -m barometer login request --phone +38267123456
  .venv/bin/python -m barometer login code --code XXXXX
  .venv/bin/python -m barometer login status

Когда все три чата видны — ежедневный запуск:

  .venv/bin/python -m barometer daily --date yesterday

Ежедневный запуск по расписанию:

  ./schedule.sh 09:00

Готовый дайджест и черновик задачника окажутся в data/. Чтобы они сами
уезжали в репозиторий, откуда их читает ассистент, — сделайте репозиторий
приватным и добавьте в .env строку BAROMETER_ALLOW_PUBLISH=1.
HINT
