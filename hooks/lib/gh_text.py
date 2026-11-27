"""The git guard's text readings, for a command whose words cannot be trusted: `quoted_split`,
the pieces it cuts, and the gated verbs and git commands their text mentions."""

from __future__ import annotations

import re
from typing import Iterator

import shell_tokens
from git_rules import resolve_push_option


# `gh`, then `pr`, then the verb, each searched after the one before it: linear in the text
UNRESOLVED_PR_PUBLISH = (shell_tokens.WORD_GH, shell_tokens.WORD_PR, re.compile(r"\b(ready|merge|create|new|revert)\b"))
DRAFT_FLAG = re.compile(r"(?<![\w-])(?:--draft(?:=(?:true|1|t))?|-[A-Za-z]*d[A-Za-z]*)(?![\w=-])")


COMMAND_SEPARATOR = re.compile(r"[;&|\n]")


def redirection_char(text: str, index: int) -> bool:
    """Whether the `&` or `|` at `index` belongs to a redirection (`>&2`, `<&-`, `&>x`, `>|x`)."""
    before = text[index - 1 : index] if index else ""
    if text[index] == "&":
        return before in {">", "<"} or text[index + 1 : index + 2] == ">"
    return text[index] == "|" and before == ">"


def quoted_split(text: str) -> list[str]:
    """`text` cut at the `;`, `&`, `|` and newlines the shell reads as separators: not one a
    quote holds (`-t "a;b"` is one word), not an escaped one (`\\;`), and not one inside a
    `$(...)`, a `${...}` or a backtick pair (`gh pr $(a; b) merge 12` is one command), and not an `&` or `|`
    of a redirection (`>&2`, `&>x`, `>|x`). Nested `sh -c` text is
    one quoted word, so it stays whole: this reading only adds to the plain split."""
    pieces: list[str] = []
    stack: list[str] = []  # open `'`, `"`, backtick, `(` (of a `$(`) and `{` (of a `${`)
    start = index = 0
    while index < len(text):
        char = text[index]
        top = stack[-1] if stack else ""
        if char == "\\" and top != "'":
            index += 2
            continue
        if top == "'":
            if char == "'":
                stack.pop()
        elif char == "`" and top == "`":
            stack.pop()
        elif top == '"' and char == '"':
            stack.pop()
        elif char == "`":
            stack.append("`")
        elif top != '"' and char in "'\"":
            stack.append(char)
        elif text.startswith("$(", index):
            stack.append("(")
            index += 1
        elif text.startswith("${", index):
            stack.append("{")
            index += 1
        elif top == "(" and char == "(":
            stack.append("(")
        elif top == "(" and char == ")":
            stack.pop()
        elif top == "{" and char == "{":
            stack.append("{")
        elif top == "{" and char == "}":
            stack.pop()
        elif not stack and char in ";&|\n" and not redirection_char(text, index):
            pieces.append(text[start:index])
            start = index + 1
        index += 1
    return pieces + [text[start:]]


def unresolved_gated(text: str) -> Iterator[str]:
    """The gated verb of every `gh pr VERB` in text that did not parse. `ready` and `merge`
    always count; a creation or revert counts unless a draft flag sits in the same separated
    command. Each search starts where the last match ended, so the scan is linear."""
    # origin/main's rule over the whole text, whatever holds a separator (`$((1|2))`, `${X-a;b}`,
    # a quote inside `$(...)`): the union with the piece-wise readings below blocks wherever main does
    whole = shell_tokens.words_in_order(text, *UNRESOLVED_PR_PUBLISH)
    if whole and (whole.group(1) in {"ready", "merge"} or DRAFT_FLAG.search(text) is None):
        yield whole.group(1)
    for command in COMMAND_SEPARATOR.split(text) + quoted_split(text):
        position = 0
        drafted = None  # DRAFT_FLAG is searched at most once per command
        while True:
            match = None
            for pattern in UNRESOLVED_PR_PUBLISH:
                match = pattern.search(command, position)
                if match is None:
                    break
                position = match.end()
            if match is None:
                break
            if drafted is None:
                drafted = DRAFT_FLAG.search(command) is not None
            if match.group(1) in {"ready", "merge"} or not drafted:
                yield match.group(1)


UNTRUSTED_VERB = re.compile(r"\b(ready|merge|create|new|revert)\b")
NOT_A_HEAD = re.compile(r"[<>]|\d+[<>]|\(|\)")


def without_spaced_quotes(text: str) -> str:
    """`text` with each quoted string that holds whitespace replaced by `Q`: it can only be one
    argument (`'gh pr merge'` in `grep -l 'gh pr merge'`). A quoted word without whitespace
    (`';'`, `'a;b'`) stays: it may be a flag value or a verb."""
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and index + 1 < len(text):
            out.append(text[index : index + 2])
            index += 2
            continue
        if char in "'\"":
            end = index + 1
            while end < len(text) and text[end] != char:
                end += 2 if char == '"' and text[end] == "\\" else 1
            quoted = text[index : end + 1]
            out.append("Q" if any(c.isspace() for c in quoted) else quoted)
            index = end + 1
            continue
        out.append(char)
        index += 1
    return "".join(out)


def piece_head(piece: str) -> str:
    """The command a separated piece of text runs: its first word that is no keyword,
    assignment, wrapper or redirection."""
    for word in piece.split():
        if (
            word in shell_tokens.KEYWORDS
            or word in shell_tokens.SIMPLE_WRAPPERS
            or shell_tokens.is_assignment(word)
            or NOT_A_HEAD.match(word)
        ):
            continue
        return shell_tokens.head_name(shell_tokens.unquoted(word))
    return ""


def untrusted_pieces(source: str) -> Iterator[str]:
    """The pieces of text a quoted or escaped operator left in doubt: `source` cut where the
    shell really separates commands (`quoted_split`), each without the quoted words that hold
    whitespace (an argument: `grep -l 'gh pr merge'`; a command a payload hands to a shell is
    walked on its own), and without one that only prints its words (`INERT_HEADS`: `echo '()' gh pr
    ready 12` runs none of them)."""
    yield from pieces_read(source, shell_tokens.Walk(), 0)


def pieces_read(source: str, walk: shell_tokens.Walk, depth: int) -> Iterator[str]:
    """`untrusted_pieces` of `source`. A command that only prints its words still runs its
    substitutions (`echo $(gh pr -t ';' merge 12)`), so their bodies are read as pieces of their
    own; past the budget or the depth limit the whole piece is read."""
    for piece in quoted_split(source):
        light = without_spaced_quotes(piece)
        if piece_head(light) not in shell_tokens.INERT_HEADS:
            yield light
            continue
        held = piece.replace("<(", "$(").replace(">(", "$(")
        if "$(" not in held and "`" not in held:
            continue
        if depth >= shell_tokens.DEPTH_LIMIT:
            yield light
            continue
        for body in shell_tokens.inner_commands(held, walk):
            if body is None:
                yield light
                return
            yield from pieces_read(body, walk, depth + 1)


def untrusted_text_verbs(piece: str) -> Iterator[str]:
    """The gated verb of a `gh ... pr ... VERB` in a piece of text, quoting removed or not. Used
    when a quoted or escaped operator standing alone as a word came out as a bare one: it cuts a
    command in two (`gh pr -t ';' merge 12`) or hides a flag behind a redirection
    (`gh >/dev/null pr -t '>' merge 12`), so no argv is trusted by itself."""
    for form in (piece, shell_tokens.unquoted(piece)):
        match = shell_tokens.words_in_order(form, shell_tokens.WORD_GH, shell_tokens.WORD_PR, UNTRUSTED_VERB)
        if match:
            yield match.group(1)
            return


FORCE_OR_DELETE = {"force", "force-with-lease", "force-if-includes", "delete", "mirror"}
GIT_COMMIT_WORD = re.compile(r"\bcommit\b")


def push_marker(word: str) -> bool:
    """Whether a word after `push` in text the guard cannot read forces or deletes: a short
    cluster with `f` or `d`, a `+` or `:` refspec, or a long option git reads as one of
    `FORCE_OR_DELETE` (a unique prefix too: `--de`, `--mi`); an ambiguous prefix of one counts."""
    if re.fullmatch(r"-[A-Za-z0-9]*[fd][A-Za-z0-9]*", word) or word[:1] in "+:" and len(word) > 1:
        return True
    if not word.startswith("--") or len(word) < 3:
        return False
    name = word[2:].split("=", 1)[0]
    resolved = resolve_push_option(name)
    if resolved is not None:
        return resolved[0] in FORCE_OR_DELETE and not resolved[1]
    return any(option.startswith(name) for option in FORCE_OR_DELETE)


def unseen_git(text: str) -> str | None:
    """`git push` with a force or delete marker, or `git commit`, in one line or separated command
    of text the guard cannot read: the branch, the directory and the staged files are unknown."""
    joined = text.replace("\\\n", "")  # bash joins a line continuation with nothing between
    try:
        joined = shell_tokens.expand_ansi_c(joined)  # `$'+main'`
    except ValueError:
        pass
    # cut where the shell separates commands, quotes honoured (`-o 'a;b' --force` is one command),
    # and, as before, at every separator once the quotes are gone: either reading may block
    pieces = [shell_tokens.unquoted(piece) for piece in quoted_split(joined)]
    pieces += COMMAND_SEPARATOR.split(shell_tokens.unquoted(joined))
    for piece in pieces:
        push = shell_tokens.words_in_order(piece, shell_tokens.WORD_GIT, shell_tokens.WORD_PUSH)
        if push and any(push_marker(word) for word in piece[push.end() :].split()):
            return "`git push` with a force or delete flag"
        if shell_tokens.words_in_order(piece, shell_tokens.WORD_GIT, GIT_COMMIT_WORD):
            return "`git commit`"
    return None
