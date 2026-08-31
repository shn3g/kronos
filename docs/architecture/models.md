# Models, executors, and sandboxes

Planner, coder, reviewer, and embedding profiles are assigned explicitly. Provider configuration is stored in SQLite without secret values. API keys live in OS credential storage (Windows Credential Manager, macOS Keychain, or libsecret) and are passed to adapters as scoped values that expire after their TTL.

The default sandbox is an in-process path jail. It does not drop network, root, or cgroups, and it fails closed when a request asks for those capabilities. Docker/SWE-ReX is a separate adapter and is not selected until a confined runtime is available. `secrets=False` strips secret-shaped worker env, not only a GitHub denylist. Local unsandboxed execution is labeled UNSAFE and cannot authorize autonomous merges. `coder_may_merge` remains unrepresentable in policy.

For the initial Klikday profile, see `examples/klikday/config.yaml`. Orchestration uses an approved planner profile. Coding uses the `cursor` executor profile. Retrieval uses the local index. Deterministic tests plus the isolated reviewer control integration merges. Other users can replace Cursor with OpenHands or an OpenAI-compatible local coder without changing the control plane.

`autonomy.mode` is an operator fuse. Models cannot change it. Observe and shadow do not create GitHub issues, pull requests, or merges.

The same synthetic executor fixture runs on the controlled open executor and the optional Cursor adapter. Cursor detection resolves `cursor-agent` from absolute PATH entries and skips the process cwd. Unapproved fallback, paid silent fallback (including billed providers when `fallback_billed` is false), secret access, path escape, and unlimited retries fail closed.

Worktree writes stay inside the sandbox root under the application cache.
