"""Папка `inbox/`: PDF, скачанные вручную, опознаются, получают имя и ложатся в библиотеку.

Работа опознаётся по номеру arXiv в имени файла, по arXiv или DOI на первых страницах, либо
по идентификатору, который назвал человек (`--id`). Найденный идентификатор сверяется с
текстом: название работы из метаданных должно встретиться на первых страницах, иначе DOI
из списка литературы или колонтитула приписал бы файлу чужую работу. Не опознанный файл
остаётся в `inbox/` с объяснением. Опознанный переносится в библиотеку под именем
«Авторы Год - Название»; если в выбранном проекте работа есть без файла, PDF прикрепляется
к её строке реестра.
"""
from __future__ import annotations

import re
import urllib.error
from pathlib import Path

from mathpaperlib import idents, library, naming, papers, paths, store

FIRST_PAGES = 2


def first_text(path: Path, pages: int = FIRST_PAGES) -> str:
    import pymupdf as fitz
    with fitz.open(path) as doc:
        return '\n'.join(doc[number].get_text() for number in range(min(pages, len(doc))))


def words(text: str) -> list[str]:
    """Слова для сверки: без формул, переносов и регистра, длиной от четырёх букв."""
    text = re.sub(r'\$[^$]*\$', ' ', text or '')
    text = re.sub(r'-\s*\n\s*', '', text).lower()
    return [word for word in re.findall(r'[^\W\d_]{4,}', text)]


def title_matches(record: dict, text: str) -> bool:
    """Название (русское или английское) встречается на первых страницах: 60 % его слов есть в тексте."""
    present = set(words(text)) | set(words(naming.translit(text)))
    for title in (record.get('title'), record.get('title_en')):
        wanted = words(title or '')
        if len(wanted) < 2:
            continue
        if sum(word in present for word in wanted) >= 0.6 * len(wanted):
            return True
    return not any(len(words(title or '')) >= 2 for title in (record.get('title'), record.get('title_en')))


def attach_to_project(key_set: set[str], record: dict) -> str:
    """Прикрепляет файл к строке реестра выбранного проекта, у которой файла ещё нет."""
    if paths.ROOT is None:
        return ''
    from mathpaperlib import registry
    rows = registry.load(refresh=False)  # без подстановки из описи: видно, был ли файл у строки до inbox
    table = registry.known(rows)
    code = next((table[key] for key in key_set if key in table), None)
    if not code:
        return ''
    row = registry.by_code(rows, code)
    if row.get('filename') == record.get('filename'):
        return ''
    if row.get('filename'):
        return f'; в проекте у {code} другой файл, {row["filename"]}'
    library.adopt(row)
    registry.save(rows)
    return f'; прикреплён к {code}'


def take(path: Path, ident: str | None = None) -> tuple[str, str | None]:
    """Разбирает один файл: сообщение и имя работы в библиотеке (None — файл не взят)."""
    data = path.read_bytes()
    if data[:5] != b'%PDF-':
        return f'{path.name}: не PDF, пропущен', None
    text = first_text(path)
    found = ident or idents.in_text(text, path.stem)
    if not found:
        return (f'{path.name}: не опознан — на первых страницах нет arXiv и DOI; '
                f'назовите работу: lit inbox "{path}" --id <DOI или arXiv>'), None
    try:
        key, record = papers.resolve(found)
    except (ValueError, ConnectionError, urllib.error.URLError) as error:
        return f'{path.name}: {found} — ОШИБКА метаданных: {error}', None
    record.pop('full_text', None)
    if not ident and not title_matches(record, text):
        return (f'{path.name}: в тексте найден {found} («{record["title"][:80]}»), но название на первых '
                f'страницах не встречается; если это та работа: lit inbox "{path}" --id {found}'), None
    entries = library.load()
    entry = library.owner(entries, record)
    digest = store.sha256(data)
    if entry and entry.get('sha256') == digest:
        keys = idents.keys(record)
        return f'{path.name}: уже в библиотеке как «{library.stem(entry)}»' + attach_to_project(keys, entry), \
            library.stem(entry)
    if entry and entry.get('filename'):
        return (f'{path.name}: в библиотеке уже есть другой PDF этой работы, «{entry["filename"]}»; '
                'файл оставлен в inbox для сверки версий'), None
    library.adopt(record)  # LaTeX этой работы уже в библиотеке: PDF получит то же имя
    target = store.store_pdf(record, data)
    note = attach_to_project(idents.keys(record), record)
    return f'{path.name} → {target.name}' + note, library.stem(record)


def inbox(files: list[str] | None = None, ident: str | None = None) -> list[str]:
    """Разбирает `inbox/` (или названные файлы); взятые файлы из inbox удаляются, чужие — копируются."""
    from mathpaperlib import search
    paths.INBOX.mkdir(parents=True, exist_ok=True)
    chosen = [Path(name).expanduser() for name in files] if files else \
        sorted(path for path in paths.INBOX.iterdir() if path.is_file() and path.suffix.lower() == '.pdf')
    if ident and len(chosen) != 1:
        raise SystemExit('--id называет одну работу: укажите ровно один файл.')
    if not chosen:
        return [f'В {paths.INBOX} нет PDF.']
    report, taken = [], []
    for path in chosen:
        if not path.is_file():
            report.append(f'{path}: файла нет')
            continue
        message, name = take(path, ident)
        report.append(message)
        if name:
            taken.append(name)
            if path.resolve().parent == paths.INBOX.resolve():
                path.unlink()
    if taken:
        # в проекте индексируются его работы (прикреплённое попадёт туда), без проекта — взятые файлы
        report += search.index(None if paths.ROOT else taken)
    return report
