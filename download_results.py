#!/usr/bin/env python3
"""
Скрипт для загрузки последних результатов AI обработки с сервера.
Загружает все результаты из последнего батча (последний отправленный код)
и сохраняет их в отдельные .md файлы.

Использование:
    python download_results.py --server http://185.130.224.177:8001 --token YOUR_TOKEN
    
Опциональные аргументы:
    --output-dir results  # директория для сохранения файлов (по умолчанию: results/)
"""

import argparse
import requests
import sys
from pathlib import Path
from typing import List, Dict, Optional


class ResultDownloader:
    def __init__(self, server_url: str, token: str):
        """
        Args:
            server_url: URL сервера (например, http://185.130.224.177:8001)
            token: Токен для авторизации
        """
        self.server_url = server_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def get_active_prompts_count(self) -> int:
        """Получает количество активных промптов"""
        url = f"{self.server_url}/api/v1/prompts/?is_active=true"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            prompts = response.json()
            return len(prompts)
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка при получении списка промптов: {e}")
            sys.exit(1)
    
    def get_latest_results(self, limit: int) -> List[Dict]:
        """Получает список ID последних результатов"""
        url = f"{self.server_url}/api/v1/ai_model/results?limit={limit}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка при получении списка результатов: {e}")
            sys.exit(1)
    
    def get_result_by_id(self, result_id: int) -> Dict:
        """Получает полную информацию о результате по ID"""
        url = f"{self.server_url}/api/v1/ai_model/results/{result_id}"
        
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка при получении результата {result_id}: {e}")
            return None
    
    def find_latest_batch_id(self, results: List[Dict]) -> Optional[str]:
        """Находит batch_id самого последнего батча"""
        if not results:
            return None
        
        # Получаем полную информацию о первом результате (самом свежем)
        first_result_id = results[0]['id']
        first_result = self.get_result_by_id(first_result_id)
        
        if not first_result:
            return None
        
        return first_result.get('batch_id')
    
    def download_batch_results(self, output_dir: Path):
        """Основная функция для загрузки результатов"""
        print("🚀 Начинаем загрузку результатов...")
        
        # Шаг 1: Получаем количество активных промптов
        prompts_count = self.get_active_prompts_count()
        print(f"📊 Количество активных промптов: {prompts_count}")
        
        # Шаг 2: Получаем список последних N результатов
        print(f"🔍 Запрашиваем последние {prompts_count} результатов...")
        results = self.get_latest_results(limit=prompts_count)
        
        if not results:
            print("⚠️  Нет доступных результатов")
            return
        
        print(f"✅ Получено {len(results)} результатов")
        
        # Шаг 3: Находим batch_id последнего батча
        latest_batch_id = self.find_latest_batch_id(results)
        
        if not latest_batch_id:
            print("❌ Не удалось определить batch_id последнего батча")
            return
        
        print(f"🎯 Batch ID последнего батча: {latest_batch_id}")
        
        # Шаг 4: Создаём директорию для результатов
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"📁 Результаты будут сохранены в: {output_dir.absolute()}")
        
        # Шаг 5: Загружаем и сохраняем результаты из последнего батча
        saved_count = 0
        
        for result_item in results:
            result_id = result_item['id']
            
            # Получаем полную информацию о результате
            full_result = self.get_result_by_id(result_id)
            
            if not full_result:
                continue
            
            # Проверяем, что результат относится к последнему батчу
            if full_result.get('batch_id') != latest_batch_id:
                continue
            
            # Проверяем, что результат завершён
            if full_result.get('status') != 'finished':
                print(f"⏭️  Пропускаем результат {result_id} (статус: {full_result.get('status')})")
                continue
            
            # Сохраняем результат в файл
            prompt_name = full_result.get('prompt_name', f'result_{result_id}')
            result_text = full_result.get('result_text', '')
            
            # Формируем имя файла (заменяем небезопасные символы)
            safe_filename = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in prompt_name)
            file_path = output_dir / f"{safe_filename}.md"
            
            # Записываем файл
            try:
                file_path.write_text(result_text, encoding='utf-8')
                print(f"✅ Сохранено: {file_path.name}")
                saved_count += 1
            except Exception as e:
                print(f"❌ Ошибка при сохранении {file_path.name}: {e}")
        
        print(f"\n🎉 Готово! Сохранено файлов: {saved_count}")


def main():
    parser = argparse.ArgumentParser(
        description='Загрузка результатов AI обработки с сервера'
    )
    parser.add_argument(
        '--server',
        required=True,
        help='URL сервера (например, http://185.130.224.177:8001)'
    )
    parser.add_argument(
        '--token',
        required=True,
        help='Токен для авторизации'
    )
    parser.add_argument(
        '--output-dir',
        default='results',
        help='Директория для сохранения результатов (по умолчанию: results/)'
    )
    
    args = parser.parse_args()
    
    # Создаём объект загрузчика
    downloader = ResultDownloader(args.server, args.token)
    
    # Запускаем загрузку
    output_dir = Path(args.output_dir)
    downloader.download_batch_results(output_dir)


if __name__ == '__main__':
    main()

