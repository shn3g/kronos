# SPDX-License-Identifier: AGPL-3.0-or-later
from kronos_engine.application.chat_mentions import MAX_MENTIONED_PATHS, mentioned_workspace_paths


def test_mentioned_workspace_paths_reads_at_tokens() -> None:
    assert mentioned_workspace_paths("Fix @src/App.tsx please") == ("src/App.tsx",)


def test_mentioned_workspace_paths_skips_email() -> None:
    assert mentioned_workspace_paths("mail a@b.com and @lib/util.ts") == ("lib/util.ts",)


def test_mentioned_workspace_paths_rejects_parent_segments() -> None:
    assert mentioned_workspace_paths("see @../secret.txt") == ()


def test_mentioned_workspace_paths_keeps_first_unique_path() -> None:
    assert mentioned_workspace_paths("Look at @src/a.ts and @src/a.ts") == ("src/a.ts",)


def test_mentioned_workspace_paths_caps_at_six() -> None:
    text = " ".join(f"@file{i}.py" for i in range(10))
    expected = tuple(f"file{i}.py" for i in range(MAX_MENTIONED_PATHS))
    assert mentioned_workspace_paths(text) == expected
