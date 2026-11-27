"""The lexer under `shell_tokens`: `tokenize`, the spans and words of one command, and the
word patterns callers match text with.

`shell_tokens` re-exports the names its callers read; its docstring describes the walk.

A file descriptor (`2` of `2>&1`, `{fd}` of `{fd}>x`) is a word glued to its operator after a word
boundary; the lexer marks it (`FdWord`) and `drop_redirections` drops only those. A number apart from its
operator (`-o 5 >x`) is an argument.

`$'...'` words are rewritten into plain quoted words before shlex, which has no ANSI-C
quoting (`expand_ansi_c`); one that never closes does not tokenize.
"""

from __future__ import annotations

import re
import shlex
from typing import Iterator


SEPARATORS = {";", "&&", "||", "|", "&", "|&", "(", ")"}
KEYWORDS = {"if", "then", "elif", "else", "do", "while", "until", "!", "{", "}"}
SIMPLE_WRAPPERS = {"command", "exec", "nohup", "time"}
# The one substitution `advance_dir` resolves instead of leaving unknown: the git top level
# of the current directory. Exactly this text, in the `$(...)` or the backtick spelling.
TOPLEVEL_SUBSTITUTIONS = ("$(git rev-parse --show-toplevel)", "`git rev-parse --show-toplevel`")
# The one substitution `check_push` resolves: the current branch, which it reads itself.
CURRENT_BRANCH_SUBSTITUTIONS = ("$(git branch --show-current)", "`git branch --show-current`")

HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([^\s'\"<>;|&()\\]+)\2")
WORD_START = " \t\n;&|("

# The override scan only: redirection operators as the tokenizer splits them,
# each followed by its target word, and the words that restart the scan when
# they appear later in an argv (behind a wrapper this module does not know).
REDIRECTIONS = {">", ">>", "<", "<<", "<<<", "<>", ">&", "<&", ">|", "&>", "&>>"}
REDIRECTION_FD = re.compile(r"\d+|\{[A-Za-z_]\w*\}")


FD_BOUNDARY = frozenset([" ", "\t", "\n", " ; ", ";", "&", "|", "(", ")"])
DIGITS = "0123456789"
FD_MARK = "\x01"  # in front of a file descriptor the lexer reads: `FdWord`


class FdWord(str):
    """A file descriptor of a redirection (`2` of `2>&1`, `{fd}` of `{fd}>x`): a word glued to
    its operator after a word boundary. The same text apart from its operator (`-o 5 >x`) is an
    argument and a plain str."""


def mark_fd(out: list[str]) -> str:
    """Mark the file descriptor that ends `out` (`2` of `2>x`, `{fd}` of `{fd}>x`) with
    `FD_MARK` and return the character before it, or "" when there is none.

    Bash reads it as a descriptor only when it is a whole word glued to the operator: after a
    word boundary (not `a2>x`, not `5 >x`, where `5` is an argument)."""
    end = len(out)
    start = end
    while start and len(out[start - 1]) == 1 and out[start - 1] in DIGITS:
        start -= 1
    if start == end and out and out[-1] == "}":
        name = end - 1
        while name and len(out[name - 1]) == 1 and (out[name - 1].isalnum() or out[name - 1] == "_"):
            name -= 1
        if name and name < end - 1 and out[name - 1] == "{" and out[name] not in DIGITS:
            start = name - 1
    if start == end:
        return ""
    before = out[start - 1] if start else "\n"
    if before not in FD_BOUNDARY or (before == "&" and start > 1 and out[start - 2] in {"<", ">"}):
        return ""  # `>&2>x`: the `2` is the target of `>&`
    out.insert(start, FD_MARK)
    return before


def split_lines(text: str) -> str:
    """Normalize a command for tokenizing.

    Unquoted newlines become `;`, backslash-newline joins lines, comments are
    dropped, and here-document bodies are skipped, including one opened inside
    a `$(...)` within double quotes (`--body "$(cat <<'EOF' ...)"`).
    """
    out: list[str] = []
    quote: str | None = None
    pending: list[tuple[bool, str]] = []
    substitutions = 0
    previous = "\n"
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'" and index + 1 < len(text):
            if text[index + 1] != "\n":
                out.append(text[index : index + 2])
                previous = "a"
            index += 2
            continue
        if quote is None and char == "#" and previous in WORD_START:
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char in "<>" and quote is None and text[index + 1 : index + 2] != "(":
            dropped = mark_fd(out)  # `2>x`, `{fd}>x`: a descriptor, no word
            previous = ("\n" if len(dropped) > 1 else dropped) or previous
        if char == "<" and (quote is None or (quote == '"' and substitutions)):
            match = None
            if not text.startswith("<<<", index) and previous in WORD_START:
                match = HEREDOC.match(text, index)
            if match:
                pending.append((match.group(1) == "-", match.group(3)))
                out.append(match.group(0))
                previous = "a"
                index = match.end()
                continue
        if quote == '"':
            if text.startswith("$(", index):
                substitutions += 1
            elif char == ")" and substitutions:
                substitutions -= 1
        if quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
            substitutions = 0
        if char == "\n" and (quote is None or pending):
            out.append(" ; " if quote is None else "\n")
            previous = "\n"
            index += 1
            for strip, delimiter in pending:
                while index < len(text):
                    end = text.find("\n", index)
                    end = len(text) if end < 0 else end
                    line = text[index:end]
                    index = min(end + 1, len(text))
                    if (line.strip() if strip else line) == delimiter:
                        break
            pending = []
            continue
        out.append(char)
        previous = char
        index += 1
    return "".join(out)


PUNCTUATION = frozenset("();<>|&")
# One shell operator at a time, longest first (maximal munch). `()` stays whole: it is the
# function-definition head `f()`. Redirection operators keep their spelling (`>&`, `&>>`).
OPERATOR = re.compile(r"&>>|<<<|&&|\|\||>>|<<|<&|>&|&>|<>|>\||\|&|\(\)|.")


def split_operators(token: str) -> list[str]:
    """A token made only of operator characters, split into the operators it holds.

    shlex (`punctuation_chars`) returns a whole run as one token: `);`, `;(`, `&&(`,
    `)&&`, `)|`, `f()(`. Left fused, the command after the run reads as arguments of the
    one before it. A quoted all-operator word (`'));'`) reads the same: an accepted over-block.
    """
    if token and all(char in PUNCTUATION for char in token):
        return OPERATOR.findall(token)
    return [token]


class Tokens(list):
    """Shell words and operators, plus whether a quoted operator came out as a bare one."""

    quoted_operators = False
    cleaned = ""  # the text the lexer read: comments, here-document bodies and descriptors gone
    backticks = True  # whether the text has a backtick no quote holds (a span `join_backtick_words` may fold)


OPERATOR_CHARS = frozenset(";&|()<>")


def unquoted_operators(text: str) -> int:
    """Operator characters (`;&|()<>`) outside quotes, not escaped and not inside `${...}`.

    Those are the ones the lexer reads as operators and the shell reads as syntax.
    """
    count = 0
    quote: str | None = None
    braces = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
        elif quote is None and text.startswith("${", index):
            braces += 1
            index += 1
        elif quote is None and braces and char == "{":
            braces += 1
        elif quote is None and braces and char == "}":
            braces -= 1
        elif quote is None and not braces and char in OPERATOR_CHARS:
            count += 1
        index += 1
    return count


def unquoted_backticks(text: str) -> int:
    """Backticks outside quotes and not escaped: the only ones that open a command-substitution
    span the words of a command can be folded over (`'a`b'` and `\\`` open none)."""
    count = 0
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            index += 2
            continue
        if quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
        elif quote is None and char == "`":
            count += 1
        index += 1
    return count


def quoted_substitution_separator(text: str) -> bool:
    """Whether a `$(...)` inside double quotes holds a `;`, `&` or `|` inside double quotes of
    its own (`"$(echo "a;b")"`). The shell reads the inner quotes on their own; the lexer closes
    the outer string at the first one, so the separator comes out bare and cuts the command in
    two: the words around the substitution are not read right. A separator in single quotes
    (`"$(echo 'a;b')"`) or outside quotes (`"$(a | b)"`) stays in the outer string: no doubt.
    One pass over the text, whatever the number of `$(`."""
    quote: str | None = None  # the outer quote
    inner: str | None = None  # the quote of its own inside a `$(...)`
    depth = 0  # open parentheses of the `$(...)` the outer double quote holds
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and (inner != "'" if depth else quote != "'"):
            index += 2
            continue
        if depth:
            if inner is None:
                if char in "'\"":
                    inner = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
            elif char == inner:
                inner = None
            elif inner == '"' and char in ";&|":
                return True
        elif quote is None and char in "'\"":
            quote = char
        elif quote == char:
            quote = None
        elif quote == '"' and text.startswith("$(", index):
            depth, inner = 1, None
            index += 1
        index += 1
    return False


ANSI_ESCAPE = re.compile(
    r"\\(?:([abefnrtv\\'\"?])|([0-7]{1,3})|x([0-9a-fA-F]{1,2})|u([0-9a-fA-F]{1,4})"
    r"|U([0-9a-fA-F]{1,8})|c(.)|(.))",
    re.S,
)
ANSI_SIMPLE = {
    "a": "\a", "b": "\b", "e": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
    "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?",
}


def decode_ansi_c(body: str) -> str:
    """The text of a `$'...'` string body: C escapes decoded, an unknown escape kept."""

    def one(match: re.Match[str]) -> str:
        simple, octal, hexadecimal, short, long, control, other = match.groups()
        if simple:
            return ANSI_SIMPLE[simple]
        if octal:
            return chr(int(octal, 8) & 0xFF)
        if hexadecimal or short or long:
            return chr(int(hexadecimal or short or long, 16))
        if control:
            return chr(ord(control) & 0x1F)
        return match.group(0)

    return ANSI_ESCAPE.sub(one, body)


def expand_ansi_c(text: str) -> str:
    """Rewrite each unquoted `$'...'` word as the plain quoted word the lexer reads right.

    shlex has no ANSI-C quoting: it ends `$'\\''` at the escaped quote and reads the rest of
    the command as one quoted word, hiding it. Raises ValueError for one that never closes.
    """
    if "$'" not in text:
        return text
    out: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\" and quote != "'":
            out.append(text[index : index + 2])
            index += 2
        elif quote is None and char == "#" and (index == 0 or text[index - 1] in WORD_START):
            end = text.find("\n", index)
            end = len(text) if end < 0 else end
            out.append(text[index:end])
            index = end
        elif quote is None and text.startswith("$'", index):
            end = index + 2
            while end < len(text) and text[end] != "'":
                end += 2 if text[end] == "\\" else 1
            if end >= len(text):
                raise ValueError("No closing quotation")
            out.append(shlex.quote(decode_ansi_c(text[index + 2 : end])))
            index = end + 1
        else:
            if quote is None and char in "'\"":
                quote = char
            elif quote == char:
                quote = None
            out.append(char)
            index += 1
    return "".join(out)


def tokenize(text: str) -> list[str]:
    """Shell words and operators; raises ValueError on unbalanced quotes.

    The result's `quoted_operators` is set when a quoted or escaped operator character
    (`echo ')'`, `\\(`, `\\;`) or one inside `${...}` came out as a bare operator token: the
    paren stack of `DirectoryModel` is not trusted then.
    """
    cleaned = split_lines(expand_ansi_c(text.replace(FD_MARK, "?")))
    lexer = shlex.shlex(cleaned, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    tokens = Tokens(
        FdWord(part[1:]) if part.startswith(FD_MARK) else part
        for token in lexer
        for part in split_operators(token)
    )
    cleaned = cleaned.replace(FD_MARK, "")
    bare = sum(
        char in OPERATOR_CHARS
        for token in tokens
        if all(char in PUNCTUATION for char in token)
        for char in token
    )
    tokens.quoted_operators = bare != unquoted_operators(cleaned) or quoted_substitution_separator(cleaned)
    tokens.backticks = unquoted_backticks(cleaned) > 0
    tokens.cleaned = cleaned
    return tokens


READ_SUBSTITUTIONS = (
    (["$", "(", "git", "rev-parse", "--show-toplevel", ")"], TOPLEVEL_SUBSTITUTIONS[0]),
    (["`git", "rev-parse", "--show-toplevel`"], TOPLEVEL_SUBSTITUTIONS[1]),
    (["$", "(", "git", "branch", "--show-current", ")"], CURRENT_BRANCH_SUBSTITUTIONS[0]),
    (["`git", "branch", "--show-current`"], CURRENT_BRANCH_SUBSTITUTIONS[1]),
)


def join_toplevel(tokens: list[str]) -> list[str]:
    """Rejoin the two substitutions read on purpose into one word each, in both spellings.

    `$ ( git rev-parse --show-toplevel )` (`advance_dir` resolves it) and `$ ( git branch
    --show-current )` (the current branch, for `check_push`), and their backtick forms. The
    lexer breaks the unquoted forms at the parentheses (or the backticks' spaces); quoted,
    they are already one word.
    """
    joined = Tokens()
    joined.quoted_operators = getattr(tokens, "quoted_operators", False)
    joined.backticks = getattr(tokens, "backticks", True)
    joined.cleaned = getattr(tokens, "cleaned", "")
    index = 0
    while index < len(tokens):
        for words, replacement in READ_SUBSTITUTIONS:
            if tokens[index : index + len(words)] == words:
                joined.append(replacement)
                index += len(words)
                break
        else:
            joined.append(tokens[index])
            index += 1
    return joined


def is_assignment(token: str, *, include_append: bool = False) -> bool:
    name, sep, _ = token.partition("=")
    if include_append and name.endswith("+"):
        name = name[:-1]
    return bool(sep) and name.isidentifier()


def segment_spans(tokens: list[str]) -> Iterator[tuple[int, list[str]]]:
    """Each non-empty segment between separators, with the index of its first token."""
    current: list[str] = []
    for index, token in enumerate(tokens):
        if token in SEPARATORS:
            if current:
                yield index - len(current), current
            current = []
        else:
            current.append(token)
    if current:
        yield len(tokens) - len(current), current


def kept_indexes(segment: list[str], fd_guess: bool = False) -> list[int]:
    """Indexes of a segment's words that are no redirection (operator, target or descriptor). A
    descriptor is the `FdWord` the lexer found glued to its operator: a digit word apart from it
    (`-o 5 >x`) is an argument. `fd_guess` is the other reading, which a caller adds to this one
    where a wrong guess can only block more: a digit or `{name}` word right before an operator
    is dropped as a descriptor too."""
    kept: list[int] = []
    index = 0
    while index < len(segment):
        token = segment[index]
        if token in REDIRECTIONS:
            index += 2
        elif (
            index + 1 < len(segment)
            and segment[index + 1] in REDIRECTIONS
            and (isinstance(token, FdWord) or (fd_guess and REDIRECTION_FD.fullmatch(token)))
        ):
            index += 1
        else:
            kept.append(index)
            index += 1
    return kept


def drop_redirections(segment: list[str], fd_guess: bool = False) -> list[str]:
    """A segment's words without its redirections (operator, target and descriptor)."""
    return [segment[index] for index in kept_indexes(segment, fd_guess)]


# What one `$(...)`, `<(...)` or `>(...)` stands for among the words of the command it sits in.
SUBSTITUTION_WORD = "${}"


def opens_substitution(tokens: list[str], index: int) -> bool:
    """Whether the `(` at `index` opens `$(`, `<(` or `>(`: the lexer leaves `$` glued to the
    word before it, and `<`, `>` as operators."""
    return (
        index > 0
        and tokens[index] == "("
        and tokens[index - 1] not in SEPARATORS
        and (tokens[index - 1].endswith("$") or tokens[index - 1] in {"<", ">"})
    )


def substitution_word(last: str) -> str:
    return last[:-1] + SUBSTITUTION_WORD if last.endswith("$") else SUBSTITUTION_WORD


def join_backtick_words(words: list[str]) -> list[str]:
    """Words of one command with each backtick span (an odd count opens, the next odd closes)
    rejoined into one word. A quoted backtick looks the same here, so `readings` reads the
    command folded and as it is, and grants neither a flag."""
    out: list[str] = []
    span: str | None = None
    for word in words:
        if span is not None:
            span += " " + word
            if word.count("`") % 2:
                out.append(span)
                span = None
        elif word.count("`") % 2:
            span = word
        else:
            out.append(word)
    if span is not None:
        out.append(span)
    return out


def command_word_from(words: list[str], start: int, end: int, pending: bool) -> tuple[int, bool, bool]:
    """Whether `words[start:end]` hold a command word (one that is no assignment, redirection or
    its target), resumable where the last call stopped, so a command with many substitutions is
    read once: (where it stopped, whether the next word is a redirection's target, found)."""
    for index in range(start, end):
        word = words[index]
        if pending:
            pending = False
        elif word in REDIRECTIONS:
            pending = True
        elif isinstance(word, FdWord) and index + 1 < len(words) and words[index + 1] in REDIRECTIONS:
            pass
        elif not is_assignment(word):
            return index + 1, False, True
    return end, pending, False


def fold_head_span(words: list[str]) -> list[str]:
    """`words` with the backtick span that opens at the command word (`` `which gh` pr ...``) joined."""
    plain = [index for index in kept_indexes(words) if not is_assignment(words[index])]
    if not plain or words[plain[0]].count("`") % 2 == 0:
        return words
    head = plain[0]
    for end in range(head + 1, len(words)):
        if words[end].count("`") % 2:
            return words[:head] + [" ".join(words[head : end + 1])] + words[end + 1 :]
    return words


def readings(words: list[str], cut: bool, backticks: bool) -> list[tuple[list[str], bool]]:
    """(words, cut) of every way the shell may read one command's words.

    One, unless an unquoted backtick is about (`backticks`) and folding the spans changes the
    words: then the words as they are and the folded ones, each cut (no draft, help or undo
    credit), so a command blocks when either reading does. The one span that is the command
    word itself (`` `which gh` pr create --draft``) is no doubt: it is the name, as `$(...)` is."""
    if backticks and any("`" in word for word in words):
        folded = join_backtick_words(words)
        if folded != words:
            if folded == fold_head_span(words):
                return [(folded, cut)]
            return [(words, True), (folded, True)]
    return [(words, cut)]


def command_spans(tokens: list[str], merge: bool = True) -> Iterator[tuple[int, list[str], bool]]:
    """(index of the first token, words, cut) of every simple command, in the order they end.

    With `merge`, a `$(...)`, `<(...)` or `>(...)` is ONE word of the command it sits in
    (`SUBSTITUTION_WORD`, glued to what precedes its `$`), the words after its `)` continue
    that command, and the commands inside it are yielded on their own. `cut`: the command holds
    an unquoted substitution (a flag glued to its `)` is lost: `-t $(x)--draft`), runs into one
    that never closes, or has a backtick span (`readings`: yielded folded and as it is). Without
    `merge` (the paren stack is not trusted) every parenthesis is a separator.
    """
    if not merge:
        for first, words in segment_spans(tokens):
            yield first, words, False
        return
    # per frame: first token, words, cut, and where `command_word_from` stopped (index, pending)
    frames: list[list] = [[None, [], False, 0, False]]
    groups: list[bool] = []
    backticks = getattr(tokens, "backticks", True)
    for index, token in enumerate(tokens):
        frame = frames[-1]
        if token not in SEPARATORS:
            if frame[0] is None:
                frame[0] = index
            frame[1].append(token)
            continue
        if token == "(" and frame[1] and opens_substitution(tokens, index):
            if not frame[2]:
                frame[3], frame[4], found = command_word_from(frame[1], frame[3], len(frame[1]) - 1, frame[4])
                frame[2] = found  # a substitution among the arguments: no credit for a flag after it
            frame[1][-1] = substitution_word(frame[1][-1])
            groups.append(True)
            frames.append([None, [], False, 0, False])
            continue
        if frame[1]:
            for words, cut in readings(frame[1], frame[2], backticks):
                yield frame[0], words, cut
        if token == "(":
            groups.append(False)
        was_substitution = token == ")" and bool(groups) and groups.pop()
        if was_substitution and len(frames) > 1:
            frames.pop()
        else:
            frames[-1] = [None, [], False, 0, False]
    for depth, frame in enumerate(reversed(frames)):
        if frame[1]:
            for words, cut in readings(frame[1], frame[2] or depth > 0, backticks):
                yield frame[0], words, cut


def command_words(
    tokens: list[str], start: int, merge: bool = True, keep_redirections: bool = False
) -> tuple[list[str], list[int], int, bool]:
    """(words, token index of each word, end index, cut) of the command that starts at `start`,
    its substitutions merged into one word each (`command_spans`) and its redirections dropped
    (kept with `keep_redirections`: with a quoted operator about, one may be a quoted word)."""
    words: list[str] = []
    positions: list[int] = []
    index = start
    cut = False
    while index < len(tokens):
        token = tokens[index]
        if merge and token == "(" and words and positions[-1] == index - 1 and opens_substitution(tokens, index):
            words[-1] = substitution_word(words[-1])
            depth, index = 1, index + 1
            while index < len(tokens) and depth:
                depth += (tokens[index] == "(") - (tokens[index] == ")")
                index += 1
            cut = cut or depth > 0
            continue
        if token in SEPARATORS:
            break
        words.append(token)
        positions.append(index)
        index += 1
    if keep_redirections:
        return words, positions, index, cut
    kept = kept_indexes(words)
    return [words[k] for k in kept], [positions[k] for k in kept], index, cut


QUOTING = re.compile(r"['\"\\`]")
WORD_GH = re.compile(r"\bgh\b", re.I)
WORD_GIT = re.compile(r"\bgit\b", re.I)
WORD_PR = re.compile(r"\bpr\b")
WORD_API = re.compile(r"\bapi\b")
WORD_GRAPHQL = re.compile(r"\bgraphql\b")
WORD_PUSH = re.compile(r"\bpush\b")


def words_in_order(text: str, *patterns: re.Pattern[str]) -> re.Match[str] | None:
    """The match of the last pattern when each one matches after the end of the previous one.

    Linear in the text: every pattern is searched once, from where the one before it
    ended (`gh`, then `pr`, then `merge`), where a single `gh.*pr.*merge` expression
    backtracks across the whole text from every start.
    """
    match = None
    position = 0
    for pattern in patterns:
        match = pattern.search(text, position)
        if match is None:
            return None
        position = match.end()
    return match


def unquoted(text: str) -> str:
    """`text` as the shell reads it once quoting is gone.

    Backslash-newline pairs are joined first, then quote characters, backslashes and
    backticks are removed, so `"gh''" pr merge`, `g\\h pr ready` and `pu\\<newline>sh` read
    as written. The one helper behind `mentions_gated` and `mentions_push`.
    """
    return QUOTING.sub("", text.replace("\\\n", ""))


EXPANSION_CHARS = re.compile(r"[$`]|\{[^{}]*,")
COMMAND_SUFFIXES = ("cd", "pushd", "popd", "git", "gh")
RESIDUE_LIMIT = 32


def residues(word: str) -> set[str]:
    """The literal words `word` may come out as when its expansions are empty or take their
    default: `${X}cd` may be `cd`, `${GIT:-git}` `git` or nothing, `{c,}d` `cd` or `d`, `$X`
    nothing. A command substitution or a backtick span counts as empty; a `$NAME` that ends in a
    command name may be an expansion glued to it (`$X'cd'`, which the lexer reads as `$Xcd`).
    Past `RESIDUE_LIMIT` alternatives, or with an unbalanced brace, nothing is among them too."""
    partials = {""}
    index = 0

    def extend(options: set[str]) -> None:
        nonlocal partials
        partials = {head + option for head in partials for option in options}
        if len(partials) > RESIDUE_LIMIT:
            partials = set(list(partials)[:RESIDUE_LIMIT]) | {""}

    while index < len(word):
        char = word[index]
        if char == "$" and word[index + 1 : index + 2] in {"{", "("}:
            opener, closer = word[index + 1], "}" if word[index + 1] == "{" else ")"
            depth, end = 1, index + 2
            while end < len(word) and depth:
                depth += (word[end] == opener) - (word[end] == closer)
                end += 1
            if depth:
                return partials | {""}  # unbalanced: the rest may be anything, nothing included
            inner = word[index + 2 : end - 1]
            options = {""}
            if opener == "{":
                default = re.match(r"[A-Za-z_]\w*:?[-=+](.*)", inner, re.S)
                if default:
                    options |= residues(default.group(1))
            extend(options)
            index = end
        elif char == "$":
            name = re.match(r"[A-Za-z_]\w*|[@*#?$!0-9-]", word[index + 1 :])
            length = len(name.group(0)) if name else 0
            options = {""}
            if name:
                options |= {suffix for suffix in COMMAND_SUFFIXES if name.group(0).endswith(suffix) and len(name.group(0)) > len(suffix)}
            extend(options)
            index += 1 + length
        elif char == "`":
            end = word.find("`", index + 1)
            if end < 0:
                return partials | {""}
            extend({""})
            index = end + 1
        elif char == "{":
            depth, end, commas = 1, index + 1, []
            while end < len(word) and depth:
                if word[end] == "{":
                    depth += 1
                elif word[end] == "}":
                    depth -= 1
                elif word[end] == "," and depth == 1:
                    commas.append(end)
                end += 1
            if depth or not commas:
                extend({char})
                index += 1
                continue
            bounds = [index] + commas + [end - 1]
            options = set()
            for left, right in zip(bounds, bounds[1:]):
                options |= residues(word[left + 1 : right])
            extend(options)
            index = end
        else:
            extend({char})
            index += 1
    return partials


def may_vanish(word: str) -> bool:
    """Whether a word may expand to nothing and leave the next word the command name: it holds an
    expansion and nothing is among its `residues` (`$X`, `${X:-${Y}}`, `{,}`, `` `true` ``, the
    `${}` a `$(...)` is merged into). Quotes are gone by here, so a quoted `"$X"`, which stays an
    empty word, reads the same: a doubt that can only block more."""
    return bool(EXPANSION_CHARS.search(word)) and "" in residues(word)


def may_be(word: str, names: set[str] | frozenset[str]) -> set[str]:
    """The names in `names` a word holding an expansion may come out as (`${X}cd` may be `cd`)."""
    if not EXPANSION_CHARS.search(word):
        return set()
    return residues(word) & set(names)
