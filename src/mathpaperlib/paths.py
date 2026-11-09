"""Где что лежит: общая библиотека файлов и реестр текущего проекта.

Библиотека — одна папка на пользователя (`~/Literature` или `MATHPAPERLIB_HOME`); проект
может указать свою в `project.toml`: `[sources] library = "…"`. В корне библиотеки лежат
только сами работы под читаемыми именами (PDF и LaTeX) и опись `library.json`; новые файлы
кладут в `inbox/`, служебное — текстовые слои, страницы, части транскрипций, индекс — в `.lit/`.

Проект — каталог с реестром (`sources/papers.json` или путь `[sources] registry`) либо с
разделом `[sources]` в `project.toml`. В проекте живут коды `S…`, связь с проектом,
описания, карточки и каталог; файлы проекта лежат в библиотеке. Без проекта инструмент
работает с одной библиотекой.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from mathpaperlib import web

DEFAULT_LIBRARY = Path.home() / 'Literature'

# Заполняются configure().
LIBRARY = DEFAULT_LIBRARY
INBOX = WORK = TEXT = PAGES = PARTS = BUILD = DB = LIBRARY_JSON = DEFAULT_LIBRARY
ROOT: Path | None = None
REGISTRY: Path | None = None
CATALOG: Path | None = None
CARDS: Path | None = None
RESULTS: Path | None = None
SETTINGS: dict = {}


def settings(root: Path | None) -> dict:
    """Раздел `[sources]` файла `project.toml` проекта; пустой, если файла или раздела нет."""
    path = root / 'project.toml' if root else None
    if not path or not path.exists():
        return {}
    return tomllib.loads(path.read_text(encoding='utf-8')).get('sources', {})


def is_project(root: Path) -> bool:
    """Каталог — проект: в нём есть реестр или раздел `[sources]` в `project.toml`."""
    found = settings(root)
    return bool(found) or (root / found.get('registry', 'sources/papers.json')).exists()


def discover(start: Path | None = None) -> Path | None:
    """Проект по умолчанию: `MATHPAPERLIB_PROJECT`, иначе ближайший проект вверх от `start`."""
    if os.environ.get('MATHPAPERLIB_PROJECT'):
        return Path(os.environ['MATHPAPERLIB_PROJECT']).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for folder in (here, *here.parents):
        if is_project(folder):
            return folder
    return None


def configure(root: Path | None, library: Path | None = None, direct_hosts: list[str] | None = None) -> None:
    """Настраивает проект (или его отсутствие) и библиотеку.

    Библиотека: аргумент, иначе `MATHPAPERLIB_HOME`, иначе `[sources] library` проекта
    (относительно его корня), иначе `~/Literature`.
    """
    global LIBRARY, INBOX, WORK, TEXT, PAGES, PARTS, BUILD, DB, LIBRARY_JSON
    global ROOT, REGISTRY, CATALOG, CARDS, RESULTS, SETTINGS
    ROOT = Path(root).resolve() if root else None
    SETTINGS = settings(ROOT)
    if library is None and os.environ.get('MATHPAPERLIB_HOME'):
        library = Path(os.environ['MATHPAPERLIB_HOME'])
    if library is None and SETTINGS.get('library'):
        library = ROOT / SETTINGS['library']
    LIBRARY = Path(library or DEFAULT_LIBRARY).expanduser().resolve()
    INBOX = LIBRARY / 'inbox'
    WORK = LIBRARY / '.lit'
    TEXT, PAGES, PARTS, BUILD = WORK / 'text', WORK / 'pages', WORK / 'parts', WORK / 'build'
    DB = WORK / 'index' / 'lit.sqlite'
    LIBRARY_JSON = LIBRARY / 'library.json'
    if ROOT:
        REGISTRY = ROOT / SETTINGS.get('registry', 'sources/papers.json')
        CATALOG = ROOT / SETTINGS.get('catalog', 'sources/catalog.md')
        CARDS = ROOT / SETTINGS.get('cards', 'sources/cards')
        RESULTS = ROOT / SETTINGS.get('results', 'sources/results.md')
    else:
        REGISTRY = CATALOG = CARDS = RESULTS = None
    web.configure(SETTINGS, direct_hosts)


def project() -> Path:
    """Корень проекта или отказ: команда работает с реестром."""
    if ROOT is None:
        raise SystemExit('Проект не выбран: укажите --root, MATHPAPERLIB_PROJECT или запустите из каталога '
                         'проекта (там есть sources/papers.json или раздел [sources] в project.toml).')
    return ROOT


def text_layer(name: str) -> Path:
    """Текстовый слой PDF: `.lit/text/<имя>.txt`, страницы разделены \\f."""
    return TEXT / (Path(name).stem + '.txt')


def shown(path: Path) -> str:
    """Путь для сообщений: относительно проекта, если файл в нём, иначе полный."""
    if ROOT:
        try:
            return path.relative_to(ROOT).as_posix()
        except ValueError:
            pass
    return str(path)


configure(None)
