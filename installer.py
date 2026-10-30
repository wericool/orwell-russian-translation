"""Orwell Russian preview installer; changes are version checked and reversible."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bsdiff4

BASE = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
digest = lambda data: hashlib.sha256(data).hexdigest()

def run(action, game, check_only=False):
    game = Path(game).expanduser().resolve()
    data_dir = game / 'Orwell_Data'
    if not (game / 'Orwell.exe').is_file() or not data_dir.is_dir():
        raise ValueError('Не найдены Orwell.exe и папка Orwell_Data.')
    running = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Orwell.exe', '/NH'], capture_output=True, text=True, errors='replace', check=True)
    if 'orwell.exe' in running.stdout.lower() and not check_only:
        raise ValueError('Закройте Orwell перед установкой или восстановлением.')
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1:
        raise ValueError('Неподдерживаемый формат сборки.')
    backup = data_dir / '.orwell-rus-backup'
    records, paths = [], set()
    for row in manifest['files']:
        rel = Path(row['path'])
        if rel.is_absolute() or '..' in rel.parts:
            raise ValueError('Некорректный путь в сборке.')
        target = (data_dir / rel).resolve()
        if not target.is_relative_to(data_dir.resolve()) or target in paths:
            raise ValueError('Некорректный или повторный путь в сборке.')
        paths.add(target)
        old = target.read_bytes()
        wanted = row['original_sha256'] if action == 'install' else row['patched_sha256']
        if digest(old) != wanted:
            raise ValueError(f'Несовместимая или изменённая игра: {rel}. Ничего не записано.')
        if action == 'install':
            patch_path = BASE / 'patches' / row['patch']
            if patch_path.parent.resolve() != (BASE / 'patches').resolve():
                raise ValueError('Некорректный путь к патчу.')
            delta = patch_path.read_bytes()
            if digest(delta) != row['patch_sha256']:
                raise ValueError(f'Повреждён файл исправления: {row["patch"]}')
            result = bsdiff4.patch(old, delta)
            if digest(result) != row['patched_sha256']:
                raise ValueError(f'Не удалось проверить результат: {rel}')
        else:
            saved = backup / rel
            result = saved.read_bytes()
            if digest(result) != row['original_sha256']:
                raise ValueError(f'Повреждена резервная копия: {rel}')
        records.append((rel, target, old, result))
    if check_only:
        print(f'Проверено файлов: {len(records)}. Изменения не записывались.')
        return
    if action == 'install':
        for rel, _, old, _ in records:
            dest = backup / rel
            if backup.exists() and dest.exists():
                if digest(dest.read_bytes()) != digest(old):
                    raise ValueError(f'Существующая резервная копия не совпадает: {rel}')
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(old)
            if digest(dest.read_bytes()) != digest(old):
                raise OSError(f'Не удалось проверить резервную копию: {rel}')
    written = []
    try:
        for rel, target, old, result in records:
            temp = target.with_name(target.name + '.orwell-rus-tmp')
            if temp.exists():
                raise FileExistsError(f'Временный файл уже существует: {temp}')
            temp.write_bytes(result)
            if digest(temp.read_bytes()) != digest(result):
                raise OSError(f'Ошибка проверки: {rel}')
            os.replace(temp, target)
            written.append((target, old))
    except Exception:
        for target, old in reversed(written):
            temp = target.with_name(target.name + '.orwell-rus-restore')
            temp.write_bytes(old)
            os.replace(temp, target)
        raise
    print('Готово. Резервная копия сохранена в Orwell_Data/.orwell-rus-backup.')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--game')
    parser.add_argument('--action', choices=['install', 'restore'])
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    try:
        game = args.game or input('Путь к папке игры Orwell: ').strip().strip('"')
        action = args.action or {'1': 'install', '2': 'restore'}.get(input('1 — установить, 2 — восстановить оригинал: ').strip())
        if not action:
            raise ValueError('Неизвестное действие.')
        run(action, game, args.check_only)
    except Exception as error:
        print('Ошибка:', error)
        if not args.game:
            input('Нажмите Enter для выхода...')
        return 1
    if not args.game:
        input('Нажмите Enter для выхода...')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
