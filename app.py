from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Literal, Dict, Pattern, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

import pdfplumber
import pandas as pd


# =========================
# Types & Config
# =========================

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


# =========================
# Models
# =========================

@dataclass
class Article:
    title: Optional[str]
    abstract: Optional[str]
    keywords: Optional[str]
    language: Language


# =========================
# Regex Cache (IMPORTANT SPEED OPTIMIZATION)
# =========================

_REGEX_CACHE: Dict[str, Pattern[str]] = {}


def get_regex(pattern: str) -> Pattern[str]:
    if pattern not in _REGEX_CACHE:
        _REGEX_CACHE[pattern] = re.compile(pattern, re.S | re.I)
    return _REGEX_CACHE[pattern]


def build_pattern(markers: List[str]) -> str:
    return "(" + "|".join(re.escape(m) for m in markers) + ")"


# =========================
# PDF LOADER
# =========================

def load_pdf_pages(pdf_path: str) -> List[str]:
    pages: List[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)

    return pages


# =========================
# SPLIT ARTICLES (FAST)
# =========================

def split_articles(page: str, abstract_markers: List[str]) -> List[str]:
    pattern = get_regex(build_pattern(abstract_markers))
    parts = pattern.split(page)

    articles: List[str] = []

    for i in range(1, len(parts), 2):
        content = parts[i] + (parts[i + 1] if i + 1 < len(parts) else "")
        articles.append(content)

    return articles


# =========================
# TITLE EXTRACTION
# =========================

def extract_title(text: str, abstract_markers: List[str]) -> Optional[str]:
    marker_pat = get_regex(build_pattern(abstract_markers))

    parts = marker_pat.split(text, maxsplit=1)
    if len(parts) < 2:
        return None

    header = parts[0]

    lines = [
        l.strip()
        for l in header.split("\n")
        if len(l.strip()) > 8
    ]

    if not lines:
        return None

    # filter noise
    cleaned = [
        l for l in lines
        if not re.search(r"@|\d|university|department|faculty", l, re.I)
    ]

    return max(cleaned, key=len) if cleaned else None


# =========================
# ABSTRACT (FAST + CLEAN)
# =========================

def extract_abstract(text: str, abstract_markers: List[str], keywords_markers: List[str]) -> Optional[str]:
    abs_pat = build_pattern(abstract_markers)
    key_pat = build_pattern(keywords_markers)

    pattern = rf"{abs_pat}\s*(.*?)(?={key_pat})"
    match = get_regex(pattern).search(text)

    if not match:
        return None

    abstract = match.group(1)

    abstract = re.sub(r"^\.+\s*", "", abstract)
    abstract = re.sub(r"\n+", " ", abstract)
    abstract = re.sub(r"\s{2,}", " ", abstract)

    return abstract.strip()


# =========================
# KEYWORDS (FAST + STOP SAFE)
# =========================

def extract_keywords(text: str, keywords_markers: List[str], stop_markers: List[str]) -> Optional[str]:
    key_pat = build_pattern(keywords_markers)
    stop_pat = build_pattern(stop_markers)

    pattern = rf"{key_pat}\s*[:：]?\s*(.*?)(?={stop_pat}|\n[A-Z]|$)"
    match = get_regex(pattern).search(text)

    if not match:
        return None

    keywords = match.group(1)

    keywords = re.sub(r"\n+", " ", keywords)
    keywords = re.sub(r"\s{2,}", " ", keywords)

    return keywords.strip(" .,\n\t")


# =========================
# NORMALIZER (LIGHTWEIGHT)
# =========================

def normalize(text: Optional[str]) -> Optional[str]:
    if not text:
        return None

    text = text.replace("ي", "ی").replace("ك", "ک").replace("\u200c", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# =========================
# PARSE SINGLE ARTICLE
# =========================

def parse_article(text: str, lang: Language) -> Article:
    cfg = LANG_CONFIG[lang]

    title = extract_title(text, cfg["abstract_markers"])
    abstract = extract_abstract(text, cfg["abstract_markers"], cfg["keywords_markers"])
    keywords = extract_keywords(text, cfg["keywords_markers"], cfg["keywords_stop_markers"])

    return Article(
        normalize(title),
        normalize(abstract),
        normalize(keywords),
        lang
    )


# =========================
# PARALLEL PAGE PROCESSING
# =========================

def process_page(page: Tuple[str, Language]) -> List[Article]:
    text, lang = page
    cfg = LANG_CONFIG[lang]

    articles_raw = split_articles(text, cfg["abstract_markers"])
    return [parse_article(a, lang) for a in articles_raw]


# =========================
# PDF PIPELINE (PARALLEL)
# =========================

def process_pdf_parallel(pdf_path: str, lang: Language, workers: int = 8) -> List[Article]:
    pages = load_pdf_pages(pdf_path)

    tasks = [(p, lang) for p in pages]

    results: List[Article] = []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(process_page, t) for t in tasks]

        for f in as_completed(futures):
            results.extend(f.result())

    return results


# =========================
# EXPORT
# =========================

def export_excel(articles: List[Article], out: str) -> None:
    df = pd.DataFrame([
        {
            "title": a.title,
            "abstract": a.abstract,
            "keywords": a.keywords,
            "language": a.language
        }
        for a in articles
    ])

    df.to_excel(out, index=False)


# =========================
# VALIDATION
# =========================

def filter_articles(articles: List[Article]) -> List[Article]:
    return [a for a in articles if a.abstract and len(a.abstract) > 50]


# =========================
# MAIN
# =========================

def run(persian_pdf: str, english_pdf: str, out: str = "out.xlsx") -> None:
    fa = process_pdf_parallel(persian_pdf, "fa")
    en = process_pdf_parallel(english_pdf, "en")

    all_articles = filter_articles(fa + en)

    export_excel(all_articles, out)


if __name__ == "__main__":
    run("persian.pdf", "english.pdf")
