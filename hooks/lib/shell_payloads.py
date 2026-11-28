"""The text a command hands to a shell, read the same way by both walkers (`shell_tokens.commands`
and `git_walk.parse_git_actions`), each in addition to what it reads itself:

- `shell_script`: the script a shell takes from its own words, by bash's option grammar (`bash -c
  -x 'cmd'` runs `cmd`: `-c` makes the first word that is no option the script), and the text
  fish (`-c`, `--command`, `-C`, `--init-command`) and pwsh (`-c`, `-Command`) are given;
- `trap_action`: the command a `trap` runs later (`trap -- 'cmd' EXIT`);
- `flag_payloads`: behind a command the guard does not know, the string after a later `-c`
  cluster or `--command` (`flock /tmp/x -c 'cmd'`, `su -c 'cmd'`, `script -c 'cmd'`).

It imports only `shell_lex`, so `shell_tokens` and `git_walk` can both import it.
"""

from __future__ import annotations

from shell_lex import SHELL_NAME, SHELLS, WORD_GH, WORD_GIT, head_name

SHELL_VALUE_LONG = {"--rcfile", "--init-file"}  # bash's long options that take a value
FISH_TEXT = {"-c", "--command", "-C", "--init-command"}
PWSH = {"pwsh", "powershell", "pwsh.exe", "powershell.exe"}
PWSH_TEXT = {"-c", "-command", "-commandwithargs", "-cwa"}
FLAG_PAYLOAD_LIMIT = 8  # later `-c`/`--command` words read per command


def is_posix_shell(word: str) -> bool:
    name = head_name(word)
    return name in SHELLS or bool(SHELL_NAME.fullmatch(name))


def shell_script(argv: list[str]) -> tuple[str, list[str]] | None:
    """(the text, the words after it) that the shell `argv[0]` runs from its own words, or None.

    bash, sh, zsh, dash, ksh and their kin: options come first in any order (`-x`, `-euo pipefail`,
    `+o posix`, `--norc`, `--rcfile FILE`); with a `c` among the short ones, the first word that is
    not an option is the script and the words after it are `$0`, `$1`, ... fish and pwsh name their
    text with a flag of their own."""
    if not argv:
        return None
    name = head_name(argv[0])
    rest = argv[1:]
    if name == "fish" or name in PWSH:
        for index, word in enumerate(rest):
            if name == "fish":
                if word in FISH_TEXT and index + 1 < len(rest):
                    return rest[index + 1], rest[index + 2 :]
                for long in ("--command=", "--init-command="):
                    if word.startswith(long):
                        return word[len(long) :], rest[index + 1 :]
            elif word.lower() in PWSH_TEXT and index + 1 < len(rest):
                return rest[index + 1], rest[index + 2 :]
        return None
    if not is_posix_shell(argv[0]):
        return None
    command_flag = False
    index = 0
    while index < len(rest):
        word = rest[index]
        if word == "--":
            index += 1
            break
        if word in SHELL_VALUE_LONG:
            index += 2
            continue
        if word.startswith("--"):
            index += 1
            continue
        if len(word) > 1 and word[0] in "-+":
            letters = word[1:]
            command_flag = command_flag or (word[0] == "-" and "c" in letters)
            index += 2 if ("o" in letters or "O" in letters) else 1  # `-o pipefail`, `-euo pipefail`
            continue
        break
    if not command_flag or index >= len(rest):
        return None
    return rest[index], rest[index + 1 :]


def trap_action(argv: list[str]) -> str | None:
    """The text `trap` runs later (its first operand past `--`), or None when it only prints
    (`-p`, `-l`), resets (`-`) or has none."""
    if not argv or head_name(argv[0]) != "trap":
        return None
    rest = argv[1:]
    while rest and rest[0].startswith("-") and rest[0] not in {"-", "--"}:
        if any(letter in rest[0][1:] for letter in "lp"):
            return None
        rest = rest[1:]
    if rest[:1] == ["--"]:
        rest = rest[1:]
    if not rest or rest[0] in {"-", ""}:
        return None
    return rest[0]


def is_command_flag(word: str) -> bool:
    """A word that hands the next one to a shell: a short cluster with `c` (`-c`, `-lc`) or
    `--command` (also `--command=TEXT`, whose text is in the word)."""
    return (word.startswith("-") and not word.startswith("--") and "c" in word[1:]) or word == "--command"


def flag_payloads(words: list[str]) -> list[str] | None:
    """The strings after each later `-c` cluster or `--command` among `words` (the words after a
    head the guard does not know). Past `FLAG_PAYLOAD_LIMIT` of them, None (the command is
    unreadable) when one of the rest mentions git or gh, else the first ones."""
    found: list[str] = []
    for index, word in enumerate(words):
        if word.startswith("--command="):
            found.append(word[len("--command=") :])
        elif is_command_flag(word):
            following = words[index + 1 :]
            following = following[1:] if following[:1] == ["--"] else following
            if following:
                found.append(following[0])
    if len(found) > FLAG_PAYLOAD_LIMIT:
        if any(WORD_GIT.search(text) or WORD_GH.search(text) for text in found[FLAG_PAYLOAD_LIMIT:]):
            return None
        return found[:FLAG_PAYLOAD_LIMIT]
    return found
