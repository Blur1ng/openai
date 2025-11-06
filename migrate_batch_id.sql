-- Миграция: добавление batch_id в таблицу job_results

-- 1. Добавляем колонку batch_id (для старых записей будет NULL)
ALTER TABLE job_results ADD COLUMN IF NOT EXISTS batch_id TEXT;

-- 2. Обновляем старые записи (присваиваем им временный batch_id)
UPDATE job_results 
SET batch_id = 'legacy-' || id::text 
WHERE batch_id IS NULL;

-- 3. Делаем поле обязательным
ALTER TABLE job_results ALTER COLUMN batch_id SET NOT NULL;

-- 4. Создаём индекс для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_job_results_batch_id ON job_results(batch_id);

