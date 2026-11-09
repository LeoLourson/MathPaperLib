"""Общие заготовки тестов: библиотека и проект во временных папках, без сети и без модели."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mathpaperlib import lit, paths, search


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    """Пустая библиотека; проект не выбран. Переменные окружения не влияют на тест."""
    monkeypatch.delenv('MATHPAPERLIB_HOME', raising=False)
    monkeypatch.delenv('MATHPAPERLIB_PROJECT', raising=False)
    library = tmp_path / 'Literature'
    lit.configure(None, library, direct_hosts=[])
    yield library
    lit.configure(None)


def make_project(root: Path, rows: list[dict], toml: str = '[sources]\ndirect_hosts = []\n') -> Path:
    (root / 'sources').mkdir(parents=True, exist_ok=True)
    (root / 'project.toml').write_text(toml, encoding='utf-8')
    (root / 'sources' / 'papers.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n',
                                                  encoding='utf-8')
    return root


@pytest.fixture
def project(tmp_path, shelf):
    """Проект с двумя источниками без файлов; библиотека — `shelf`."""
    rows = [dict(code='S1', title='Первая работа', authors='А. А. Иванов', version='v1', url='https://example.org/1',
                 role='метод'),
            dict(code='S2', title='Вторая работа', authors='Б. Б. Петров', version='v2', url='https://example.org/2',
                 role='оценка')]
    root = make_project(tmp_path / 'project', rows)
    lit.configure(root, shelf)
    return root


def pdf_bytes(*pages: str) -> bytes:
    """Настоящий PDF с текстовым слоем: по странице на строку."""
    import pymupdf as fitz
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


LONG = ' '.join(['Spectral analysis of differential operators with involution and Riesz bases.'] * 12)


def fake_embed(texts: list[str], prefix: str):
    """Детерминированные «векторы» по словам: модель e5 в тестах не грузится."""
    import numpy as np
    vectors = np.zeros((len(texts), 64), dtype='float32')
    for row, text in enumerate(texts):
        for word in text.lower().split():
            vectors[row, int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)
    return vectors.astype('float16')


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    monkeypatch.setattr(search, 'embed', fake_embed)
    monkeypatch.setattr(lit, 'embed', fake_embed)
    search._corpus = None


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(url, tries=4):
        raise AssertionError(f'сеть в тестах запрещена: {url}')
    from mathpaperlib import web
    monkeypatch.setattr(web, 'http_get', refuse)


def library_files(library: Path) -> list[str]:
    return sorted(path.name for path in library.iterdir() if path.is_file() and path.name != 'library.json')


__all__ = ['make_project', 'pdf_bytes', 'LONG', 'library_files', 'paths']
