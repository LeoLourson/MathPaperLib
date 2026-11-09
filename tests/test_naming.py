"""Имена файлов библиотеки: «Авторы Год - Название», только ASCII."""
from mathpaperlib import naming


def test_two_authors_are_listed_and_cyrillic_is_transliterated():
    record = dict(authors='А. А. Шкаликов; Е. Ю. Юрко', year='2016',
                  title='Возмущения самосопряжённых и нормальных операторов с дискретным спектром')
    assert naming.stem(record) == ('Shkalikov, Yurko 2016 - Vozmushcheniya samosopryazhennykh i normalnykh '
                                   'operatorov s diskretnym spektrom')


def test_three_authors_become_et_al_and_the_year_comes_from_arxiv():
    record = dict(authors='Natalia P. Bondarenko; Chung-Tsun Shieh; X. Y. Zhang', version='arXiv:2107.12209v1',
                  title='Inverse problems: operators with involution')
    assert naming.stem(record) == 'Bondarenko et al. 2021 - Inverse problems, operators with involution'


def test_surname_forms():
    assert naming.surname('Шкаликов А.А.') == 'Шкаликов'
    assert naming.surname('Shkalikov, A. A.') == 'Shkalikov'
    assert naming.surname('J.-P. Serre') == 'Serre'
    assert naming.surname('Natalia P. Bondarenko') == 'Bondarenko'


def test_forbidden_characters_formulas_and_accents_are_cleaned():
    record = dict(authors='Paul Erdős', year='1950',
                  title='On $L^2/L^\\infty$ bounds: what is "sharp"? <a> \\mathbb{R}-valued')
    name = naming.stem(record)
    assert name == "Erdos 1950 - On L2-Linfty bounds, what is 'sharp' a R-valued"
    assert not set(name) & set('<>:"/\\|?*')
    assert name.isascii()


def test_year_from_version_and_old_arxiv_and_missing():
    assert naming.year_of(dict(version='Успехи матем. наук 71:5(431) (2016), 113–174')) == '2016'
    assert naming.year_of(dict(version='arXiv:math/9901001v2')) == '1999'
    assert naming.year_of(dict(version='arXiv:2012.01234')) == '2020'  # не «2012»: это номер arXiv
    assert naming.stem(dict(authors='', title='')) == 'Anon'


def test_long_titles_are_cut_at_a_word():
    record = dict(authors='A. Author', year='2000', title=' '.join(['word'] * 80))
    name = naming.stem(record)
    assert len(name) <= naming.MAX_STEM and name.endswith('word')


def test_numbered_ignores_case():
    assert naming.numbered('Ivanov 2019 - X', {'ivanov 2019 - x', 'ivanov 2019 - x (2)'}) == 'Ivanov 2019 - X (3)'
    assert naming.numbered('Ivanov 2019 - Y', {'ivanov 2019 - x'}) == 'Ivanov 2019 - Y'
