"""Индекс полных текстов: смысловая и словарная близость, выдача куска.

Индекс один на библиотеку (`.lit/index/lit.sqlite`) и хранит куски по имени работы в
библиотеке, а не по коду проекта: работа, добавленная в двух проектах, индексируется один
раз. Поиск в проекте ограничен работами его реестра и показывает их коды; без проекта
поиск идёт по всей библиотеке.

Модель загружается лениво и держится в памяти: MCP-сервер прогревает её при запуске,
потому что под Windows загрузка из обработчика запроса зависает. Индекс — производное, он
пересобирается по изменившимся текстам.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from mathpaperlib import library, paths, store, tex, web

MODEL = 'intfloat/multilingual-e5-small'
CHUNKER = 3  # увеличить после изменения нарезки: индекс пересоберётся
LAYOUT = 'library-1'  # раскладка таблиц: куски по имени работы в библиотеке
_model = None
_corpus = None


def embed(texts: list[str], prefix: str):
    """Нормированные векторы e5: ONNX Runtime на процессоре, усреднение по токенам."""
    global _model
    import numpy as np
    if _model is None:
        import onnxruntime
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        def cached(name: str) -> str:
            try:
                return hf_hub_download(MODEL, name, local_files_only=True)
            except OSError:
                return hf_hub_download(MODEL, name)

        tokenizer = Tokenizer.from_file(cached('tokenizer.json'))
        tokenizer.enable_truncation(max_length=512)
        tokenizer.enable_padding(pad_id=tokenizer.token_to_id('<pad>') or 0, pad_token='<pad>')
        _model = tokenizer, onnxruntime.InferenceSession(cached('onnx/model.onnx'),
                                                         providers=['CPUExecutionProvider'])
    tokenizer, session = _model
    inputs = {item.name for item in session.get_inputs()}
    vectors = np.zeros((len(texts), 1), dtype='float32')
    order = sorted(range(len(texts)), key=lambda i: len(texts[i]))  # близкие длины — меньше дополнения
    for start in range(0, len(order), 16):
        batch = order[start:start + 16]
        encoded = tokenizer.encode_batch([prefix + texts[i] for i in batch])
        mask = np.array([item.attention_mask for item in encoded], dtype='int64')
        feed = {'input_ids': np.array([item.ids for item in encoded], dtype='int64'), 'attention_mask': mask}
        if 'token_type_ids' in inputs:
            feed['token_type_ids'] = np.zeros_like(mask)
        hidden = session.run(None, feed)[0]
        pooled = (hidden * mask[..., None]).sum(1) / mask.sum(1, keepdims=True)
        if vectors.shape[1] != pooled.shape[1]:
            vectors = np.zeros((len(texts), pooled.shape[1]), dtype='float32')
        vectors[batch] = pooled / np.linalg.norm(pooled, axis=1, keepdims=True)
    return vectors.astype('float16')


def connect() -> sqlite3.Connection:
    paths.DB.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(paths.DB)
    db.execute('create table if not exists meta(key text primary key, value text)')
    version = f'{MODEL}:{CHUNKER}:{LAYOUT}'
    if db.execute("select value from meta where key = 'version'").fetchone() != (version,):
        with db:  # другая модель, нарезка или раскладка: старый индекс несовместим
            for table in ('chunks', 'fts', 'papers', 'docs'):
                db.execute(f'drop table if exists {table}')
            db.execute("insert or replace into meta values ('version', ?)", (version,))
    db.executescript('''
        create table if not exists docs(doc text primary key, stamp text);
        create table if not exists chunks(id integer primary key, doc text, seq integer, kind text,
            label text, section text, file text, loc integer, page text, text text, vec blob);
        create index if not exists chunks_doc on chunks(doc, seq);
        create virtual table if not exists fts using fts5(text, section, tokenize='unicode61 remove_diacritics 2');
    ''')
    return db


def text_file(record: dict) -> Path | None:
    """Файл для индекса: LaTeX, а без него текстовый слой PDF."""
    if record.get('tex') and (paths.LIBRARY / record['tex']).exists():
        return paths.LIBRARY / record['tex']
    if record.get('filename') and paths.text_layer(record['filename']).exists():
        return paths.text_layer(record['filename'])
    return None


def targets(refs: list[str] | None = None) -> list[tuple[str, dict]]:
    """Работы, с которыми работает поиск: (подпись, запись).

    В проекте — строки реестра (подпись — код, refs — коды), без проекта — работы описи
    (подпись — имя в библиотеке, refs — имена или их начала).
    """
    if paths.ROOT is not None:
        from mathpaperlib import registry
        return [(row['code'], row) for row in registry.selected(registry.load(), refs)]
    entries = [entry for entry in library.load() if library.has_files(entry)]
    if refs:
        entries = [library.find(ref) for ref in refs]
    return [(library.stem(entry), entry) for entry in entries]


def index(refs: list[str] | None = None, log=None) -> list[str]:
    """Индексирует новые и изменившиеся тексты; остальные пропускает."""
    db, report = connect(), []
    stamps = dict(db.execute('select doc, stamp from docs'))
    for name, record in targets(refs):
        path = text_file(record)
        if path is None:
            if refs:
                report.append(f'{name}: текста для индекса нет')
            continue
        doc, raw = library.stem(record), path.read_bytes()
        stamp = store.sha256(raw) + path.suffix
        if stamps.get(doc) == stamp:
            continue
        text = raw.decode('utf-8').replace('\r\n', '\n')
        chunks = tex.tex_chunks(text) if path.suffix == '.tex' else tex.txt_chunks(text)
        if log:
            log(f'{name}: {len(chunks)} кусков, считаю векторы')
        title = f"{record['title']}. {record.get('title_en', '')}"
        vectors = embed([f"{title}. {chunk['section']}. {chunk['text']}" for chunk in chunks], 'passage: ')
        with db:
            db.execute('delete from fts where rowid in (select id from chunks where doc = ?)', (doc,))
            db.execute('delete from chunks where doc = ?', (doc,))
            for seq, (chunk, vector) in enumerate(zip(chunks, vectors)):
                rowid = db.execute(
                    'insert into chunks(doc, seq, kind, label, section, file, loc, page, text, vec) '
                    'values (?,?,?,?,?,?,?,?,?,?)',
                    (doc, seq, chunk['kind'], chunk['label'], chunk['section'], path.name, chunk['loc'],
                     chunk['page'], chunk['text'], vector.tobytes())).lastrowid
                db.execute('insert into fts(rowid, text, section) values (?,?,?)',
                           (rowid, chunk['text'], chunk['section']))
            db.execute('insert or replace into docs values (?,?)', (doc, stamp))
        stamps[doc] = stamp
        report.append(f'{name}: {len(chunks)} кусков из {path.name}')
    db.close()
    return report


def corpus(db: sqlite3.Connection):
    """Матрица векторов индекса; перечитывается после изменения базы."""
    global _corpus
    import numpy as np
    stamp = (str(paths.DB), paths.DB.stat().st_mtime_ns)
    if _corpus is None or _corpus[0] != stamp:
        rows = db.execute('select id, doc, kind, vec from chunks order by id').fetchall()
        matrix = np.frombuffer(b''.join(row[3] for row in rows), dtype='float16').reshape(len(rows), -1)
        _corpus = (stamp, [row[0] for row in rows], [row[1] for row in rows], [row[2] for row in rows],
                   matrix.astype('float32'))
    return _corpus[1:]


def place(file: str, loc: int, page: str) -> str:
    if file.endswith('.tex'):
        return f'{paths.LIBRARY / file}:{loc}' + (f', печатная с. {page}' if page else '')
    return f'{Path(file).stem}.pdf, стр. файла {loc}'


def first_author(record: dict) -> str:
    names = (record.get('authors') or '?').split(';')[0].split()
    return names[-1] if names else '?'


def search(query: str, k: int = 8, refs: list[str] | None = None, kind: str | None = None,
           log=None) -> str:
    """Гибридный поиск: BM25 по словам и близость векторов, объединённые по рангам."""
    import numpy as np
    chosen = targets(refs)  # неизвестный код — отказ, а не пустой результат поиска
    index(log=log)
    named = {library.stem(record): (name, record) for name, record in chosen if library.has_files(record)}
    db = connect()
    ids, docs, kinds, matrix = corpus(db)
    if not ids:
        db.close()
        return f'Индекс пуст: в библиотеке {paths.LIBRARY} нет текстов.'
    allowed = np.array([doc in named and (not kind or kind.lower() in item.lower())
                        for doc, item in zip(docs, kinds)])
    scores: dict[int, float] = {}
    similarity = np.where(allowed, matrix @ embed([query], 'query: ')[0].astype('float32'), -1.0)
    for rank, position in enumerate(np.argsort(-similarity)[:100]):
        if allowed[position]:
            scores[ids[position]] = 1 / (60 + rank)
    words = re.findall(r'\w{2,}', query.lower())
    if words:
        permitted = {chunk for chunk, ok in zip(ids, allowed) if ok}
        lexical = [rowid for (rowid,) in db.execute(
            'select rowid from fts where fts match ? order by bm25(fts) limit 2000',
            (' OR '.join(f'"{word}"' for word in words),)) if rowid in permitted][:100]
        for rank, rowid in enumerate(lexical):
            scores[rowid] = scores.get(rowid, 0) + 1 / (60 + rank)
    out = []
    for rowid in sorted(scores, key=scores.get, reverse=True)[:k]:
        doc, item, label, section, file, loc, page, text = db.execute(
            'select doc, kind, label, section, file, loc, page, text from chunks where id = ?', (rowid,)).fetchone()
        name, record = named[doc]
        head = [f"#{rowid} {name}" + (f" {first_author(record)}, «{record['title'][:70]}»" if paths.ROOT else ''),
                item + (f' {label}' if label else '')]
        if section:
            head.append('§ ' + section[:70])
        out.append(' · '.join(head + [place(file, loc, page)]) + '\n    ' + web.squash(text)[:340])
    db.close()
    return '\n'.join(out) or 'Ничего не найдено.'


def show(rowid: int, around: int = 0) -> str:
    """Полный текст куска и его соседей по работе."""
    db = connect()
    found = db.execute('select doc, seq from chunks where id = ?', (rowid,)).fetchone()
    if not found:
        db.close()
        return f'Куска #{rowid} нет в индексе.'
    out = []
    for ident, item, label, section, file, loc, page, text in db.execute(
            'select id, kind, label, section, file, loc, page, text from chunks where doc = ? and seq between ? '
            'and ? order by seq', (found[0], found[1] - around, found[1] + around)):
        out.append(f"#{ident} {found[0]} · {item}{' ' + label if label else ''} · § {section} · "
                   f"{place(file, loc, page)}\n{text}\n")
    db.close()
    return '\n'.join(out)


def listing() -> str:
    """Работы проекта с числом кусков в индексе; без проекта — опись библиотеки."""
    if paths.ROOT is None:
        return library.listing()
    db = connect()
    counts = dict(db.execute('select doc, count(*) from chunks group by doc'))
    db.close()
    return '\n'.join(
        f"{name} · {record['version']} · {record['authors'].split(';')[0]} · {record['title'][:80]} · "
        f"{counts.get(library.stem(record), 0) if library.has_files(record) else 0} кусков · "
        f"{library.stem(record) or 'файлов нет'}"
        for name, record in targets()) or 'Реестр пуст.'
