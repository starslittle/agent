# Agent Runtime Prompts

Only prompts referenced by `agent.specs.PROMPT_BUNDLES` belong here.
Every invocation records the source SHA-256 and rendered-content hash; prompt
text is not copied into Runtime events.

- `chat_v1`: `generate_default_system.txt`
- `research_v1`: plan, evidence grade, and cited synthesis prompts
- `fortune_v1`: birth-profile extraction and bounded interpretation prompts

Adding a prompt requires updating `PROMPT_BUNDLES`, readiness tests, and the
prompt hash fixture. Unreferenced compatibility prompts are not retained.
