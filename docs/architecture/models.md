# Models, executors, and sandboxes

Planner, coder, reviewer, and embedding profiles are assigned explicitly. Provider configuration is stored in SQLite without secret values. API keys live in owner-only files under the config root and are passed to adapters as short-lived scoped values.

The same synthetic executor fixture runs on the controlled open executor and the optional Cursor adapter. Unapproved fallback, paid silent fallback, secret access, path escape, and unlimited retries fail closed. Local unsandboxed execution is labeled UNSAFE and cannot authorize autonomous merges. `coder_may_merge` remains unrepresentable in policy.

Worktree writes stay inside the sandbox root under the application cache.
