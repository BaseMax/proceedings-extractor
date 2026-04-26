from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Literal

import pdfplumber
import pandas as pd

# =========================
# Models
# =========================
Language = Literal["fa", "en"]


@dataclass
class Article:
    title: Optional[str]
    abstract: Optional[str]
    keywords: Optional[str]
    language: Language


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


def merge_pages(pages: List[str]) -> str:
    return "\n".join(pages)


# =========================
# Splitter
# =========================
def split_articles(text: str) -> List[str]:
    """
    Split articles using Abstract / چکیده markers.
    """
    pattern: str = r'(چکیده|Abstract)'
    parts: List[str] = re.split(pattern, text)

    articles: List[str] = []

    for i in range(1, len(parts), 2):
        marker: str = parts[i]
        content: str = parts[i + 1] if i + 1 < len(parts) else ""
        articles.append(marker + content)

    return articles


# =========================
# Parsers
# =========================
def extract_title_from_block(block: str, marker: str) -> Optional[str]:
    parts = block.split(marker)

    if len(parts) < 2:
        return None

    header = parts[0]

    lines = [
        l.strip()
        for l in header.split("\n")
        if l.strip() and len(l.strip()) > 10
    ]

    if not lines:
        return None

    title = max(lines, key=len)

    return title

def extract_abstract(
    text: str,
    start_marker: str,
    end_marker_pattern: str
) -> Optional[str]:

    pattern = rf"{start_marker}\s*(.*?)\s*(?:{end_marker_pattern})"

    match = re.search(pattern, text, re.S | re.I)

    if match:
        return match.group(1).strip()

    return None

def extract_keywords(text: str) -> Optional[str]:
    pattern = r"Keywords\s*[:：]?\s*(.*?)(?:\n\s*\n|$)"

    match = re.search(pattern, text, re.S | re.I)

    if not match:
        return None

    keywords_block = match.group(1)

    keywords_block = keywords_block.replace("\n", " ")

    keywords_block = re.sub(r"\s+", " ", keywords_block)
    keywords_block = keywords_block.strip(" .,")

    return keywords_block

# -------------------------
# Persian Parser
# -------------------------
def parse_persian(article: str) -> Article:
    title: Optional[str] = extract_title_from_block(article, "چکیده")

    abstract: Optional[str] = extract_abstract(
        article,
        start_marker="چکیده",
        end_marker_pattern=r"کلیدواژه"
    )

    keywords: Optional[str] = exstract_keywords(
        article,
        r"کلیدواژه.?[:：]?(.*)"
    )

    return Article(title, abstract, keywords, "fa")


# -------------------------
# English Parser
# -------------------------
def parse_english(article: str) -> Article:
    title: Optional[str] = extract_title_from_block(article, "Abstract")

    abstract: Optional[str] = extract_abstract(
        article,
        start_marker="Abstract",
        end_marker_pattern=r"Keywords"
    )

    keywords: Optional[str] = extract_keywords(
        article,
        r"Keywords.?[:：]?(.*)"
    )

    return Article(title, abstract, keywords, "en")


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
# Pipeline
# =========================
def parse_articles(
    raw_articles: List[str],
    lang: Language
) -> List[Article]:

    parsed: List[Article] = []

    for raw in raw_articles:
        if lang == "fa":
            article: Article = parse_persian(raw)
        else:
            article = parse_english(raw)

        parsed.append(normalize_article(article))

    return parsed


def process_pdf(pdf_path: str, lang: Language) -> List[Article]:
    pages: List[str] = extract_pages_text(pdf_path)

    all_articles: List[Article] = []

    for page in pages:
        raw_articles: List[str] = split_articles(page)
        parsed: List[Article] = parse_articles(raw_articles, lang)
        all_articles.extend(parsed)

    return all_articles


# =========================
# Exporter
# =========================
def articles_to_dataframe(articles: List[Article]) -> pd.DataFrame:
    data = [
        {
            "title": a.title,
            "abstract": a.abstract,
            "keywords": a.keywords,
            "language": a.language,
        }
        for a in articles
    ]

    return pd.DataFrame(data)


def export_to_excel(
    articles: List[Article],
    output_path: str
) -> None:

    df: pd.DataFrame = articles_to_dataframe(articles)
    df.to_excel(output_path, index=False)


# =========================
# Validation
# =========================
def is_valid_article(article: Article) -> bool:
    if not article.abstract:
        return False

    if len(article.abstract) < 50:
        return False

    return True


def filter_valid_articles(articles: List[Article]) -> List[Article]:
    return [a for a in articles if is_valid_article(a)]


# =========================
# Main
# =========================
def run_pipeline(
    persian_pdf: str,
    english_pdf: str,
    output_file: str = "conference_articles.xlsx"
) -> None:

    fa_articles: List[Article] = []
    # fa_articles: List[Article] = process_pdf(persian_pdf, "fa")

    en_articles: List[Article] = process_pdf(english_pdf, "en")

    all_articles: List[Article] = fa_articles + en_articles

    valid_articles: List[Article] = filter_valid_articles(all_articles)

    # print(valid_articles)
    export_to_excel(valid_articles, output_file)


if __name__ == "__main__":
    run_pipeline(
        persian_pdf="persian.pdf",
        english_pdf="english.pdf",
        output_file="conference_articles.xlsx"
    )
