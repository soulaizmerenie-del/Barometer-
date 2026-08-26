#!/usr/bin/env bash
# Ставит ежедневный запуск сбора в cron.
# Использование:  ./schedule.sh [ЧЧ:ММ]     (по умолчанию 09:00)
set -euo pipefail

cd "$(dirname "$0")"
PROJECT="$(pwd)"
TIME="${1:-09:00}"
HOUR="${TIME%%:*}"
MINUTE="${TIME##*:}"

if [ ! -x "$PROJECT/.venv/bin/python" ]; then
    echo "Сначала выполните ./setup.sh <api_id> <api_hash>"
    exit 1
fi

LINE="$MINUTE $HOUR * * * cd $PROJECT && ./daily.sh >> $PROJECT/data/cron.log 2>&1"

cat > "$PROJECT/daily.sh" <<'INNER'
#!/usr/bin/env bash
# Ежедневный сбор: читает чаты за вчера, строит дайджест и черновик задачника.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
.venv/bin/python -m barometer daily --date yesterday ${BAROMETER_ALLOW_PUBLISH:+--publish}
INNER
chmod +x "$PROJECT/daily.sh"

# Ставим строку, предварительно убрав прежнюю запись для этого проекта.
( crontab -l 2>/dev/null | grep -vF "$PROJECT/daily.sh" || true; echo "$LINE" ) | crontab -

echo "Ежедневный запуск установлен на $TIME:"
echo "  $LINE"
echo
echo "Проверить:      crontab -l"
echo "Журнал:         $PROJECT/data/cron.log"
echo "Отключить:      crontab -l | grep -v daily.sh | crontab -"
