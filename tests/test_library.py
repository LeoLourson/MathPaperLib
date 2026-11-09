"""Библиотека: имена при скачивании, один файл на два проекта, inbox, перенос, общий индекс."""
import json

import pytest

from conftest import LONG, library_files, make_project, pdf_bytes
from mathpaperlib import library, lit, migrate as migration, papers, paths, registry, web

ARTICLE = dict(authors='Natalia P. Bondarenko', title='Inverse spectral problems for operators with involution',
               year='2021', version='Journal of Spectral Theory 11 (2021), 1-30', url='https://doi.org/10.1234/abc',
               doi='10.1234/abc', pdf_url='https://example.org/abc.pdf')
NAME = 'Bondarenko 2021 - Inverse spectral problems for operators with involution'


@pytest.fixture
def online(monkeypatch):
    """Метаданные и PDF работы ARTICLE вместо сети; счётчик скачиваний."""
    downloads = []
    page = pdf_bytes('Inverse spectral problems for operators with involution\nN. P. Bondarenko\n'
                     'doi:10.1234/abc\n' + LONG, LONG)

    def resolve(ident):
        assert ident in ('10.1234/abc', 'doi:10.1234/abc')
        return 'doi:10.1234/abc', dict(ARTICLE)

    def http_get(url, tries=4):
        downloads.append(url)
        return page
    monkeypatch.setattr(papers, 'resolve', resolve)
    monkeypatch.setattr(web, 'http_get', http_get)
    return downloads, page


def test_add_names_the_file_by_its_metadata(project, shelf, online):
    report = lit.add(['10.1234/abc'], 'обратная задача для оператора с инволюцией и её отличие от нашей')
    assert 'S3' in report[0] and 'PDF открытого доступа' in report[0]
    assert library_files(shelf) == [NAME + '.pdf']
    assert (shelf / '.lit' / 'text' / (NAME + '.txt')).exists()
    row = registry.by_code(registry.load(), 'S3')
    assert row['filename'] == NAME + '.pdf' and row['pages'] == 2
    entry = library.find('10.1234/abc')
    assert entry['filename'] == NAME + '.pdf' and entry['sha256'] == row['sha256']
    assert 'code' not in entry and 'role' not in entry  # опись хранит работу, а не связь с проектом
    assert f'PDF: `{NAME}.pdf`' in (project / 'sources' / 'catalog.md').read_text(encoding='utf-8')


def test_second_project_takes_the_file_from_the_library(project, shelf, online, tmp_path):
    downloads, _ = online
    lit.add(['10.1234/abc'], 'первый проект берёт оценку резольвенты из этой работы')
    other = make_project(tmp_path / 'other', [])
    lit.configure(other, shelf)
    report = lit.add(['10.1234/abc'], 'второй проект сравнивает постановку обратной задачи')
    assert 'из библиотеки' in report[0]
    assert len(downloads) == 1
    assert library_files(shelf) == [NAME + '.pdf']
    assert len(library.load()) == 1
    assert registry.by_code(registry.load(), 'S1')['filename'] == NAME + '.pdf'


def test_add_without_a_project_fills_the_library_only(shelf, online):
    report = lit.add(['10.1234/abc'])
    assert report[0].startswith(NAME)
    assert library_files(shelf) == [NAME + '.pdf']


def test_project_requires_a_role(project, online):
    with pytest.raises(SystemExit, match='role'):
        lit.add(['10.1234/abc'])


def test_inbox_renames_the_file_and_attaches_it_to_the_project(project, shelf, online, monkeypatch):
    rows = registry.load()
    rows.append(dict(code='S3', **{key: ARTICLE[key] for key in ('authors', 'title', 'year', 'version', 'url', 'doi')},
                     role='работа без открытого PDF'))
    registry.save(rows)
    _, page = online
    monkeypatch.setattr(web, 'http_get', lambda url, tries=4: pytest.fail('inbox не скачивает'))
    (shelf / 'inbox').mkdir(parents=True)
    (shelf / 'inbox' / 'download (3).pdf').write_bytes(page)
    report = lit.inbox()
    assert report[0] == f'download (3).pdf → {NAME}.pdf; прикреплён к S3'
    assert list((shelf / 'inbox').iterdir()) == []
    assert registry.by_code(registry.load(), 'S3')['filename'] == NAME + '.pdf'
    # Тот же файл ещё раз: дубль убирается из inbox, в библиотеке один файл
    (shelf / 'inbox' / 'again.pdf').write_bytes(page)
    assert 'уже в библиотеке' in lit.inbox()[0]
    assert list((shelf / 'inbox').iterdir()) == [] and library_files(shelf) == [NAME + '.pdf']


def test_inbox_leaves_unknown_and_mismatched_files(shelf, monkeypatch):
    (shelf / 'inbox').mkdir(parents=True)
    (shelf / 'inbox' / 'scan.pdf').write_bytes(pdf_bytes('no identifiers at all\n' + LONG))
    unrelated = ' '.join(['Asymptotics of orthogonal polynomials on the unit circle.'] * 12)
    (shelf / 'inbox' / 'other.pdf').write_bytes(pdf_bytes('A different paper\ndoi:10.1234/abc\n' + unrelated))
    monkeypatch.setattr(papers, 'resolve', lambda ident: ('doi:10.1234/abc', dict(ARTICLE)))
    report = '\n'.join(lit.inbox())
    assert 'scan.pdf: не опознан' in report
    assert 'other.pdf: в тексте найден 10.1234/abc' in report and 'не встречается' in report
    assert sorted(path.name for path in (shelf / 'inbox').iterdir()) == ['other.pdf', 'scan.pdf']
    # Человек подтверждает работу: файл берётся
    report = lit.inbox([str(shelf / 'inbox' / 'other.pdf')], '10.1234/abc')
    assert report[0] == f'other.pdf → {NAME}.pdf'
    assert library_files(shelf) == [NAME + '.pdf']


def test_migrate_moves_an_old_project_into_the_library(tmp_path, shelf):
    rows = [dict(code='S1', title='Возмущения самосопряженных операторов', authors='А. А. Шкаликов',
                 version='Успехи матем. наук 71:5(431) (2016), 113–174', url='https://doi.org/10.4213/rm9740',
                 mathnet='rm9740', filename='Shkalikov-rm9740.pdf', tex='Shkalikov-rm9740.tex',
                 tex_origin='transcription', role='обзор'),
            dict(code='S2', title='Closed paper', authors='X. Author', version='J. (2001)', url='https://e.org',
                 filename='S2.pdf', role='нет файла')]
    root = make_project(tmp_path / 'old', rows, toml='[sources]\nregistry = "sources/papers.json"\n')
    old = root / 'output' / 'literature'
    (old / 'parts' / 'Shkalikov-rm9740').mkdir(parents=True)
    (old / 'Shkalikov-rm9740.pdf').write_bytes(pdf_bytes(LONG))
    (old / 'Shkalikov-rm9740.tex').write_text('\\documentclass{article}\n', encoding='utf-8')
    (old / 'Shkalikov-rm9740.txt').write_text(LONG, encoding='utf-8')
    (old / 'parts' / 'Shkalikov-rm9740' / 'p0001-0002.tex').write_text('часть', encoding='utf-8')
    lit.configure(root, shelf)
    report = '\n'.join(lit.migrate())
    stem = 'Shkalikov 2016 - Vozmushcheniya samosopryazhennykh operatorov'
    assert library_files(shelf) == [stem + '.pdf', stem + '.tex']
    assert (shelf / '.lit' / 'text' / (stem + '.txt')).exists()
    assert (shelf / '.lit' / 'parts' / stem / 'p0001-0002.tex').exists()
    saved = {row['code']: row for row in json.loads((root / 'sources' / 'papers.json').read_text(encoding='utf-8'))}
    assert (saved['S1']['filename'], saved['S1']['tex']) == (stem + '.pdf', stem + '.tex')
    assert saved['S2']['filename'] == 'Author 2001 - Closed paper.pdf'  # файла нет, но имя выдано: fetch скачает
    assert 'S1: Shkalikov-rm9740.pdf → ' in report
    assert (old / 'Shkalikov-rm9740.pdf').exists()  # копия: старая папка не тронута
    assert 'Переносить нечего' in lit.migrate()[0]
    assert library.find('mathnet:rm9740')['tex'] == stem + '.tex'


def test_one_index_for_two_projects_and_search_stays_in_the_project(project, shelf, online, tmp_path):
    lit.add(['10.1234/abc'], 'первый проект берёт оценку резольвенты из этой работы')
    found = lit.search_texts('Riesz bases involution', k=3)
    assert found.startswith('#') and ' S3 Bondarenko' in found.split('\n')[0]
    other = make_project(tmp_path / 'other', [])
    lit.configure(other, shelf)
    assert lit.search_texts('Riesz bases involution') == 'Ничего не найдено.'
    lit.add(['10.1234/abc'], 'второй проект сравнивает постановку обратной задачи')
    assert lit.index_texts() == []  # работа уже проиндексирована первым проектом
    assert ' S1 Bondarenko' in lit.search_texts('Riesz bases involution', k=1)
    lit.configure(None, shelf)
    assert lit.search_texts('Riesz bases involution', k=1).startswith('#1 ' + NAME) or NAME in \
        lit.search_texts('Riesz bases involution', k=1)


def test_cli_where_and_library(shelf, online, capsys):
    lit.main(['--no-project', '--library', str(shelf), 'add', '10.1234/abc'])
    lit.main(['--no-project', '--library', str(shelf), 'library'])
    out = capsys.readouterr().out
    assert NAME in out and 'doi:10.1234/abc' in out
    assert paths.LIBRARY == shelf.resolve()


def old_project(tmp_path):
    rows = [dict(code='S1', title='First paper', authors='A. Author', version='J. (2010)', url='https://e.org/1',
                 filename='one.pdf', role='r'),
            dict(code='S2', title='Second paper', authors='B. Writer', version='J. (2011)', url='https://e.org/2',
                 filename='two.pdf', role='r')]
    root = make_project(tmp_path / 'old', rows)
    old = root / 'output' / 'literature'
    old.mkdir(parents=True)
    (old / 'one.pdf').write_bytes(pdf_bytes(LONG))
    (old / 'two.pdf').write_bytes(pdf_bytes(LONG + ' two'))
    return root


def saved_names(root):
    rows = json.loads((root / 'sources' / 'papers.json').read_text(encoding='utf-8'))
    return {row['code']: row['filename'] for row in rows}


def test_migrate_dry_run_changes_nothing_and_a_real_run_follows(tmp_path, shelf):
    root = old_project(tmp_path)
    lit.configure(root, shelf)
    report = '\n'.join(lit.migrate(dry_run=True))
    assert 'S1: one.pdf → Author 2010 - First paper.pdf' in report
    assert not shelf.exists()  # библиотека даже не создана
    assert saved_names(root) == {'S1': 'one.pdf', 'S2': 'two.pdf'}
    lit.migrate()
    assert library_files(shelf) == ['Author 2010 - First paper.pdf', 'Writer 2011 - Second paper.pdf']


def test_migrate_keeps_a_row_whose_file_could_not_be_written(tmp_path, shelf, monkeypatch):
    root = old_project(tmp_path)
    lit.configure(root, shelf)
    real_put = migration._put

    def failing_put(source, target, move):
        if source.name == 'one.pdf':
            raise FileNotFoundError(3, 'path too long', str(target))
        real_put(source, target, move)

    monkeypatch.setattr(migration, '_put', failing_put)
    report = '\n'.join(lit.migrate())
    assert 'S1: ОШИБКА' in report
    assert saved_names(root) == {'S1': 'one.pdf', 'S2': 'Writer 2011 - Second paper.pdf'}
    monkeypatch.setattr(migration, '_put', real_put)
    lit.migrate()
    assert saved_names(root)['S1'] == 'Author 2010 - First paper.pdf'
