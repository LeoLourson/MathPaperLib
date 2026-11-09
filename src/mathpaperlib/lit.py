"""MathPaperLib: библиотека статей для агентов — поиск работ, скачивание, имена файлов, поиск по текстам.

Модуль — единственный вход: командная строка `lit` и MCP-сервер (`lit mcp`) зовут его
функции, поэтому политика одна для всех входов: после правки реестра каталог проекта
пересобирается. Остальные модули заняты каждый своим делом (`web`, `papers`, `idents`,
`library`, `store`, `registry`, `catalog`, `search`, `tex`, `inbox`, `migrate`).

Библиотека — общая папка с работами под именами «Авторы Год - Название» (`~/Literature`,
`MATHPAPERLIB_HOME` или `[sources] library` в project.toml). Проект — каталог с реестром
`sources/papers.json`: там коды S…, связь с проектом, описания и карточки.

С чего начать (веб-поиск — последнее средство):
  find "запрос" -n 15              zbMATH + arXiv (режим по умолчанию)
  find "запрос" --in all           zbMATH + arXiv + Crossref + OpenAlex
  find "запрос" --in mathnet       журналы Math-Net.Ru (Crossref, префикс 10.4213)
  doi 10.3934/math.2026892         журнал, том, страницы, авторы, аннотация, открытый PDF
  cites S2 [--refs]                кто цитирует источник / его список литературы
  add 2107.12209 mathnet:rm9740 10.1070/RM9740 --role "…"   в библиотеку и в реестр проекта
  inbox                            разобрать PDF, положенные в inbox/ библиотеки
  search "запрос"; show N          поиск по полным текстам
  annotate файл.json; audit        описания источников

Порядок: find → doi (сверить метаданные и статус) → add или inbox (полный текст) → annotate
(описание) → карточка → сверка с PDF.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from mathpaperlib import catalog, idents, library, migrate as migration, papers, paths, registry, store, web
from mathpaperlib import inbox as inbox_source
from mathpaperlib import search as search_source
from mathpaperlib import tex as tex_source

# Настройка и по одной функции каждого рода работы — то, чем пользуются снаружи.
classify, amsbib, flatten = idents.classify, papers.amsbib, papers.flatten
find, cites, doi_info = papers.find, papers.cites, papers.doi_info
load, save, known, next_code = registry.load, registry.save, registry.known, registry.next_code
status_of, catalog_page = catalog.status_of, catalog.catalog
index_texts, search_texts, show = search_source.index, search_source.search, search_source.show
embed, text_file = search_source.embed, search_source.text_file
PREAMBLE, tex_escape, lint_tex = tex_source.PREAMBLE, tex_source.tex_escape, tex_source.lint_tex
tex_chunks, txt_chunks = tex_source.tex_chunks, tex_source.txt_chunks


def configure(root: Path | None, library_dir: Path | None = None, direct_hosts: list[str] | None = None) -> None:
    """Проект (None — работа с одной библиотекой), библиотека и хосты в обход туннеля."""
    paths.configure(root, library_dir, direct_hosts)


def where() -> str:
    """Где проект, реестр, библиотека и inbox."""
    lines = [f'Библиотека: {paths.LIBRARY} (работ: {len(library.load())})', f'Inbox: {paths.INBOX}']
    if paths.ROOT:
        lines += [f'Проект: {paths.ROOT}', f'Реестр: {paths.REGISTRY}', f'Каталог: {paths.CATALOG}',
                  f'Карточки: {paths.CARDS}']
    else:
        lines.append('Проект не выбран: команды работают с одной библиотекой.')
    return '\n'.join(lines)


def cards() -> set[str]:
    """Коды источников с карточкой: правило одно и живёт у реестра (`registry.facts`)."""
    return registry.facts().carded


def _rebuilt(function, *args) -> list[str]:
    """Изменяющая команда: после неё пересобирается каталог проекта, если проект выбран.

    Пересборка идёт и тогда, когда команда закончилась ошибкой после записи реестра:
    страница обязана отражать реестр.
    """
    try:
        return function(*args)
    finally:
        if paths.ROOT is not None:
            catalog.catalog()


def _record(ref: str):
    """Запись по ссылке и функция её сохранения: код проекта или работа библиотеки."""
    if paths.ROOT is not None and re.fullmatch(r'[Ss]\d+', ref.strip()):
        rows = registry.load()
        return registry.by_code(rows, ref.strip()), lambda: registry.save(rows)
    entry = library.find(ref)
    return entry, lambda: library.remember(entry)


def _indexed(ref: str, record: dict) -> list[str]:
    return index_texts([record['code']] if record.get('code') else [library.stem(record)])


def add(ids: list[str], role: str | None = None) -> list[str]:
    """Добавляет работы по идентификаторам arXiv, MathNet и DOI."""
    return _rebuilt(registry.add, ids, role)


def add_file(source: str, title: str, authors: str, version: str, url: str, role: str | None = None,
             year: str = '') -> list[str]:
    """Добавляет работу без arXiv, MathNet и DOI: PDF или LaTeX по ссылке либо из файла."""
    return _rebuilt(registry.add_file, source, title, authors, version, url, role, year)


def attach(ref: str, source: str) -> list[str]:
    """Прикрепляет PDF или LaTeX, полученный вручную, к коду проекта или к работе библиотеки."""
    if paths.ROOT is not None and re.fullmatch(r'[Ss]\d+', ref.strip()):
        return _rebuilt(registry.attach, ref, source)
    record, save_record = _record(ref)
    got = registry._attach(record, source, 'local')
    save_record()
    return [f'{library.stem(record)}: прикреплён {got}'] + _indexed(ref, record)


def fetch(codes: list[str] | None = None) -> list[str]:
    """Восстанавливает недостающие файлы: исходники arXiv и PDF; с кодами — скачивает и открытый PDF."""
    def run() -> list[str]:
        if paths.ROOT is not None:
            rows = registry.load()
            return store.fetch(registry.selected(rows, codes), lambda: registry.save(rows), bool(codes))
        entries = [library.find(code) for code in codes] if codes else library.load()
        return store.fetch(entries, lambda: None, bool(codes))
    return _rebuilt(run)


def pdf(ref: str) -> list[str]:
    """Скачивает PDF работы: по нему сверяются номер теоремы и страница для карточки."""
    record, save_record = _record(ref)
    return _rebuilt(store.pdf, record, save_record)


def pages(ref: str, first: int = 1, last: int | None = None, dpi: int = 170) -> list[str]:
    """Страницы PDF в PNG и их текстовый слой: материал для транскрипции и сверки карточек."""
    record, save_record = _record(ref)
    return _rebuilt(store.pages, record, save_record, first, last, dpi)


def tex(ref: str, origin: str = 'transcription', build: bool = False) -> list[str]:
    """Собирает транскрипцию из частей `.lit/parts/<имя>/` в один LaTeX работы."""
    record, save_record = _record(ref)
    return _rebuilt(lambda: tex_source.tex(record, save_record, origin, build) + _indexed(ref, record))


def parts_folder(ref: str) -> str:
    """Куда класть части транскрипции работы."""
    record, _ = _record(ref)
    return str(tex_source.parts_folder(record))


def _annotate(source: str) -> list[str]:
    """Проверяет описания из JSON и записывает их в реестр; при замечаниях не пишет ничего."""
    data = json.loads(store.read_source(source).decode('utf-8'))
    rows, notes, fresh = registry.load(), [], {}
    for code, given in data.items():
        row = registry.by_code(rows, code)
        fresh[row['code']] = (row, registry.about_of(given), given.get('role'))
    for code, (row, about, role) in fresh.items():
        others = [dict(other, about=fresh[other['code']][1]) if other['code'] in fresh else other
                  for other in rows]
        notes += [f'{code}: {note}' for note in registry.check_about(row, about, others)]
        if about.get('basis') in registry.BASES[:2] and search_source.text_file(row) is None:
            notes.append(f'{code}: basis «{about["basis"]}», но текста источника в библиотеке нет')
        if role is not None and (len(web.squash(role)) < 30 or registry.UNFINISHED.search(role)):
            notes.append(f'{code}: role — связь с проектом одной-двумя фразами, без отложенных проверок')
    if notes:
        raise SystemExit('Описания не записаны:\n' + '\n'.join(notes))
    for row, about, role in fresh.values():
        row['about'] = about
        if role is not None:
            row['role'] = web.squash(role)
    registry.save(rows)
    return [f"Описания записаны: {', '.join(fresh)}."] + index_texts(list(fresh))


def annotate(source: str) -> list[str]:
    """Записывает описания источников из JSON вида {"S34": {…}, "S35": {…}}.

    Поля описания: kind, object, results, methods, related, keywords, basis; необязательные
    date и role (role заменяет связь с проектом). При замечаниях к любому описанию реестр
    не меняется — команда выходит с отказом и списком замечаний.
    """
    paths.project()
    return _rebuilt(_annotate, source)


def audit() -> list[str]:
    """Источники без описания, с описанием слабее имеющегося текста и с повторяющейся связью."""
    rows, notes = registry.load(), []
    for row in rows:
        code, about = row['code'], row.get('about')
        if not about:
            notes.append(f'{code}: описания нет')
        else:
            notes += [f'{code}: {note}' for note in registry.check_about(row, about, rows)]
            if about.get('basis') in registry.BASES[2:] and search_source.text_file(row) is not None:
                notes.append(f"{code}: описание составлено по «{about['basis']}», хотя полный текст есть")
        twins = [other['code'] for other in rows if other['code'] != code and other.get('role') == row.get('role')]
        if twins:
            notes.append(f"{code}: связь с проектом дословно совпадает с {', '.join(twins)}")
        if registry.UNFINISHED.search(row.get('role') or ''):
            notes.append(f'{code}: связь с проектом содержит отложенную проверку')
    return notes


def inbox(files: list[str] | None = None, ident: str | None = None) -> list[str]:
    """Разбирает PDF из inbox/ библиотеки: опознаёт, называет, кладёт в библиотеку."""
    return _rebuilt(inbox_source.inbox, files, ident)


def migrate(source: str | None = None, move: bool = False) -> list[str]:
    """Переносит файлы проекта со старой раскладки (output/literature) в библиотеку."""
    return _rebuilt(lambda: migration.migrate(source, move) + index_texts())


def listing() -> str:
    """Работы проекта с числом кусков в индексе; без проекта — опись библиотеки."""
    return search_source.listing()


def library_listing() -> str:
    return library.listing()


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser(prog='lit', description=__doc__.split('\n')[0],
                                     epilog=__doc__.split('\n\n', 3)[3],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', type=Path, help='корень проекта; по умолчанию ближайший проект вверх от текущей '
                                                  'папки или MATHPAPERLIB_PROJECT')
    parser.add_argument('--library', type=Path, help='папка библиотеки; по умолчанию MATHPAPERLIB_HOME, '
                                                     '[sources] library проекта или ~/Literature')
    parser.add_argument('--no-project', action='store_true', help='работать с одной библиотекой')
    commands = parser.add_subparsers(dest='command', required=True)

    p = commands.add_parser('add', help='добавить работы: arXiv, mathnet:rm9740, DOI')
    p.add_argument('ids', nargs='+')
    p.add_argument('--role', help='связь с проектом, одна-две фразы (обязательна в проекте)')
    p = commands.add_parser('add-file', help='добавить PDF или LaTeX без arXiv, MathNet и DOI')
    p.add_argument('source', help='ссылка или путь к файлу')
    for name in ('title', 'authors', 'version', 'url'):
        p.add_argument('--' + name, required=True)
    p.add_argument('--year', default='')
    p.add_argument('--role')
    p = commands.add_parser('attach', help='прикрепить PDF или LaTeX, полученный вручную')
    p.add_argument('ref', help='код проекта (S31) или работа библиотеки (DOI, arXiv, начало имени)')
    p.add_argument('source', help='ссылка или путь к файлу')
    p = commands.add_parser('inbox', help='разобрать PDF из inbox/: опознать, назвать, положить в библиотеку')
    p.add_argument('files', nargs='*', help='файлы; по умолчанию все PDF в inbox/')
    p.add_argument('--id', dest='ident', help='идентификатор работы, если по тексту она не опознаётся')
    p = commands.add_parser('migrate', help='перенести файлы проекта из output/literature в библиотеку')
    p.add_argument('--from', dest='source', help='старая папка; по умолчанию output/literature')
    p.add_argument('--move', action='store_true', help='переносить, а не копировать')
    p = commands.add_parser('fetch', help='восстановить недостающие файлы; с кодами — скачать и открытый PDF')
    p.add_argument('codes', nargs='*')
    p = commands.add_parser('pdf', help='скачать PDF работы для сверки номеров и страниц')
    p.add_argument('ref')
    p = commands.add_parser('pages', help='страницы PDF в PNG и текстовый слой: для транскрипции и сверки')
    p.add_argument('ref')
    p.add_argument('--range', default='', help='страницы файла: 3-10, 5, 5-, -10; по умолчанию все')
    p.add_argument('--dpi', type=int, default=170)
    p = commands.add_parser('parts', help='папка для частей транскрипции работы')
    p.add_argument('ref')
    p = commands.add_parser('tex', help='собрать транскрипцию из частей и записать её как LaTeX работы')
    p.add_argument('ref')
    p.add_argument('--build', action='store_true', help='проверить сборку pdflatex')
    p = commands.add_parser('annotate', help='записать описания источников из JSON-файла')
    p.add_argument('source', help='путь к JSON вида {"S34": {…}} или ссылка')
    commands.add_parser('audit', help='проверить описания источников и связи с проектом')
    commands.add_parser('catalog', help='пересобрать каталог и статусы в реестре')
    p = commands.add_parser('index', help='проиндексировать новые и изменившиеся тексты')
    p.add_argument('refs', nargs='*')
    p = commands.add_parser('search', help='поиск по полным текстам')
    p.add_argument('query')
    p.add_argument('-k', type=int, default=8)
    p.add_argument('--code', action='append', help='ограничить работой; можно повторять')
    p.add_argument('--kind', help='тип куска: theorem, lemma, proposition, definition, proof, text, page')
    p = commands.add_parser('show', help='полный текст куска по номеру из поиска')
    p.add_argument('id', type=int)
    p.add_argument('-n', type=int, default=0, help='сколько соседних кусков показать с каждой стороны')
    p = commands.add_parser('find', help='кандидаты: zbMATH, arXiv, Crossref, OpenAlex, Semantic Scholar, MathNet')
    p.add_argument('query')
    p.add_argument('--in', dest='where', choices=['zbmath', 'arxiv', 'mathnet', 'crossref', 'openalex', 's2', 'all'])
    p.add_argument('-n', type=int, default=15)
    p = commands.add_parser('doi', help='метаданные DOI: журнал, том, страницы, авторы, аннотация, открытый PDF')
    p.add_argument('doi')
    p = commands.add_parser('cites', help='кто цитирует работу: OpenAlex, MathNet, Semantic Scholar')
    p.add_argument('ref', help='код проекта, arXiv, mathnet:… или DOI')
    p.add_argument('--refs', action='store_true', help='наоборот: список литературы работы')
    p.add_argument('-n', type=int, default=60)
    commands.add_parser('list', help='работы проекта (без проекта — библиотеки) и число кусков в индексе')
    commands.add_parser('library', help='опись библиотеки')
    commands.add_parser('where', help='где проект, реестр, библиотека и inbox')
    commands.add_parser('mcp', help='запустить MCP-сервер на stdio')

    args = parser.parse_args(argv)
    root = None if args.no_project else (args.root or paths.discover())
    configure(root, args.library)
    if args.command == 'mcp':
        from mathpaperlib import server
        server.run()
        return
    log = lambda line: print(line, file=sys.stderr, flush=True)
    refs = [ref.upper() if re.fullmatch(r'[Ss]\d+', ref) else ref for ref in getattr(args, 'codes', None) or []]
    commands_ = {
        'add': lambda: add(args.ids, args.role),
        'add-file': lambda: add_file(args.source, args.title, args.authors, args.version, args.url, args.role,
                                     args.year),
        'attach': lambda: attach(args.ref, args.source),
        'inbox': lambda: inbox(args.files, args.ident),
        'migrate': lambda: migrate(args.source, args.move),
        'fetch': lambda: fetch(refs or None),
        'pdf': lambda: pdf(args.ref),
        'pages': lambda: pages(args.ref, *store.page_range(args.range), args.dpi),
        'parts': lambda: [parts_folder(args.ref)],
        'tex': lambda: tex(args.ref, build=args.build),
        'annotate': lambda: annotate(args.source),
        'audit': lambda: audit() or ['Описания источников и связи с проектом в порядке.'],
        'catalog': lambda: [catalog_page()],
        'index': lambda: index_texts(args.refs or None, log) or ['Индекс актуален.'],
        'search': lambda: [search_texts(args.query, args.k, args.code, args.kind, log)],
        'show': lambda: [show(args.id, args.n)],
        'find': lambda: [find(args.query, args.where, args.n)],
        'doi': lambda: [doi_info(args.doi)],
        'cites': lambda: [cites(args.ref, args.refs, args.n)],
        'list': lambda: [listing()],
        'library': lambda: [library_listing()],
        'where': lambda: [where()],
    }
    result = commands_[args.command]()
    print('\n'.join(result))
    if any('ОШИБКА' in line for line in result):
        sys.exit(1)


if __name__ == '__main__':
    main()
