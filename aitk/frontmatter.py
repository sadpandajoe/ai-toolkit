"""Minimal reader for PROJECT.md's YAML-style frontmatter header.

Scoped narrowly to the shapes `PROJECT_TEMPLATE.md` actually uses: flat
scalars (string/int/bool/blank), one empty-or-not list (`modifiers: []`),
and one level of nested mapping (`reasoning_attempts:` with three integer
sub-keys). This is not a YAML parser -- aitk/ declares zero dependencies
(`pyproject.toml`'s `dependencies = []`) and `aitk.doctor._frontmatter`
already establishes the pattern of a small hand-rolled reader over pulling
in a general-purpose library for a narrow, known document shape.

Anything outside these shapes (multi-line strings, flow mappings, quoted
keys, anchors) is out of scope; a document that uses them will parse
partially or raise rather than silently misreading the value.
"""

from __future__ import annotations

from pathlib import Path

FRONTMATTER_DELIMITER = "---"


class FrontmatterError(ValueError):
    """The frontmatter header is missing or malformed."""


def _coerce_scalar(raw: str) -> object:
    text = raw.strip()
    if text == "":
        return None
    if text == "[]":
        return []
    if text == "true":
        return True
    if text == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise FrontmatterError(f"expected 'key: value', got {line!r}")
    key, _, value = line.partition(":")
    key = key.strip()
    if not key:
        raise FrontmatterError(f"empty key in line {line!r}")
    return key, value


def parse_frontmatter(text: str) -> dict[str, object]:
    """Parse the leading `---`-delimited YAML-style header of `text`.

    Returns `{}` if `text` has no frontmatter header at all. Raises
    `FrontmatterError` if a header exists but is malformed (unterminated,
    or a nested block deeper than one level).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return {}
    try:
        end_index = next(
            index
            for index in range(1, len(lines))
            if lines[index].strip() == FRONTMATTER_DELIMITER
        )
    except StopIteration as error:
        raise FrontmatterError("frontmatter header is not terminated by '---'") from error

    body = [line for line in lines[1:end_index] if line.strip()]
    result: dict[str, object] = {}
    current_nested: dict[str, object] | None = None

    for index, line in enumerate(body):
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            key, value = _split_key_value(line)
            scalar = _coerce_scalar(value)
            next_is_nested = (
                scalar is None
                and line.rstrip().endswith(":")
                and index + 1 < len(body)
                and body[index + 1][0] == " "
            )
            if next_is_nested:
                current_nested = {}
                result[key] = current_nested
            else:
                current_nested = None
                result[key] = scalar
        elif indent > 0 and current_nested is not None:
            key, value = _split_key_value(line.strip())
            current_nested[key] = _coerce_scalar(value)
        else:
            raise FrontmatterError(f"unexpected indented line with no parent: {line!r}")

    return result


def read_frontmatter(path: Path) -> dict[str, object]:
    """Read and parse the frontmatter header of the file at `path`."""
    return parse_frontmatter(path.read_text())
