# Models, executors, and sandboxes

Orchestrator, planner, coder, reviewer, and embedding profiles are assigned explicitly. Each role can use an online API or a local OpenAI-compatible endpoint on its own. Provider configuration is stored in SQLite without secret values. API keys live in OS credential storage (Windows Credential Manager, macOS Keychain, or libsecret) and are passed to adapters as scoped values that expire after their TTL.

The Models page ships presets for OpenAI (`https://api.openai.com/v1`), OpenRouter (`https://openrouter.ai/api/v1`), OpenCode Zen (`https://opencode.ai/zen/v1`), Ollama (`http://127.0.0.1:11434/v1`), and LM Studio (`http://127.0.0.1:1234/v1`). Cost ceiling and max tokens are editable per profile. A billed call with a zero ceiling is refused. The reviewer GitHub App is the merge identity; the reviewer model role is reserved for future use.

Chat uses the orchestrator role. Planning uses the planner role, with `LlmPlanner` calling that profile and falling back to `IndexedPlanner` when the LLM is missing or fails. Coding uses the executor profile in committed policy: `controlled` (template default `standard` maps to controlled), `cursor`, or `opencode`. Retrieval uses the local index. Deterministic tests plus the isolated reviewer control integration merges. You can replace Cursor with OpenHands or an OpenAI-compatible local coder without changing the control plane.

The default sandbox is an in-process path jail. It does not drop network, root, or cgroups, and it fails closed when a request asks for those capabilities. Docker/SWE-ReX is a separate adapter and is not selected until a confined runtime is available. `secrets=False` strips secret-shaped worker env, not only a GitHub denylist. Local unsandboxed execution is labeled UNSAFE and cannot authorize autonomous merges. `coder_may_merge` remains unrepresentable in policy.

`autonomy.mode` is an operator fuse. Models cannot change it. Observe and shadow do not create GitHub issues, pull requests, or merges.

The same synthetic executor fixture runs on the controlled open executor and the optional Cursor adapter. Cursor detection resolves `cursor-agent` from absolute PATH entries and skips the process cwd. Unapproved fallback, paid silent fallback (including billed providers when `fallback_billed` is false), secret access, path escape, and unlimited retries fail closed.

Worktree writes stay inside the sandbox root under the application cache.
