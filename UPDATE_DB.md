# Обновление БД для batch_id

## Изменения в схеме БД

Добавлено новое поле `batch_id` в таблицу `job_results` для группировки задач из одного запроса.

## Миграция существующей БД

### Вариант 1: Пересоздание БД (простой способ)

⚠️ **Внимание**: Все существующие данные будут удалены!

```bash
# Остановить контейнеры и удалить volumes
docker-compose down -v

# Запустить заново (БД создастся с новой схемой)
docker-compose up -d --build
```

### Вариант 2: Ручная миграция (сохранение данных)

```bash
# 1. Подключитесь к БД
docker exec -it pg psql -U postgres -d prompt_db

# 2. Добавьте колонку batch_id (для старых записей будет NULL)
ALTER TABLE job_results ADD COLUMN batch_id TEXT;

# 3. Обновите старые записи (присвойте им временный batch_id)
UPDATE job_results 
SET batch_id = 'legacy-' || id::text 
WHERE batch_id IS NULL;

# 4. Сделайте поле обязательным
ALTER TABLE job_results ALTER COLUMN batch_id SET NOT NULL;

# 5. Создайте индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_job_results_batch_id ON job_results(batch_id);

# 6. Выйдите
\q
```

### Проверка миграции

```bash
# Проверьте структуру таблицы
docker exec -it pg psql -U postgres -d prompt_db \
    -c "\d job_results"

# Проверьте, что batch_id добавлен
docker exec -it pg psql -U postgres -d prompt_db \
    -c "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name='job_results' AND column_name='batch_id';"

# Проверьте индексы
docker exec -it pg psql -U postgres -d prompt_db \
    -c "\di job_results*"
```

## После миграции

1. Перезапустите приложение:
```bash
docker-compose restart app
```

2. Перезапустите воркеры:
```bash
docker-compose restart worker
```

3. Отправьте тестовый запрос и проверьте, что возвращается `batch_id`:
```bash
curl -X POST "http://185.130.224.177:8001/api/v1/ai_model/send_prompt/" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "ai_model": "chatgpt",
    "model": "gpt-4",
    "request": "test code"
  }'
```

Ответ должен содержать:
```json
{
  "jobs": [...],
  "total": 4,
  "batch_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

## Использование скрипта загрузки

После обновления БД можно использовать скрипт `download_results.py`:

```bash
python download_results.py \
    --server http://185.130.224.177:8001 \
    --token YOUR_TOKEN \
    --output-dir results
```

Скрипт автоматически найдёт последний `batch_id` и загрузит все связанные с ним результаты.

