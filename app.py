from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Literal, Dict

import pdfplumber
import pandas as pd


# =========================
# Models & Config
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
        "keywords_stop_markers": ["طبقه‌بندی موضوعی", "طبقه‌ بندی موضوعی", "MSC"],
    },
}

@dataclass
class Article:
    title: Optional[str]
    abstract: Optional[str]
    keywords: Optional[str]
    language: Language


# =========================
# Utilities
# =========================

def build_marker_pattern(markers: List[str]) -> str:
    escaped = [re.escape(m) for m in markers]
    return "(" + "|".join(escaped) + ")"


# =========================
# PDF Reader
# =========================

def extract_pages_text(pdf_path: str) -> List[str]:
    pages: List[str] = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text: Optional[str] = page.extract_text()
            if text:
                pages.append(text)

    return pages


# =========================
# Splitter
# =========================

def split_articles(text: str, abstract_markers: List[str]) -> List[str]:
    pattern = build_marker_pattern(abstract_markers)
    parts = re.split(pattern, text)

    articles: List[str] = []

    for i in range(1, len(parts), 2):
        marker = parts[i]
        content = parts[i + 1] if i + 1 < len(parts) else ""
        articles.append(marker + content)

    return articles


# =========================
# Extractors
# =========================
def extract_title(block: str, abstract_markers: List[str]) -> Optional[str]:
    marker_pattern = build_marker_pattern(abstract_markers)

    parts = re.split(marker_pattern, block, maxsplit=1)

    if len(parts) < 2:
        return None

    header = parts[0]

    lines = [
        l.strip()
        for l in header.split("\n")
        if l.strip()
    ]

    if not lines:
        return None

    filtered = [
        l for l in lines
        if len(l) > 15 and not l.strip().startswith(".")
    ]

    if not filtered:
        return None

    return max(filtered, key=len)

def extract_abstract(
    text: str,
    abstract_markers: List[str],
    keywords_markers: List[str],
) -> Optional[str]:
    abs_pattern = build_marker_pattern(abstract_markers)
    key_pattern = build_marker_pattern(keywords_markers)

    pattern = rf"{abs_pattern}\s*(.*?)\s*(?:{key_pattern})"

    match = re.search(pattern, text, re.S | re.I)

    if not match:
        return None

    abstract = match.group(2)

    abstract = re.sub(r"^\s*\.+\s*", "", abstract)

    abstract = re.sub(r"\s+", " ", abstract)

    return abstract.strip()

def extract_keywords(
    text: str,
    keywords_markers: List[str],
    stop_markers: List[str],
) -> Optional[str]:
    key_pattern = build_marker_pattern(keywords_markers)
    stop_pattern = build_marker_pattern(stop_markers)

    pattern = rf"{key_pattern}\s*[:：]?\s*(.*?)(?:{stop_pattern}|\n\s*\n|$)"

    match = re.search(pattern, text, re.S | re.I)

    if not match:
        return None

    keywords_block = match.group(2)

    keywords_block = keywords_block.replace("\n", " ")
    keywords_block = re.sub(r"\s+", " ", keywords_block)

    return keywords_block.strip(" .,\n\t")

# =========================
# Normalizer
# =========================

def normalize_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None

    replacements = {
        "ي": "ی",
        "ك": "ک",
        "\u200c": " ",
    }

    for k, v in replacements.items():
        text = text.replace(k, v)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_article(article: Article) -> Article:
    return Article(
        title=normalize_text(article.title),
        abstract=normalize_text(article.abstract),
        keywords=normalize_text(article.keywords),
        language=article.language,
    )


# =========================
# Parser
# =========================

def parse_article(text: str, lang: Language) -> Article:
    config = LANG_CONFIG[lang]

    abstract_markers: List[str] = config["abstract_markers"]
    keywords_markers: List[str] = config["keywords_markers"]

    title = extract_title(text, abstract_markers)

    abstract = extract_abstract(
        text,
        abstract_markers,
        keywords_markers,
    )

    keywords = extract_keywords(
        text,
        keywords_markers,
        config["keywords_stop_markers"],
    )
    return normalize_article(
        Article(title, abstract, keywords, lang)
    )


def parse_articles(texts: List[str], lang: Language) -> List[Article]:
    return [parse_article(t, lang) for t in texts]


# =========================
# Pipeline
# =========================

def process_pdf(pdf_path: str, lang: Language) -> List[Article]:
    pages = extract_pages_text(pdf_path)
    config = LANG_CONFIG[lang]

    all_articles: List[Article] = []

    for page in pages:
        raw_articles = split_articles(page, config["abstract_markers"])
        parsed = parse_articles(raw_articles, lang)
        all_articles.extend(parsed)

    return all_articles


# =========================
# Export
# =========================

def articles_to_dataframe(articles: List[Article]) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "title": a.title,
            "abstract": a.abstract,
            "keywords": a.keywords,
            "language": a.language,
        }
        for a in articles
    ])


def export_to_excel(articles: List[Article], output_path: str) -> None:
    df = articles_to_dataframe(articles)
    df.to_excel(output_path, index=False)


# =========================
# Validation
# =========================

def is_valid_article(article: Article) -> bool:
    return bool(article.abstract and len(article.abstract) > 50)


def filter_valid_articles(articles: List[Article]) -> List[Article]:
    return [a for a in articles if is_valid_article(a)]


# =========================
# Main
# =========================

def run_pipeline(
    persian_pdf: str,
    english_pdf: str,
    output_file: str = "conference_articles.xlsx",
) -> None:
    fa_articles: List[Article] = process_pdf(persian_pdf, "fa")
    en_articles: List[Article] = process_pdf(english_pdf, "en")

    all_articles = fa_articles + en_articles
    valid_articles = filter_valid_articles(all_articles)

    export_to_excel(valid_articles, output_file)


if __name__ == "__main__":
    run_pipeline(
        persian_pdf="persian.pdf",
        english_pdf="english.pdf",
        output_file="conference_articles.xlsx",
    )
