"""gh_args: the pflag walker and verb lookup, and a locked check that the walker-based
rules only tighten what the rules at 99b041f allowed (hooks/lib/gh_args.py)."""

from __future__ import annotations

from pathlib import Path
import random
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
          "-d=t", "-f=t", "--draft=yes", "--draft=true", "--draft=false", "--undo=true", "--undo=false", "--bogus",
          "-x", "-ft", "-fdt", "-dtx", "--title=-d", "--body=-h", "-h=false", "x", "-d", "-t", "t"]
VERB_FLAGS = {
    "create": ["--draft", "-d", "--title", "-t", "--body", "-b", "-H", "--head", "--head=x",
               "-Hx", "-dH", "-dHx", "-fd", "-fb", "-f", "--fill", "--web", "-w", "--base=m"],
    "new": ["--draft", "-d", "--title", "-t", "--body", "-b", "-H", "--head", "-fd", "-f", "--fill"],
    "ready": ["--undo", "--undo=false"],
    "merge": ["--squash", "-s", "--body", "-b", "--subject", "-t", "-bh", "-d", "--admin", "-A"],
}


def old_takes_next_word(arg: str) -> bool:
    """Whether the old short-flag scan took the word after `arg` as its value: its first value
    character (`-ft`, `-dH`, `-d=t`) is the last one."""
    if not arg.startswith("-") or arg.startswith("--") or len(arg) < 2 or arg in OLD_CREATE_VALUE_FLAGS:
        return False  # the exact `-t` was always read right
    for position, char in enumerate(arg[1:], start=2):
        if char in OLD_CREATE_SHORT_VALUE:
            return position == len(arg)
    return False


# The old `is_draft` and `create_flags` took the word after such an argument for a flag, so
# `-ft --repo -d` or `-d=t -h` read as not a draft or not help, where pflag takes it as the
# value and gh agrees with the new reading. The one widening the test accepts: dropping that
# word (or reading `-d=t` as complete) makes the old rules allow the sample too.
def pflag_fixed(sample: list[str], clusters: bool = True) -> list[str] | None:
    """`sample` with the old scan's misreads undone, or None when it has none."""
    fixed: list[str] = []
    skip = False
    changed = False
    for index, arg in enumerate(sample):
        if skip:
            skip = False
            continue
        if old_takes_next_word(arg) and ("=" in arg or index + 1 < len(sample)):
            changed = True
            if "=" in arg:  # `-d=t` is complete: the next word is read as a flag
                fixed.append(arg.split("=")[0])
            elif clusters:  # `-ft` takes the next word as its value (is_draft only; create_flags knew it)
                fixed.append(arg)
                skip = True
            else:
                fixed.append(arg)
        else:
            fixed.append(arg)
    return fixed if changed else None


def old_misread(verb: str, sample: list[str]) -> bool:
    fixed = pflag_fixed(sample)
    return verb in {"create", "new"} and fixed is not None and old_allows(verb, ["pr", verb, *fixed])


def last_undo_is_true(sample: list[str]) -> bool:
    """`--undo=<true>` is the last `--undo` form, and no `--` comes before it."""
    forms = [i for i, arg in enumerate(sample) if arg == "--undo" or arg.startswith("--undo=")]
    if "--" in sample:
        forms = [i for i in forms if i < sample.index("--")]
    return bool(forms) and sample[forms[-1]].startswith("--undo=") and sample[forms[-1]][7:] in gh_args.TRUE


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
                if verb == "ready" and last_undo_is_true(sample):
                    continue
                if old_misread(verb, sample):
                    continue
                widened.append(f"{verb} {sample}")
        self.assertEqual([], widened[:10])

    def test_the_exemptions_stay_narrow(self) -> None:
        self.assertFalse(new_allows("ready", ["pr", "ready", "--undo=true", "--undo=false"]))
        self.assertFalse(new_allows("ready", ["pr", "ready", "--", "--undo=true"]))
        self.assertFalse(new_allows("create", ["pr", "create", "-fb", "x"]))
        self.assertTrue(last_undo_is_true(["--undo=false", "--undo=true"]))
        self.assertFalse(last_undo_is_true(["--undo=true", "--undo"]))
        self.assertFalse(last_undo_is_true(["--", "--undo=true"]))

    def test_help_in_the_verify_gate_only_tightens(self) -> None:
        rng = random.Random(7)
        alphabet = COMMON + VERB_FLAGS["create"]
        for _ in range(20000):
            args = ["pr", "create", *[rng.choice(alphabet) for _ in range(rng.randint(0, 5))]]
            if gh_args.walk(args, "create").asks_help and not old_create_flags(args)[0]:
                fixed = pflag_fixed(args[2:], clusters=False)
                self.assertTrue(fixed is not None and old_create_flags(["pr", "create", *fixed])[0], args)


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
    def test_h_is_no_boolean_above_the_verb(self) -> None:
        self.assertEqual(["merge"], [v for v, _ in gh_args.pr_commands(["pr", "-sb", "-h", "12", "merge"])])
        self.assertEqual([], gh_args.pr_commands(["pr", "-h", "view", "checks"]))
        self.assertEqual(["pr"], gh_args.cobra_words(["--help", "pr"]))

    def test_expansions_flag_positionals_and_cuts(self) -> None:
        self.assertTrue(gh_args.walk(["12", "--undo", "$X"], "ready").expanded)
        self.assertFalse(gh_args.walk(["--title", "$X", "--draft"], "create").expanded)
        self.assertTrue(gh_args.walk(["--draft"], "create", cut=True).expanded)
        self.assertFalse(gh_args.walk(["--draft", "--", "$X"], "create").expanded)
        self.assertEqual(["merge"], [v for v, _ in gh_args.pr_commands(["gh`", "pr", "merge"], expands=True)])

    def test_both_readings(self) -> None:
        self.assertEqual(["merge"], verbs(["pr", "-t", "view", "merge", "12"]))
        self.assertEqual(["create"], verbs(["pr", "-t", "list", "create", "--fill"]))
        self.assertEqual([], verbs(["pr", "-R", "o/r", "view", "12"]))
        self.assertEqual(["merge"], verbs(["pr", "-t", "merge"]))  # the guard's reading

    def test_expansions(self) -> None:
        self.assertEqual([gh_args.UNKNOWN], verbs(["pr", "$V", "12"]))
        self.assertEqual([gh_args.UNKNOWN], verbs(["$SUB", "merge", "12"]))
        self.assertEqual([gh_args.UNKNOWN], verbs(["pr", "{merge,}", "12"]))
        self.assertEqual([], verbs(["pr", "view", "$N"]))
        self.assertEqual([], verbs(["run", "view", "$ID"]))
        self.assertEqual([], verbs(["--jq", "$Q", "api", "/x"]))
        self.assertEqual([], verbs(["pr", "--json", "$F", "view", "12"]))
        self.assertEqual(["merge"], verbs(["pr", "merge", "12"], expands=True))
        self.assertEqual([], verbs(["$FILE"], expands=True))


class ApiTests(unittest.TestCase):
    def effect(self, line: str) -> str | None:
        return gh_args.api_effect(line.split())

    def test_endpoint_is_normalised(self) -> None:
        for endpoint in (
            "/repos/o/r/pulls", "https://api.github.com/repos/o/r/pulls",
            "https://ghe.example.com/api/v3/repos/o/r/pulls", "repos/o/r/pulls?state=all",
        ):
            self.assertEqual(["repos/o/r/pulls"], gh_args.read_api([endpoint]).endpoints, endpoint)

    def test_method_is_the_last_one_or_follows_the_fields(self) -> None:
        def methods(*args: str) -> tuple[bool, bool]:
            api = gh_args.read_api(list(args))
            return api.may_post, api.may_put

        self.assertEqual((False, False), methods("x"))
        self.assertEqual((True, False), methods("x", "-f", "a=b"))
        self.assertEqual((True, False), methods("x", "--input", "f"))
        self.assertEqual((False, False), methods("x", "-f", "a=b", "-X", "get"))
        self.assertEqual((False, True), methods("-X", "GET", "-iX", "put", "x"))
        self.assertEqual((False, False), methods("--method=patch", "x"))
        self.assertEqual((True, True), methods("x", "-X", "$M"))

    def test_queries_come_from_both_field_flags(self) -> None:
        api = gh_args.read_api(["graphql", "-f", "query=a", "--field=query=b", "-F", "n=1"])
        self.assertEqual(["a", "b"], api.queries)
        self.assertFalse(api.unreadable_query)
        for words in (
            ["-F", "query=@q.graphql"], ["--input", "q.json"], ["-f", "query=$Q"],
            ["-f", "query=${Q}"], ["-f", "query=$(cat q)"], ["-f", "query=`cat q`"],
        ):
            self.assertTrue(gh_args.read_api(["graphql", *words]).unreadable_query, words)
        self.assertFalse(gh_args.read_api(["graphql", "-f", "query=query($n:Int){a(n:$n)}"]).unreadable_query)

    def test_effects(self) -> None:
        self.assertEqual("merge", self.effect("repos/o/r/pulls/12/merge -X PUT"))
        self.assertEqual("merge", self.effect("repos/o/r/pulls/$PR/merge -X PUT -f merge_method=squash"))
        self.assertEqual("merge", self.effect("graphql -f query=mutation{mergePullRequest}"))
        self.assertEqual("create", self.effect("repos/{owner}/{repo}/pulls -f title=t"))
        self.assertEqual("create", self.effect("graphql -f query=mutation{createPullRequest}"))
        self.assertEqual("unreadable", self.effect("graphql --input q.json"))
        self.assertIsNone(self.effect("repos/o/r/pulls"))
        self.assertIsNone(self.effect("repos/o/r/pulls/12/merge"))
        self.assertIsNone(self.effect("repos/o/r/pulls/12/comments -f body=x"))
        self.assertIsNone(self.effect("graphql -f query=query{viewer{login}}"))
        self.assertIsNone(self.effect("repos/o/r/pulls -f a=b --help"))

    def test_expansions_that_could_name_a_pull_request(self) -> None:
        self.assertEqual("merge", self.effect("$URL -X PUT"))
        self.assertEqual("unreadable", self.effect("$URL -f a=b"))
        self.assertIsNone(self.effect("$URL"))
        self.assertEqual("merge", self.effect("repos/o/r/pulls/12/merge -X $M"))
        self.assertEqual("merge", self.effect("repos/o/r/pulls/12/merge $OPTS"))
        self.assertEqual("create", self.effect("repos/o/$R/pulls -f a=b"))
        self.assertEqual("unreadable", self.effect("graphql -f query=query{a} $OPTS"))
        self.assertIsNone(self.effect("repos/o/r/issues/$N/comments -f body=x"))

    def test_an_unknown_flag_makes_every_positional_an_endpoint(self) -> None:
        self.assertEqual("merge", self.effect("--new val repos/o/r/pulls/12/merge"))
        self.assertIsNone(self.effect("--new repos/o/r/issues/1"))

    def test_only_post_opens_and_only_put_merges(self) -> None:
        for line in (
            "repos/o/r/pulls/$PR -X PATCH -f body=x",
            "-X PATCH repos/{owner}/{repo}/issues/$N",
            "-X DELETE repos/{owner}/{repo}/issues/comments/$ID",
            "repos/$GITHUB_REPOSITORY/statuses/$SHA -f state=success",
            "-X PATCH repos/$GITHUB_REPOSITORY/check-runs/$ID",
            "-X HEAD repos/o/r/pulls",
            "-X PUT repos/{owner}/{repo}/contents/docs/$NAME.md",
            "-X PUT repos/o/r/pulls -f a=b",
            "-X POST repos/o/r/pulls/12/merge",
        ):
            self.assertIsNone(self.effect(line), line)
        self.assertEqual("create", self.effect("-X POST repos/{owner}/{repo}/pulls"))
        self.assertEqual("create", self.effect("repos/$GITHUB_REPOSITORY/pulls -f title=t"))
        self.assertEqual("merge", self.effect("repos/o/r/pulls/12/${X:?}erge -X PUT"))
        self.assertEqual("merge", self.effect("-X PUT repositories/1/pulls/12/merge"))
        self.assertEqual("create", self.effect("repositories/1/pulls -f title=t"))
        self.assertEqual("unreadable", self.effect("-X PUT"))
        self.assertIsNone(self.effect("-X PATCH"))
        # a limit: a whole-segment expansion alone for `pulls` or `merge` is not read
        self.assertIsNone(self.effect("repos/o/r/$X -f title=t"))

    def test_the_matcher_is_fast_on_many_expansions(self) -> None:
        self.assertIsNone(self.effect("/".join(["$A"] * 40) + "/x -X PATCH"))
        self.assertIsNone(self.effect("/".join(["$A"] * 40) + " -f a=b"))

    def test_endpoint_fragment_and_ghes_prefixes(self) -> None:
        self.assertEqual(["repos/o/r/pulls"], gh_args.read_api(["repos/o/r/pulls#x"]).endpoints)
        self.assertEqual(["graphql"], gh_args.read_api(["https://ghe.example.com/api/graphql"]).endpoints)
        self.assertEqual("merge", self.effect("https://ghe.example.com/api/graphql -f query=mutation{mergePullRequest}"))
        self.assertEqual("merge", self.effect("-X PUT repos/o/r/pulls/12/merge#x"))

    def test_only_the_query_field_decides(self) -> None:
        query = "query($ids:[ID!]!){nodes(ids:$ids){id}}"
        self.assertIsNone(self.effect(f"graphql -f query={query} -f ids[]=A -F n=$N"))
        for text in ("mutation{$M(input:{})}", "mutation{merge${E}PullRequest}", "${Q}", "$Q", "a(b:$(x))"):
            self.assertTrue(gh_args.read_api(["graphql", "-f", "query=" + text]).unreadable_query, text)
        for text in ("query($n:Int!){a(n:$n)}", "query($a:Int,$b:Int=1){x(a:$a, b: $b)}"):
            self.assertFalse(gh_args.read_api(["graphql", "-f", "query=" + text]).unreadable_query, text)

    def test_a_cut_command_reads_the_rest_as_unknown(self) -> None:
        self.assertEqual("merge", gh_args.api_effect(["repos/o/r/pulls/$"], True))
        self.assertEqual("create", gh_args.api_effect(["repos/$"], True))
        self.assertEqual(
            "unreadable", gh_args.api_effect(["graphql", "-F", "id=$", "-f", "query=mutation{mergePullRequest}"], True)
        )
        self.assertIsNone(gh_args.api_effect(["repos/o/r/issues/1/comments"], False))

    def test_help_and_command_lookup(self) -> None:
        self.assertIsNone(self.effect("graphql -h"))

    def test_command_lookup(self) -> None:
        self.assertEqual([["x"]], gh_args.api_commands(["api", "x"]))
        self.assertEqual([["-R", "o/r", "x"]], gh_args.api_commands(["-R", "o/r", "api", "x"]))
        self.assertEqual([], gh_args.api_commands(["pr", "view", "api"]))
        self.assertEqual([["-X", "PUT", "x"]], gh_args.api_commands(["api", "-X", "PUT", "x"]))
        self.assertEqual([["x"]], gh_args.api_commands(["api", "x"], expands=True))

    def test_graphql_variables_must_be_declared(self) -> None:
        def unreadable(query: str) -> bool:
            return gh_args.read_api(["graphql", "-f", "query=" + query]).unreadable_query

        for query in (
            "query($o: String! $n: String!){ r(owner: $o, name: $n) { id } }",
            "query($o: String!\n$n: String!){ r(owner: $o, name: $n) { id } }",
            "query Q($o: String!, $n: String!) { r(owner: $o, name: $n) { id } }",
            "mutation M($i: ID!) { x(id: $i) }",
        ):
            with self.subTest(query=query):
                self.assertFalse(unreadable(query))
        for query in (
            "mutation { $M: __typename }",
            "mutation { a: $M }",
            "query { f(a: $a) }",
            "query($a: Int) { f(a: $b) }",
            "query($M: Int) { $M: x }",
            "{x(a: \"$5\")}",
            "{ query($M: Int) { a } a: $M }",
            "# query($M: Int)\nmutation { a: $M }",
            "mutation { a(s: \"query($M: Int)\") b: $M }",
        ):
            with self.subTest(query=query):
                self.assertTrue(unreadable(query))

    def test_a_header_that_expands_may_override_the_method(self) -> None:
        self.assertEqual(
            gh_args.MERGE_API, gh_args.api_effect(["-X", "POST", "-H", "$H", "repos/o/r/pulls/12/merge"])
        )
        self.assertIsNone(gh_args.api_effect(["-H", "Accept: x", "repos/o/r/pulls/12"]))


def verbs(args: list[str], expands: bool = False) -> list[str]:
    return [verb for verb, _ in gh_args.pr_commands(args, expands)]


if __name__ == "__main__":
    unittest.main()
