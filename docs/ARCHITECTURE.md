# Architecture

The toolkit is facts and boundaries. It has no workflow engine. Up to v0.3,
a Python runtime classified work by complexity, size and shape, ran
PASS/RETRY/ESCALATE gates with retry budgets, planned review lanes, and bound
prose paragraphs to a model-routing manifest. That machinery made up for
models that needed rails. Current models plan, verify and escalate on their
own, and every such rule went out of date with the next release. v0.4 keeps
only what doesn't decay.

## The admission rule

A line, file or module exists only if it is one of these:

1. **A fact the model can't infer.** Preset and Superset hosts and
   credentials, the external CI that `gh run list` doesn't show, cherry-pick
   incidents, browser-recording traps, the user's thresholds and preferences.
2. **A boundary a hook or script enforces.** The git guard and its verify
   gate, the production refusals in the Preset scripts, the PGM preflight.
3. **A format surviving code parses.** For example, the host table that
   `scripts/preset/hosts.mjs` and its test hold in step.
4. **A Claude Code ↔ Codex portability shim.**

A regression on a newer model is fixed by adding a fact or a boundary, never
by putting procedure back.

## Layers

| Layer | Where | Loaded |
|---|---|---|
| Rules | `rules/universal.md` | Every session, by `hooks/session-start.sh` |
| Skills | `skills/*/SKILL.md`, `extensions/pgm/skills/pgm/` | When a description matches the request |
| Agents | `agents/claude/*.md`, `agents/codex/*.toml` | When a skill hands work to a fresh context |
| Hooks | `hooks/hooks.json`, `hooks/*.sh`, `hooks/lib/` | On every Bash tool call and session start |
| Scripts | `skills/*/scripts/`, `scripts/` | When a skill runs them |

## Agents: when a fresh context pays

A subagent is justified only by context isolation, independence, or a
different tool or model set. Being "a simple task" isn't enough, because the
parent does simple work inline.

- `reviewer`: independence. It hasn't seen how the change was made. It is
  also the contract `second-opinion.py` sends to the other model family.
- `ci-investigator`: isolation. CI logs stay out of the parent's context.
- `qa-runner`: isolation. Browser runs and their artifacts stay out too.

Each agent is one body in two files. A Codex plugin can't ship agents, so
`install.sh` links the TOML files. `tests/test_plugin.py` holds the two
bodies equal.

## Cross-family review

`skills/review/scripts/second-opinion.py` runs `codex exec` from Claude Code
and `claude -p` from anywhere else. The run is read-only: Codex gets
`--sandbox read-only`; Claude gets plan mode, no write tools, and git
read-only commands only. The reviewer contract goes in as system or developer
instructions, and the diff (or a file such as `PLAN.md`) on stdin, so the
worker needs no file pointers.

## The PR gate

A draft PR opens only for a tree a check passed on. `scripts/verify.py -- <command>`
runs the check and records, in `.ai-toolkit/verify.json`, the commit it
started from and the blob id of every path the working tree changed
(`hooks/lib/verify_record.py`). Before `gh pr create`, the git guard compares
that with `git diff --raw <base> <commit>`, where the commit is HEAD or the
`--head` branch: a run before the commit counts once the commit holds exactly
what was tested, and any edit in between does not. The newest run of each
command on that tree must have passed, so a failed run blocks the tree until
that same command passes there or the tree changes. A command whose first
word is no program on PATH and no builtin or keyword of `sh` (exit 126 or 127,
no expansion in the word, no leading `PATH=`) records nothing; one that ran and
then exited 126 or 127 is a failure. Untracked files
a check creates are its outputs, remembered apart from the records, left out
of later runs, and forgotten once deleted.
`--partial` marks a
run of related checks only and names what CI still runs; the PR's test plan
carries the level. The record and the fingerprint stay outside `.git`, which
Codex keeps read-only; adding `.ai-toolkit/` to `info/exclude` is best effort.

The gate has no off switch. A session-wide one is easy to leave on, and v0.3
told users to start sessions with `SKIP_PR_GATE=1`, so an old name would have
switched the new gate off unseen (the session-start hook now warns when it is
still set). When nothing meaningful can run, the user's agreement goes into a
`--partial` record the PR discloses; a misfire is escaped by opening the PR
from the user's own terminal, where the hook does not run.

The gate checks that tests ran, not that the change was reviewed: a recorded
command run is something a hook can check, while whether a review was good
enough is a judgment, so review stays in the `review` skill. The record is a
tripwire against forgetting, not proof: it shows what ran, so a command that
checks nothing is visible in the record. Its known limits:

- it keeps the last 200 runs from the newest 20 commits they started from, so
  200 further runs, or runs on 20 newer commits, drop a failure;
- it is a plain file: deleting it or writing it by hand goes unseen;
- the guard reads the command's text. `gh` behind a variable or an escape
  (`"$GH" pr ready 12`) and a verb a variable hides (`gh pr $V 12`) are gated,
  and flags are read as gh's pflag does, from gh 2.103.0's tables
  (`hooks/lib/gh_args.py`; a flag a newer gh adds grants no draft or help),
  and `gh pr revert` is gated like `create`. A positional word with an expansion
  grants no draft, help or undo (accepted over-block: `gh pr ready --undo
  "$PR"`). Not seen: an unquoted expansion in a flag's value that splits
  into a flag (`-b $V` holding `x --draft=false`) or vanishes so the next
  word becomes the value (`-t $X --draft` with `X` unset); the guard cannot
  tell `$V` from `"$V"`. A `$(...)` is one word of the command it sits in, so
  `gh -R $(echo o/r) pr merge 12` is read and a substitution where the verb
  stands is unknown. What a substitution where the command word stands prints
  is run as the command with the words after it, so that text is read like
  text the guard cannot parse (`$(echo gh pr) merge 12` and `$X $(echo gh pr
  merge 12)` block), with `printf` and `echo -e` escapes decoded. A lookup
  (`$(command -v gh) pr view 12`) is read as the name it looks up, and an
  `echo` of literal words as the command it makes (`$(echo gh) pr merge 12
  --help` is help). Not seen: other encodings of the printed text
  (`$(base64 -d <<< ...)`); a
  command with an unquoted substitution or a backtick span among its words
  grants no draft, help or undo (`-t $(x)--draft`; accepted over-block:
  `gh pr create --draft -t $(git log -1 --format=%s)`). A backtick opens a span
  only outside quotes (`'a`b'` opens none); a command with one is read folded
  and as it is. Text
  the guard cannot parse is searched for `gh`, `pr`, then `ready`, `merge`,
  `create`, `new` or `revert` in order over the whole text as well as piece by
  piece. A function wrapper (`g() { gh "$@"; }; g pr merge 12`), an expanded
  name behind an unknown wrapper (`g=gh; setsid $g pr merge 12`), a variable
  that holds more than the name (`c='gh pr'; $c merge 12`), `gh` aliases and
  extensions and connector tools open a PR unseen;
- `gh api` PR create, merge and ready are gated: a PUT to `pulls/<n>/merge` (also
  `repositories/<id>/...`) or a GraphQL `mergePullRequest`,
  `markPullRequestReadyForReview`, `enablePullRequestAutoMerge` or
  `enqueuePullRequest` needs `AITK_PR_READY=1`; a POST to `pulls`, a
  `createPullRequest` or `revertPullRequest`, and a GraphQL query the guard
  cannot read (`--input`, `-F query=@file`, a shell expansion or backtick in
  `query=`; a `$name` counts as a GraphQL variable only when an operation's
  definition list declares it and it stands where GraphQL allows a variable,
  inside parentheses: `x: $M(input: ...)` is a field, not a variable) block
  with no override, like an unchecked `gh pr create`. An
  expansion in the endpoint, the method or a `-H` value, or an unclosed `$(`,
  blocks when it could be one of these. Not seen: `gh api $ARGS` (the whole call in a
  variable), a whole path segment that is an expansion standing alone for
  `pulls` or `merge`, and `curl`. Other API writes (refs, contents, merges
  into a branch, `gh repo sync --force`) are not modelled either: for those,
  GitHub's branch protection is the boundary, not this hook. A literal query
  holding a backtick blocks with no override (an accepted over-block), and so
  does one with a `$5` inside a string literal;
- a quoted or escaped operator character standing alone as a word (`'>'`, `\;`,
  a `;` inside a `${...}`, or inside the quotes of a `$(...)` within double
  quotes) reads like the operator and cuts the command. The guard then reads
  the text as well as the words, which stay read with no draft, help or undo
  credit, also as they stand, since a redirection may be a quoted word
  (`G=gh; $G pr -t '>' merge 12`, `git push -o '>' --force origin main`).
  git's words are also read in each real piece with the separators the lexer
  made of quoted words kept as words (`git commit -m ';' --no-verify`). The
  text is read
  in each piece cut where the shell really separates commands, without
  the quoted words that hold whitespace and without the words of an
  `echo`-like command (its substitutions are read: `echo $(gh pr -t ';' merge 12)`), a
  `gh ... pr ... ready|merge|create|new|revert` or a `gh api` pull request
  mention blocks, and `gh pr create` must run as a command of its own. A
  separator in the inner double quotes of a `$(...)` within double quotes
  triggers it (`"$(echo "a;b")"`), one in single quotes does not. Over-block
  that remains: a verb word as an argument in the same piece as `gh pr`
  (`gh pr list --search merge | cut -d '|' -f1`);
- a shell that runs a script the guard never reads as commands has that
  script read like text that did not parse:
  - when its stdin carries text and it has no script, or `-s`, `-` or
    `/dev/stdin` (a here-document, a here-string, a process substitution or a
    pipe on fd 0; a file there is a script file),
    or the script is a `/dev/fd/N`, the whole command text is read,
    here-document bodies included. The stdin may be the command's anywhere,
    reaching a shell in a group, a subshell, a body or a payload (`{ bash; }
    <<< ...`, `... | (cd x && bash)`, `bash -c 'exec sh' <<EOF`), or an fd
    dup (`<&3`). A shell is any name ending in `sh` (`ash`, `bash5`, `ssh`,
    whose remote shell reads it too), and a command name that is an
    expansion with such a stdin (`$SHELL <<< ...`) counts as one;
  - when the script or a startup file is a process substitution (`bash
    <(...)`, `. <(...)`, `--rcfile <(...)`) or a `-c` or `eval` text holds a
    substitution, the substitutions' text is read.
  A gated `gh`, a `gh pr create`, a `gh api` pull request call, a `git push`
  with a force or delete flag, or a `git commit` in that text blocks, even
  one aimed at a feature branch (an accepted over-block). Line
  continuations are joined and `$'...'` is decoded first. `curl ... | bash`
  with none of those stays allowed, and a shell's name as an argument reads
  no script (`docker exec -it app bash`, `ps aux | grep sh`) unless a wrapper
  that runs its words hands it the stdin (`... | docker exec -i app bash`).
  Not read: a script file (`bash x.sh`, also one the same command writes
  first), a payload in a variable (`bash -c "$X"`, `eval "$X"`), words from
  stdin (`... | xargs gh`), other interpreters (`python3 -`, `perl -e`, `node
  -e`) and a `<<-` whose delimiter follows a space;
- a digit word or `{name}` glued to `<` or `>` after a word boundary is a file
  descriptor (`2>&1`, `{fd}>x`) and is no word; a digit apart from the operator
  (`-o 5 >x`) is an argument, and `gh` reads the command both ways;
- git's words are read without redirections and with each `$(...)` as one word,
  push options as git 2.39's parse-options does, and the words after a `$(...)`
  continue its command for the directory too (`X=$(x) cd D` is a `cd`, `echo
  $(x) cd D` moves nothing, and a prefix's options keep it a prefix: `command
  -p $(x) cd D`). A word is read by what it may come out as when its
  expansions are empty or take their default: a word that may come out as
  nothing (a `$(...)` whatever its body, `$X`, `${X:-${Y}}`, `{,}`, a backtick
  word) leaves the next word the command as well, and one that may come out
  as `cd` or `git` may be that command (`${X}cd D`, `$X'cd' D`, `{c,}d D`,
  `${GIT:-git} push`). So the directory after `$X cd D` is unknown, `$X git
  push` and `git $X push` are read as git, and a quoted `"$X"` reads the same
  (an accepted over-block). A command name that is an expansion the guard
  cannot resolve (`$GIT push`, `$(which git) push`) blocks when its words
  push with a force or delete flag or commit. git nested more than 8 levels
  deep (`sh -c`, `eval`, functions, backtick spans) blocks. Not seen: a word
  that expands to a push option (`git push origin main $F`);
- the model misses element and nameref assignments: `S[0]=x A=M` as one
  segment, `declare -n R=S; R=M`, `S[a[0]]=M` and `declare 'S[0]=M'`;
- the directory a `gh pr create` runs in comes from `shell_dirs`' static
  model: a subshell's `cd` is restored, and a `cd` that may not have run (after
  `||`, after `&&` once the list ends, in a pipeline, in a list ended by `&`, in
  an if/while/until/for/select/case body, in an `eval`, or in text with a quoted
  or escaped operator character, `find -exec ... \;` included, an accepted
  over-block) leaves the directory unknown until an absolute `cd`, and so does
  everything after a function definition that a `cd` follows;
  `cd -`, `popd` and a bare `pushd` leave it unknown too, which blocks the
  decisions that need it. A directory the same command creates, `GIT_DIR`,
  `GIT_WORK_TREE`, a variable that is not a literal path set earlier in the same
  command (`S=/repo; cd $S` is read, `$PWD`, `${S:-x}` and `$S$T` are not),
  a sourced file's `cd`, `CDPATH`, `pushd +N`, `cd ~-`,
  `C=cd; $C X`, `trap 'cd X' DEBUG` and `eval "$X"` are not
  followed;
- it checks the local commit, while the PR shows the pushed branch;
- the could-not-start rule reads only the first word, so a check that goes on to
  run more after a missing first program (`"no-such-tool; exit 127"`), a leading
  redirection (`"2>err.log ./run-tests.sh"`) or a function it defines
  (`"f() { exit 127; }; f"`) records nothing; and the other way, a typo behind
  `exec` or an expansion (`"exec pytets"`, `"$HOME/bin/pytets"`) records a
  failure only the user can get past.

## Local notes

`PROJECT.md`, `PROJECT_ARCHIVE.md`, `PLAN.md`, `WATCH.md`, `CHERRY_PICK.md`
and `CI_FIX.md` are freeform working notes with no schema. The git guard
refuses to commit them, and anything under `.ai-toolkit/`. The `handoff`
skill describes how to keep them.

## Install

Both CLIs install the repository root as a plugin from the one-plugin
marketplace in `.claude-plugin/marketplace.json`. Claude Code discovers
`skills/` and `hooks/hooks.json` by convention, and its manifest adds the PGM
skill and the agents. The Codex manifest names the skills and hooks. Codex
runs plugin hooks only after the user trusts them in `/hooks`; until then
neither the rules nor the git guard reach a session, so `install.sh` adds a
marked block to `${CODEX_HOME:-~/.codex}/AGENTS.md` that tells the model to
stop and ask for the trust when the rules are missing.
