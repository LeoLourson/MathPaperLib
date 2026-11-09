"""Реестр проекта: карточки, каталог, описания, настройка путей."""
import json
from unittest.mock import patch

import pytest

from conftest import make_project
from mathpaperlib import catalog, lit, paths, registry


@pytest.fixture
def carded(tmp_path, shelf):
    """Два источника: у S1 карточка файлом (сверена), у S2 — только заголовок в results.md."""
    rows = [dict(code='S1', title='Первая', authors='А. А.', version='v1', url='https://example.org/1',
                 role='метод', filename='one.pdf', sha256='abc', pages=3),
            dict(code='S2', title='Вторая', authors='Б. Б.', version='v2', url='https://example.org/2',
                 role='оценка')]
    root = make_project(tmp_path / 'p', rows)
    (root / 'sources' / 'cards').mkdir()
    (root / 'sources' / 'cards' / 'S1.md').write_text('---\nsource: S1\nverified: 2026-01-01\n---\n\n# Теорема\n',
                                                      encoding='utf-8')
    (root / 'sources' / 'results.md').write_text('# Результаты\n\n## S2. Вторая\n\nПроверено по PDF.\n',
                                                 encoding='utf-8')
    lit.configure(root, shelf)
    return root


def test_cards_are_counted_by_one_rule(carded):
    facts = registry.facts()
    assert (facts.codes, facts.carded, facts.verified) == ({'S1', 'S2'}, {'S1', 'S2'}, {'S1'})
    text = catalog.text()
    assert 'карточка есть.' in text.split('## S1.')[1].split('## S2.')[0]
    assert 'карточка есть.' in text.split('## S2.')[1]


def test_catalog_text_is_pure_and_the_page_matches_it(carded):
    before = (carded / 'sources' / 'papers.json').read_bytes()
    text = catalog.text()
    assert 'Обновлено' not in text  # дата делала бы текст другим каждые сутки
    assert (carded / 'sources' / 'papers.json').read_bytes() == before
    assert not (carded / 'sources' / 'catalog.md').exists()
    catalog.catalog()
    assert (carded / 'sources' / 'catalog.md').read_text(encoding='utf-8') == catalog.text()
    rows = {row['code']: row['status'] for row in
            json.loads((carded / 'sources' / 'papers.json').read_text(encoding='utf-8'))}
    assert rows['S1'].startswith('PDF; карточка есть. Нет файлов: one.pdf')
    assert rows['S2'] == 'Полного текста нет; карточка есть.'


def test_catalog_names_files_of_a_shared_library_and_links_a_local_one(carded, shelf):
    assert 'PDF: `one.pdf`' in catalog.text()
    lit.configure(carded, carded / 'output' / 'literature')
    assert '[локальный PDF](../output/literature/one.pdf)' in catalog.text()


def test_annotate_records_description_and_audit_sees_gaps(carded):
    assert 'S2: описания нет' in '\n'.join(lit.audit())
    given = {'S2': {'kind': 'статья',
                    'object': 'Спектральная задача второго порядка с отражением аргумента ' * 2,
                    'results': ['Теорема 1.1, с. 5'], 'methods': ['резольвента'],
                    'related': ['S1'], 'keywords': ['базис', 'спектр', 'bases'],
                    'basis': 'аннотация'}}
    payload = carded / 'about.json'
    payload.write_text(json.dumps(given, ensure_ascii=False), encoding='utf-8')
    lit.annotate(str(payload))
    row = next(row for row in registry.load() if row['code'] == 'S2')
    assert row['about']['kind'] == 'статья' and row['about']['related'] == ['S1']
    page = (carded / 'sources' / 'catalog.md').read_text(encoding='utf-8')
    assert '**О чём** (статья' in page
    assert '**Ключевые слова:** базис, спектр, bases.' in page
    assert 'S2: описания нет' not in '\n'.join(lit.audit())


def test_annotate_with_a_note_writes_no_description(carded):
    payload = carded / 'about.json'
    payload.write_text(json.dumps({'S2': {'kind': 'роман', 'object': 'коротко', 'basis': 'аннотация'}},
                                  ensure_ascii=False), encoding='utf-8')
    with pytest.raises(SystemExit, match='kind: одно из'):
        lit.annotate(str(payload))
    assert 'about' not in registry.by_code(registry.load(), 'S2')


def test_mutating_command_rebuilds_the_catalog_even_after_a_failure(carded, shelf):
    source = carded / 'one.tex'
    source.write_text('\\documentclass{article}\n', encoding='utf-8')
    lit.attach('S2', str(source))
    page = (carded / 'sources' / 'catalog.md').read_text(encoding='utf-8')
    assert page == catalog.text()
    assert 'LaTeX: `B. B - Vtoraya.tex`' in page  # года нет ни в поле, ни в версии — в имени его нет
    assert (shelf / 'B. B - Vtoraya.tex').exists()
    (carded / 'sources' / 'catalog.md').unlink()
    # Реестр уже записан, а индексация сорвалась: страница всё равно должна появиться.
    with patch('mathpaperlib.search.index', side_effect=RuntimeError('нет модели')):
        with pytest.raises(RuntimeError):
            lit.attach('S2', str(source))
    assert (carded / 'sources' / 'catalog.md').exists()


def test_configure_reads_the_project_settings(tmp_path, monkeypatch):
    monkeypatch.delenv('MATHPAPERLIB_HOME', raising=False)
    root = make_project(tmp_path / 'p', [], toml='[sources]\ndirect_hosts = ["example.org"]\n'
                                                 'registry = "sources/registry.json"\ncards = "claims"\n'
                                                 'library = "lib"\n')
    lit.configure(root)
    try:
        assert paths.REGISTRY == root / 'sources' / 'registry.json'
        assert paths.CARDS == root / 'claims'
        assert paths.LIBRARY == (root / 'lib').resolve()
        assert paths.DB == (root / 'lib' / '.lit' / 'index' / 'lit.sqlite').resolve()
        from mathpaperlib import web
        assert web.DIRECT_HOSTS == ['example.org']
        assert paths.discover(root / 'sources') == root
    finally:
        lit.configure(None)


def test_without_a_project_registry_commands_refuse(shelf):
    with pytest.raises(SystemExit, match='Проект не выбран'):
        registry.load()
    assert 'Проект не выбран' in lit.where()


def test_unknown_code_is_a_refusal(carded):
    with pytest.raises(SystemExit, match='S9'):
        registry.selected(registry.load(), ['S9'])
