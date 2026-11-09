"""Имена файлов библиотеки: «Ivanov, Petrov 2019 - Spectral theory of involutions».

Имя строится из метаданных работы и только из ASCII: кириллица транслитерируется, диакритика
снимается, знаки, запрещённые в именах файлов Windows, заменяются. Два автора перечисляются,
с трёх — «Первый et al.». Года нет — имя без года; названия нет — только авторы и год.
Функции здесь чистые: уникальность имени в библиотеке решает `library`.
"""
from __future__ import annotations

import re
import unicodedata

# Транслитерация по-научному (близко к BGN/PCGN): Шкаликов → Shkalikov, Юрко → Yurko.
CYRILLIC = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e', 'ж': 'zh', 'з': 'z',
    'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r',
    'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh',
    'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'і': 'i', 'ї': 'yi', 'є': 'ye', 'ґ': 'g', 'ў': 'u',
}
# Команды оформления в названии исчезают вместе с именем, остальные остаются словом: \alpha → alpha
FONT_COMMANDS = re.compile(r'\\(?:math[a-z]*|text[a-z]*|emph|operatorname|mbox|rm|bf|it|cal|bb|frak|left|right)\b')
INITIAL = re.compile(r'^(?:\w\.)+(?:-\w\.)*$|^\w$')
MAX_STEM = 140


def translit(text: str) -> str:
    """Кириллица латиницей; регистр первой буквы сохраняется (Щ → Shch)."""
    out = []
    for char in text:
        latin = CYRILLIC.get(char.lower())
        if latin is None:
            out.append(char)
        elif char.isupper():
            out.append(latin[:1].upper() + latin[1:])
        else:
            out.append(latin)
    return ''.join(out)


def ascii_only(text: str) -> str:
    """Латиница без диакритики: é → e, ö → o; тире и кавычки — ASCII; прочее снимается."""
    text = translit(text).translate(str.maketrans({'–': '-', '—': '-', '‐': '-', '−': '-',
                                                   '’': "'", '‘': "'", '«': '', '»': '', '“': '', '”': ''}))
    text = unicodedata.normalize('NFKD', text)
    return ''.join(char for char in text if ord(char) < 128 and not unicodedata.combining(char))


def surname(author: str) -> str:
    """Фамилия из «Natalia P. Bondarenko», «А. А. Шкаликов», «Шкаликов А.А.» или «Shkalikov, A.»."""
    author = ' '.join(author.split())
    if ',' in author:
        return author.split(',')[0].strip()
    words = author.replace('.', '. ').split()
    names = [word for word in words if not INITIAL.match(word)]
    if not names:
        return author
    # «Шкаликов А. А.»: инициалы в конце — фамилия стоит первой
    return names[0] if INITIAL.match(words[-1]) else names[-1]


def authors_part(authors: str) -> str:
    """«Ivanov», «Ivanov, Petrov» или «Ivanov et al.»; авторы в реестре разделены «;»."""
    names = [clean(surname(author)) for author in re.split(r';| and ', authors or '') if author.strip()]
    names = [name for name in names if name]
    if not names:
        return 'Anon'
    return ', '.join(names) if len(names) <= 2 else names[0] + ' et al.'


def year_of(record: dict) -> str:
    """Год: поле year, иначе номер arXiv (2107.12209 → 2021), иначе первое «19xx/20xx» в версии."""
    year = str(record.get('year') or '').strip()
    if re.fullmatch(r'\d{4}', year):
        return year
    version = record.get('version') or ''
    arxiv = re.match(r'arXiv:(?:[a-z-]+(?:\.[A-Z]{2})?/)?(\d{2})(\d{2})', version)
    if arxiv:
        yy = int(arxiv.group(1))
        return str(1900 + yy if yy >= 90 else 2000 + yy)
    found = re.search(r'\b(1[89]\d\d|20\d\d)\b', version)
    return found.group(1) if found else ''


def clean(text: str) -> str:
    """Текст, пригодный для имени файла в Windows, macOS и Linux."""
    text = FONT_COMMANDS.sub('', text or '')
    text = re.sub(r'\\([A-Za-z]+)', r'\1', text).replace('$', '').replace('{', '').replace('}', '')
    text = ascii_only(text)
    text = re.sub(r'\s*[:;]\s*', ', ', text)
    text = re.sub(r'[/\\|]', '-', text)
    text = text.replace('"', "'")
    text = re.sub(r'[<>?*\x00-\x1f^~`]', '', text)
    text = ' '.join(text.split())
    return text.strip(' .,-')


def shorten(text: str, limit: int) -> str:
    """Обрезка по границе слова."""
    if len(text) <= limit:
        return text
    cut = text[:limit + 1].rsplit(' ', 1)[0]
    return (cut if len(cut) >= limit // 2 else text[:limit]).rstrip(' .,-')


def stem(record: dict) -> str:
    """Имя файла без расширения: «Авторы Год - Название»."""
    head = authors_part(record.get('authors') or '')
    year = year_of(record)
    if year:
        head += ' ' + year
    title = clean(record.get('title') or '')
    if not title:
        return head
    return head + ' - ' + shorten(title, max(20, MAX_STEM - len(head) - 3))


def numbered(name: str, taken: set[str]) -> str:
    """Свободное имя: «имя», «имя (2)», «имя (3)»…; сравнение без учёта регистра, как в Windows."""
    if name.lower() not in taken:
        return name
    number = 2
    while f'{name} ({number})'.lower() in taken:
        number += 1
    return f'{name} ({number})'
