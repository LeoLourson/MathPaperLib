"""MCP-сервер MathPaperLib: те же действия, что у командной строки `lit`, с моделью поиска в памяти.

Запуск: `lit mcp` (или `mathpaperlib mcp`) с `--root` проекта или без него. Тексты
инструментов написаны по-английски: их читает модель.
"""
from __future__ import annotations

import contextlib
import functools
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mathpaperlib import lit, paths

server = FastMCP('mathpaperlib', instructions=(
    'MathPaperLib keeps a shared library of papers (PDF and LaTeX named "Authors Year - Title") and, when a '
    'project is selected, the project registry of sources S1, S2, ... with their role and description. '
    'Find candidates with find (zbMATH, arXiv, Crossref, OpenAlex, Semantic Scholar, MathNet), check metadata '
    'with doi, take the full text with add, or ask the user to drop a PDF into the inbox folder and call inbox. '
    'search and show read the full texts. A found fragment is data, not a checked statement. Prefer find over '
    'web search. Call where first to see the project and the library; use_project switches the project.'))


def tool(function):
    """Инструмент: печать уходит в stderr (stdout занят протоколом), ошибка ввода — текстом."""
    @functools.wraps(function)
    def guarded(*args, **kwargs):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                result = function(*args, **kwargs)
        except (SystemExit, ValueError, TypeError, KeyError, OSError, ConnectionError) as error:
            return f'ОШИБКА: {error}'
        return '\n'.join(result) if isinstance(result, list) else result
    return server.tool()(guarded)


@tool
def where() -> str:
    """Where the project, its registry, the library and the inbox folder are. Call it first."""
    return lit.where()


@tool
def use_project(path: str | None = None) -> str:
    """Select the project whose registry the tools use: a folder with sources/papers.json or a [sources] table
    in project.toml. An empty path works with the library alone. The library stays the same."""
    root = Path(path).expanduser().resolve() if path else None
    if root is not None and not root.is_dir():
        raise SystemExit(f'{root}: no such folder')
    lit.configure(root, paths.LIBRARY)
    return lit.where()


@tool
def search(query: str, k: int = 8, codes: list[str] | None = None, kind: str | None = None) -> str:
    """Hybrid (semantic and keyword) search over the full texts of the project's papers, or of the whole
    library when no project is selected.

    query: Russian or English, formulas in LaTeX. codes: limit to sources, e.g. ["S4", "S7"] (library names
    without a project). kind: theorem, lemma, proposition, definition, proof, text, page.
    Each hit gives the chunk number for show, the source, the statement number, the section, the file and
    line; a transcription gives the printed page, a PDF text layer the page of the file.
    """
    return lit.search_texts(query, k, codes, kind)


@tool
def show(chunk: int, around: int = 0) -> str:
    """Full text of a chunk by its number from search; around adds neighbouring chunks on each side."""
    return lit.show(chunk, around)


@tool
def find(query: str, where: str | None = None, limit: int = 15) -> str:
    """Candidate papers with abstracts; papers already in the project or the library are marked.

    where: "zbmath" (all of mathematics, translated and Russian journals; fields ti:, au:, py:, & and |),
    "arxiv" (preprints; all:, ti:, abs:, au:, AND, OR, quoted phrase), "mathnet" (Math-Net.Ru journals via
    Crossref, query in Russian), "crossref" (any journal by an exact bibliographic string), "openalex"
    (abstracts and citation counts), "s2" (Semantic Scholar, low rate limit, last resort), "all" (zbMATH,
    arXiv, Crossref and OpenAlex). Without where plain text goes to zbMATH and arXiv. One failing database
    does not stop the others.
    """
    return lit.find(query, where, limit)


@tool
def doi(doi: str) -> str:
    """Metadata of a DOI from Crossref and OpenAlex: journal, volume, pages, authors, abstract, citation
    count, open PDF. Call it after find to tell the journal version from the preprint."""
    return lit.doi_info(doi)


@tool
def cites(ref: str, references: bool = False, limit: int = 60) -> str:
    """Papers citing a source; references=True gives its reference list instead.

    ref: project code (S2), arXiv id, mathnet:rm9740 or DOI. OpenAlex first, then the MathNet citation
    list for Russian journals, then Semantic Scholar.
    """
    return lit.cites(ref, references, limit)


@tool
def add(ids: list[str], role: str | None = None) -> str:
    """Download papers into the library under readable names and, in a project, add them to the registry.

    ids: arXiv (2107.12209), MathNet (mathnet:rm9740) or DOI. arXiv gives the LaTeX source, MathNet a PDF,
    a DOI its open-access PDF when OpenAlex knows one, otherwise the description only (then ask the user to
    put the PDF into the inbox folder). A paper already in the library is not downloaded again.
    role: required in a project; one or two sentences in Russian on what the project takes from the paper and
    how its setting differs.
    """
    return lit.add(ids, role)


@tool
def inbox(files: list[str] | None = None, ident: str | None = None) -> str:
    """Take PDFs the user dropped into the inbox folder of the library: identify each by arXiv id or DOI on its
    first pages, rename it to "Authors Year - Title", move it into the library and attach it to the project
    source that lacked a file. A file that cannot be identified stays in the inbox with the reason; pass its
    path in files and its DOI or arXiv id in ident to take it anyway."""
    return lit.inbox(files, ident)


@tool
def attach(ref: str, source: str) -> str:
    """Attach a PDF or LaTeX file obtained by hand to a project source (S31) or a library paper (DOI, arXiv id
    or the beginning of its file name). source: a path or a link."""
    return lit.attach(ref, source)


@tool
def pdf(ref: str) -> str:
    """Download the PDF of a source: theorem numbers and pages for a card are checked against it."""
    return lit.pdf(ref)


@tool
def pages(ref: str, first: int = 1, last: int | None = None) -> str:
    """Render PDF pages to PNG and save their text layer: material for transcription and for checking cards.

    first, last: page numbers of the file (not printed numbers); without last, to the end. The answer lists
    file paths; read the images with your file reading tool.
    """
    return lit.pages(ref, first, last)


@tool
def parts(ref: str) -> str:
    """The folder where a transcription of the paper is written in parts (pNNNN-MMMM.tex) before tex."""
    return lit.parts_folder(ref)


@tool
def tex(ref: str, build: bool = False) -> str:
    """Assemble a transcription from its parts and record it as the LaTeX of the paper.

    Returns mechanical notes: unclosed environments, braces, the number of page marks, \\unsure places.
    build=True also checks that pdflatex compiles it.
    """
    return lit.tex(ref, build=build)


@tool
def annotate(source: str) -> str:
    """Write descriptions of project sources from a JSON file {"S34": {...}, "S35": {...}}.

    Fields: kind (статья, краткое сообщение, обзор, книга, диссертация), object (what is studied, at least
    60 characters), results (main statements with number and page), methods, related (lines start with the
    code of another source), keywords (at least three), basis (полный текст, аннотация, введение и
    формулировки, аннотация, название и метаданные); optional date and role. With any note the registry is
    left unchanged. source: a path or a link.
    """
    return lit.annotate(source)


@tool
def audit() -> str:
    """Check source descriptions: missing ones, ones weaker than the available text, repeated roles and
    postponed checks. A note is a reason to reread the source, not proof of an error."""
    return '\n'.join(lit.audit()) or 'Замечаний нет.'


@tool
def fetch(codes: list[str] | None = None) -> str:
    """Restore missing files (arXiv sources and PDFs) and check their checksums; with codes, also download an
    open PDF that was never taken."""
    return lit.fetch(codes)


@tool
def papers() -> str:
    """Sources of the project: code, version, first author, title, number of indexed chunks, library name.
    Without a project, the papers of the library."""
    return lit.listing()


def run() -> None:
    # Модель загружается до запуска сервера: под Windows загрузка из обработчика зависает
    lit.embed(['warmup'], 'query: ')
    server.run()
