"""The tool schemas the model is given must match the functions it calls.

This exists because on 6 November seven of the nine schemas in src/agent.py
did not match the signatures in src/tools.py. The model would have been told
to send `feature_year` to a function expecting `fyear`, `cohort_key` and
`cohort_value` to one expecting `slice_name`, and `sic` to one expecting
`gvkey`. Every one of those raises TypeError.

Nothing caught it. The contract tests check the functions. The smoke test
drives the loop with a scripted stand-in that calls the functions directly,
so it never reads the schemas. The defect was only reachable with a real
provider, which is week nine.

These tests close that gap. They are cheap, they run without a model, an API
key or any data, and they fail the moment either side moves.
"""

from __future__ import annotations

import inspect

import pytest

from src import agent, tools

SCHEMAS = {s["function"]["name"]: s["function"] for s in agent.TOOL_SCHEMAS}


def _params(name: str) -> inspect.Signature:
    return inspect.signature(getattr(tools, name))


def test_every_contract_tool_has_a_schema():
    assert set(SCHEMAS) == set(agent.TOOL_NAMES)


def test_no_schema_names_a_tool_that_does_not_exist():
    for name in SCHEMAS:
        assert hasattr(tools, name), f"{name} has a schema but no implementation"


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schema_parameters_are_accepted_by_the_function(name):
    """Anything the model may send must be a parameter the function takes."""
    declared = set(SCHEMAS[name]["parameters"]["properties"])
    accepted = set(_params(name).parameters)
    unknown = declared - accepted
    assert not unknown, (
        f"{name}: the schema lets the model send {sorted(unknown)}, "
        f"but the function accepts {sorted(accepted)}. "
        f"A model that follows the schema raises TypeError."
    )


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_required_parameters_have_no_default(name):
    """A parameter the schema marks required must not be optional in the code.

    The reverse of the look-ahead bug: if the schema says through_fyear is
    required but the function defaults it to None, a model that omits it
    still gets an uncapped answer.
    """
    required = set(SCHEMAS[name]["parameters"].get("required", []))
    sig = _params(name).parameters
    for param in required:
        assert param in sig, f"{name}: required parameter {param} is not in the signature"
        assert sig[param].default is inspect.Parameter.empty, (
            f"{name}: the schema requires {param}, but the function defaults it. "
            f"A model that omits it would still get an answer."
        )


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_mandatory_function_arguments_are_declared_required(name):
    """Anything the function has no default for must be required in the schema."""
    sig = _params(name).parameters
    mandatory = {
        p for p, v in sig.items()
        if v.default is inspect.Parameter.empty
        and v.kind in (v.POSITIONAL_OR_KEYWORD, v.KEYWORD_ONLY)
    }
    required = set(SCHEMAS[name]["parameters"].get("required", []))
    missing = mandatory - required
    assert not missing, (
        f"{name}: {sorted(missing)} has no default but the schema does not "
        f"require it. A model that omits it raises TypeError."
    )


# --- the look-ahead amendment of 2026-11-06 -------------------------------

YEAR_CAPPED = {
    "get_firm_history": "through_fyear",
    "get_control_history": "through_fyear",
    "get_cohort_rate": "fyear",
}


@pytest.mark.parametrize("name,param", sorted(YEAR_CAPPED.items()))
def test_year_capped_tools_require_their_year(name, param):
    """No tool may return anything observed after the assessment year.

    docs/TOOL_CONTRACT.md section 1, amended 2026-11-06. These three had no
    cap. get_control_history had no year argument at all, so assessing FY2018
    returned the FY2019 opinion, which is the label.
    """
    sig = _params(name).parameters
    assert param in sig, f"{name} must take {param}"
    assert sig[param].default is inspect.Parameter.empty, (
        f"{name}: {param} must be required, not defaulted"
    )
    assert param in set(SCHEMAS[name]["parameters"].get("required", [])), (
        f"{name}: the schema must mark {param} required"
    )
