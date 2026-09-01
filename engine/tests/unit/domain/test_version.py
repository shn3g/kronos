# SPDX-License-Identifier: AGPL-3.0-or-later

from kronos_engine.domain.version import client_is_compatible


def test_matching_versions_are_compatible() -> None:
    assert client_is_compatible("0.1.0", "0.1.0", "0.1.0") is True
    assert client_is_compatible("0.1.0", "0.1.0", "0.2.0") is True


def test_newer_desktop_is_incompatible_with_older_engine() -> None:
    assert client_is_compatible("0.2.0", "0.1.0", "0.1.0") is False


def test_older_or_invalid_clients_are_incompatible() -> None:
    assert client_is_compatible("0.0.9", "0.1.0", "0.1.0") is False
    assert client_is_compatible("1.0.0", "0.1.0", "0.1.0") is False
    assert client_is_compatible("", "0.1.0", "0.1.0") is False
    assert client_is_compatible("not-a-version", "0.1.0", "0.1.0") is False
