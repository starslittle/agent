# Prompt source of truth

All runtime prompts are resolved relative to the `backend/` directory and loaded
through `agent.prompts.loader`.

The public `/query_stream` path currently uses:

- `intent_classification.txt`
- `planner_research.txt` or `planner_fortune.txt`
- `executor_tool_selection.txt`
- `executor_birth_extract.txt`
- `replanner.txt`
- `generate_default_system.txt`, `generate_research_system.txt`, or
  `generate_fortune_system.txt`

`direct_llm_system.txt` belongs to the compiled/synchronous compatibility graph
and is not used by the public streaming default route.

`general_prompt.txt` and `fortune_general_prompt.txt` are legacy design prompts.
They are retained for reference but are not part of the current public streaming
execution path.

Prompt paths stored in configuration must use this same backend-relative base.
Prompt files are UTF-8 with LF line endings, enforced by `.gitattributes`.
SHA-256 is calculated over the exact file bytes: Python uses `Path.read_bytes()`
and Go must use `os.ReadFile()` without trimming, newline conversion, or
re-encoding.

Runtime state appends every prompt that was actually invoked to
`metadata.prompt_versions`. Each entry contains the stage, backend-relative
path, raw-file SHA-256, rendered-text SHA-256, and iteration where applicable.
Code paths that do not invoke an LLM prompt must not add a synthetic entry.
