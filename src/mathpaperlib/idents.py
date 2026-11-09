"""Идентификаторы работ: arXiv, MathNet и DOI, их нормальная форма и ключи.

Ключ — строка `arxiv:2107.12209` (без версии), `mathnet:rm9740` или `doi:10.1070/rm9740`
(DOI в нижнем регистре). По ключам реестр проекта и опись библиотеки узнают одну и ту же
работу, пришла ли она по ссылке, по DOI или файлом из `inbox/`.
"""
from __future__ import annotations

import re


def classify(ident: str) -> tuple[str, str]:
    """Вид идентификатора и его нормальная форма: arxiv, mathnet или doi."""
    text = ident.strip()
    match = (re.search(r'mathnet\.ru/(?:rus/|eng/)?([a-z]+\d+)\b', text)
             or re.fullmatch(r'(?i)(?:mathnet:|mi\s+)([a-z]+\d+)', text))
    if match:
        return 'mathnet', match.group(1).lower()
    match = re.search(r'jrnid=([a-z]+)&(?:amp;)?paperid=(\d+)', text)
    if match:
        return 'mathnet', match.group(1) + match.group(2)
    doi = re.sub(r'(?i)^(doi:\s*|https?://(dx\.)?doi\.org/)', '', text)
    if doi.startswith('10.'):
        if doi.lower().startswith('10.4213/'):  # DOI журналов MathNet: суффикс — идентификатор статьи
            return 'mathnet', doi.split('/', 1)[1].lower()
        if doi.lower().startswith('10.48550/arxiv.'):
            return 'arxiv', doi[len('10.48550/arxiv.'):]
        return 'doi', doi
    match = re.search(r'arxiv\.org/(?:abs|pdf)/([^\s?#]+?)(?:\.pdf)?$', text)
    if match:
        return 'arxiv', match.group(1)
    if re.fullmatch(r'(?i)(arxiv:)?(\d{4}\.\d{4,5}|[a-z-]+(\.[a-z]{2})?/\d{7})(v\d+)?', text):
        return 'arxiv', re.sub(r'(?i)^arxiv:', '', text)
    if re.fullmatch(r'[a-z]+\d+', text):
        return 'mathnet', text
    raise ValueError(f'не распознан идентификатор «{ident}»: нужен arXiv, mathnet:… или DOI')


def bare(ident: str) -> str:
    """Номер arXiv без префикса и версии."""
    return re.sub(r'v\d+$', '', re.sub(r'(?i)^arxiv:', '', ident.strip()))


def key_of(kind: str, value: str) -> str:
    return f'{kind}:{bare(value) if kind == "arxiv" else value.lower()}'


def arxiv_id(record: dict) -> str | None:
    version = record.get('version', '')
    return version[6:] if version.startswith('arXiv:') else None


def dois_of(record: dict) -> list[str]:
    found = [record.get('doi'), record.get('doi_en')]
    match = re.search(r'doi\.org/(.+)$', record.get('url', '') or '')
    return [doi.lower() for doi in found + [match.group(1) if match else None] if doi]


def keys(record: dict) -> set[str]:
    """Все ключи записи реестра или описи: arXiv, MathNet, DOI (русский и английский)."""
    found = set()
    if arxiv_id(record):
        found.add('arxiv:' + bare(arxiv_id(record)))
    if record.get('mathnet'):
        found.add('mathnet:' + record['mathnet'])
    found |= {'doi:' + doi for doi in dois_of(record)}
    return found


def found_keys(paper: dict) -> list[tuple[str, str]]:
    """Ключи и подписи работы из выдачи поиска (поля arxiv, mathnet, doi)."""
    pairs = [('arxiv:' + bare(paper['arxiv']), 'arXiv:' + paper['arxiv']) if paper.get('arxiv') else None,
             ('mathnet:' + paper['mathnet'], 'mathnet:' + paper['mathnet']) if paper.get('mathnet') else None,
             ('doi:' + paper['doi'].lower(), 'DOI:' + paper['doi']) if paper.get('doi') else None]
    return [pair for pair in pairs if pair]


# Идентификаторы в тексте PDF: по ним опознаётся файл из inbox/
ARXIV_IN_TEXT = re.compile(r'arXiv:\s*((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?)')
ARXIV_IN_NAME = re.compile(r'^((?:\d{4}\.\d{4,5})(?:v\d+)?)$')
DOI_IN_TEXT = re.compile(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9<>\[\]]+)')


def in_text(text: str, name: str = '') -> str | None:
    """Первый надёжный идентификатор работы: номер arXiv в имени файла, arXiv в тексте, DOI в тексте."""
    match = ARXIV_IN_NAME.match(name)
    if match:
        return 'arXiv:' + match.group(1)
    match = ARXIV_IN_TEXT.search(text)
    if match:
        return 'arXiv:' + match.group(1)
    match = DOI_IN_TEXT.search(text)
    if match:
        return match.group(1).rstrip('.,;)]>')
    return None
