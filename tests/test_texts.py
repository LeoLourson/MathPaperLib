"""Разбор идентификаторов, страниц MathNet, исходников arXiv и нарезка текстов — без сети."""
import pytest

from mathpaperlib import idents, lit


def test_identifiers():
    cases = {
        '2107.12209v2': ('arxiv', '2107.12209v2'),
        'arXiv:math/0601001': ('arxiv', 'math/0601001'),
        'https://arxiv.org/abs/0906.2631v1': ('arxiv', '0906.2631v1'),
        'mathnet:rm9740': ('mathnet', 'rm9740'),
        'https://www.mathnet.ru/rus/mzm12557': ('mathnet', 'mzm12557'),
        'https://www.mathnet.ru/php/archive.phtml?wshow=paper&jrnid=sm&paperid=1167': ('mathnet', 'sm1167'),
        '10.4213/rm9740': ('mathnet', 'rm9740'),
        'https://doi.org/10.1070/RM9740': ('doi', '10.1070/RM9740'),
        'doi: 10.1070/RM9740': ('doi', '10.1070/RM9740'),
        '10.48550/arXiv.2107.12209': ('arxiv', '2107.12209'),
    }
    for given, expected in cases.items():
        assert lit.classify(given) == expected, given
    with pytest.raises(ValueError):
        lit.classify('теорема Маркуса')


def test_identifier_in_pdf_text():
    assert idents.in_text('', '2107.12209v1') == 'arXiv:2107.12209v1'
    assert idents.in_text('header arXiv:math/0601001v2 [math.SP] 3 Jan 2006', 'paper') == 'arXiv:math/0601001v2'
    assert idents.in_text('Journal 12 (2020). doi:10.1016/j.jde.2022.02.027.\nAbstract', 'x') == \
        '10.1016/j.jde.2022.02.027'
    assert idents.in_text('no identifiers here', 'scan') is None


def test_amsbib():
    page = ('<div class=showamsbib><code>\\RBibitem{Shk16}<br />\n\\by А.~А.~Шкаликов<br />\n'
            '\\paper Возмущения операторов с~дискретным спектром<br />\n\\jour УМН<br />\n\\yr 2016<br />\n'
            '\\vol 71<br />\n\\issue 5(431)<br />\n\\pages 113--174<br />\n'
            '\\crossref{https://doi.org/10.4213/rm9740}<br />\n\\transl<br />\n\\jour Russian Math. Surveys<br />\n'
            '\\pages 907--964<br />\n\\crossref{https://doi.org/10.1070/RM9740}<br />\n</code></div>')
    fields = lit.amsbib(page)
    assert fields['by'] == 'А. А. Шкаликов'
    assert fields['paper'] == 'Возмущения операторов с дискретным спектром'
    assert (fields['pages'], fields['pages_en']) == ('113–174', '907–964')
    assert fields['crossref_en'] == 'https://doi.org/10.1070/RM9740'


def test_flatten_inlines_inputs_and_bibliography():
    files = {
        'main.tex': b'\\documentclass{article}\n\\begin{document}\n% note\n\\input{sec/one}\n'
                    b'\\bibliography{refs}\n\\end{document}\n',
        'sec/one.tex': b'First section. % trailing\n',
        'main.bbl': b'\\begin{thebibliography}{1}\\bibitem{a} A.\\end{thebibliography}\n',
    }
    text = lit.flatten(files)
    assert 'First section.' in text
    assert 'note' not in text and 'trailing' not in text
    assert '\\bibitem{a}' in text


def test_chunks_keep_printed_numbers_and_pages():
    text = (lit.PREAMBLE + '\\begin{document}\n\\section{Базисы}\n\\pagemark{140}\n'
            '\\begin{statement}{Теорема}{6.6}\nПусть $T$ --- нормальный оператор порядка $\\alpha$. '
            'Тогда корневые векторы образуют безусловный базис со скобками.\n\\end{statement}\n\n'
            '\\begin{proof}\nДостаточно оценить резольвенту вне углов, содержащих лучи спектра.\n\\end{proof}\n'
            '\\pagemark{141}\nЗамечание 6.7. Условие на порядок нельзя ослабить, как показывает пример '
            'оператора умножения.\n\\end{document}\n')
    chunks = lit.tex_chunks(text)
    assert [(c['kind'], c['label'], c['page']) for c in chunks] == \
        [('Theorem', 'Теорема 6.6', '140'), ('Proof', '', '140'), ('Remark', 'Замечание 6.7', '141')]
    assert chunks[0]['section'] == 'Базисы'


def test_lint_reports_mechanical_problems():
    text = (lit.PREAMBLE + '\\begin{document}\n\\pagemark{1}\n\\begin{statement}{Лемма}{1}\n$a_{n$\n'
            '\\unsure{x}\n\\end{document}\n')
    notes = '\n'.join(lit.lint_tex(text, pages=2))
    for expected in ('statement', 'фигурные скобки', 'меток \\pagemark: 1, страниц в PDF: 2', '(\\unsure): 1'):
        assert expected in notes
    clean = lit.PREAMBLE + '\\begin{document}\n\\pagemark{1}\nТекст.\n\\end{document}\n'
    assert lit.lint_tex(clean, pages=1) == []


def test_text_layer_headings_start_chunks():
    page = ('Введение, в котором нет утверждений, но есть достаточно длинный текст для отдельного куска.\n'
            'Theorem 4.1. Let $a$ be even. Then the eigenfunctions form a Riesz basis in $L_2(-1,1)$.\n')
    chunks = lit.txt_chunks(page)
    assert [(c['kind'], c['label'], c['loc']) for c in chunks] == [('page', '', 1), ('Theorem', 'Theorem 4.1', 1)]


def test_page_range():
    from mathpaperlib import store
    assert store.page_range('') == (1, None)
    assert store.page_range('5') == (5, 5)
    assert store.page_range('5-') == (5, None)
    assert store.page_range('-10') == (1, 10)
    with pytest.raises(SystemExit):
        store.page_range('10-5')
