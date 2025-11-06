#!/usr/bin/env python3
"""
Repository Code Exporter

Скрипт для экспорта всего кода из git-репозитория в один txt файл
с учетом исключений из .gitignore и JSON конфига.
"""

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Set, List, Dict

import git
import pathspec


class RepoExporter:
    """Класс для экспорта кода репозитория в текстовый файл."""
    
    def __init__(self, config_path: str):
        """
        Инициализация экспортера.
        
        Args:
            config_path: Путь к JSON файлу с конфигурацией исключений
        """
        self.config = self._load_config(config_path)
        self.gitignore_spec = None
        
    def _load_config(self, config_path: str) -> Dict:
        """
        Загрузка конфигурации из JSON файла.
        
        Args:
            config_path: Путь к JSON файлу
            
        Returns:
            Словарь с конфигурацией
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Валидация структуры конфига
            required_keys = ['exclude_patterns', 'exclude_directories', 'exclude_files']
            for key in required_keys:
                if key not in config:
                    config[key] = []
                    
            return config
        except FileNotFoundError:
            print(f"Ошибка: Файл конфигурации '{config_path}' не найден", file=sys.stderr)
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Ошибка: Неверный формат JSON в файле '{config_path}': {e}", file=sys.stderr)
            sys.exit(1)
    
    def _load_gitignore(self, repo_path: Path) -> None:
        """
        Загрузка и парсинг .gitignore из репозитория.
        
        Args:
            repo_path: Путь к клонированному репозиторию
        """
        gitignore_path = repo_path / '.gitignore'
        
        if gitignore_path.exists():
            try:
                with open(gitignore_path, 'r', encoding='utf-8') as f:
                    patterns = f.read()
                self.gitignore_spec = pathspec.PathSpec.from_lines(
                    pathspec.patterns.GitWildMatchPattern,
                    patterns.splitlines()
                )
                print(f"✓ Загружен .gitignore с {len(self.gitignore_spec.patterns)} паттернами")
            except Exception as e:
                print(f"Предупреждение: Не удалось загрузить .gitignore: {e}", file=sys.stderr)
                self.gitignore_spec = None
        else:
            print("Файл .gitignore не найден в репозитории")
            self.gitignore_spec = None
    
    def _should_exclude_path(self, path: Path, repo_path: Path) -> bool:
        """
        Проверка, должен ли путь быть исключен.
        
        Args:
            path: Проверяемый путь
            repo_path: Корневой путь репозитория
            
        Returns:
            True если путь должен быть исключен
        """
        relative_path = path.relative_to(repo_path)
        relative_str = str(relative_path)
        
        # Всегда исключаем .git
        if '.git' in relative_path.parts:
            return True
        
        # Проверка по .gitignore
        if self.gitignore_spec and self.gitignore_spec.match_file(relative_str):
            return True
        
        # Проверка по директориям из конфига
        for exclude_dir in self.config['exclude_directories']:
            exclude_dir = exclude_dir.rstrip('/')
            if exclude_dir in relative_path.parts:
                return True
        
        # Проверка по файлам из конфига
        if relative_str in self.config['exclude_files']:
            return True
        
        # Проверка по паттернам из конфига
        config_spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern,
            self.config['exclude_patterns']
        )
        if config_spec.match_file(relative_str):
            return True
        
        return False
    
    def _is_binary_file(self, file_path: Path) -> bool:
        """
        Проверка, является ли файл бинарным.
        
        Args:
            file_path: Путь к файлу
            
        Returns:
            True если файл бинарный
        """
        try:
            with open(file_path, 'rb') as f:
                chunk = f.read(8192)
                # Проверяем наличие null-байтов
                if b'\x00' in chunk:
                    return True
            return False
        except Exception:
            return True
    
    def _collect_files(self, repo_path: Path) -> List[Path]:
        """
        Сбор всех файлов для экспорта.
        
        Args:
            repo_path: Путь к репозиторию
            
        Returns:
            Список путей к файлам
        """
        files = []
        
        for root, dirs, filenames in os.walk(repo_path):
            root_path = Path(root)
            
            # Фильтрация директорий на месте
            dirs[:] = [
                d for d in dirs 
                if not self._should_exclude_path(root_path / d, repo_path)
            ]
            
            # Сбор файлов
            for filename in filenames:
                file_path = root_path / filename
                
                if not self._should_exclude_path(file_path, repo_path):
                    if not self._is_binary_file(file_path):
                        files.append(file_path)
        
        return sorted(files)
    
    def export_repository(self, repo_url: str, output_file: str) -> None:
        """
        Экспорт репозитория в текстовый файл.
        
        Args:
            repo_url: URL git-репозитория
            output_file: Путь к выходному файлу
        """
        temp_dir = None
        
        try:
            # Создание временной директории
            temp_dir = tempfile.mkdtemp(prefix='repo_export_')
            repo_path = Path(temp_dir)
            
            print(f"Клонирование репозитория: {repo_url}")
            print(f"Временная директория: {temp_dir}")
            
            # Клонирование репозитория
            try:
                git.Repo.clone_from(repo_url, repo_path, depth=1)
                print("✓ Репозиторий успешно склонирован")
            except git.GitCommandError as e:
                print(f"Ошибка при клонировании репозитория: {e}", file=sys.stderr)
                sys.exit(1)
            
            # Загрузка .gitignore
            self._load_gitignore(repo_path)
            
            # Сбор файлов
            print("\nСбор файлов для экспорта...")
            files = self._collect_files(repo_path)
            print(f"✓ Найдено файлов для экспорта: {len(files)}")
            
            # Экспорт в файл
            print(f"\nЭкспорт в файл: {output_file}")
            exported_count = 0
            skipped_count = 0
            
            with open(output_file, 'w', encoding='utf-8') as out:
                for file_path in files:
                    relative_path = file_path.relative_to(repo_path)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Запись заголовка файла
                        out.write(f"=== {relative_path} ===\n")
                        out.write(content)
                        
                        # Добавляем перенос строки если файл не заканчивается на \n
                        if content and not content.endswith('\n'):
                            out.write('\n')
                        
                        # Запись разделителя
                        out.write("---\n")
                        
                        exported_count += 1
                        
                    except UnicodeDecodeError:
                        print(f"Предупреждение: Не удалось прочитать файл {relative_path} (encoding issue)", 
                              file=sys.stderr)
                        skipped_count += 1
                    except Exception as e:
                        print(f"Предупреждение: Ошибка при обработке файла {relative_path}: {e}", 
                              file=sys.stderr)
                        skipped_count += 1
            
            print(f"\n✓ Экспорт завершен!")
            print(f"  - Экспортировано файлов: {exported_count}")
            if skipped_count > 0:
                print(f"  - Пропущено файлов: {skipped_count}")
            print(f"  - Выходной файл: {output_file}")
            
        finally:
            # Удаление временной директории
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"\n✓ Временная директория удалена")
                except Exception as e:
                    print(f"\nПредупреждение: Не удалось удалить временную директорию {temp_dir}: {e}", 
                          file=sys.stderr)


def main():
    """Главная функция."""
    parser = argparse.ArgumentParser(
        description='Экспорт кода из git-репозитория в текстовый файл',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:
  %(prog)s https://github.com/user/repo config.json
  %(prog)s https://github.com/user/repo config.json -o output.txt
  %(prog)s git@github.com:user/repo.git /path/to/config.json -o result.txt
        """
    )
    
    parser.add_argument(
        'repo_url',
        help='URL git-репозитория (https или ssh)'
    )
    
    parser.add_argument(
        'config',
        help='Путь к JSON файлу с конфигурацией исключений'
    )
    
    parser.add_argument(
        '-o', '--output',
        default='repo_export.txt',
        help='Путь к выходному текстовому файлу (по умолчанию: repo_export.txt)'
    )
    
    args = parser.parse_args()
    
    # Создание экспортера и выполнение экспорта
    exporter = RepoExporter(args.config)
    exporter.export_repository(args.repo_url, args.output)


if __name__ == '__main__':
    main()

