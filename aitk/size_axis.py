"""Pure schema validation for PROJECT.md v2's size-axis frontmatter fields.

Mirrors aitk.gates's pure-helper shape: no I/O, no PROJECT.md access, no
frontmatter parsing. No YAML frontmatter parser exists anywhere in aitk/
today (routing.py/gate_state.py/checkpoint.py all read a JSON marker block
in the document body, not the YAML header) and this module does not add
one -- the caller supplies an already-parsed dict of frontmatter fields;
wiring an actual reader is deferred to whichever workflow first needs to
read these fields live (Wave 5's create-feature skill).

Size and complexity are orthogonal per the source plan: complexity picks
the reasoning tier, size estimates implementation surface, and
execution_shape is derived from both plus a phaseability decision.
architecture_plan_status, phase_plan_status, and verification_status reuse
aitk.gates's six-state vocabulary -- they are gate outcomes, not a separate
status vocabulary.
"""

from __future__ import annotations

from .gates import GATE_STATES

SIZE_VALUES = {"S", "M", "L", "XL"}
EXECUTION_SHAPE_VALUES = {"SINGLE_PHASE", "BATCHED", "MULTI_PHASE"}
COMPLEXITY_VALUES = {"TRIVIAL", "STANDARD", "COMPLEX"}
REASONING_ATTEMPT_UNITS = {"architecture", "phase_plan", "implementation"}

_ENUM_FIELDS = {
    "size": SIZE_VALUES,
    "execution_shape": EXECUTION_SHAPE_VALUES,
    "phase_complexity": COMPLEXITY_VALUES,
    "phase_size": SIZE_VALUES,
    "phase_execution_shape": EXECUTION_SHAPE_VALUES,
    "architecture_plan_status": GATE_STATES,
    "phase_plan_status": GATE_STATES,
    "verification_status": GATE_STATES,
}
_STRING_FIELDS = {"phaseability_reason"}
SIZE_AXIS_FIELDS = frozenset(_ENUM_FIELDS) | _STRING_FIELDS | {"reasoning_attempts"}


class SizeAxisError(ValueError):
    """A size-axis field is present but does not conform to its schema."""


def validate_size_axis(payload: dict[str, object]) -> None:
    """Validate whichever size-axis fields are present in `payload`.

    `payload` is expected to be a full PROJECT.md frontmatter dict (or any
    superset of it) -- only the size-axis keys this module owns are
    inspected; every other key is ignored, since this module does not own
    the rest of the v1/v2 schema. Every size-axis field is itself optional:
    an unfilled PROJECT_TEMPLATE.md, where every size-axis field is blank
    or absent, must validate cleanly, since a fresh TRIVIAL/STANDARD
    project never sets any of them.
    """
    if not isinstance(payload, dict):
        raise SizeAxisError("size-axis payload must be an object")
    for field, allowed in _ENUM_FIELDS.items():
        value = payload.get(field)
        if value is not None and value not in allowed:
            raise SizeAxisError(f"{field} must be one of {sorted(allowed)}")
    for field in _STRING_FIELDS:
        value = payload.get(field)
        if value is not None and (not isinstance(value, str) or not value):
            raise SizeAxisError(f"{field} must be a nonempty string")
    attempts = payload.get("reasoning_attempts")
    if attempts is not None:
        if not isinstance(attempts, dict) or set(attempts) != REASONING_ATTEMPT_UNITS:
            raise SizeAxisError(
                "reasoning_attempts must have exactly the keys "
                f"{sorted(REASONING_ATTEMPT_UNITS)}"
            )
        for unit, count in attempts.items():
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                raise SizeAxisError(
                    f"reasoning_attempts.{unit} must be a non-negative integer"
                )
