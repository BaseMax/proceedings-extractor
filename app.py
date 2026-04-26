from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Literal, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor

import pdfplumber
import pandas as pd

Language = Literal["fa", "en"]

LANG_CONFIG: Dict[Language, dict] = {
    "en": {
        "abstract_markers": ["Abstract"],
        "keywords_markers": ["Keywords", "Key words"],
        "keywords_stop_markers": ["MSC", "Mathematics Subject Classification"],
    },
    "fa": {
        "abstract_markers": ["چکیده"],
        "keywords_markers": ["کلیدواژه", "کلید واژه", "کلمات کلیدی", "واژه‌های کلیدی"],
        "keywords_stop_markers": ["طبقه‌بندی موضوعی", "MSC"],
    },
}

@dataclass
class Article:
    title: Optional[str]
    abstract: Optional[str]
    keywords: Optional[str]
    language: Language
    page_start: int = 0
    page_end: Optional[int] = None

_REGEX_CACHE: Dict[str, re.Pattern] = {}

_NOISE_RE = re.compile(
    r"@|^\d+$|^\d+\s*[-–]\s*\d+$"
    r"|\b(faculty|university|department|institute|laboratory|lab)\b",
    re.I,
)

def _re(pattern: str) -> re.Pattern:
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern, re.S | re.I)
    return _REGEX_CACHE[pattern]


def _pat(markers: List[str]) -> str:
    return "(" + "|".join(re.escape(m) for m in markers) + ")"

def _page_text(page) -> str:
    chars = page.chars
    if not chars:
        return ""

    lines: Dict[int, list] = {}
    for ch in chars:
        if not ch.get("text"):
            continue
        y = round(float(ch["top"]))
        lines.setdefault(y, []).append(ch)

    parts = []
    for y in sorted(lines):
        row = sorted(lines[y], key=lambda c: float(c["x0"]))
        text = ""
        prev_x1: Optional[float] = None
        prev_width: float = 1.0
        for ch in row:
            ch_text = ch["text"]
            x0 = float(ch["x0"])
            x1 = float(ch["x1"])
            width = max(x1 - x0, 0.0)
            if prev_x1 is not None:
                gap = x0 - prev_x1
                ref = max(prev_width, width, 1.0)
                if gap > ref * 0.15:
                    text += " "
            text += ch_text
            prev_x1 = x1
            prev_width = width if width > 0 else prev_width
        stripped = text.strip()
        if stripped:
            parts.append(stripped)

    return "\n".join(parts)

def _load_chunk(args: Tuple[str, int, int]) -> List[Tuple[int, str]]:
    pdf_path, start, end = args
    out: List[Tuple[int, str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for i in range(start, end):
            text = _page_text(pdf.pages[i])
            if text:
                out.append((i, text))
    return out

def load_pdf_pages(pdf_path: str, workers: int = 8) -> List[str]:
    with pdfplumber.open(pdf_path) as pdf:
        n = len(pdf.pages)
    if n == 0:
        return []

    chunk = max(1, (n + workers - 1) // workers)
    chunks = [(pdf_path, s, min(s + chunk, n)) for s in range(0, n, chunk)]

    indexed: List[Tuple[int, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for batch in pool.map(_load_chunk, chunks):
            indexed.extend(batch)

    indexed.sort(key=lambda x: x[0])
    return indexed

def _title_from_header(header: str) -> Optional[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", header) if p.strip()]
    if not paras:
        return None
    lines = [l.strip() for l in paras[-1].split("\n") if l.strip()]
    for line in lines:
        if _NOISE_RE.search(line) or len(line) < 4:
            continue
        return line
    return None

def _abstract(text: str, abs_markers: List[str], kw_markers: List[str]) -> Optional[str]:
    m = _re(rf"{_pat(abs_markers)}\s*(.*?)(?={_pat(kw_markers)})").search(text)
    if not m:
        return None
    body = re.sub(r"^[.:\s]+", "", m.group(2))
    body = re.sub(r"\n+", " ", body)
    return re.sub(r"\s{2,}", " ", body).strip()

def _keywords(text: str, kw_markers: List[str], stop_markers: List[str]) -> Optional[str]:
    m = _re(rf"{_pat(kw_markers)}\s*[:：]?\s*(.*?)(?={_pat(stop_markers)}|\n[A-Z]|$)").search(text)
    if not m:
        return None
    body = re.sub(r"\n+", " ", m.group(2))
    return re.sub(r"\s{2,}", " ", body).strip(" .,\n\t")

def _norm(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    return re.sub(r"\s+", " ", text).strip()

def _process_page(args: Tuple[str, Language, int]) -> List[Article]:
    text, lang, page_num = args
    cfg = LANG_CONFIG[lang]
    abs_m = cfg["abstract_markers"]
    kw_m  = cfg["keywords_markers"]
    stp_m = cfg["keywords_stop_markers"]

    splitter = _re(_pat(abs_m))
    if not splitter.search(text):
        return []

    parts = splitter.split(text)

    articles: List[Article] = []
    for i in range(1, len(parts), 2):
        header    = parts[i - 1]
        remainder = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
        
        articles.append(Article(
            _norm(_title_from_header(header)),
            _norm(_abstract(remainder, abs_m, kw_m)),
            _norm(_keywords(remainder, kw_m, stp_m)),
            lang,
            page_start=page_num,
        ))
    return articles

def process_pdf(pdf_path: str, lang: Language, workers: int = 8) -> List[Article]:
    indexed_pages = load_pdf_pages(pdf_path, workers)
    tasks = [(text, lang, idx + 1) for idx, text in indexed_pages]
    results: List[Article] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for articles in pool.map(_process_page, tasks):
            results.extend(articles)
    results.sort(key=lambda a: a.page_start)
    for i, art in enumerate(results):
        if i + 1 < len(results):
            art.page_end = max(art.page_start, results[i + 1].page_start - 1)
        else:
            art.page_end = art.page_start
    return results

def export_excel(articles: List[Article], out: str) -> None:
    pd.DataFrame([
        {
            "title": a.title,
            "abstract": a.abstract,
            "keywords": a.keywords,
            "language": a.language,
            "page_start": a.page_start,
            "page_end": a.page_end,
        }
        for a in articles
    ]).to_excel(out, index=False)

def filter_articles(articles: List[Article]) -> List[Article]:
    return [a for a in articles if a.abstract and len(a.abstract) > 50]

def run(persian_pdf: str, english_pdf: str, out: str = "out.xlsx", workers: int = 8) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        fa_f = pool.submit(process_pdf, persian_pdf, "fa", workers)
        en_f = pool.submit(process_pdf, english_pdf, "en", workers)
        all_articles = filter_articles(fa_f.result() + en_f.result())

    export_excel(all_articles, out)

if __name__ == "__main__":
    run("persian.pdf", "english.pdf")
