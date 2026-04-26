# proceedings-extractor

A parallel PDF proceedings extractor that collects article metadata (title, abstract, keywords, page range) from conference proceedings PDFs and exports them to Excel.

Originally designed for **CACNA 2025** - a mathematics conference held at the **University of Kashan** - to produce a structured spreadsheet of all articles so that the Iran government credit system could identify authors and assign publication credits.

---

## Features

- Extracts **title**, **abstract**, **keywords**, **page start**, and **page end** for every article
- Supports both **Persian (Farsi)** and **English** proceedings PDFs simultaneously
- **Parallel page loading** - each thread opens its own PDF handle, no locking overhead
- **Parallel page processing** - all pages processed concurrently with `ThreadPoolExecutor`
- Both PDFs (Persian + English) are processed **fully in parallel** with each other
- **Character-level space detection** - uses raw glyph bounding boxes to reconstruct proper word spacing, fixing the missing-space problem common in tightly-kerned academic PDFs
- **RTL text support** - Persian/Arabic lines are automatically detected (>40% RTL characters) and character order is reversed to correct right-to-left reading direction
- **Unicode normalization** - NFKC decomposition converts Arabic Presentation Forms (U+FB50–FEFF) to base characters, ZWNJ (U+200C) is replaced with a regular space, and `(cid:N)` glyph-mapping artifacts are stripped
- **Clean Excel output** - XML-illegal characters (control characters, U+FFFE, U+FFFF) are stripped before writing, preventing Excel recovery errors
- **Persian keyword cleanup** - `طبقه بندی موضوعی` classification labels and trailing MSC codes are automatically removed from Persian keyword fields
- **Debug mode** - inspect raw extracted text and marker matches page-by-page without running the full pipeline
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

### Debug mode

Inspect raw extracted text and marker matches for a specific PDF without running the full pipeline:

```bash
# Show first 5 pages with content from the Persian PDF
python app.py debug persian.pdf fa 5

# Show first 10 pages from the English PDF
python app.py debug english.pdf en 10
```

Arguments: `debug <pdf_path> <lang> [pages]`  
- `lang` — `fa` for Persian, `en` for English  
- `pages` — number of non-empty pages to show (default: 5)

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
| `page_start` | 1-based PDF page where the article abstract/title was found |
| `page_end` | 1-based PDF page just before the next article begins |

---

## How It Works

1. **PDF loading** - the PDF is split into equal page-range chunks; each thread opens its own `pdfplumber` instance and extracts its chunk in parallel, then results are merged in page order.

2. **Text reconstruction** - instead of `extract_text()` (which loses spaces under tight kerning), raw character bounding boxes (`page.chars`) are used. A gap between two consecutive characters that exceeds 15% of the reference character width is treated as a word boundary and a space is inserted.

3. **Text normalisation** - on each reconstructed line: NFKC Unicode normalisation is applied (converting Arabic Presentation Forms to base characters), ZWNJ (`U+200C`) is replaced with a regular space, and `(cid:N)` glyph-mapping artifacts are stripped. The cleaned line is then tested for RTL content: if more than 40% of its non-space characters fall in the Arabic/Persian Unicode blocks, the character order is reversed to restore correct reading direction.

4. **Article detection** - each page is scanned for abstract marker words (`Abstract.` / `چکیده.`). Every occurrence splits the page into a new article region. Pages with no abstract marker are skipped immediately (fast path).

5. **Title extraction** - the header text before the abstract marker on the same page is split into paragraph blocks (separated by blank lines). The last block's first non-noise line is the title — noise being email addresses, bare numbers, page ranges, and affiliation keywords.

6. **Abstract & keyword extraction** - regex patterns anchored between known markers capture the body text; line breaks are collapsed to spaces. For Persian articles, a second pass strips any trailing `طبقه بندی موضوعی` label and MSC classification codes (e.g. `62F10, 54H11`) from the keywords field.

7. **Page range computation** - after all pages are processed, articles are sorted by `page_start`. `page_end` for article _i_ is set to `page_start[i+1] - 1` (the last page before the next article begins).

8. **Sanitisation & export** - XML-illegal characters (control codes, U+FFFE, U+FFFF) are stripped from all text fields before writing. Filtered articles (abstract length > 50 characters) are written to `.xlsx`.

---

## Configuration

Marker words for each language are defined in `LANG_CONFIG` at the top of `app.py`:

```python
LANG_CONFIG = {
    "en": {
        "abstract_markers":        ["Abstract."],
        "keywords_markers":        ["Keywords:"],
        "keywords_stop_markers":   ["MSC("],
    },
    "fa": {
        "abstract_markers":        ["چکیده."],
        "keywords_markers":        ["واژه های کلیدی:"],
        "keywords_stop_markers":   ["طبقه بندی موضوعی"],
    },
}
```

Add or change any marker to match the conventions of your conference proceedings.

---

## Project Structure

```
proceedings-extractor/
├── app.py        # Main script - all extraction logic
├── README.md
└── LICENSE
```

---

## License

MIT License

Copyright (c) 2026 Seyyed Ali Mohammadiyeh (MAX BASE)
