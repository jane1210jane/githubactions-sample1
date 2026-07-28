"""解説ドキュメント内の「N行目」引用を、同じ文書に転記された YAML と突き合わせて検査する。

本教材では、各ステージの解説にそのステージ時点のワークフロー YAML を転記し、
本文の行番号引用は転記ブロック内の行を指す約束にしている。
転記ブロックを編集したときに引用がズレるのを人の目で防ぐのは繰り返し失敗したため、
機械で検査する。

転記ブロックは、行頭が `NN| ` 形式の行だけで構成されたフェンス付きコードブロック。
その直前の非空行には、転記元を示す出所宣言を1行だけ書く。

    <!-- transcript: <repo-relative-path> @ <tag> -->

出所宣言は、フェーズ2の最終レビューで見つかった2つの穴を塞ぐために存在する。

1. 宣言が無いと、引用が「どのファイルの」行番号かをツールが判別できない。
   文書内に複数の転記ブロックがあると、`action.yml` の12行目を指したつもりの
   引用が `ci.yml` の12行目で満たされてしまう。宣言でブロックごとにファイルを
   区別し、本文の引用も `ファイル名` を名指しさせることでこれを防ぐ。
2. 宣言（とタグ）が無いと、転記ブロック自体がそのタグ時点のファイルと一致して
   いるかを検証できない。転記ブロックを機械的に `git show <tag>:<path>` の
   内容と突き合わせ、転記が古くなっていないかを検査する。
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

FENCE_PREFIX = "```"
TRANSCRIPT_LINE = re.compile(r"^\s*(\d+)\|")
TRANSCRIPT_BODY = re.compile(r"^\s*\d+\|\s?")
DECLARATION = re.compile(r"^<!--\s*transcript:\s*(\S+)\s*@\s*(\S+)\s*-->\s*$")
CITATION = re.compile(r"(\d+)\s*(?:〜|～|-)\s*(\d+)\s*行目|(\d+)\s*行目")
EXIT_OK = 0
EXIT_PROBLEMS_FOUND = 1

SourceReader = Callable[[str, str], tuple[str, ...] | None]


@dataclass(frozen=True)
class Citation:
    """本文中の行番号引用。単一行の引用は start == end とする。"""

    source_line: int
    start: int
    end: int
    file_hint: str | None


@dataclass(frozen=True)
class Transcript:
    """解説に転記されたファイル1つ分のブロック。"""

    source_path: str
    tag: str
    declared_at: int
    line_numbers: frozenset[int]
    body: tuple[str, ...]

    @property
    def name(self) -> str:
        """本文が名指しに使うファイル名（basename）。"""
        return self.source_path.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class Problem:
    path: Path
    source_line: int
    message: str


def collect_transcripts(lines: Sequence[str]) -> tuple[Transcript, ...]:
    """出所宣言を伴う転記ブロックを、文書に現れる順にすべて集める。

    宣言を伴わない番号付きフェンスは、ここでは無視する
    （`check_document` が別途「宣言がありません」として報告する）。
    """
    transcripts: list[Transcript] = []
    for fence_start, numbers, body in _iter_numbered_fence_blocks(lines):
        declaration = _preceding_declaration(lines, fence_start)
        if declaration is None:
            continue
        declared_at, source_path, tag = declaration
        transcripts.append(
            Transcript(
                source_path=source_path,
                tag=tag,
                declared_at=declared_at,
                line_numbers=frozenset(numbers),
                body=body,
            )
        )
    return tuple(transcripts)


def collect_citations(lines: Sequence[str], names: frozenset[str]) -> tuple[Citation, ...]:
    """転記ブロックの外にある行番号引用を、名指しされたファイル名つきで集める。

    `names` に含まれるファイル名（basename）が本文に現れるたびに「今どのファイルの
    話をしているか」を更新し、以降の引用の `file_hint` として使う。同じ行の中で
    引用より前に現れたファイル名を優先し、同じ行に無ければ、文書内でそれまでに
    現れた最後のファイル名を引き継ぐ。1つも無ければ `None`。
    """
    name_pattern = _build_name_pattern(names)
    citations: list[Citation] = []
    current_hint: str | None = None
    for source_line, line in _prose_lines(lines):
        if DECLARATION.match(line):
            # 出所宣言そのものはファイル名の「言及」として数えない。
            # 宣言コメントにはファイル名の文字列がそのまま含まれるため、
            # ここで拾うと本文の引用が意図せず宣言側のファイルを指してしまう。
            continue
        for _, name, start, end in _line_events(line, name_pattern):
            if name is not None:
                current_hint = name
                continue
            citations.append(
                Citation(source_line=source_line, start=start, end=end, file_hint=current_hint)
            )
    return tuple(citations)


def check_document(path: Path, read_source: SourceReader) -> tuple[Problem, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return (Problem(path, 0, "ファイルが見つかりません"),)

    unclosed_fence_line = _find_unclosed_fence(lines)
    if unclosed_fence_line is not None:
        return (
            Problem(
                path,
                unclosed_fence_line,
                f"{unclosed_fence_line}行目で開始したコードフェンスが閉じられていません",
            ),
        )

    problems: list[Problem] = []

    undeclared_line = _find_undeclared_transcript(lines)
    if undeclared_line is not None:
        problems.append(
            Problem(
                path,
                undeclared_line,
                "転記ブロックに出所宣言（<!-- transcript: <path> @ <tag> -->）がありません",
            )
        )

    transcripts = collect_transcripts(lines)
    by_name = {transcript.name: transcript for transcript in transcripts}

    for transcript in transcripts:
        source_lines = read_source(transcript.source_path, transcript.tag)
        if source_lines is None:
            problems.append(
                Problem(
                    path,
                    transcript.declared_at,
                    f"{transcript.source_path} @ {transcript.tag} の内容を取得できません",
                )
            )
            continue
        mismatch_line = _first_mismatch(transcript.body, source_lines)
        if mismatch_line is not None:
            problems.append(
                Problem(
                    path,
                    transcript.declared_at,
                    f"{transcript.source_path} の転記が {transcript.tag} 時点の内容と"
                    f"一致しません（{mismatch_line}行目）",
                )
            )

    names = frozenset(by_name)
    for citation in collect_citations(lines, names):
        label = _label(citation)
        if citation.file_hint is None:
            problems.append(
                Problem(
                    path,
                    citation.source_line,
                    f"{label} がどのファイルの引用か本文から判別できません",
                )
            )
            continue
        cited_transcript = by_name.get(citation.file_hint)
        if cited_transcript is None:
            problems.append(
                Problem(
                    path, citation.source_line, f"{citation.file_hint} の転記ブロックがありません"
                )
            )
            continue
        if citation.start > citation.end:
            problems.append(Problem(path, citation.source_line, f"{label} は範囲が逆順"))
            continue
        missing = [
            number
            for number in range(citation.start, citation.end + 1)
            if number not in cited_transcript.line_numbers
        ]
        if missing:
            problems.append(
                Problem(
                    path,
                    citation.source_line,
                    f"{citation.file_hint} の {label} は転記ブロックの範囲外",
                )
            )

    return tuple(problems)


def git_source_reader(repo_root: Path) -> SourceReader:
    """`git show <tag>:<path>` で転記元の内容を読む SourceReader を返す。"""

    def read(source_path: str, tag: str) -> tuple[str, ...] | None:
        completed = subprocess.run(
            ["git", "show", f"{tag}:{source_path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            return None
        return tuple(completed.stdout.splitlines())

    return read


def main(argv: Sequence[str] | None = None) -> int:
    paths = tuple(_iter_markdown(Path(argument) for argument in (argv or ["docs/stages"])))
    read_source = git_source_reader(Path.cwd())
    problems = tuple(problem for path in paths for problem in check_document(path, read_source))

    for problem in problems:
        print(f"{problem.path}:{problem.source_line}: {problem.message}", file=sys.stderr)

    if problems:
        print(f"{len(problems)} 件の引用ズレが見つかりました", file=sys.stderr)
        return EXIT_PROBLEMS_FOUND

    print(f"{len(paths)} 件のドキュメントを検査し、引用ズレはありませんでした")
    return EXIT_OK


def _iter_fence_blocks(lines: Sequence[str]) -> Iterable[tuple[int, list[str]]]:
    """フェンスで囲まれた行ブロックを (開始行番号(1-indexed), 中身の行のリスト) として列挙する。"""
    fence_start: int | None = None
    body: list[str] = []
    for index, line in enumerate(lines, start=1):
        if line.lstrip().startswith(FENCE_PREFIX):
            if fence_start is None:
                fence_start = index
                body = []
            else:
                yield fence_start, body
                fence_start = None
            continue
        if fence_start is not None:
            body.append(line)


def _iter_numbered_fence_blocks(
    lines: Sequence[str],
) -> Iterable[tuple[int, tuple[int, ...], tuple[str, ...]]]:
    """行番号付きの行だけで構成されたフェンスブロックを列挙する。

    番号付き行が1行も無いフェンスは転記ブロックではないので無視する。
    """
    for fence_start, body in _iter_fence_blocks(lines):
        numbers = tuple(int(m.group(1)) for line in body if (m := TRANSCRIPT_LINE.match(line)))
        if not numbers:
            continue
        body_text = tuple(TRANSCRIPT_BODY.sub("", line, count=1) for line in body)
        yield fence_start, numbers, body_text


def _preceding_declaration(lines: Sequence[str], fence_start: int) -> tuple[int, str, str] | None:
    """フェンス開始行(1-indexed)の直前の非空行が出所宣言なら (行番号, path, tag) を返す。"""
    for index in range(fence_start - 1, 0, -1):
        line = lines[index - 1]
        if line.strip() == "":
            continue
        match = DECLARATION.match(line)
        if match:
            return index, match.group(1), match.group(2)
        return None
    return None


def _find_undeclared_transcript(lines: Sequence[str]) -> int | None:
    """出所宣言を伴わない番号付きフェンスがあれば、その開始行番号を返す。無ければ None。"""
    for fence_start, _, _ in _iter_numbered_fence_blocks(lines):
        if _preceding_declaration(lines, fence_start) is None:
            return fence_start
    return None


def _first_mismatch(body: tuple[str, ...], source_lines: tuple[str, ...]) -> int | None:
    """転記本文と転記元の内容を行単位で比較し、最初に食い違った行番号(1-indexed)を返す。

    行数が異なる場合も、共通する範囲を越えた最初の行を食い違いとして扱う。
    """
    length = max(len(body), len(source_lines))
    for index in range(length):
        body_line = body[index] if index < len(body) else None
        source_line = source_lines[index] if index < len(source_lines) else None
        if body_line != source_line:
            return index + 1
    return None


def _build_name_pattern(names: frozenset[str]) -> re.Pattern[str] | None:
    """`names` のいずれかに一致するファイル名トークンを検出する正規表現を作る。

    他のファイル名の一部（例: `ci.yml` が `reusable-python-ci.yml` の末尾に
    含まれる）と誤って一致しないよう、前後が単語文字・`.`・`-` ではないことを
    要求する。
    """
    if not names:
        return None
    alternation = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    return re.compile(rf"(?<![\w.-])(?:{alternation})(?![\w.-])")


def _line_events(
    line: str, name_pattern: re.Pattern[str] | None
) -> list[tuple[int, str | None, int, int]]:
    """1行の中の「ファイル名の言及」と「行番号引用」を、出現位置順のイベント列にする。

    各要素は (開始位置, ファイル名 or None, 引用開始行, 引用終了行)。
    ファイル名の言及は `name` が非 None、引用は `name` が None で表す。
    """
    events: list[tuple[int, str | None, int, int]] = []
    if name_pattern is not None:
        for match in name_pattern.finditer(line):
            events.append((match.start(), match.group(0), 0, 0))
    for match in CITATION.finditer(line):
        if match.group(3) is not None:
            value = int(match.group(3))
            events.append((match.start(), None, value, value))
        else:
            events.append((match.start(), None, int(match.group(1)), int(match.group(2))))
    events.sort(key=lambda event: event[0])
    return events


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


def _find_unclosed_fence(lines: Sequence[str]) -> int | None:
    """閉じられていないコードフェンスがあれば、その開始行番号を返す。無ければ None。

    フェンスは入れ子にならない前提（開始・終了が単純に交互に現れる）で数えている。
    """
    fence_start: int | None = None
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith(FENCE_PREFIX):
            fence_start = number if fence_start is None else None
    return fence_start


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
    raise SystemExit(main(sys.argv[1:]))
