"""Опись библиотеки `library.json`: какие работы лежат в библиотеке и под какими именами.

Запись описи — метаданные работы (авторы, название, год, версия, ссылки, идентификаторы)
и её файлы: PDF (`filename`, `pages`, `sha256`, `text_layer`) и LaTeX (`tex`, `tex_origin`).
Имя файла выдаётся один раз, при первом сохранении, из метаданных (`naming.stem`) и дальше
не меняется. Реестр проекта хранит копию полей записи, а файлы берёт отсюда: работа,
добавленная в двух проектах, лежит в библиотеке одним файлом.
"""
from __future__ import annotations

import json
from pathlib import Path

from mathpaperlib import idents, naming, paths

META = ('authors', 'title', 'title_en', 'year', 'version', 'url', 'pdf_url', 'doi', 'doi_en', 'mathnet')
FILES = ('filename', 'pages', 'sha256', 'text_layer', 'tex', 'tex_origin', 'tex_date', 'eprint', 'eprint_sha256')


def load() -> list[dict]:
    if not paths.LIBRARY_JSON.exists():
        return []
    return json.loads(paths.LIBRARY_JSON.read_text(encoding='utf-8'))


def save(entries: list[dict]) -> None:
    entries.sort(key=lambda entry: (entry.get('filename') or entry.get('tex') or '').lower())
    paths.LIBRARY.mkdir(parents=True, exist_ok=True)
    temporary = paths.LIBRARY_JSON.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temporary.replace(paths.LIBRARY_JSON)


def stem(entry: dict) -> str:
    return Path(entry.get('filename') or entry.get('tex') or '').stem


def has_files(entry: dict) -> bool:
    return bool(entry.get('filename') or entry.get('tex'))


def owner(entries: list[dict], record: dict) -> dict | None:
    """Запись описи для записи реестра: по общему файлу, а без файлов — по идентификатору."""
    for entry in entries:
        for field in ('filename', 'tex'):
            if record.get(field) and entry.get(field) and record[field].lower() == entry[field].lower():
                return entry
    if record.get('filename') or record.get('tex'):
        return None
    wanted = idents.keys(record)
    return next((entry for entry in entries if has_files(entry) and wanted & idents.keys(entry)), None)


def known() -> dict[str, str]:
    """Имя работы в библиотеке по её ключу: для пометок в выдаче поиска."""
    table = {}
    for entry in load():
        for key in idents.keys(entry):
            table.setdefault(key, stem(entry))
    return table


def taken(entries: list[dict]) -> set[str]:
    """Занятые основы имён: из описи и с диска (файлы, положенные вручную, тоже считаются)."""
    names = {stem(entry).lower() for entry in entries if has_files(entry)}
    if paths.LIBRARY.exists():
        names |= {path.stem.lower() for path in paths.LIBRARY.iterdir() if path.is_file()}
    return names


def stem_for(record: dict) -> str:
    """Основа имени файлов работы: уже выданная, выданная той же работе в описи или новая."""
    for field in ('filename', 'tex'):
        if record.get(field):
            return Path(record[field]).stem
    entries = load()
    entry = owner(entries, record)
    if entry:
        return stem(entry)
    return naming.numbered(naming.stem(record), taken(entries))


def remember(record: dict) -> dict:
    """Вносит в опись метаданные и файлы записи; возвращает запись описи."""
    entries = load()
    entry = owner(entries, record)
    if entry is None:
        entry = {}
        entries.append(entry)
    for field in META + FILES:
        if record.get(field) not in (None, ''):
            entry[field] = record[field]
    save(entries)
    return entry


def adopt(record: dict) -> bool:
    """Берёт в запись реестра файлы работы, уже лежащей в библиотеке; True — файлы есть."""
    entry = owner(load(), record)
    if not entry:
        return False
    for field in FILES:
        if entry.get(field) not in (None, '') and not record.get(field):
            record[field] = entry[field]
    return True


def refresh(rows: list[dict]) -> list[dict]:
    """Дополняет записи реестра файлами, появившимися в описи после их добавления."""
    entries = load()
    for row in rows:
        entry = owner(entries, row)
        if entry:
            for field in FILES:
                if entry.get(field) not in (None, '') and not row.get(field):
                    row[field] = entry[field]
    return rows


def find(ref: str) -> dict:
    """Запись описи по идентификатору (arXiv, mathnet:…, DOI) или по началу имени файла."""
    entries = load()
    try:
        key = idents.key_of(*idents.classify(ref))
        found = [entry for entry in entries if key in idents.keys(entry)]
    except ValueError:
        found = []
    if not found:
        wanted = ref.strip().lower()
        found = [entry for entry in entries if stem(entry).lower().startswith(wanted)]
    if len(found) == 1:
        return found[0]
    if not found:
        raise SystemExit(f'В библиотеке нет работы «{ref}».')
    raise SystemExit(f'«{ref}» подходит к нескольким работам: ' + '; '.join(stem(entry) for entry in found[:6]))


def listing() -> str:
    """Работы библиотеки: имя, идентификаторы, что есть из файлов."""
    out = []
    for entry in load():
        have = [kind for kind, field in (('PDF', 'filename'), ('LaTeX', 'tex')) if entry.get(field)]
        names = sorted(idents.keys(entry))
        out.append(f"{stem(entry)} · {', '.join(have) or 'файлов нет'}" + (f" · {', '.join(names)}" if names else ''))
    head = f'Библиотека {paths.LIBRARY}: работ {len(out)}.'
    return '\n'.join([head] + out)
