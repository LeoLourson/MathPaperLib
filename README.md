# MathPaperLib

[Русская версия](README.ru.md)

MathPaperLib keeps the papers you work with in one folder, `~/Literature`, under names such as
`Bondarenko 2021 - Inverse spectral problems for functional-differential operators with involution.pdf`,
and gives an AI agent tools to find papers, download them, read them page by page and search
their full texts. The tools run as an MCP server, which any agent harness with MCP support can
start, and as the `lit` command.

arXiv and Math-Net.Ru serve files under identifiers (`2107.12209v1.pdf`, `rm9740.pdf`), so a
folder of downloads cannot be read by eye. A PDF saved by hand from a publisher's site keeps the
name the site gave it, and the tool that fetched the other papers knows nothing about it. When
every project keeps its own papers, a paper used by two projects is downloaded and indexed twice.

MathPaperLib keeps one library per user. Each paper is stored once, under a name built from its
authors, year and title. A PDF downloaded by hand goes into the inbox folder, where it is
identified from its first pages and filed under the same rule. A project keeps only its registry,
the list of papers it uses with their roles, and reads the files from the library. Full-text
search covers LaTeX sources and the text layers of PDFs; it combines BM25 with the multilingual
embedding model `intfloat/multilingual-e5-small`, run on the CPU.

## The library

```
~/Literature/
  Bondarenko 2021 - Inverse spectral problems for functional-differential operators with involution.pdf
  Bondarenko 2021 - Inverse spectral problems for functional-differential operators with involution.tex
  Shkalikov 2016 - Vozmushcheniya samosopryazhennykh i normalnykh operatorov s diskretnym spektrom.pdf
  library.json
  inbox/
  .lit/
```

`library.json` records the metadata of every paper, its identifiers (arXiv, DOI, Math-Net.Ru),
the names of its files and their SHA-256 checksums. `.lit/` holds what is derived from the
papers: text layers of PDFs, rendered pages, parts of transcriptions and the search index. To keep
the library elsewhere, set `MATHPAPERLIB_HOME` or pass `--library`.

A file is named `Authors Year - Title`. One or two authors are listed by surname, three or more
give `First et al.`; the year comes from the metadata, or else from the arXiv identifier.
Cyrillic is transliterated and accents are removed, so every name is ASCII. Characters that
Windows, macOS or Linux forbid in file names are replaced, a name longer than 140 characters is
cut at a word, and a name already taken gets ` (2)`. The name is given when the paper enters the
library and does not change afterwards.

## The inbox

Put a PDF you downloaded into `inbox/` and run `lit inbox`, or let the agent call the `inbox`
tool. The identifier is looked for in this order: an arXiv number in the file name, an arXiv
number in the text of the first two pages, a DOI in the same text. Since the first DOI on a page
may belong to a cited paper, the identifier is accepted only when at least 60 % of the title
words of four letters or more occur on those pages. The accepted file moves into the library
under its name and is indexed; in a project it is also attached to the registry entry with the
same identifier, if that entry has no file yet. A file that is not identified stays in the inbox
with the reason, and `lit inbox FILE --id DOI` takes it under the identifier you give.

## Projects

A project is a folder with `sources/papers.json` or a `[sources]` table in `project.toml`. Its
registry gives every paper a code `S1, S2, …`, the role of the paper in the project, a checked
description and the status of its theorem cards; `lit catalog` builds `sources/catalog.md` from
the registry. Search inside a project is limited to the papers of its registry. Every key of the
table below is optional:

```toml
[sources]
registry = "sources/papers.json"
catalog = "sources/catalog.md"
cards = "sources/cards"            # theorem cards S*.md, `verified:` in the header
results = "sources/results.md"
library = "output/literature"      # a library of this project only
direct_hosts = ["mathnet.ru"]      # hosts reached past the VPN tunnel
```

Requests to a host from `direct_hosts` go out from the address of a network interface other than
the default route, that is, past a VPN tunnel; the default list is `mathnet.ru`.

The project is taken from `--root`, else from `MATHPAPERLIB_PROJECT`, else it is the nearest
project up from the current folder. With `--no-project`, or when no project is found, the tools
work on the library alone; the MCP tool `use_project` selects a project during a session.

A project made with the `lit.py` of the AutoMath research template keeps its files in
`output/literature/` under identifier names. `lit migrate` copies them into the library under new
names together with their text layers and transcription parts, then rewrites the registry. The
old folder stays until you delete it; with `--move` the files are moved instead. `--dry-run`
lists what would be moved and changes nothing: a trial run without it already rewrites the
registry, and a second run then finds nothing to move.

## Installation

The package runs with [uv](https://docs.astral.sh/uv/). The first start of the MCP server, or the first
indexing or search from the command line, downloads the embedding model from Hugging Face,
about 470 MB; the server begins to answer only after the download ends.

Command line:

```
uv tool install git+https://github.com/LeoLourson/MathPaperLib
lit where
```

The MCP server is started by
`uvx --from git+https://github.com/LeoLourson/MathPaperLib mathpaperlib mcp` and talks over stdio.

- Claude Code: `/plugin marketplace add LeoLourson/MathPaperLib`, then
  `/plugin install mathpaperlib@mathpaperlib`. The plugin adds the MCP server and two skills,
  `literature` and `transcribe-paper`.
- DSH: the bundle `dsh-mathpaperlib` lives in [`dsh/`](dsh/). Link it into `node_modules` of a
  profile and add it to `dependencies` and to `dsh.profile.bundles`. It adds the MCP server, the
  two skills and a prompt section with the path of the library and the number of PDFs waiting in
  its inbox. To run a local checkout instead of the GitHub version, override the entry
  `mcp-mathpaperlib` in the profile patch with `command: uv` and
  `args: [run, --directory, <checkout>, lit, --no-project, mcp]`.
- Codex, in `~/.codex/config.toml`:

  ```toml
  [mcp_servers.mathpaperlib]
  command = "uvx"
  args = ["--from", "git+https://github.com/LeoLourson/MathPaperLib", "mathpaperlib", "mcp"]
  ```

- Any other MCP client: the same command. The skills in [`skills/`](skills/) are plain `SKILL.md`
  files; copy them where the harness reads instructions, or into `AGENTS.md`.

## Commands

| Command | What it does |
| --- | --- |
| `find "query" [--in zbmath\|arxiv\|mathnet\|crossref\|openalex\|s2\|all]` | candidates with abstracts; papers already in the project or the library are marked |
| `doi 10.xxxx/...` | journal, volume, pages, authors, abstract, open PDF |
| `cites REF [--refs]` | papers citing a paper, or its reference list |
| `add ID... [--role "..."]` | download into the library; in a project, also add to the registry, where the role is required |
| `inbox [FILE...] [--id ID]` | take PDFs from the inbox |
| `attach REF FILE` | attach a file obtained by hand |
| `add-file FILE --title --authors --version --url` | add a paper that has no arXiv number, DOI or Math-Net.Ru id |
| `search "query" [--code S4] [--kind theorem]`, `show N [-n 1]` | full-text search; a chunk by its number, with neighbours |
| `pdf REF`, `pages REF [--range 3-10]` | the PDF; pages as PNG with their text layer |
| `parts REF`, `tex REF [--build]` | transcription of a PDF into LaTeX by parts, then assembly and a pdflatex check |
| `annotate FILE.json`, `audit` | descriptions of the papers of a project, and their check |
| `fetch [CODE...]`, `catalog`, `index` | restore missing files, rebuild the catalog, index new texts |
| `list`, `library`, `where` | papers of the project, the inventory of the library, the paths in use |
| `migrate [--from DIR] [--move] [--dry-run]` | move a project of the old layout into the library |
| `mcp` | the MCP server on stdio |

`REF` is a registry code (`S4`), an identifier, or the beginning of a file name in the library.
The MCP server offers the same actions as tools.

## Limits

Only open copies are downloaded: arXiv sources and PDFs, Math-Net.Ru PDFs with open full text,
and the open-access PDF that OpenAlex knows for a DOI. For any other paper `add` records the
metadata, and the PDF comes through the inbox or `attach`.

The inbox recognises a paper only by an arXiv number or a DOI. A scan without a text layer, or a
paper whose first two pages carry neither, stays in the inbox until it is named with `--id`.

Titles are transliterated, not translated: a paper in Russian gets its Russian title in Latin
letters even when an English title is known. An author given by initials alone appears in the
name as those initials.

Messages of the tool are in Russian; descriptions of the MCP tools and the skills are in English.

## Development

```
uv sync
uv run pytest
node dsh/test/smoke.mjs
```

The tests need neither the network nor the model. License: MIT.
