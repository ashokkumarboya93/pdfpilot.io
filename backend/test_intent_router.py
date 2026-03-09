"""
Simple smoke test script for the semantic intent router.
"""

from __future__ import annotations

from pathlib import Path

from backend.intent_router import IntentRouter


def main() -> None:
    router = IntentRouter()
    samples = [
        ("combine these images and create a pdf", [Path("sample.png"), Path("sample2.jpg")]),
        ("merge these pdf files", [Path("a.pdf"), Path("b.pdf")]),
        ("turn this document into pdf", [Path("report.docx")]),
        ("make this file smaller", [Path("report.pdf")]),
        ("extract text from this document", [Path("scan.pdf")]),
        ("split this pdf into pages", [Path("deck.pdf")]),
        ("convert this pdf to images", [Path("deck.pdf")]),
        ("merge these pdfs and compress the result", [Path("a.pdf"), Path("b.pdf")]),
    ]

    for prompt, files in samples:
        result = router.detect_intent(prompt, files=files)
        print(prompt)
        print(result)
        print("-" * 60)


if __name__ == "__main__":
    main()
