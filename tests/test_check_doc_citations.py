from pathlib import Path

from check_doc_citations import (
    Citation,
    check_document,
    collect_citations,
    collect_transcript_line_numbers,
    main,
)

DOC_WITH_VALID_CITATION = """# 見出し

本文では 2行目 と 3〜4行目 を引用する。

```
  1| name: CI
  2| on:
  3|   push:
  4|     branches: [main]
```
"""

DOC_WITH_OUT_OF_RANGE_CITATION = """# 見出し

本文では 9行目 を引用する。

```
  1| name: CI
  2| on:
```
"""

DOC_WITH_CITATION_BUT_NO_TRANSCRIPT = """# 見出し

本文では 2行目 を引用するが、転記ブロックが無い。
"""


def test_collect_transcript_line_numbers_reads_numbered_fenced_block():
    lines = DOC_WITH_VALID_CITATION.splitlines()

    assert collect_transcript_line_numbers(lines) == frozenset({1, 2, 3, 4})


def test_collect_transcript_line_numbers_returns_empty_when_no_block():
    lines = DOC_WITH_CITATION_BUT_NO_TRANSCRIPT.splitlines()

    assert collect_transcript_line_numbers(lines) == frozenset()


def test_collect_citations_finds_single_and_range_forms():
    lines = DOC_WITH_VALID_CITATION.splitlines()

    citations = collect_citations(lines)

    assert citations == (
        Citation(source_line=3, start=2, end=2),
        Citation(source_line=3, start=3, end=4),
    )


def test_collect_citations_ignores_text_inside_the_transcript_block():
    lines = [
        "本文に引用は無い。",
        "```",
        "  1| # ここに 5行目 と書いてあっても引用ではない",
        "```",
    ]

    assert collect_citations(lines) == ()


def test_check_document_reports_nothing_for_a_valid_document(tmp_path: Path):
    path = tmp_path / "ok.md"
    path.write_text(DOC_WITH_VALID_CITATION, encoding="utf-8")

    assert check_document(path) == ()


def test_check_document_reports_a_citation_outside_the_transcript(tmp_path: Path):
    path = tmp_path / "ng.md"
    path.write_text(DOC_WITH_OUT_OF_RANGE_CITATION, encoding="utf-8")

    problems = check_document(path)

    assert len(problems) == 1
    assert "9行目" in problems[0].message


def test_check_document_reports_a_citation_with_no_transcript_block(tmp_path: Path):
    path = tmp_path / "no-block.md"
    path.write_text(DOC_WITH_CITATION_BUT_NO_TRANSCRIPT, encoding="utf-8")

    problems = check_document(path)

    assert len(problems) == 1
    assert "転記ブロック" in problems[0].message


def test_check_document_reports_a_reversed_range(tmp_path: Path):
    path = tmp_path / "reversed.md"
    path.write_text(
        "本文で 4〜2行目 を引用する。\n\n```\n  1| a\n  2| b\n  3| c\n  4| d\n```\n",
        encoding="utf-8",
    )

    problems = check_document(path)

    assert len(problems) == 1
    assert "逆順" in problems[0].message


def test_main_returns_zero_for_a_directory_of_valid_documents(tmp_path: Path, capsys):
    (tmp_path / "a.md").write_text(DOC_WITH_VALID_CITATION, encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.md").write_text(DOC_WITH_VALID_CITATION, encoding="utf-8")

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    assert "2 件のドキュメント" in capsys.readouterr().out


def test_main_returns_one_and_reports_to_stderr_when_a_document_is_broken(tmp_path: Path, capsys):
    (tmp_path / "ng.md").write_text(DOC_WITH_OUT_OF_RANGE_CITATION, encoding="utf-8")

    exit_code = main([str(tmp_path)])

    assert exit_code == 1
    assert "ng.md" in capsys.readouterr().err
