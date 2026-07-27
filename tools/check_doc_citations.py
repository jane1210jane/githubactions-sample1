"""解説ドキュメント内の「N行目」引用を、同じ文書に転記された YAML と突き合わせて検査する。

本教材では、各ステージの解説にそのステージ時点のワークフロー YAML を転記し、
本文の行番号引用は転記ブロック内の行を指す約束にしている。
転記ブロックを編集したときに引用がズレるのを人の目で防ぐのは繰り返し失敗したため、
機械で検査する。

転記ブロックは、行頭が `NN| ` 形式の行だけで構成されたフェンス付きコードブロック。
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

FENCE_PREFIX = "```"
TRANSCRIPT_LINE = re.compile(r"^\s*(\d+)\|")
CITATION = re.compile(r"(\d+)\s*(?:〜|～|-)\s*(\d+)\s*行目|(\d+)\s*行目")
EXIT_OK = 0
EXIT_PROBLEMS_FOUND = 1


@dataclass(frozen=True)
class Citation:
    """本文中の行番号引用。単一行の引用は start == end とする。"""

    source_line: int
    start: int
    end: int


@dataclass(frozen=True)
class Problem:
    path: Path
    source_line: int
    message: str


def collect_transcript_line_numbers(lines: Sequence[str]) -> frozenset[int]:
    """転記ブロックに現れる行番号をすべて集める。"""
    numbers: set[int] = set()
    for line in _transcript_lines(lines):
        match = TRANSCRIPT_LINE.match(line)
        if match:
            numbers.add(int(match.group(1)))
    return frozenset(numbers)


def collect_citations(lines: Sequence[str]) -> tuple[Citation, ...]:
    """転記ブロックの外にある行番号引用を集める。"""
    citations: list[Citation] = []
    for source_line, line in _prose_lines(lines):
        for match in CITATION.finditer(line):
            if match.group(3) is not None:
                value = int(match.group(3))
                citations.append(Citation(source_line=source_line, start=value, end=value))
            else:
                citations.append(
                    Citation(
                        source_line=source_line,
                        start=int(match.group(1)),
                        end=int(match.group(2)),
                    )
                )
    return tuple(citations)


def check_document(path: Path) -> tuple[Problem, ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    transcript = collect_transcript_line_numbers(lines)
    problems: list[Problem] = []

    for citation in collect_citations(lines):
        label = _label(citation)
        if not transcript:
            problems.append(
                Problem(path, citation.source_line, f"{label} を引用しているが転記ブロックが無い")
            )
            continue
        if citation.start > citation.end:
            problems.append(Problem(path, citation.source_line, f"{label} は範囲が逆順"))
            continue
        missing = [n for n in range(citation.start, citation.end + 1) if n not in transcript]
        if missing:
            problems.append(Problem(path, citation.source_line, f"{label} は転記ブロックの範囲外"))

    return tuple(problems)


def main(argv: Sequence[str] | None = None) -> int:
    paths = tuple(_iter_markdown(Path(argument) for argument in (argv or ["docs/stages"])))
    problems = tuple(problem for path in paths for problem in check_document(path))

    for problem in problems:
        print(f"{problem.path}:{problem.source_line}: {problem.message}", file=sys.stderr)

    if problems:
        print(f"{len(problems)} 件の引用ズレが見つかりました", file=sys.stderr)
        return EXIT_PROBLEMS_FOUND

    print(f"{len(paths)} 件のドキュメントを検査し、引用ズレはありませんでした")
    return EXIT_OK


def _transcript_lines(lines: Sequence[str]) -> list[str]:
    return [line for line, is_prose in _classify(lines) if not is_prose]


def _prose_lines(lines: Sequence[str]) -> list[tuple[int, str]]:
    return [
        (number, line)
        for number, (line, is_prose) in enumerate(_classify(lines), start=1)
        if is_prose
    ]


def _classify(lines: Sequence[str]) -> list[tuple[str, bool]]:
    """各行を (本文か否か) の判定つきで返す。フェンス行自体は本文扱いしない。"""
    classified: list[tuple[str, bool]] = []
    inside_fence = False
    for line in lines:
        if line.lstrip().startswith(FENCE_PREFIX):
            inside_fence = not inside_fence
            classified.append((line, False))
            continue
        classified.append((line, not inside_fence))
    return classified


def _iter_markdown(paths: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(sorted(path.rglob("*.md")))
        else:
            found.append(path)
    return found


def _label(citation: Citation) -> str:
    if citation.start == citation.end:
        return f"{citation.start}行目"
    return f"{citation.start}〜{citation.end}行目"


if __name__ == "__main__":
    raise SystemExit(main())
