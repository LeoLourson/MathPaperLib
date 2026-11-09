"""Каталог подборки проекта: страница `sources/catalog.md`, статус источника, наличие карточки.

Каталог — сводка реестра: что скачано, что сверено, чего не хватает и о чём источник.
Описание (`about`) приходит из реестра; страница только раскладывает его на разделы «О чём»,
«Результаты», «Методы», «Связанные источники», «Ключевые слова». Ручных правок в нём
не бывает. Сборка текста (`text`) отделена от записи (`catalog`): проверка свежести берёт
чистую сборку и писать не должна. Запись обновляет статусы в реестре и переписывает страницу.

Строки «Обновлено <дата>» в тексте нет: с ней содержимое менялось бы каждые сутки и точная
сверка свежести была бы невозможна. Когда страница правилась, видно в Git.

Файлы лежат в библиотеке. Если библиотека внутри проекта, каталог ссылается на них
относительными путями; общая библиотека пользователя лежит в разных местах на разных
машинах, поэтому тогда каталог называет файл, а не ссылается на него.
"""
from __future__ import annotations

import os
from datetime import date

from mathpaperlib import paths, registry


def about_markdown(row: dict) -> list[str]:
    """Описание источника разделами страницы; при отсутствии описания — строка «Описание: нет»."""
    about = row.get('about')
    if not about:
        return ['**Описание:** нет. Источник не прочитан: `lit annotate`.']
    try:
        stamp = date.fromisoformat(about.get('date') or '').strftime('%d.%m.%Y')
    except (TypeError, ValueError):
        stamp = 'дата не записана'
    out = [f"**О чём** ({about.get('kind', '')}; описано {stamp}, "
           f"основание — {about.get('basis', '')}): {about.get('object', '')}"]
    for title, key in (('Результаты', 'results'), ('Методы', 'methods'), ('Связанные источники', 'related')):
        if about.get(key):
            out += ['', f'**{title}:**', ''] + [f'- {item}' for item in about[key]] + ['']
    out.append('**Ключевые слова:** ' + ', '.join(about.get('keywords', [])) + '.')
    return out


def status_of(row: dict, carded: set[str]) -> str:
    have = []
    if row.get('tex'):
        have.append({'arxiv': 'LaTeX-исходник', 'transcription': 'LaTeX-транскрипция'}.get(row.get('tex_origin'), 'LaTeX'))
    if row.get('filename'):
        have.append('PDF' if row.get('text_layer', True) else 'PDF-скан без текстового слоя')
    missing = [row[key] for key in ('tex', 'filename') if row.get(key) and not (paths.LIBRARY / row[key]).exists()]
    return ((', '.join(have) if have else 'Полного текста нет')
            + ('; карточка есть.' if row['code'] in carded else '; теоремы не проверены.')
            + (f" Нет файлов: {', '.join(missing)} — `lit fetch`." if missing else ''))


def marked(rows: list[dict], carded: set[str]) -> list[dict]:
    """Копии строк реестра с пересчитанным полем status: сам реестр при сборке не меняется."""
    found = [dict(row) for row in rows]
    for row in found:
        row['status'] = status_of(row, carded)
    return found


def local(name: str) -> str | None:
    """Относительная ссылка из каталога на файл библиотеки, если библиотека внутри проекта."""
    target = paths.LIBRARY / name
    try:
        target.relative_to(paths.ROOT)
    except ValueError:
        return None
    return os.path.relpath(target, paths.CATALOG.parent).replace(os.sep, '/').replace(' ', '%20')


def page(rows: list[dict]) -> str:
    """Текст страницы по строкам реестра со статусами."""
    inside = local('x') is not None
    where = f'`{paths.shown(paths.LIBRARY)}`' if inside else 'общей библиотеке пользователя'
    out = [
        '# Подборка полных текстов', '',
        f'Работ в подборке: {len(rows)}. Файл собран командой `lit catalog` из реестра '
        f'[{paths.REGISTRY.name}]({paths.REGISTRY.name}); правки вносятся в реестр. Тексты лежат в {where} '
        'под именами «Авторы Год - Название». Наличие полного текста не означает проверку его теорем. '
        'LaTeX-транскрипция сделана моделью по PDF: при расхождении первичен PDF.', '',
    ]
    for row in rows:
        links = [f"[Первичный источник]({row['url']})"]
        if row.get('pdf_url'):
            links.append(f"[полный текст]({row['pdf_url']})")
        for kind, field in (('LaTeX', 'tex'), ('PDF', 'filename')):
            if row.get(field):
                link = local(row[field])
                links.append(f'[локальный {kind}]({link})' if link else f'{kind}: `{row[field]}`')
        volume = f"**Объём:** {row['pages']} стр. " if row.get('pages') else ''
        sums = [f"PDF `{row['sha256']}`"] if row.get('sha256') else []
        if row.get('eprint_sha256'):
            sums.append(f"исходник arXiv `{row['eprint_sha256']}`")
        title = row['title'] + (f" / {row['title_en']}" if row.get('title_en') else '')
        out += [f"## {row['code']}. {title}", '',
                f"**Авторы:** {row['authors']}. **Версия:** {row['version']}.",
                '; '.join(links) + '.',
                f"{volume}**Статус:** {row['status']}",
                *about_markdown(row), '',
                f"**Связь с проектом:** {row.get('role', '')}"]
        if sums:
            out.append('**SHA-256:** ' + '; '.join(sums) + '.')
        out.append('')
    return '\n'.join(out)


def text() -> str:
    """Чистая сборка текста каталога: ничего не пишет и реестр не меняет."""
    facts = registry.facts()
    return page(marked(registry.load(), facts.carded))


def catalog() -> str:
    """Пересобирает страницу каталога и статусы в реестре; возвращает сообщение."""
    facts = registry.facts()
    rows = marked(registry.load(), facts.carded)
    if rows:
        registry.save(rows)
    paths.CATALOG.parent.mkdir(parents=True, exist_ok=True)
    paths.CATALOG.write_text(page(rows), encoding='utf-8', newline='\n')
    return f'Каталог пересобран, работ: {len(rows)}.'
