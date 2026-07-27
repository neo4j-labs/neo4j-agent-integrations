# Known Issues

## 1. CLI import of a native agent with a toolkit fails

**ADK version affected:** 2.12.0

```
$ orchestrate agents import -f agents/neo4j_explorer.yaml
[ERROR] - Toolkits are only supported for experimental_customer_care style agents
```

| Attempt | Result |
|---|---|
| `style: default` | Fails |
| `style: react` | Fails |
| ADK upgraded, retried | Fails |
| Same agent + toolkit created in the console | **Succeeds** |

`experimental_customer_care` is documented as an ended public preview, and the
ADK 2.10.0 release notes state that toolkits can be used in agentic workflows
like any other toolkit. Because the console accepts the identical
configuration, this appears to be CLI-side validation rather than a platform
limitation.

**Workaround:** create the agent in the console
(see [console-agent-setup.md](console-agent-setup.md)). `agents/neo4j_explorer.yaml`
is kept in the repo as the canonical definition and as the source for the
console fields.

**Open question for IBM:** is this expected in ADK 2.12.0? If not, which
version resolves it, and is there a supported CLI path?

## 2. First call to a Python tool returns a "configuring" message

```json
{ "error": "We are configuring your tool in the background. This may take a
   few minutes, please try after some time.", "type": "PythonToolExecutionError" }
```

Expected. Dependencies in `requirements.txt` are installed server-side after
import. Wait 2-5 minutes and retry the same prompt.

## 3. `ModuleNotFoundError` from a Python tool

```
ModuleNotFoundError: No module named 'neo4j'
```

The tool was imported without `-r requirements.txt`, or the dependency was not
pinned to an exact version. Every dependency must be declared and pinned
(`package==version`); packages are also validated against a tenant-specific
allowlist at import time.
