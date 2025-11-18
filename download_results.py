#!/usr/bin/env python3
"""
Скрипт для скачивания объединенной документации из последнего батча
Использование: python download_results.py
"""
import requests
import sys
from pathlib import Path
from datetime import datetime

# Настройки API
API_URL = "http://185.130.224.177:8001"
API_TOKEN = "your_admin_token_here"  # Не используется если авторизация отключена

def get_latest_batch_id():
    """Получает ID последнего батча"""
    try:
        # Получаем информацию о количестве активных промптов
        response = requests.get(
            f"{API_URL}/api/v1/prompts/",
            params={"is_active": True},
            headers={"Authorization": f"Bearer {API_TOKEN}"}
        )
        response.raise_for_status()
        prompts = response.json()
        
        print(f"Найдено активных промптов: {len(prompts)}")
        
        # Здесь можно было бы получить список батчей, но такого endpoint нет
        # Поэтому просим пользователя ввести batch_id вручную
        return None
        
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении информации о промптах: {e}")
        return None

def get_batch_status(batch_id):
    """Получает статус батча"""
    try:
        response = requests.get(
            f"{API_URL}/api/v1/ai_model/batch/{batch_id}"
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка при получении статуса батча: {e}")
        return None

def download_merged_result(batch_id, output_dir="results"):
    """Скачивает объединенный результат батча"""
    print(f"\nПолучение информации о батче {batch_id}...")
    
    batch_data = get_batch_status(batch_id)
    if not batch_data:
        print("Не удалось получить информацию о батче")
        return False
    
    print(f"Статус батча: {batch_data['status']}")
    print(f"Завершено задач: {batch_data['completed_jobs']}/{batch_data['total_jobs']}")
    print(f"Ошибок: {batch_data['failed_jobs']}")
    
    if not batch_data.get('has_merged_result'):
        print("\n❌ Объединенный результат еще не готов")
        print("Батч должен быть полностью завершен для создания объединенного файла")
        return False
    
    merged_job_id = batch_data.get('merged_job_id')
    if not merged_job_id:
        print("\n❌ ID объединенного результата не найден")
        return False
    
    print(f"\n✅ Объединенный результат найден (ID: {merged_job_id})")
    
    # Скачиваем объединенный результат
    try:
        response = requests.get(
            f"{API_URL}/api/v1/ai_model/jobs/{merged_job_id}"
        )
        response.raise_for_status()
        result_data = response.json()
        
        # Создаем директорию для результатов
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)
        
        # Формируем имя файла
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"documentation_{batch_id[:8]}_{timestamp}.md"
        filepath = output_path / filename
        
        # Сохраняем файл
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(result_data['result_text'])
        
        print(f"\n✅ Документация сохранена: {filepath}")
        
        # Выводим статистику
        stats = result_data.get('statistics', {})
        if stats:
            print(f"\n📊 Статистика:")
            print(f"   - Токенов (prompt): {stats.get('prompt_tokens', 0):,}")
            print(f"   - Токенов (completion): {stats.get('completion_tokens', 0):,}")
            print(f"   - Всего токенов: {stats.get('total_tokens', 0):,}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Ошибка при скачивании результата: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Ошибка при сохранении файла: {e}")
        return False

def main():
    print("=" * 60)
    print("Скачивание объединенной документации")
    print("=" * 60)
    
    # Получаем batch_id
    if len(sys.argv) > 1:
        batch_id = sys.argv[1]
    else:
        batch_id = input("\nВведите batch_id: ").strip()
    
    if not batch_id:
        print("❌ Batch ID не указан")
        sys.exit(1)
    
    # Скачиваем результат
    success = download_merged_result(batch_id)
    
    if success:
        print("\n✅ Готово!")
    else:
        print("\n❌ Не удалось скачать документацию")
        sys.exit(1)

if __name__ == "__main__":
    main()
