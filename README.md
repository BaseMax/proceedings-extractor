# proceedings-extractor

A parallel PDF proceedings extractor that collects article metadata (title, abstract, keywords, page range) from conference proceedings PDFs and exports them to Excel.

Originally designed for **CACNA 2025** — a mathematics conference held at the **University of Kashan** — to produce a structured spreadsheet of all articles so that the Iran government credit system could identify authors and assign publication credits.

---

## Features

- Extracts **title**, **abstract**, **keywords**, **page start**, and **page end** for every article
- Supports both **Persian (Farsi)** and **English** proceedings PDFs simultaneously
- **Parallel page loading** — each thread opens its own PDF handle, no locking overhead
- **Parallel page processing** — all pages processed concurrently with `ThreadPoolExecutor`
- Both PDFs (Persian + English) are processed **fully in parallel** with each other
- **Character-level space detection** — uses raw glyph bounding boxes to reconstruct proper word spacing, fixing the missing-space problem common in tightly-kerned academic PDFs
- Exports a clean `.xlsx` file via `pandas`

---

## Requirements

- Python 3.9+
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [pandas](https://pandas.pydata.org/)
- [openpyxl](https://openpyxl.readthedocs.io/) (Excel writer backend for pandas)

Install all dependencies:

```bash
pip install pdfplumber pandas openpyxl
```

---

## Usage

### As a script

Place your PDF files in the project directory and run:

```bash
python app.py
```

By default it looks for `persian.pdf` and `english.pdf` and writes `out.xlsx`.

### As a module

```python
from app import run

run(
    persian_pdf="persian.pdf",
    english_pdf="english.pdf",
    out="out.xlsx",
    workers=8,        # number of parallel threads per PDF
)
```

### Output columns

| Column | Description |
|---|---|
| `title` | Article title (first clean line before the abstract on the same page) |
| `abstract` | Full abstract text |
| `keywords` | Keywords / key phrases |
| `language` | `fa` (Persian) or `en` (English) |
| `page_start` | 1-based PDF page where the article's abstract/title was found |
| `page_end` | 1-based PDF page just before the next article begins |

---

## How It Works

1. **PDF loading** — the PDF is split into equal page-range chunks; each thread opens its own `pdfplumber` instance and extracts its chunk in parallel, then results are merged in page order.

2. **Text reconstruction** — instead of `extract_text()` (which loses spaces under tight kerning), raw character bounding boxes (`page.chars`) are used. A gap between two consecutive characters that exceeds 15% of the reference character width is treated as a word boundary and a space is inserted.

3. **Article detection** — each page is scanned for abstract marker words (`Abstract` / `چکیده`). Every occurrence splits the page into a new article region. Pages with no abstract marker are skipped immediately (fast path).

4. **Title extraction** — the header text before the abstract marker on the same page is split into paragraph blocks (separated by blank lines). The last block's first non-noise line is the title — noise being email addresses, bare numbers, page ranges, and affiliation keywords.

5. **Abstract & keyword extraction** — regex patterns anchored between known markers capture the body text; line breaks are collapsed to spaces.

6. **Page range computation** — after all pages are processed, articles are sorted by `page_start`. `page_end` for article _i_ is set to `page_start[i+1] - 1` (the last page before the next article begins).

7. **Export** — filtered articles (abstract length > 50 characters) are written to `.xlsx`.

---

## Configuration

Marker words for each language are defined in `LANG_CONFIG` at the top of `app.py`:

```python
LANG_CONFIG = {
    "en": {
        "abstract_markers":        ["Abstract"],
        "keywords_markers":        ["Keywords", "Key words"],
        "keywords_stop_markers":   ["MSC", "Mathematics Subject Classification"],
    },
    "fa": {
        "abstract_markers":        ["چکیده"],
        "keywords_markers":        ["کلیدواژه", "کلید واژه", "کلمات کلیدی", "واژه‌های کلیدی"],
        "keywords_stop_markers":   ["طبقه‌بندی موضوعی", "MSC"],
    },
}
```

Add or change any marker to match the conventions of your conference proceedings.

---

## Project Structure

```
proceedings-extractor/
├── app.py          # Main script — all extraction logic
├── README.md
└── LICENSE
```

---

## License

MIT License

Copyright (c) 2026 Seyyed Ali Mohammadiyeh (MAX BASE)
