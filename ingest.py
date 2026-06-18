"""
ingest.py

Reads data/services.md, splits it into topic-sized chunks (one per service,
package, or FAQ), embeds each chunk with Gemini's embedding model, and stores
everything in a single local JSON file: data/knowledge_base.json.

This replaces an earlier version that used chromadb. chromadb's full
dependency tree (onnxruntime, grpcio, opentelemetry, a kubernetes client,
fastapi/uvicorn for its server mode) is heavy, hundreds of MB, almost all of
it unused for a small, local, read-only knowledge base like this one. For 48
chunks of text, a plain JSON file plus an in-memory cosine similarity search
is simpler, lighter (no extra disk-hungry dependencies), and just as fast.

Run this once after setup, and again any time data/services.md is edited:
    python ingest.py
"""

import os
import re
import json
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")

genai.configure(api_key=GEMINI_API_KEY)

DATA_PATH = "data/services.md"
OUTPUT_PATH = "data/knowledge_base.json"
EMBEDDING_MODEL = "models/embedding-001"


def clean_text(text: str) -> str:
    """Strip markdown escape characters and bold/italic markers."""
    text = re.sub(r'\\([.!#*])', r'\1', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text.strip()


def parse_sections(md_text: str):
    """
    Splits the markdown into chunks at each heading.
    Plain '# pagename' lines are treated as page markers (no content of
    their own). Bold '# **Heading**' lines set the current category and
    may carry their own content. '## **Heading**' lines are individual
    services or FAQ entries.
    """
    heading_re = re.compile(r'^(#{1,2})\s+(.*)$')
    lines = md_text.split('\n')

    sections = []
    category = "General"
    title = None
    body_lines = []

    def flush():
        if title:
            body = clean_text('\n'.join(body_lines)).strip()
            if len(body) >= 20:
                sections.append({
                    "category": category,
                    "title": clean_text(title),
                    "content": f"{clean_text(title)}\n\n{body}",
                })

    for raw_line in lines:
        line = raw_line.strip()
        match = heading_re.match(line)
        if match:
            flush()
            level, heading_text = match.groups()
            body_lines = []
            if level == '#':
                if heading_text.startswith('**'):
                    category = clean_text(heading_text)
                    title = clean_text(heading_text)
                else:
                    category = clean_text(heading_text).title()
                    title = None
            else:
                title = clean_text(heading_text)
        else:
            if line:
                body_lines.append(raw_line)
    flush()
    return sections


def embed_text(text: str) -> list:
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_document",
    )
    return result["embedding"]


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        md_text = f.read()

    sections = parse_sections(md_text)
    print(f"Parsed {len(sections)} chunks from {DATA_PATH}")

    for i, section in enumerate(sections, start=1):
        section["embedding"] = embed_text(section["content"])
        print(f"  [{i}/{len(sections)}] embedded: {section['title']}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(sections, f)

    print(f"\nStored {len(sections)} embedded chunks in {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
