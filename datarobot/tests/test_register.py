"""Tests that the NAT `register.py` module loads correctly and wires the
Neo4j research agent per DataRobot's official `af-component-agent` template
(`base` framework) pattern.

These are structural/wiring tests — they don't exercise a full `nat run`
(that's covered manually via `task validate`/`task run`; see README.md),
but they catch import/registration regressions (e.g. the
`NameError: name 'Streaming' is not defined` bug found during testing,
caused by `from __future__ import annotations` breaking `Streaming`'s
runtime resolution inside `register.py`'s locally-scoped import).
"""

from nat.data_models.agent import AgentBaseConfig

from agent.register import Neo4jAgentConfig, neo4j_agent


class TestRegisterModule:
    def test_config_class_is_agent_base_config(self):
        assert issubclass(Neo4jAgentConfig, AgentBaseConfig)

    def test_config_static_type_is_neo4j_agent(self):
        assert Neo4jAgentConfig.static_type() == "neo4j_agent"

    def test_registered_function_is_callable(self):
        assert callable(neo4j_agent)

    def test_register_module_has_no_future_annotations(self):
        """Regression test: `from __future__ import annotations` at module
        scope makes `Annotated[..., Streaming(...)]` a string annotation,
        which `typing.get_type_hints()` can't resolve because `Streaming`
        is only imported inside the function body (matching the official
        template), not at module scope. This broke `nat run`/`nat validate`
        with `NameError: name 'Streaming' is not defined` until fixed.
        """
        import agent.register as register_module

        with open(register_module.__file__, encoding="utf-8") as f:
            source = f.read()
        assert "from __future__ import annotations" not in source
