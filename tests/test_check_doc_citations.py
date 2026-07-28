import os
import subprocess
import sys
from pathlib import Path

from check_doc_citations import (
    Citation,
    Transcript,
    check_document,
    collect_citations,
    collect_transcripts,
    git_source_reader,
    main,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _reader(sources: dict[tuple[str, str], tuple[str, ...]]):
    def read(source_path: str, tag: str) -> tuple[str, ...] | None:
        return sources.get((source_path, tag))

    return read


DOC_WITH_VALID_CITATION = """# 見出し

<!-- transcript: ci.yml @ stage-01 -->
```
  1| name: CI
  2| on:
  3|   push:
  4|     branches: [main]
```

本文では `ci.yml` の 2行目 と 3〜4行目 を引用する。
"""

DOC_WITH_OUT_OF_RANGE_CITATION = """# 見出し

<!-- transcript: sample.yml @ stage-01 -->
```
  1| name: CI
  2| on:
```

本文では `sample.yml` の 9行目 を引用する。
"""

DOC_WITH_CITATION_BUT_NO_TRANSCRIPT = """# 見出し

本文では 2行目 を引用するが、転記ブロックが無い。
"""

DOC_WITH_NO_TRANSCRIPTS_OR_CITATIONS = """# 見出し

本文のみで、転記ブロックも行番号引用も無い。
"""

DOC_WITH_HYPHEN_RANGE_CITATION = """# 見出し

<!-- transcript: h.yml @ stage-01 -->
```
  1| a
  2| b
  3| c
  4| d
```

本文では `h.yml` の 2-4行目 を引用する。
"""

# 転記ブロックを2つ持つ文書。1つ目は1〜2行目、2つ目は10〜12行目という
# 別々の行番号を、別々のファイル（first.yml / second.yml）として転記している。
DOC_WITH_TWO_TRANSCRIPT_BLOCKS = """# 見出し

<!-- transcript: first.yml @ stage-01 -->
```
  1| name: CI
  2| on:
```

<!-- transcript: second.yml @ stage-01 -->
```
 10| jobs:
 11|   test:
 12|     runs-on: ubuntu-latest
```

本文では `second.yml` の 11行目 を引用する。
"""


def test_collect_transcripts_reads_numbered_fenced_block_line_numbers():
    lines = DOC_WITH_VALID_CITATION.splitlines()

    transcripts = collect_transcripts(lines)

    assert len(transcripts) == 1
    assert transcripts[0].source_path == "ci.yml"
    assert transcripts[0].tag == "stage-01"
    assert transcripts[0].line_numbers == frozenset({1, 2, 3, 4})


def test_collect_transcripts_returns_empty_when_no_block():
    lines = DOC_WITH_CITATION_BUT_NO_TRANSCRIPT.splitlines()

    assert collect_transcripts(lines) == ()


def test_collect_citations_finds_single_and_range_forms():
    lines = DOC_WITH_VALID_CITATION.splitlines()

    citations = collect_citations(lines, frozenset({"ci.yml"}))

    assert citations == (
        Citation(source_line=11, start=2, end=2, file_hint="ci.yml"),
        Citation(source_line=11, start=3, end=4, file_hint="ci.yml"),
    )


def test_collect_citations_ignores_text_inside_the_transcript_block():
    lines = [
        "本文に引用は無い。",
        "```",
        "  1| # ここに 5行目 と書いてあっても引用ではない",
        "```",
    ]

    assert collect_citations(lines, frozenset()) == ()


def test_check_document_reports_nothing_for_a_valid_document(tmp_path: Path):
    path = tmp_path / "ok.md"
    path.write_text(DOC_WITH_VALID_CITATION, encoding="utf-8")
    reader = _reader(
        {("ci.yml", "stage-01"): ("name: CI", "on:", "  push:", "    branches: [main]")}
    )

    assert check_document(path, reader) == ()


def test_check_document_reports_a_citation_outside_the_transcript(tmp_path: Path):
    path = tmp_path / "ng.md"
    path.write_text(DOC_WITH_OUT_OF_RANGE_CITATION, encoding="utf-8")
    reader = _reader({("sample.yml", "stage-01"): ("name: CI", "on:")})

    problems = check_document(path, reader)

    assert len(problems) == 1
    assert "9行目" in problems[0].message


def test_check_document_reports_a_citation_with_no_transcript_block(tmp_path: Path):
    """転記ブロックが1つも無い文書での引用の扱いを確認する。

    出所宣言の仕組みが入る前は「転記ブロックが無い」という専用メッセージだった。
    宣言も転記ブロックも無い以上、そもそも本文がどのファイルを指しているかを
    判別する材料が無いため、今は「どのファイルの引用か判別できない」という、
    より正確なメッセージで報告される。「引用があるのに検査できる転記が無ければ
    問題として報告する」という本来の意図は変わっていない。
    """
    path = tmp_path / "no-block.md"
    path.write_text(DOC_WITH_CITATION_BUT_NO_TRANSCRIPT, encoding="utf-8")

    problems = check_document(path, _reader({}))

    assert len(problems) == 1
    assert "どのファイル" in problems[0].message


def test_check_document_reports_a_reversed_range(tmp_path: Path):
    path = tmp_path / "reversed.md"
    path.write_text(
        "<!-- transcript: r.yml @ stage-01 -->\n"
        "```\n  1| a\n  2| b\n  3| c\n  4| d\n```\n\n"
        "本文で `r.yml` の 4〜2行目 を引用する。\n",
        encoding="utf-8",
    )
    reader = _reader({("r.yml", "stage-01"): ("a", "b", "c", "d")})

    problems = check_document(path, reader)

    assert len(problems) == 1
    assert "逆順" in problems[0].message


def test_main_returns_zero_for_a_directory_of_valid_documents(tmp_path: Path, capsys):
    (tmp_path / "a.md").write_text(DOC_WITH_NO_TRANSCRIPTS_OR_CITATIONS, encoding="utf-8")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "b.md").write_text(
        DOC_WITH_NO_TRANSCRIPTS_OR_CITATIONS, encoding="utf-8"
    )

    exit_code = main([str(tmp_path)])

    assert exit_code == 0
    assert "2 件のドキュメント" in capsys.readouterr().out


def test_main_returns_one_and_reports_to_stderr_when_a_document_is_broken(tmp_path: Path, capsys):
    (tmp_path / "ng.md").write_text(DOC_WITH_OUT_OF_RANGE_CITATION, encoding="utf-8")

    exit_code = main([str(tmp_path)])

    assert exit_code == 1
    assert "ng.md" in capsys.readouterr().err


def test_cli_entrypoint_passes_command_line_arguments_to_main(tmp_path: Path):
    (tmp_path / "ng.md").write_text(DOC_WITH_OUT_OF_RANGE_CITATION, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "tools/check_doc_citations.py", str(tmp_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    assert result.returncode == 1
    assert "ng.md" in result.stderr


def test_check_document_reports_an_unclosed_fence(tmp_path: Path):
    path = tmp_path / "unclosed.md"
    path.write_text(
        "本文で 2行目 を引用する。\n\n```\n  1| a\n  2| b\n",
        encoding="utf-8",
    )

    problems = check_document(path, _reader({}))

    assert len(problems) == 1
    assert "フェンス" in problems[0].message


def test_check_document_reports_a_missing_file(tmp_path: Path):
    path = tmp_path / "missing.md"

    problems = check_document(path, _reader({}))

    assert len(problems) == 1
    assert "見つかりません" in problems[0].message


def test_collect_citations_finds_hyphen_range_form():
    """CITATION の `-` 区切り（全角の〜／～だけでなく半角ハイフンも受け付ける）を確認する。"""
    lines = DOC_WITH_HYPHEN_RANGE_CITATION.splitlines()

    citations = collect_citations(lines, frozenset({"h.yml"}))

    assert citations == (Citation(source_line=11, start=2, end=4, file_hint="h.yml"),)


def test_collect_transcripts_keeps_multiple_blocks_separate():
    """2つの転記ブロックを持つ文書で、行番号がブロックごとに独立していることを確認する。

    宣言が導入される前は、文書内の全転記ブロックの行番号を1つの集合にまとめており、
    どちらのファイルの行なのか区別できないという穴があった（フェーズ2最終レビュー
    の指摘）。宣言の仕組みにより、ブロックごとに line_numbers が分離されることを
    ここで確認する。これはかつて「区別しない現状の挙動」を記録していたテストを、
    その穴を塞いだ後の挙動を確認するテストに置き換えたものである。
    """
    lines = DOC_WITH_TWO_TRANSCRIPT_BLOCKS.splitlines()

    transcripts = collect_transcripts(lines)

    assert [t.source_path for t in transcripts] == ["first.yml", "second.yml"]
    assert transcripts[0].line_numbers == frozenset({1, 2})
    assert transcripts[1].line_numbers == frozenset({10, 11, 12})


def test_check_document_accepts_a_citation_that_only_exists_in_the_second_block(
    tmp_path: Path,
):
    """2つ目の転記ブロックだけに存在する行番号への、ファイル名を明記した引用が通ることを確認する。

    宣言導入前は、ブロックの区別なく「どこかの転記ブロックにこの行番号があれば良い」
    という緩い検査だった（これが塞ぐべき穴だった）。今はファイル名を明記した上で、
    そのファイルの転記ブロックの範囲内かどうかを検査するので、正しく名指しした
    引用は変わらず通る。
    """
    path = tmp_path / "two-blocks.md"
    path.write_text(DOC_WITH_TWO_TRANSCRIPT_BLOCKS, encoding="utf-8")
    reader = _reader(
        {
            ("first.yml", "stage-01"): ("name: CI", "on:"),
            ("second.yml", "stage-01"): ("jobs:", "  test:", "    runs-on: ubuntu-latest"),
        }
    )

    assert check_document(path, reader) == ()


# --- Step 2: 出所宣言の導入で閉じる2つの穴（クロスファイル引用・陳腐化検出）のテスト ---

DOC_WITH_TWO_DECLARED_BLOCKS = """# 見出し

<!-- transcript: a.yml @ stage-01 -->
```
  1| name: A
  2| on: push
```

<!-- transcript: b.yml @ stage-01 -->
```
  1| name: B
  2| on: pull_request
  3| jobs: {}
```

本文では `a.yml` の 2行目 と `b.yml` の 3行目 を引用する。
"""


A_YML = ("name: A", "on: push")
B_YML = ("name: B", "on: pull_request", "jobs: {}")
BOTH = {("a.yml", "stage-01"): A_YML, ("b.yml", "stage-01"): B_YML}


def test_collect_transcripts_reads_declarations_and_bodies():
    transcripts = collect_transcripts(DOC_WITH_TWO_DECLARED_BLOCKS.splitlines())

    assert all(isinstance(transcript, Transcript) for transcript in transcripts)
    assert [t.source_path for t in transcripts] == ["a.yml", "b.yml"]
    assert transcripts[0].tag == "stage-01"
    assert transcripts[0].line_numbers == frozenset({1, 2})
    assert transcripts[1].body == B_YML


def test_check_document_accepts_citations_scoped_to_the_named_file(tmp_path, capsys):
    path = tmp_path / "ok.md"
    path.write_text(DOC_WITH_TWO_DECLARED_BLOCKS, encoding="utf-8")

    assert check_document(path, _reader(BOTH)) == ()


def test_check_document_rejects_a_citation_valid_only_in_another_block(tmp_path):
    doc = DOC_WITH_TWO_DECLARED_BLOCKS.replace("`a.yml` の 2行目", "`a.yml` の 3行目")
    path = tmp_path / "cross.md"
    path.write_text(doc, encoding="utf-8")

    problems = check_document(path, _reader(BOTH))

    assert len(problems) == 1
    assert "a.yml" in problems[0].message
    assert "3行目" in problems[0].message


def test_check_document_reports_a_citation_that_names_no_file(tmp_path):
    doc = DOC_WITH_TWO_DECLARED_BLOCKS.replace(
        "本文では `a.yml` の 2行目 と `b.yml` の 3行目 を引用する。",
        "本文では 2行目 を引用する。",
    )
    path = tmp_path / "unnamed.md"
    path.write_text(doc, encoding="utf-8")

    problems = check_document(path, _reader(BOTH))

    assert len(problems) == 1
    assert "どのファイル" in problems[0].message


def test_check_document_detects_a_stale_transcript(tmp_path):
    path = tmp_path / "stale.md"
    path.write_text(DOC_WITH_TWO_DECLARED_BLOCKS, encoding="utf-8")
    drifted = {("a.yml", "stage-01"): ("name: A", "on: workflow_dispatch")}

    problems = check_document(path, _reader({**BOTH, **drifted}))

    assert len(problems) == 1
    assert "a.yml" in problems[0].message
    assert "2行目" in problems[0].message


def test_check_document_reports_a_source_that_cannot_be_read(tmp_path):
    path = tmp_path / "missing-source.md"
    path.write_text(DOC_WITH_TWO_DECLARED_BLOCKS, encoding="utf-8")

    problems = check_document(path, _reader({("b.yml", "stage-01"): B_YML}))

    assert len(problems) == 1
    assert "取得できません" in problems[0].message


def test_check_document_reports_an_undeclared_transcript_block(tmp_path):
    doc = DOC_WITH_TWO_DECLARED_BLOCKS.replace("<!-- transcript: a.yml @ stage-01 -->\n", "")
    path = tmp_path / "undeclared.md"
    path.write_text(doc, encoding="utf-8")

    problems = check_document(path, _reader(BOTH))

    assert any("宣言" in problem.message for problem in problems)


def test_git_source_reader_returns_none_for_an_unknown_tag(tmp_path):
    read = git_source_reader(tmp_path)

    assert read("nope.yml", "no-such-tag") is None


# --- レビュー修正1: file_hint の引き継ぎを段落内に限定する ---

DOC_WITH_UNRELATED_PARAGRAPH_BETWEEN_MENTION_AND_CITATION = """# 見出し

<!-- transcript: a.yml @ stage-01 -->
```
  1| name: A
  2| on: push
```

<!-- transcript: c.yml @ stage-01 -->
```
  1| name: C
  2| on: push
  3| jobs: {}
```

まず `a.yml` について説明する。

これは無関係な段落である。

ところで 2行目 が重要だ。
"""


def test_check_document_does_not_carry_a_file_hint_across_paragraphs(tmp_path):
    """段落をまたいだファイル名の引き継ぎは行わず、無名の引用として報告されることを確認する。

    レビューで再現された回帰（フェーズ2の穴1の再発）: `a.yml` を名指しした段落から、
    間に無関係な段落を挟んで数段落後に現れる無名の「2行目」引用にまで `a.yml` が
    引き継がれ、`a.yml` にたまたま2行目が存在するために誤って通っていた。引き継ぎの
    範囲を段落内に限定したことで、この引用は「どのファイルの引用か判別できない」
    として報告されるべきである。
    """
    path = tmp_path / "unrelated-paragraph.md"
    path.write_text(DOC_WITH_UNRELATED_PARAGRAPH_BETWEEN_MENTION_AND_CITATION, encoding="utf-8")
    reader = _reader(
        {
            ("a.yml", "stage-01"): ("name: A", "on: push"),
            ("c.yml", "stage-01"): ("name: C", "on: push", "jobs: {}"),
        }
    )

    problems = check_document(path, reader)

    assert len(problems) == 1
    assert "どのファイル" in problems[0].message


DOC_WITH_MULTILINE_PARAGRAPH_CITATION = """# 見出し

<!-- transcript: p.yml @ stage-01 -->
```
  1| name: P
  2| on: push
  3| jobs: {}
```

`p.yml` の内容について、
続く行で 3行目 に触れる。
"""


def test_check_document_carries_a_file_hint_within_the_same_paragraph(tmp_path):
    """段落内であれば、改行をまたいでもファイル名の引き継ぎが引き続き効くことを確認する。

    段落をまたいだ引き継ぎを止めた修正1が、同じ段落内での引き継ぎ（同じ行に無くても
    直前の行にファイル名があれば解決する）まで壊していないことを確認する。
    """
    path = tmp_path / "multiline-paragraph.md"
    path.write_text(DOC_WITH_MULTILINE_PARAGRAPH_CITATION, encoding="utf-8")
    reader = _reader({("p.yml", "stage-01"): ("name: P", "on: push", "jobs: {}")})

    assert check_document(path, reader) == ()


# --- レビュー修正2: 宣言漏れの転記ブロックをすべて報告する ---


def test_check_document_reports_every_undeclared_transcript_block(tmp_path):
    """宣言漏れの転記ブロックが複数あれば、最初の1件だけでなくすべて報告することを確認する。"""
    doc = (
        "# 見出し\n\n"
        "```\n  1| name: A\n  2| on: push\n```\n\n"
        "```\n  1| name: B\n  2| on: pull_request\n```\n"
    )
    path = tmp_path / "two-undeclared.md"
    path.write_text(doc, encoding="utf-8")

    problems = check_document(path, _reader({}))

    assert len(problems) == 2
    assert all("宣言" in problem.message for problem in problems)
