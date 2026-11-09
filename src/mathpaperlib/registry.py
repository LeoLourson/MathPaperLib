"""Реестр источников проекта: коды `S…`, связь с проектом, описания, карточки.

Реестр — единственное место, где источник получает код `S…`; номера не переиспользуются.
Файлы работ лежат в библиотеке (`library`, `store`), а строка реестра хранит их имена и
копию метаданных: каталог проекта читается без библиотеки. Теорема источника становится
посылкой доказательства только после карточки и её сверки с PDF, а не после добавления.

Здесь же считается единственный набор фактов о подборке (`facts`): коды реестра, коды с
карточкой и коды с карточкой, сверенной по PDF. Каталог и проверки проекта выносят
суждения по нему, а не по своим правилам.

Описание источника (`about`) — тоже поле реестра: `kind`, `object`, `results`, `methods`,
`related`, `keywords`, `basis`, `date`. Его разбирает `about_of`, а проверяет `check_about`.
"""
from __future__ import annotations

import json
import re
import urllib.error
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from mathpaperlib import idents, library, papers, paths, store, web


def load(refresh: bool = True) -> list[dict]:
    """Строки реестра проекта; файлы, появившиеся в библиотеке позже, дописываются в них (refresh)."""
    paths.project()
    rows = json.loads(paths.REGISTRY.read_text(encoding='utf-8')) if paths.REGISTRY.exists() else []
    return library.refresh(rows) if refresh else rows


def save(rows: list[dict]) -> None:
    paths.project()
    rows.sort(key=lambda row: int(row['code'][1:]))
    paths.REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    paths.REGISTRY.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def next_code(rows: list[dict]) -> str:
    return 'S%d' % (max((int(row['code'][1:]) for row in rows), default=0) + 1)


def header(path: Path) -> dict:
    """Поля шапки `---`-записи (карточки): ключ: значение."""
    text = path.read_text(encoding='utf-8').replace('\r\n', '\n')
    if not text.startswith('---\n'):
        return {}
    meta = {}
    for line in text[4:].partition('\n---\n')[0].split('\n'):
        key, colon, value = line.partition(':')
        if colon and key.strip() and not key.lstrip().startswith('#'):
            meta[key.strip()] = value.strip()
    return meta


@dataclass
class Facts:
    """Факты подборки, по которым выносят суждения о источниках."""
    codes: set[str]      # коды источников реестра
    carded: set[str]     # коды, у которых есть карточка
    verified: set[str]   # коды, у которых карточка сверена с PDF


def facts() -> Facts:
    """Единственное правило: есть ли у источника карточка и сверена ли она.

    Карточка — файл `S*.md` в папке карточек (`[sources] cards`, по умолчанию
    `sources/cards`) либо заголовок в едином `sources/results.md`: обе раскладки поддержаны.
    Отметку `verified` даёт только шапка файла карточки.
    """
    codes = {row['code'] for row in load()}
    files = sorted(paths.CARDS.glob('S*.md')) if paths.CARDS.exists() else []
    named = {path: re.match(r'S\d+', path.stem) for path in files}
    carded = {match.group(0) for match in named.values() if match}
    verified = {match.group(0) for path, match in named.items() if match and header(path).get('verified')}
    if paths.RESULTS.exists():
        headings = ' '.join(re.findall(r'^## (.*)$', paths.RESULTS.read_text(encoding='utf-8'), re.M))
        carded |= set(re.findall(r'S\d+', headings))
    return Facts(codes, carded, verified)


# Описание источника — поле `about` записи реестра. Оно говорит, что в работе есть и на чём
# это прочитано; поля перечислены здесь, потому что их проверяет реестр, а не каталог.
KINDS = ('статья', 'краткое сообщение', 'обзор', 'книга', 'диссертация')
BASES = ('полный текст', 'аннотация, введение и формулировки', 'аннотация', 'название и метаданные')
UNFINISHED = re.compile(r'(?i)нужно сверить|нужно уточнить|предстоит|todo|\?\?')


def about_of(given: dict) -> dict:
    """Описание источника из присланного JSON: известные поля и дата составления."""
    about = {key: given[key] for key in ('kind', 'object', 'results', 'methods', 'related', 'keywords', 'basis')
             if given.get(key)}
    about['date'] = given.get('date') or date.today().isoformat()
    return about


def check_about(row: dict, about: dict, rows: list[dict]) -> list[str]:
    """Замечания к описанию источника; пустой список — описание принято."""
    notes, codes = [], {other['code'] for other in rows}
    if about.get('kind') not in KINDS:
        notes.append(f"kind: одно из {', '.join(KINDS)}")
    if about.get('basis') not in BASES:
        notes.append(f"basis: одно из «{'», «'.join(BASES)}»")
    try:
        date.fromisoformat(about.get('date') or '')
    except (TypeError, ValueError):
        notes.append('date: дата в виде ГГГГ-ММ-ДД')
    if len(web.squash(about.get('object'))) < 60:
        notes.append('object: что изучается — оператор, пространство, краевые условия, класс данных; от 60 знаков')
    lists = {key: about.get(key) or [] for key in ('results', 'methods', 'related', 'keywords')}
    for key, value in lists.items():
        if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
            notes.append(f'{key}: список непустых строк')
            lists[key] = []
    read = about.get('basis') in BASES[:2]
    if read and not lists['results']:
        notes.append('results: главные утверждения с номером и страницей, если они есть в тексте')
    if read and not lists['methods']:
        notes.append('methods: чем доказано, по одному методу в строке')
    if len(lists['keywords']) < 3:
        notes.append('keywords: не меньше трёх; фамилии и термины по-русски и по-английски')
    for item in lists['related']:
        match = re.match(r'(S\d+)\b', item)
        if not match or match.group(1) not in codes or match.group(1) == row['code']:
            notes.append(f'related: строка начинается с кода другого источника реестра — «{item[:40]}»')
    whole = ' '.join([about.get('object') or ''] + [item for value in lists.values() for item in value])
    if UNFINISHED.search(whole):
        notes.append('описание содержит отложенную проверку: запиши прочитанное, а не план чтения')
    for other in rows:
        if other['code'] != row['code'] \
                and web.squash((other.get('about') or {}).get('object')) == web.squash(about.get('object')):
            notes.append(f"object дословно совпадает с {other['code']}")
    return notes


def known(rows: list[dict]) -> dict[str, str]:
    """Код источника по ключам arxiv:…, mathnet:…, doi:…"""
    return {key: row['code'] for row in rows for key in idents.keys(row)}


def by_code(rows: list[dict], code: str) -> dict:
    for row in rows:
        if row['code'] == code.upper():
            return row
    raise SystemExit(f'В реестре нет источника {code}.')


def selected(rows: list[dict], codes: list[str] | None) -> list[dict]:
    """Записи по списку кодов. Неизвестный код — отказ, а не пустая выборка."""
    if not codes:
        return rows
    found = {row['code']: row for row in rows}
    unknown = [code for code in codes if code.upper() not in found]
    if unknown:
        raise SystemExit(f"В реестре нет источников: {', '.join(unknown)}.")
    return [found[code.upper()] for code in codes]


def obtain(record: dict) -> str:
    """Полный текст работы: из библиотеки, если он там есть, иначе скачивание. Что получено — словами."""
    if library.adopt(record):
        return 'из библиотеки: ' + library.stem(record)
    if idents.arxiv_id(record):
        return 'LaTeX-исходник' if store.store_eprint(record) == 'tex' else 'на arXiv только PDF'
    if record.get('mathnet'):
        if not record.get('full_text'):
            return f'полный текст на MathNet закрыт; положите PDF в {paths.INBOX} или прикрепите командой attach'
        store.store_pdf(record, web.http_get(record['pdf_url']))
        got = f"PDF, {record['pages']} стр." + ('' if record['text_layer'] else ', скан без текстового слоя')
        return got + '; LaTeX нет — транскрипция по страницам (pages, tex)'
    if record.get('pdf_url'):
        try:
            store.store_pdf(record, web.http_get(record['pdf_url']))
            return f"PDF открытого доступа, {record['pages']} стр."
        except (ValueError, ConnectionError, urllib.error.URLError) as error:
            return f'только описание (открытый PDF не получен: {error})'
    return f'только описание; PDF положите в {paths.INBOX} или прикрепите командой attach'


def add(idents_: list[str], role: str | None) -> list[str]:
    """Добавляет работы по идентификаторам arXiv, MathNet и DOI: в библиотеку и, в проекте, в реестр.

    Каталог после правки реестра пересобирает фасад `lit`, одинаково для командной строки и MCP.
    """
    if paths.ROOT is None:
        return _add_to_library(idents_)
    if not role:
        raise SystemExit('В проекте нужна связь с проектом (role): одна-две фразы.')
    from mathpaperlib import search
    rows, report, added = load(), [], []
    for ident in idents_:
        try:
            key, meta = papers.resolve(ident)
            if key in known(rows):
                report.append(f'{known(rows)[key]}: {key} уже в реестре')
                continue
            row = dict(code=next_code(rows), **meta, role=role)
            got = obtain(row)
        except (ValueError, ConnectionError, urllib.error.URLError) as error:
            report.append(f'{ident}: ОШИБКА — {error}')
            continue
        row.pop('full_text', None)
        rows.append(row)
        save(rows)
        added.append(row['code'])
        report.append(f"{row['code']}: {row['title']} ({row['version']}) — {got}")
    if added:
        report.append(f"Описания нет у {', '.join(added)}: прочитай текст и запиши его командой annotate.")
    return report + (search.index(added) if added else [])


def _add_to_library(idents_: list[str]) -> list[str]:
    """Без проекта: работа ложится в библиотеку под своим именем, реестра нет."""
    from mathpaperlib import search
    report, stems = [], []
    for ident in idents_:
        try:
            _, record = papers.resolve(ident)
            got = obtain(record)
        except (ValueError, ConnectionError, urllib.error.URLError) as error:
            report.append(f'{ident}: ОШИБКА — {error}')
            continue
        if library.has_files(record):
            stems.append(library.stem(record))
            report.append(f'{library.stem(record)} — {got}')
        else:
            report.append(f"{record['title']} ({record['version']}) — {got}; в библиотеку не положено")
    return report + (search.index(stems) if stems else [])


def add_file(source: str, title: str, authors: str, version: str, url: str, role: str | None,
             year: str = '') -> list[str]:
    """Добавляет работу без arXiv, MathNet и DOI: PDF или LaTeX по ссылке либо из локального файла."""
    from mathpaperlib import search
    record = dict(authors=authors, title=title, year=year, version=version, url=url)
    if paths.ROOT is None:
        got = _attach(record, source, 'local')
        return [f'{library.stem(record)} — {got}'] + search.index([library.stem(record)])
    rows = load()
    row = dict(code=next_code(rows), **record, role=role or '')
    got = _attach(row, source, 'local')
    rows.append(row)
    save(rows)
    return [f"{row['code']}: {title} — {got}, {library.stem(row)}"] + search.index([row['code']])


def _attach(record: dict, source: str, origin: str) -> str:
    data = store.read_source(source)
    if data[:5] == b'%PDF-':
        if re.match(r'https?://', source):
            record['pdf_url'] = source
        record.pop('sha256', None)
        store.store_pdf(record, data)
        return 'PDF'
    store.store_tex(record, papers.decode(data), origin)
    return 'LaTeX'


def attach(code: str, source: str, origin: str = 'local') -> list[str]:
    """Прикрепляет к записи реестра PDF или LaTeX, полученный вручную."""
    from mathpaperlib import search
    rows = load()
    row = by_code(rows, code)
    got = _attach(row, source, origin)
    save(rows)
    return [f"{row['code']}: прикреплён {got}: {library.stem(row)}"] + search.index([row['code']])
