from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from aitk.workflow_usage import (
    UNATTRIBUTED,
    WorkflowReport,
    WorkflowUsage,
    collect_workflow_usage,
)

SELECTORS = ("claude-opus", "claude-fable", "gpt-5.6-sol")


def _record(
    *,
    cwd: str,
    session_id: str,
    timestamp: str | None,
    model: str = "claude-sonnet-5",
    usage: dict[str, int] | None = None,
    skill: str | None = None,
) -> str:
    content: list[dict[str, object]] = [{"type": "text", "text": "..."}]
    if skill is not None:
        content.append(
            {"type": "tool_use", "name": "Skill", "input": {"skill": skill}}
        )
    message: dict[str, object] = {"model": model, "content": content}
    if usage is not None:
        message["usage"] = usage
    record: dict[str, object] = {
        "type": "assistant",
        "cwd": cwd,
        "sessionId": session_id,
        "message": message,
    }
    if timestamp is not None:
        record["timestamp"] = timestamp
    return json.dumps(record)


def _usage(input_tokens: int, output_tokens: int = 0, **rest: int) -> dict[str, int]:
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, **rest}


def _write(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def test_missing_projects_root_is_an_empty_report(tmp_path: Path) -> None:
    report = collect_workflow_usage(tmp_path / "missing", SELECTORS)
    assert report == WorkflowReport(
        workflows=(), total_tokens=0, premium_tokens=0, cost=0.0
    )


def test_lines_are_attributed_to_the_most_recent_skill_invocation(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            # Before any Skill invocation: unattributed.
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:00Z",
                    usage=_usage(10)),
            # The invoking turn itself is charged to the skill.
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:01:00Z",
                    usage=_usage(20), skill="debug"),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:02:00Z",
                    usage=_usage(30)),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:03:00Z",
                    usage=_usage(40), skill="review"),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:04:00Z",
                    usage=_usage(50)),
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)

    by_name = {row.workflow: row for row in report.workflows}
    assert set(by_name) == {UNATTRIBUTED, "debug", "review"}
    assert by_name[UNATTRIBUTED].total_tokens == 10
    assert by_name["debug"].total_tokens == 50
    assert by_name["debug"].invocations == 1
    assert by_name["review"].total_tokens == 90
    assert report.total_tokens == 150
    # Sorted by spend, descending.
    assert [row.workflow for row in report.workflows] == [
        "review",
        "debug",
        UNATTRIBUTED,
    ]


def test_subagent_transcripts_are_charged_to_the_parent_sessions_workflow(
    tmp_path: Path,
) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:01:00Z",
                    usage=_usage(1), skill="cherry-pick"),
        ],
    )
    _write(
        projects / "-repo" / "s1" / "subagents" / "agent-1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:05:00Z",
                    model="claude-opus-5", usage=_usage(100, 10)),
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)

    (row,) = report.workflows
    assert row.workflow == "cherry-pick"
    assert row.total_tokens == 111
    assert row.premium_tokens == 110
    assert row.sessions == 1


def test_fable_and_opus_families_count_as_premium(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:00Z",
                    model="claude-fable-5-1", usage=_usage(5), skill="planning"),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:01Z",
                    model="claude-opus-4-8", usage=_usage(7)),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:02Z",
                    model="claude-sonnet-5", usage=_usage(11)),
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)
    (row,) = report.workflows
    assert row.premium_tokens == 12
    assert row.total_tokens == 23


def test_peak_context_is_the_largest_prompt_not_a_sum(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:00Z",
                    usage=_usage(10, 5, cache_read_input_tokens=1000),
                    skill="debug"),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:01Z",
                    usage=_usage(20, 500, cache_read_input_tokens=1500,
                                 cache_creation_input_tokens=300)),
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)
    (row,) = report.workflows
    # Output tokens are not context; the second call's prompt was 1820.
    assert row.peak_context_tokens == 1820


def test_lines_without_a_timestamp_are_unattributed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:00Z",
                    usage=_usage(1), skill="debug"),
            _record(cwd=cwd, session_id="s1", timestamp=None, usage=_usage(99)),
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)
    by_name = {row.workflow: row for row in report.workflows}
    assert by_name["debug"].total_tokens == 1
    assert by_name[UNATTRIBUTED].total_tokens == 99


def test_since_drops_older_lines_and_invocations(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    cwd = str(tmp_path / "repo")
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-07-01T00:00:00Z",
                    usage=_usage(1), skill="old-skill"),
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-02T00:00:00Z",
                    usage=_usage(2), skill="debug"),
        ],
    )
    since = datetime(2026, 8, 1, tzinfo=timezone.utc)
    report = collect_workflow_usage(projects, SELECTORS, since=since)
    assert [row.workflow for row in report.workflows] == ["debug"]
    assert report.total_tokens == 2


def test_workflow_summaries_join_by_command_per_cwd(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    repo = tmp_path / "repo"
    cwd = str(repo)
    _write(
        projects / "-repo" / "s1.jsonl",
        [
            _record(cwd=cwd, session_id="s1", timestamp="2026-08-01T00:00:00Z",
                    usage=_usage(10), skill="fix-ci"),
        ],
    )
    _write(
        repo / ".ai-toolkit" / "metrics.jsonl",
        [
            json.dumps({"event": "gate", "timestamp": "2026-08-01T00:00:00Z",
                        "command": "fix-ci", "state": "RETRY"}),
            json.dumps({"event": "workflow-summary",
                        "timestamp": "2026-08-01T00:01:00Z", "command": "fix-ci",
                        "retries": 1, "reclassifications": 0,
                        "reviewer_yield": 0.5}),
            json.dumps({"event": "workflow-summary",
                        "timestamp": "2026-08-01T00:02:00Z", "command": "fix-ci",
                        "retries": 2, "reviewer_yield": 1.0}),
            # A workflow with telemetry but no transcript tokens still rows.
            json.dumps({"event": "workflow-summary",
                        "timestamp": "2026-08-01T00:03:00Z",
                        "command": "release-prep"}),
            "{not json",
        ],
    )
    report = collect_workflow_usage(projects, SELECTORS)

    by_name = {row.workflow: row for row in report.workflows}
    fix_ci = by_name["fix-ci"]
    assert fix_ci.total_tokens == 10
    assert fix_ci.summaries == 2
    assert fix_ci.retries == 3
    assert fix_ci.reclassifications == 0
    assert fix_ci.reviewer_yield == 0.75
    release = by_name["release-prep"]
    assert release == WorkflowUsage(
        workflow="release-prep",
        invocations=0,
        sessions=0,
        total_tokens=0,
        premium_tokens=0,
        cost=0.0,
        peak_context_tokens=0,
        summaries=1,
        retries=0,
        reclassifications=0,
        reviewer_yield=None,
    )


def test_as_dict_round_trips(tmp_path: Path) -> None:
    row = WorkflowUsage(
        workflow="debug", invocations=1, sessions=1, total_tokens=3,
        premium_tokens=1, cost=0.5, peak_context_tokens=2, summaries=0,
        retries=0, reclassifications=0, reviewer_yield=None,
    )
    report = WorkflowReport(workflows=(row,), total_tokens=3, premium_tokens=1, cost=0.5)
    payload = report.as_dict()
    assert payload["workflows"][0]["workflow"] == "debug"
    assert payload["workflows"][0]["reviewer_yield"] is None
    assert payload["total_tokens"] == 3
