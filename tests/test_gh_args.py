"""gh_args: the pflag walker and verb lookup, and a locked check that the walker-based
rules only tighten what the rules at 99b041f allowed (hooks/lib/gh_args.py)."""

from __future__ import annotations

from pathlib import Path
import random
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import gh_args  # noqa: E402
import git_guard  # noqa: E402

sys.path.pop(0)

# The decision logic of 99b041f:hooks/lib/git_guard.py, frozen as the oracle.
OLD_CREATE_VALUE_FLAGS = {
    "-a", "--assignee", "-B", "--base", "-b", "--body", "-F", "--body-file",
    "-H", "--head", "-l", "--label", "-m", "--milestone", "-p", "--project",
    "-r", "--reviewer", "-T", "--template", "-t", "--title", "-R", "--repo",
    "--hostname", "--attach", "--recover",
}
OLD_CREATE_SHORT_VALUE = {"a", "B", "b", "F", "H", "l", "m", "p", "r", "T", "t", "R"}


def old_is_draft(args: list[str]) -> bool:
    draft = False
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg == "--":
            break
        if arg in OLD_CREATE_VALUE_FLAGS:
            skip = True
        elif arg == "--draft":
            draft = True
        elif arg.startswith("--draft="):
            draft = arg.split("=", 1)[1].strip().lower() in {"true", "1", "t"}
        elif arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            for char in arg[1:]:
                if char == "d":
                    draft = True
                if char in OLD_CREATE_SHORT_VALUE:
                    break
    return draft


def old_create_flags(args: list[str]) -> tuple[bool, list[str]]:
    asks_help = False
    heads: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        index += 1
        if arg == "--":
            break
        if arg in {"-h", "--help"}:
            asks_help = True
        elif arg.startswith("--"):
            name, given, value = arg.partition("=")
            if name in OLD_CREATE_VALUE_FLAGS:
                if not given:
                    value = args[index] if index < len(args) else ""
                    index += 1
                if name == "--head":
                    heads.append(value)
        elif arg.startswith("-") and len(arg) > 1:
            for position, char in enumerate(arg[1:], start=2):
                if char in OLD_CREATE_SHORT_VALUE:
                    value = arg[position:]
                    if value.startswith("="):
                        value = value[1:]
                    elif not value:
                        value = args[index] if index < len(args) else ""
                        index += 1
                    if char == "H":
                        heads.append(value)
                    break
    return asks_help, heads


def old_allows(verb: str, args: list[str]) -> bool:
    """The old `check_pr_publish` decision for a located verb, `args` including `pr VERB`."""
    if verb in {"create", "new"}:
        return old_create_flags(args)[0] or old_is_draft(args)
    if verb == "ready" and "--undo" in args:
        return True
    return bool({"-h", "--help"} & set(args))


def new_allows(verb: str, args: list[str]) -> bool:
    return git_guard.publishes_nothing(verb, gh_args.walk(args, verb))


COMMON = ["-h", "--help", "--help=false", "-dh", "--", "-", "-R", "-R=o/r", "--repo", "--repo=o/r",
          "--hostname", "--hostname=h", "-t=", "-d=", "-d=false", "-fd=false", "-d=true",
          "--draft=yes", "--draft=true", "--draft=false", "--undo=true", "--undo=false", "--bogus",
          "-x", "-ft", "-fdt", "-dtx", "--title=-d", "--body=-h", "-h=false", "x", "-d", "-t", "t"]
VERB_FLAGS = {
    "create": ["--draft", "-d", "--title", "-t", "--body", "-b", "-H", "--head", "--head=x",
               "-Hx", "-dH", "-dHx", "-fd", "-fb", "-f", "--fill", "--web", "-w", "--base=m"],
    "new": ["--draft", "-d", "--title", "-t", "--body", "-b", "-H", "--head", "-fd", "-f", "--fill"],
    "ready": ["--undo", "--undo=false"],
    "merge": ["--squash", "-s", "--body", "-b", "--subject", "-t", "-bh", "-d", "--admin", "-A"],
}


# A short cluster that ends in a value flag with nothing after it (`-ft`, `-dH`) takes the next
# word as its value, as pflag does. The old `is_draft` knew only the exact `-t` and read that
# word as a flag, so it called a real draft (`-ft --repo -d`) not a draft: the one place the
# new rules allow what the old ones blocked, and gh agrees with the new reading.
OLD_MISREAD = re.compile(r"-[A-Za-z]+[aBbFHlmprTtR]")


class OnlyTightensTests(unittest.TestCase):
    def test_the_new_allow_set_is_a_subset_of_the_old_one(self) -> None:
        rng = random.Random(20260518)
        widened: list[str] = []
        for verb, flags in VERB_FLAGS.items():
            alphabet = COMMON + flags
            for _ in range(20000):
                sample = [rng.choice(alphabet) for _ in range(rng.randint(0, 5))]
                args = ["pr", verb, *sample]
                if not new_allows(verb, args) or old_allows(verb, args):
                    continue
                # gh turns `--undo=<true>` into the conversion to a draft: it publishes nothing
                if verb == "ready" and any(arg.startswith("--undo=") and arg[7:] in gh_args.TRUE for arg in sample):
                    continue
                if verb in {"create", "new"} and any(OLD_MISREAD.fullmatch(arg) for arg in sample):
                    continue
                widened.append(f"{verb} {sample}")
        self.assertEqual([], widened[:10])

    def test_help_in_the_verify_gate_only_tightens(self) -> None:
        rng = random.Random(7)
        alphabet = COMMON + VERB_FLAGS["create"]
        for _ in range(20000):
            args = ["pr", "create", *[rng.choice(alphabet) for _ in range(rng.randint(0, 5))]]
            if gh_args.walk(args, "create").asks_help:
                self.assertTrue(old_create_flags(args)[0], args)


class WalkTests(unittest.TestCase):
    def test_a_boolean_never_takes_the_next_word(self) -> None:
        flags = gh_args.walk(["pr", "create", "--draft", "false"], "create")
        self.assertTrue(flags.on("draft"))

    def test_short_clusters(self) -> None:
        self.assertFalse(gh_args.walk(["-ft", "-d"], "create").on("draft"))  # `-d` is the title
        self.assertFalse(gh_args.walk(["-fd=false"], "create").on("draft"))
        self.assertTrue(gh_args.walk(["-fd=1"], "create").on("draft"))
        self.assertEqual(["x"], gh_args.walk(["-dHx"], "create").heads)
        self.assertEqual(["="], gh_args.walk(["-H="], "create").heads)

    def test_parse_bool(self) -> None:
        for value in ("1", "t", "T", "TRUE", "true", "True"):
            self.assertTrue(gh_args.walk([f"--draft={value}"], "create").on("draft"), value)
        for value in ("tRuE", "yes", "", " true"):
            self.assertFalse(gh_args.walk([f"--draft={value}"], "create").on("draft"), value)

    def test_help_is_a_bare_flag_no_other_flag_took(self) -> None:
        self.assertTrue(gh_args.walk(["--help"], "merge").asks_help)
        self.assertTrue(gh_args.walk(["-h"], "merge").asks_help)
        self.assertFalse(gh_args.walk(["--body", "-h"], "merge").asks_help)
        self.assertFalse(gh_args.walk(["--help=false"], "merge").asks_help)
        self.assertFalse(gh_args.walk(["-dh"], "create").asks_help)
        self.assertFalse(gh_args.walk(["--repo", "--undo"], "ready").on("undo"))

    def test_an_unknown_flag_grants_nothing(self) -> None:
        flags = gh_args.walk(["--new", "--draft"], "create")
        self.assertTrue(flags.unknown)
        self.assertFalse(flags.on("draft"))
        self.assertFalse(gh_args.walk(["--new", "--help"], "merge").asks_help)

    def test_flags_may_follow_positionals_and_dashdash_ends_them(self) -> None:
        self.assertTrue(gh_args.walk(["12", "--undo"], "ready").on("undo"))
        self.assertFalse(gh_args.walk(["--", "--undo"], "ready").on("undo"))


class VerbTests(unittest.TestCase):
    def test_both_readings(self) -> None:
        self.assertEqual(["merge"], gh_args.pr_verbs(["pr", "-t", "view", "merge", "12"]))
        self.assertEqual(["create"], gh_args.pr_verbs(["pr", "-t", "list", "create", "--fill"]))
        self.assertEqual([], gh_args.pr_verbs(["pr", "-R", "o/r", "view", "12"]))
        self.assertEqual(["merge"], gh_args.pr_verbs(["pr", "-t", "merge"]))  # the guard's reading

    def test_expansions(self) -> None:
        self.assertEqual([gh_args.UNKNOWN], gh_args.pr_verbs(["pr", "$V", "12"]))
        self.assertEqual([gh_args.UNKNOWN], gh_args.pr_verbs(["$SUB", "merge", "12"]))
        self.assertEqual([], gh_args.pr_verbs(["pr", "view", "$N"]))
        self.assertEqual([], gh_args.pr_verbs(["run", "view", "$ID"]))
        self.assertEqual(["merge"], gh_args.pr_verbs(["pr", "merge", "12"], expands=True))
        self.assertEqual([], gh_args.pr_verbs(["$FILE"], expands=True))


if __name__ == "__main__":
    unittest.main()
