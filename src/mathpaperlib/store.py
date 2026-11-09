"""Файлы работ в библиотеке: скачивание, имена, текстовый слой, страницы.

Каждый файл получает имя из метаданных (`library.stem_for`) и ложится в корень библиотеки;
текстовый слой PDF — в `.lit/text/`, отрисованные страницы — в `.lit/pages/<имя>/`.
Контрольная сумма из записи сверяется при каждой записи файла, поэтому подмена версии
заметна сразу. Функции принимают запись (строку реестра или описи) и меняют её поля;
сохраняет запись вызывающий, а опись библиотеки обновляется здесь же.
"""
from __future__ import annotations

import gzip
import hashlib
import re
import urllib.error
from pathlib import Path
from typing import Callable

from mathpaperlib import idents, library, papers, paths, web


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def label(record: dict) -> str:
    """Как назвать запись в сообщении: код проекта или имя в библиотеке."""
    return record.get('code') or library.stem(record) or record.get('title', '?')[:60]


def pdf_text(pdf: Path) -> tuple[int, bool]:
    """Число страниц и признак текстового слоя; слой пишется в `.lit/text/` (страницы через \\f)."""
    import pymupdf as fitz
    with fitz.open(pdf) as doc:
        pages = [page.get_text() for page in doc]
    layer = sum(map(len, pages)) >= 400 * len(pages)
    if layer:
        target = paths.text_layer(pdf.name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('\f'.join(pages), encoding='utf-8', newline='\n')
    return len(pages), layer


def store_pdf(record: dict, data: bytes) -> Path:
    """Кладёт PDF работы в библиотеку под её именем и вносит его в опись."""
    if data[:5] != b'%PDF-':
        raise ValueError(f"{label(record)}: по ссылке {record.get('pdf_url', '')} пришёл не PDF (доступ закрыт?)")
    if record.get('sha256') and record['sha256'] != sha256(data):
        raise ValueError(f'{label(record)}: PDF отличается от записанного; сверь версию')
    name = record.get('filename') or library.stem_for(record) + '.pdf'
    paths.LIBRARY.mkdir(parents=True, exist_ok=True)
    target = paths.LIBRARY / name
    target.write_bytes(data)
    pages, layer = pdf_text(target)
    record.update(filename=name, pages=pages, sha256=sha256(data), text_layer=layer)
    library.remember(record)
    return target


def store_tex(record: dict, text: str, origin: str) -> Path:
    """Кладёт LaTeX работы рядом с её PDF под тем же именем."""
    name = record.get('tex') or library.stem_for(record) + '.tex'
    paths.LIBRARY.mkdir(parents=True, exist_ok=True)
    target = paths.LIBRARY / name
    target.write_text(text, encoding='utf-8', newline='\n')
    record.update(tex=name, tex_origin=origin)
    library.remember(record)
    return target


def store_eprint(record: dict) -> str:
    """Скачивает исходник arXiv в библиотеку; возвращает 'tex' или 'pdf'."""
    data = web.http_get('https://arxiv.org/e-print/' + idents.arxiv_id(record))
    if record.get('eprint_sha256') not in (None, sha256(data)):
        raise ValueError(f'{label(record)}: исходник arXiv отличается от записанного')
    files = papers.unpack(data)
    if files is None:
        if not record.get('filename'):
            store_pdf(record, gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data)
        record['eprint'] = 'pdf'
        library.remember(record)
        return 'pdf'
    record['eprint_sha256'] = sha256(data)
    store_tex(record, papers.flatten(files), 'arxiv')
    return 'tex'


def read_source(source: str) -> bytes:
    return web.http_get(source) if re.match(r'https?://', source) else Path(source).expanduser().read_bytes()


def open_pdf_url(record: dict) -> None:
    """Ссылка на открытый PDF из OpenAlex, если своей у записи нет, а DOI есть."""
    if record.get('pdf_url') or not idents.dois_of(record):
        return
    try:
        found = papers.openalex_meta(record.get('doi') or idents.dois_of(record)[0])
    except Exception:  # noqa: BLE001 — ссылка необязательна
        return
    if found.get('pdf_url'):
        record['pdf_url'] = found['pdf_url']


def fetch(records: list[dict], save: Callable[[], None], explicit: bool = False) -> list[str]:
    """Восстанавливает недостающие файлы записей: исходники arXiv и PDF.

    explicit — записи названы по именам: тогда скачивается и PDF, которого ещё не было
    (открытый по DOI), а не только восстанавливаются записанные файлы.
    """
    report = []
    for record in records:
        done = []
        try:
            if explicit and not record.get('filename'):
                open_pdf_url(record)
                if record.get('pdf_url'):
                    store_pdf(record, web.http_get(record['pdf_url']))
                    done.append(f"PDF, {record['pages']} стр.")
            if record.get('filename') and not (paths.LIBRARY / record['filename']).exists():
                if not record.get('pdf_url'):
                    raise ValueError(f"у записи нет ссылки на PDF для {record['filename']}; "
                                     'прикрепите файл командой attach или положите его в inbox/')
                store_pdf(record, web.http_get(record['pdf_url']))
                done.append('PDF')
            if record.get('filename') and record.get('text_layer', True) \
                    and not paths.text_layer(record['filename']).exists():
                record['pages'], record['text_layer'] = pdf_text(paths.LIBRARY / record['filename'])
                library.remember(record)
                done.append('текст PDF')
            if idents.arxiv_id(record) and record.get('eprint') != 'pdf' \
                    and not (record.get('tex') and (paths.LIBRARY / record['tex']).exists()):
                done.append('LaTeX' if store_eprint(record) == 'tex' else 'на arXiv только PDF')
            if record.get('tex') and not (paths.LIBRARY / record['tex']).exists():
                raise ValueError(f"нет {record['tex']}: транскрипция и локальный LaTeX по ссылке не восстанавливаются")
        except (ValueError, ConnectionError, urllib.error.URLError) as error:
            report.append(f'{label(record)}: ОШИБКА — {error}')
            continue
        if done:
            save()
            report.append(f'{label(record)}: ' + ', '.join(done))
    return report or ['Все файлы на месте.']


def pdf(record: dict, save: Callable[[], None]) -> list[str]:
    """Скачивает PDF работы: номера теорем и страницы для карточки сверяются по нему."""
    if record.get('filename') and (paths.LIBRARY / record['filename']).exists():
        return [f"{label(record)}: {paths.LIBRARY / record['filename']} уже есть"]
    open_pdf_url(record)
    if not record.get('pdf_url'):
        raise SystemExit(f'{label(record)}: ссылки на PDF нет; прикрепите файл командой attach '
                         f'или положите его в {paths.INBOX}')
    target = store_pdf(record, web.http_get(record['pdf_url']))
    save()
    return [f"{label(record)}: {target}, {record['pages']} стр."]


def page_range(text: str) -> tuple[int, int | None]:
    """Границы страниц: «5-10», «5» (одна), «5-» (до конца), «-10» (с начала), '' (все)."""
    text = (text or '').strip()
    if not text:
        return 1, None
    first, dash, last = text.partition('-')
    try:
        start = int(first) if first.strip() else 1
        stop = (int(last) if last.strip() else None) if dash else start
    except ValueError:
        raise SystemExit(f'Не разобран диапазон страниц «{text}»: нужен вид 5-10, 5, 5- или -10.')
    if start < 1 or (stop is not None and stop < start):
        raise SystemExit(f'Пустой диапазон страниц «{text}».')
    return start, stop


def pages(record: dict, save: Callable[[], None], first: int = 1, last: int | None = None,
          dpi: int = 170) -> list[str]:
    """Страницы PDF в PNG и их текстовый слой: материал для транскрипции и сверки карточек."""
    import pymupdf as fitz
    if not (record.get('filename') and (paths.LIBRARY / record['filename']).exists()):
        pdf(record, save)
    folder = paths.PAGES / Path(record['filename']).stem
    folder.mkdir(parents=True, exist_ok=True)
    report = []
    with fitz.open(paths.LIBRARY / record['filename']) as doc:
        for number in range(first, min(last or len(doc), len(doc)) + 1):
            page = doc[number - 1]
            image = folder / f'p{number:04d}.png'
            if not image.exists():
                page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY).save(image)
            text = page.get_text()
            note = 'текстового слоя нет'
            if len(text) >= 400:
                image.with_suffix('.txt').write_text(text, encoding='utf-8', newline='\n')
                note = f'слой: {image.with_suffix(".txt")}'
            report.append(f'стр. файла {number}: {image}; {note}')
    return report
