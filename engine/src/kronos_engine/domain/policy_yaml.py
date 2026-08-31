# SPDX-License-Identifier: AGPL-3.0-or-later
"""YAML subset for Kronos-emitted repository policy. Pure parse. No I/O."""

from __future__ import annotations

from kronos_engine.domain.policy import PolicyError


def parse_simple_yaml(text: str) -> object:
    rows: list[tuple[int, str]] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        rows.append((indent, line.strip()))
    value, _index = _parse_value(rows, 0, 0)
    return value


def _parse_value(
    rows: list[tuple[int, str]], index: int, indent: int
) -> tuple[object, int]:
    if index >= len(rows):
        return {}, index
    _current_indent, content = rows[index]
    if content.startswith("-"):
        return _parse_list(rows, index, indent)
    return _parse_mapping(rows, index, indent)


def _parse_mapping(
    rows: list[tuple[int, str]], index: int, indent: int
) -> tuple[dict[str, object], int]:
    result: dict[str, object] = {}
    while index < len(rows):
        current_indent, content = rows[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise PolicyError("invalid YAML indent")
        if content.startswith("-"):
            break
        key, sep, rest = content.partition(":")
        if sep == "":
            raise PolicyError("invalid YAML mapping line")
        key = key.strip()
        rest = rest.strip()
        index += 1
        if rest == "[]":
            result[key] = []
            continue
        if rest != "":
            result[key] = _parse_scalar(rest)
            continue
        if index < len(rows) and rows[index][0] > current_indent:
            nested, index = _parse_value(rows, index, rows[index][0])
            result[key] = nested
        else:
            result[key] = {}
    return result, index


def _parse_list(
    rows: list[tuple[int, str]], index: int, indent: int
) -> tuple[list[object], int]:
    result: list[object] = []
    while index < len(rows):
        current_indent, content = rows[index]
        if current_indent < indent:
            break
        if not content.startswith("-"):
            break
        rest = content[1:].strip()
        index += 1
        if rest == "":
            nested, index = _parse_value(rows, index, indent + 2)
            result.append(nested)
        else:
            result.append(_parse_scalar(rest))
    return result, index


def _parse_scalar(raw: str) -> object:
    if raw in {"true", "false"}:
        return raw == "true"
    if raw.startswith('"') and raw.endswith('"') and len(raw) >= 2:
        return raw[1:-1].replace('\\"', '"')
    if raw.isdigit() or (raw.startswith("-") and raw[1:].isdigit()):
        return int(raw)
    return raw
