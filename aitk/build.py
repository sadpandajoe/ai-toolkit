"""Deterministic generation of provider-facing toolkit files."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile

from .review_plan import NEVER_DEMOTED, YIELD_TABLE
from .routing_policy import GENERATED_HEADER
from .workflows import extension_manifest_path, load_workflows, manifest_path


PLACEHOLDER = "{{TOOLKIT_DIR}}"
MODEL_ROUTING = Path("interfaces/model-routing.json")
TESTER_SOURCE = Path("agents/claude/aitk-tester.md")
SKILLS = Path("interfaces/skills.json")
GUIDANCE = Path("interfaces/guidance.json")
WORKFLOWS = Path("interfaces/workflows.json")
README = Path("README.md")
ARCHITECTURE = Path("docs/ARCHITECTURE.md")
# Words a generated display name keeps upper-case.
ACRONYMS = {"ai", "pgm", "pm", "pr", "qa", "rbac"}


@dataclass(frozen=True)
class AgentSpec:
    """One native agent pair rendered from a canonical contract (N12).

    The body is the boundary's contract list exactly as a routed worker on that
    boundary receives it, so the native agent and the routed lane cannot drift.
    The Claude `model:` line is the route family's alias; the Codex twin pins the
    manifest selector and the route's effort.
    """

    name: str
    route: str
    boundary: str
    description: str
    lead: str
    claude_tools: tuple[str, ...]
    claude_extra: tuple[tuple[str, str], ...]
    codex_sandbox: str
    codex_note: str = ""


AGENTS = (
    AgentSpec(
        name="aitk-debugger",
        route="rca",
        boundary="debug.rca-specialist",
        description=(
            "Evidence-first investigation worker. Reproduces a failure, reads logs "
            "and history, and returns the RCA record with alternatives ruled out, "
            "keeping verbose logs out of the parent context. Does not change "
            "product code. Use for bugs and CI failures whose diagnosis would "
            "flood the main session."
        ),
        lead=(
            "You are the toolkit's debugger. Apply the RCA contract below in "
            "producing mode unless your prompt says you are validating: you "
            "investigate; you do not fix. You may run commands to reproduce and "
            "write throwaway scripts under a temporary directory; never edit "
            "product code or tests."
        ),
        claude_tools=("Read", "Grep", "Glob", "Bash"),
        claude_extra=(("maxTurns", "60"),),
        codex_sandbox="workspace-write",
        codex_note=(
            "Under the workspace-write sandbox the investigate-only restriction "
            "is prose: this instruction, not the sandbox, keeps you from editing "
            "product code."
        ),
    ),
    AgentSpec(
        name="aitk-implementer",
        route="implementation",
        boundary="workflows.create-feature-implementation",
        description=(
            "Bounded implementation worker for substantial STANDARD or "
            "COMPLEX-phase work. Receives an accepted plan slice or RCA and a "
            "bounded scope, edits code, writes and runs the tests named in the "
            "slice, and returns a compact handoff. Never commits, never changes "
            "routing state or PROJECT.md."
        ),
        lead=(
            "You are the toolkit's implementer. Apply the implementer contract "
            "below to the one accepted unit in your prompt."
        ),
        claude_tools=("Read", "Grep", "Glob", "Edit", "Write", "Bash"),
        claude_extra=(("permissionMode", "acceptEdits"), ("maxTurns", "80")),
        codex_sandbox="workspace-write",
    ),
    AgentSpec(
        name="aitk-planner",
        route="planning",
        boundary="workflows.create-feature-planning",
        description=(
            "Plan-only specialist for COMPLEX work. Returns an architecture "
            "decomposition or one just-in-time phase plan as the PLAN.md section "
            "the parent writes verbatim. Read-only; never implements or edits "
            "files. Use only when the goal workflow classified the work COMPLEX."
        ),
        lead=(
            "You are the toolkit's planner. Apply the planner contract below in "
            "the mode your prompt names; the plan shapes it returns follow it. "
            "You are read-only: use Bash only for read-only commands such as "
            "`git log`, `git show`, `git blame` and `git diff`."
        ),
        claude_tools=("Read", "Grep", "Glob", "Bash"),
        claude_extra=(("permissionMode", "plan"),),
        codex_sandbox="read-only",
    ),
)

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n+", re.DOTALL)


@dataclass(frozen=True)
class BuildResult:
    written: int
    unchanged: int
    removed: list[Path]


def _target(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"generated destination escapes repository: {relative}")
    target = root / relative
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"generated destination has symlink ancestor: {current}")
    if target.is_symlink():
        raise ValueError(f"generated destination cannot be a symlink: {target}")
    return target


def expected_build(root: Path, include_pgm: bool = False) -> dict[Path, str]:
    """Return the complete generated file map without touching the filesystem."""
    root = root.resolve()
    if manifest_path(root).is_file():
        # Loading raises on a malformed manifest, before anything is written.
        load_workflows(
            root,
            include_pgm=include_pgm and extension_manifest_path(root, "pgm").is_file(),
        )
    expected: dict[Path, str] = dict(expected_guidance_imports(root))
    for config_name in ("CLAUDE.md", "AGENTS.md"):
        source = root / "config" / config_name
        if source.is_file():
            # Render the entry file as the build regenerates it, not as it is.
            text = expected.get(Path("config") / config_name, source.read_text())
            expected[Path("build/config") / config_name] = text.replace(
                PLACEHOLDER, str(root)
            )
    expected.update(expected_agents(root))
    expected.update(expected_skill_metadata(root))
    expected.update(expected_readme(root))
    expected.update(expected_architecture(root))
    return expected


def _first_clause(description: str) -> str:
    """The description up to its first sentence, colon, semicolon or dash."""
    clause = re.split(r"\.\s|\.$|:\s|;\s|\s[—–]\s", description.strip(), maxsplit=1)[0]
    clause = re.sub(r"^Use (?:for|when|to)\s+", "", clause).strip()
    return clause[:1].upper() + clause[1:]


def _yaml_string(value: str) -> str:
    # A JSON string is a valid YAML double-quoted scalar.
    return json.dumps(value, ensure_ascii=False)


def expected_skill_metadata(root: Path) -> dict[Path, str]:
    """Render each skill's `agents/openai.yaml` from interfaces/skills.json.

    The display name comes from the skill name, the short description from the
    first clause of its SKILL.md description, and an internal skill disables
    implicit Codex invocation (the only enforcement of that policy once the
    interface validator goes).
    """
    if not (root / SKILLS).is_file():
        return {}
    expected: dict[Path, str] = {}
    for entry in json.loads((root / SKILLS).read_text())["skills"]:
        skill = root / entry["path"] / "SKILL.md"
        if not skill.is_file():
            continue
        description = _frontmatter_value(skill.read_text(), "description").strip('"')
        clause = _first_clause(description)
        name = entry["name"]
        display = " ".join(
            word.upper() if word in ACRONYMS else word.capitalize()
            for word in name.split("-")
        )
        lines = [
            f"# {GENERATED_HEADER} Sources: {SKILLS.as_posix()}, {entry['path']}/SKILL.md.",
            "interface:",
            f"  display_name: {_yaml_string(display)}",
            f"  short_description: {_yaml_string(clause)}",
        ]
        if entry["classification"] == "internal_support":
            lines += ["", "policy:", "  allow_implicit_invocation: false"]
        else:
            lead = clause if clause[1:2].isupper() else clause[:1].lower() + clause[1:]
            lines.append(f"  default_prompt: {_yaml_string(f'Use ${name}: {lead}.')}")
        expected[Path(entry["path"]) / "agents/openai.yaml"] = "\n".join(lines) + "\n"
    return expected


def expected_guidance_imports(root: Path) -> dict[Path, str]:
    """Own the always-on import lines in the two provider entry files.

    `config/CLAUDE.md` starts with one `@{{TOOLKIT_DIR}}/<rule>` line per rule
    in interfaces/guidance.json; `config/AGENTS.md` names the same rules in its
    "Before acting" bullet. The rest of each file stays hand-written.
    """
    if not (root / GUIDANCE).is_file():
        return {}
    rules = json.loads((root / GUIDANCE).read_text())["always_on_rules"]
    expected: dict[Path, str] = {}
    claude = root / "config/CLAUDE.md"
    if claude.is_file():
        body = re.sub(r"\A(?:@\{\{TOOLKIT_DIR\}\}/\S+\n)*\n*", "", claude.read_text())
        imports = "".join(f"@{PLACEHOLDER}/{rule}\n" for rule in rules)
        expected[Path("config/CLAUDE.md")] = imports + "\n" + body
    codex = root / "config/AGENTS.md"
    if codex.is_file():
        named = ", ".join(f"`{PLACEHOLDER}/{rule}`" for rule in rules)
        bullet = (
            "- Before acting, read and follow the always-on rules that\n"
            f"  `{GUIDANCE.as_posix()}` declares: {named}.\n"
        )
        text = codex.read_text()
        expected[Path("config/AGENTS.md")] = re.sub(
            r"(?ms)^- Before acting, read and follow .*?(?=^- |\Z)", lambda _: bullet, text, count=1
        )
    return expected


def _generated_block(text: str, name: str, body: str) -> str | None:
    start = f"<!-- aitk-generated:{name} -->"
    end = f"<!-- /aitk-generated:{name} -->"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if pattern.search(text) is None:
        return None
    note = f"<!-- {GENERATED_HEADER} -->"
    return pattern.sub(lambda _: f"{start}\n{note}\n{body}{end}", text, count=1)


def _model_table(root: Path) -> str:
    routing = json.loads((root / MODEL_ROUTING).read_text())
    providers = routing["providers"]

    def family(provider: str, model: str) -> str:
        return model.capitalize() if model in providers[provider]["models"] else model

    orchestrator = routing["policy"]["orchestrator"]
    rows = [
        "| Route | Claude | Codex | Effort | Contract |",
        "|---|---|---|---|---|",
        f"| Orchestrator (parent session) | {family('claude', orchestrator['claude'])} "
        f"| {family('codex', orchestrator['codex'])} | {routing['policy']['efforts']['standard']} | "
        "Classification, the goal loop, TRIVIAL and STANDARD work |",
    ]
    for route in routing["routes"]:
        models = route["providers"]
        rows.append(
            f"| `{route['name']}` | {family('claude', models['claude']['model'])} "
            f"| {family('codex', models['codex']['model'])} | {route['effort']} "
            f"| {route['restrictions'][0]} |"
        )
    return "\n".join(rows) + "\n"


def _rule_table(root: Path) -> str:
    workflows = json.loads((root / WORKFLOWS).read_text())["workflows"]
    always_on = set(json.loads((root / GUIDANCE).read_text())["always_on_rules"])
    skills = json.loads((root / SKILLS).read_text())["skills"]
    routing = json.loads((root / MODEL_ROUTING).read_text())
    rows = ["| Rule | Covers | Workflows that declare it | Also read by |", "|---|---|---|---|"]
    for path in sorted((root / "rules").glob("*.md")):
        rule = path.relative_to(root).as_posix()
        title = path.read_text().split("\n", 1)[0].lstrip("# ").strip()
        declared = sorted(item["name"] for item in workflows if rule in item.get("rules", []))
        readers = sorted(
            entry["name"]
            for entry in skills
            if any(
                rule in source.read_text()
                for source in sorted((root / entry["path"]).rglob("*.md"))
            )
        )
        boundaries = sum(
            rule in boundary.get("contracts", []) for boundary in routing["dispatch_boundaries"]
        )
        also = []
        if rule in always_on:
            also.append("always on")
        if readers:
            also.append("skills: " + ", ".join(readers))
        if boundaries:
            also.append(f"{boundaries} routed worker contract list" + ("s" if boundaries > 1 else ""))
        rows.append(
            f"| `{rule}` | {title} | "
            + (", ".join(f"`{name}`" for name in declared) or "none")
            + f" | {'; '.join(also) or 'none'} |"
        )
    return "\n".join(rows) + "\n"


def expected_readme(root: Path) -> dict[Path, str]:
    """Regenerate README's model and rule tables between their markers."""
    sources = (README, MODEL_ROUTING, WORKFLOWS, GUIDANCE, SKILLS)
    if not all((root / source).is_file() for source in sources):
        return {}
    text = (root / README).read_text()
    for name, render in (("models", _model_table), ("rules", _rule_table)):
        replaced = _generated_block(text, name, render(root))
        if replaced is not None:
            text = replaced
    return {README: text}


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER.sub("", text, count=1)


def _frontmatter_value(text: str, key: str) -> str:
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ValueError(f"agent source has no frontmatter: {key}")
    for line in match.group(0).splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"agent source frontmatter has no {key}")


def _toml_string(value: str) -> str:
    # JSON's string escapes are a subset of TOML's basic-string escapes.
    return json.dumps(value, ensure_ascii=False)


def _toml_block(value: str) -> str:
    """A multi-line literal string when TOML allows one, else an escaped string."""
    literal = "'''"
    if literal not in value and all(
        character in "\t\n" or (ord(character) >= 0x20 and ord(character) != 0x7F)
        for character in value
    ):
        return literal + "\n" + value + literal
    return _toml_string(value)


def _contract_body(root: Path, spec: AgentSpec, contracts: tuple[str, ...]) -> str:
    parts = [spec.lead, "The contracts follow in full, each under its repository path."]
    for contract in contracts:
        text = _strip_frontmatter((root / contract).read_text()).strip()
        parts.append(f"Contract: `{contract}`\n\n{text}")
    return "\n\n".join(parts) + "\n"


def _generated_note(sources: tuple[str, ...]) -> list[str]:
    """The provenance header, as lines a comment marker can prefix."""
    return [
        f"{GENERATED_HEADER} Sources:",
        *(f"  {source}" for source in sources + (MODEL_ROUTING.as_posix(),)),
        "Edit a source and rebuild; `bin/aitk build --check` reports drift.",
    ]


def _claude_agent(spec: AgentSpec, family: str, effort: str, body: str, sources: tuple[str, ...]) -> str:
    lines = [
        "---",
        f"name: {spec.name}",
        f"description: {spec.description}",
        f"model: {family}",
        f"effort: {effort}",
        *(f"{key}: {value}" for key, value in spec.claude_extra),
        f"tools: {', '.join(spec.claude_tools)}",
        "---",
        "",
        "<!--",
        *_generated_note(sources),
        "-->",
        "",
    ]
    return "\n".join(lines) + "\n" + body


def _codex_agent(
    name: str,
    description: str,
    selector: str,
    effort: str,
    sandbox: str,
    body: str,
    sources: tuple[str, ...],
) -> str:
    lines = [
        f"# AI Toolkit {name.removeprefix('aitk-')}: Codex custom agent.",
        *(f"# {line}" for line in _generated_note(sources)),
        f"# Installed by `bin/aitk install` as $CODEX_HOME/agents/{name}.toml.",
        "# The model and effort are pinned from the route; sandbox_mode is the",
        "# custom-agent sandbox key, and the instructions state the same limit.",
        "",
        f"name = {_toml_string(name)}",
        f"description = {_toml_string(description)}",
        f"model = {_toml_string(selector)}",
        f"model_reasoning_effort = {_toml_string(effort)}",
        f"sandbox_mode = {_toml_string(sandbox)}",
        "",
        f"developer_instructions = {_toml_block(body)}",
    ]
    return "\n".join(lines) + "\n"


def expected_agents(root: Path) -> dict[Path, str]:
    """Render the native agent roster from its canonical sources.

    Generation needs the routing manifest and every source; a checkout without
    them (a fixture, a partial copy) generates nothing rather than guessing.
    """

    root = root.resolve()
    sources = [root / MODEL_ROUTING, root / TESTER_SOURCE]
    if not all(path.is_file() for path in sources):
        return {}
    from .routing_policy import ModelRouteError
    from .routing_resolver import resolve_route

    expected: dict[Path, str] = {}
    try:
        for spec in AGENTS:
            claude = resolve_route(root, spec.route, "claude", boundary=spec.boundary)
            codex = resolve_route(root, spec.route, "codex", boundary=spec.boundary)
            contracts = claude.required_contracts
            body = _contract_body(root, spec, contracts)
            expected[Path("agents/claude") / f"{spec.name}.md"] = _claude_agent(
                spec, claude.family, claude.effort, body, contracts
            )
            codex_body = body if not spec.codex_note else body + "\n" + spec.codex_note + "\n"
            expected[Path("agents/codex") / f"{spec.name}.toml"] = _codex_agent(
                spec.name,
                spec.description,
                codex.selector,
                codex.effort,
                spec.codex_sandbox,
                codex_body,
                contracts,
            )
        # The tester stays hand-edited (N12): the build owns only its model line
        # and renders the Codex twin from its body.
        tester = (root / TESTER_SOURCE).read_text()
        claude = resolve_route(root, "implementation", "claude")
        codex = resolve_route(root, "implementation", "codex")
    except ModelRouteError as error:
        raise ValueError(f"invalid model routing: {error}") from error
    expected[TESTER_SOURCE] = re.sub(
        r"^model: .*$", f"model: {claude.family}", tester, count=1, flags=re.MULTILINE
    )
    expected[Path("agents/codex/aitk-tester.toml")] = _codex_agent(
        "aitk-tester",
        _frontmatter_value(tester, "description"),
        codex.selector,
        codex.effort,
        "workspace-write",
        _strip_frontmatter(tester),
        (TESTER_SOURCE.as_posix(),),
    )
    return expected


def _yield_table() -> str:
    rows = ["| Lane | Window (runs) | Demoted when | Consequence |", "|---|---|---|---|"]
    for lanes, window, condition, consequence in YIELD_TABLE:
        names = ", ".join(f"`{lane}`" for lane in lanes)
        rows.append(f"| {names} | {window} | {condition} | {consequence} |")
    never = ", ".join(f"`{lane}`" for lane in NEVER_DEMOTED)
    return "\n".join(rows) + f"\n\n{never} is never demoted.\n"


def expected_architecture(root: Path) -> dict[Path, str]:
    """Regenerate the lane-yield table from `aitk/review_plan.py`'s thresholds."""
    if not (root / ARCHITECTURE).is_file():
        return {}
    text = (root / ARCHITECTURE).read_text()
    replaced = _generated_block(text, "lane-yield", _yield_table())
    return {} if replaced is None else {ARCHITECTURE: replaced}


def compare_build(root: Path, include_pgm: bool = False) -> list[str]:
    """Describe deterministic build drift in stable path order."""
    root = root.resolve()
    expected = expected_build(root, include_pgm)
    differences: list[str] = []
    for relative, content in expected.items():
        target = _target(root, relative)
        if not target.exists():
            differences.append(f"missing: {relative.as_posix()}")
        elif target.read_text() != content:
            differences.append(f"different: {relative.as_posix()}")

    expected_paths = set(expected)
    generated_directories = [root / "build/config"]
    for directory in generated_directories:
        if not directory.is_dir():
            continue
        for target in sorted(directory.glob("*.md")):
            relative = target.relative_to(root)
            if relative not in expected_paths:
                differences.append(f"extra: {relative.as_posix()}")
    return sorted(differences)


def _write_if_changed(target: Path, content: str) -> bool:
    if target.exists() and target.read_text() == content:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{target.name}.", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(content)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return True


def write_build(root: Path, include_pgm: bool = False) -> BuildResult:
    """Write the expected build and prune only stale generated Markdown files."""
    root = root.resolve()
    expected = expected_build(root, include_pgm)
    written = 0
    unchanged = 0
    for relative, content in expected.items():
        if _write_if_changed(_target(root, relative), content):
            written += 1
        else:
            unchanged += 1

    removed: list[Path] = []
    expected_paths = set(expected)
    generated_directories = [root / "build/config"]
    for directory in generated_directories:
        if not directory.is_dir():
            continue
        for target in sorted(directory.glob("*.md")):
            relative = target.relative_to(root)
            if relative not in expected_paths:
                _target(root, relative).unlink()
                removed.append(relative)
    return BuildResult(written=written, unchanged=unchanged, removed=removed)
