"""Перенос проекта со старой раскладки: файлы из `output/literature/` — в библиотеку.

Старый `lit.py` держал тексты в папке проекта под именами-идентификаторами
(`2107.12209v1.pdf`, `Shkalikov-rm9740.tex`). Перенос копирует каждый файл реестра в
библиотеку под именем «Авторы Год - Название», переносит текстовый слой и части
транскрипции, переписывает имена в реестре и вносит работы в опись. Старая папка не
трогается (`--move` переносит вместо копирования): её удаляет человек, сверив результат.
Повторный запуск ничего не портит: перенесённые строки пропускаются. `dry_run` только
сообщает, что было бы перенесено, и ничего не пишет.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from mathpaperlib import library, paths, registry, store


def _put(source: Path, target: Path, move: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if move:
        shutil.move(str(source), str(target))
    else:
        shutil.copy2(source, target)


def migrate_row(row: dict, old: Path, move: bool, dry_run: bool = False) -> str | None:
    """Переносит файлы одной строки; сообщение или None, если переносить нечего."""
    names = {field: row[field] for field in ('filename', 'tex') if row.get(field)}
    if not names:
        return None
    base = {key: value for key, value in row.items() if key not in library.FILES}
    stem = library.stem_for(base)
    if all(Path(name).stem == stem and not (old / name).exists() for name in names.values()):
        return None  # уже перенесено: имена новые, в старой папке под ними ничего нет
    old_stem = Path(names.get('filename') or names['tex']).stem
    moved = []
    for field, name in names.items():
        source, new = old / name, stem + Path(name).suffix
        target = paths.LIBRARY / new
        if source.exists():
            if target.exists() and store.sha256(target.read_bytes()) != store.sha256(source.read_bytes()):
                return f"{row['code']}: ОШИБКА — в библиотеке уже есть другой файл {new}; строка не перенесена"
            if not target.exists() and not dry_run:
                _put(source, target, move)
            moved.append(f'{name} → {new}')
        row[field] = new
    if dry_run:
        return f"{row['code']}: " + ('; '.join(moved) if moved else f'файлов в {old} нет, имена: {stem}')
    layer = old / (old_stem + '.txt')
    if layer.exists() and row.get('filename') and not paths.text_layer(row['filename']).exists():
        _put(layer, paths.text_layer(row['filename']), move)
    parts = old / 'parts' / old_stem
    if parts.is_dir() and not (paths.PARTS / stem).exists():
        shutil.copytree(parts, paths.PARTS / stem)
    if any((paths.LIBRARY / row[field]).exists() for field in names):
        library.remember(row)
    return f"{row['code']}: " + ('; '.join(moved) if moved else f'файлов в {old} нет, имена записаны: {stem}')


def migrate(source: str | None = None, move: bool = False, dry_run: bool = False) -> list[str]:
    """Переносит файлы проекта из старой папки (по умолчанию `output/literature`) в библиотеку."""
    old = Path(source).expanduser() if source else paths.project() / 'output' / 'literature'
    if not old.is_absolute():
        old = paths.project() / old
    if old.resolve() == paths.LIBRARY:
        raise SystemExit('Старая папка совпадает с библиотекой: переносить некуда.')
    rows, report = registry.load(), []
    for row in rows:
        before = dict(row)
        try:
            message = migrate_row(row, old, move, dry_run)
        except OSError as error:  # например, путь длиннее предела Windows: строка остаётся прежней
            row.clear()
            row.update(before)
            message = f"{row['code']}: ОШИБКА — {error}; строка не перенесена"
        if message:
            report.append(message)
            if not dry_run:
                registry.save(rows)
    if not report:
        return [f'Переносить нечего: файлы реестра уже в библиотеке {paths.LIBRARY}.']
    if dry_run:
        return report + ['Пробный запуск: файлы и реестр не изменены.']
    return report + [f'Библиотека: {paths.LIBRARY}. Старая папка {old} не тронута'
                     + (' (файлы перенесены)' if move else '; удалите её, сверив результат') + '.']
