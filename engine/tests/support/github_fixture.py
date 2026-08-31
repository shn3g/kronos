# SPDX-License-Identifier: AGPL-3.0-or-later
"""In-memory GitHub HTTP fixture. CI never calls live GitHub; this is the contract."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from tests.support.secrets import InMemorySecretStore

from kronos_engine.adapters.github import GitHubForge, InstallationAuth
from kronos_engine.adapters.github.client import GitHubClient, HttpRequest, HttpResponse
from kronos_engine.domain.github import KRONOS_REVIEW_CHECK_NAME
from kronos_engine.ports.forge import AppCredentials, ForgeTarget


def _rsa_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


TEST_CONTROLLER_PEM = _rsa_pem()
TEST_REVIEWER_PEM = _rsa_pem()
DEFAULT_SHA = "a" * 40
INTEGRATION_SHA = "b" * 40


def _b64url_decode(raw: str) -> bytes:
    padding_chars = "=" * ((4 - len(raw) % 4) % 4)
    return base64.urlsafe_b64decode(raw + padding_chars)


def _public_key(pem: str) -> object:
    return serialization.load_pem_private_key(pem.encode(), password=None).public_key()


def _verify_jwt(token: str, pem: str) -> dict[str, Any]:
    header_b64, payload_b64, signature_b64 = token.split(".")
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = _b64url_decode(signature_b64)
    public = _public_key(pem)
    public.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
    return json.loads(_b64url_decode(payload_b64))


@dataclass
class GitHubFixture:
    owner: str = "acme"
    repo: str = "app"
    default_branch: str = "main"
    integration_branch: str = "integration"
    controller_app_id: int = 1001
    reviewer_app_id: int = 1002
    controller_installation_id: int = 2001
    reviewer_installation_id: int = 2002
    webhook_enabled: bool = False
    integration_sha: str = INTEGRATION_SHA
    _branches: dict[str, str] = field(default_factory=dict)
    _branch_source: dict[str, str] = field(default_factory=dict)
    _issues: list[dict[str, Any]] = field(default_factory=list)
    _comments: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    _labels: dict[int, list[str]] = field(default_factory=dict)
    _discussions: list[dict[str, Any]] = field(default_factory=list)
    _pulls: list[dict[str, Any]] = field(default_factory=list)
    _rulesets: list[dict[str, Any]] = field(default_factory=list)
    _check_runs: list[dict[str, Any]] = field(default_factory=list)
    _logical: list[str] = field(default_factory=list)
    _ref_writes: list[str] = field(default_factory=list)
    _logs: list[str] = field(default_factory=list)
    _status_queue: list[tuple[int, str | None, str | None]] = field(default_factory=list)
    _always_status: int | None = None
    _etags_enabled: bool = False
    _page_fetches: int = 0
    _last_request: HttpRequest | None = None
    _last_status: int = 0
    _last_mutating_headers: dict[str, str] = field(default_factory=dict)
    _last_token_role: str | None = None
    _saw_status: set[int] = field(default_factory=set)
    _retried: set[int] = field(default_factory=set)
    _next_issue: int = 1
    _next_comment: int = 1
    _next_discussion: int = 1
    _next_pull: int = 1
    _next_ruleset: int = 1
    _next_check: int = 1
    _merges: list[int] = field(default_factory=list)
    repository_node_id: str = "R_kgDO_fixture"
    general_category_id: str = "DIC_kwDO_general"
    _graphql_queries: list[str] = field(default_factory=list)
    _create_discussion_variables: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._branches = {
            self.default_branch: DEFAULT_SHA,
            self.integration_branch: self.integration_sha,
        }

    def send(self, request: HttpRequest) -> HttpResponse:
        self._last_request = request
        parsed = urlparse(request.url)
        path = parsed.path
        method = request.method.upper()
        self._logs.append(f"{method} {path}")
        if method in {"POST", "PUT", "PATCH"} and path.startswith("/repos"):
            self._last_mutating_headers = dict(request.headers)
        if method == "POST" and path == "/graphql":
            self._last_mutating_headers = dict(request.headers)
        if path.startswith("/repos") and self._always_status is not None:
            return self._error(self._always_status, remaining="0")
        if path.startswith("/repos") and self._status_queue:
            status, remaining, retry_after = self._status_queue.pop(0)
            return self._error(status, remaining=remaining, retry_after=retry_after)
        response = self._route(method, path, parsed.query, request)
        self._last_status = response.status
        if (
            path.startswith("/repos")
            and response.status < 400
            and response.status != 304
            and self._saw_status
        ):
            self._retried.update(self._saw_status)
        return response

    def _error(
        self, status: int, *, remaining: str | None, retry_after: str | None = None
    ) -> HttpResponse:
        self._saw_status.add(status)
        self._last_status = status
        headers: dict[str, str] = {}
        if retry_after is not None:
            headers["Retry-After"] = retry_after
        if remaining is not None:
            headers["X-RateLimit-Remaining"] = remaining
        return HttpResponse(status=status, headers=headers, body=b"{}")

    def _route(
        self, method: str, path: str, query: str, request: HttpRequest
    ) -> HttpResponse:
        if method == "POST" and path.endswith("/access_tokens"):
            return self._mint_token(path, request)
        if method == "POST" and "/app-manifests/" in path and path.endswith("/conversions"):
            return self._convert_manifest(path)
        if method == "GET" and path.startswith("/app/installations/"):
            return self._installation(path, request)
        if path == "/graphql":
            return self._graphql(request)
        prefix = f"/repos/{self.owner}/{self.repo}"
        if not path.startswith(prefix):
            return HttpResponse(404, {}, b"{}")
        rest = path[len(prefix) :]
        params = {key: values[-1] for key, values in parse_qs(query).items()}
        if rest == "/issues" or rest == "/issues/":
            if method == "GET":
                return self._list_issues(params, request)
            if method == "POST":
                return self._create_issue(request)
        if rest.startswith("/issues/") and rest.endswith("/comments"):
            number = int(rest.split("/")[2])
            if method == "GET":
                return self._json(self._comments.get(number, []))
            if method == "POST":
                return self._create_comment(number, request)
        if rest.startswith("/issues/") and rest.endswith("/labels"):
            number = int(rest.split("/")[2])
            if method == "GET":
                return self._json([{"name": name} for name in self._labels.get(number, [])])
            if method == "POST":
                return self._add_labels(number, request)
        if rest == "/pulls":
            if method == "GET":
                return self._json(self._pulls)
            if method == "POST":
                return self._create_pull(request)
        if rest.startswith("/git/ref/heads/"):
            name = rest.split("/git/ref/heads/", 1)[1]
            sha = self._branches.get(name)
            if sha is None:
                return HttpResponse(404, {}, b"{}")
            return self._maybe_etag(
                {"ref": f"refs/heads/{name}", "object": {"sha": sha}}, request
            )
        if rest == "/git/refs" and method == "POST":
            return self._create_ref(request)
        if rest == "/rulesets":
            if method == "GET":
                return self._json(self._rulesets)
            if method == "POST":
                return self._create_ruleset(request)
        if rest.startswith("/rulesets/") and rest.count("/") == 2:
            ruleset_id = int(rest.rsplit("/", 1)[-1])
            if method == "GET":
                found = next((item for item in self._rulesets if item["id"] == ruleset_id), None)
                if found is None:
                    return HttpResponse(404, {}, b"{}")
                return self._json(found)
            if method == "PUT":
                return self._update_ruleset(ruleset_id, request)
        if rest == "/check-runs" and method == "POST":
            return self._create_check_run(request)
        if rest.startswith("/commits/") and rest.endswith("/check-runs") and method == "GET":
            sha = rest.split("/")[2]
            return self._json(
                {
                    "total_count": len(
                        [item for item in self._check_runs if item.get("head_sha") == sha]
                    ),
                    "check_runs": [
                        item for item in self._check_runs if item.get("head_sha") == sha
                    ],
                }
            )
        if rest.startswith("/pulls/") and rest.endswith("/merge") and method == "PUT":
            return self._merge_pull(rest, request)
        if rest.startswith("/pulls/") and method == "GET" and rest.count("/") == 2:
            number = int(rest.split("/")[2])
            found = next((item for item in self._pulls if item["number"] == number), None)
            if found is None:
                return HttpResponse(404, {}, b"{}")
            return self._json(found)
        return HttpResponse(404, {}, b"{}")

    def _mint_token(self, path: str, request: HttpRequest) -> HttpResponse:
        installation_id = int(path.rstrip("/").split("/")[-2])
        authorization = request.headers.get("Authorization") or request.headers.get("authorization")
        token = (authorization or "").removeprefix("Bearer ").strip()
        role = "controller" if installation_id == self.controller_installation_id else "reviewer"
        pem = TEST_CONTROLLER_PEM if role == "controller" else TEST_REVIEWER_PEM
        claims = _verify_jwt(token, pem)
        expected_iss = self.controller_app_id if role == "controller" else self.reviewer_app_id
        if claims.get("iss") != expected_iss:
            return HttpResponse(401, {}, b"{}")
        self._last_token_role = role
        body = {
            "token": f"ghs_fixture_{role}",
            "expires_at": "2099-01-01T00:00:00Z",
        }
        return self._json(body)

    def _installation(self, path: str, request: HttpRequest) -> HttpResponse:
        _ = request
        installation_id = int(path.rstrip("/").split("/")[-1])
        role = "controller" if installation_id == self.controller_installation_id else "reviewer"
        app_id = self.controller_app_id if role == "controller" else self.reviewer_app_id
        return self._json(
            {
                "id": installation_id,
                "app_id": app_id,
                "account": {"login": self.owner},
            }
        )

    def _convert_manifest(self, path: str) -> HttpResponse:
        code = path.rstrip("/").split("/")[-2]
        if code == "controller-manifest":
            body = {
                "id": self.controller_app_id,
                "slug": "kronos-controller",
                "pem": TEST_CONTROLLER_PEM,
                "name": "Kronos Controller",
            }
            return self._json(body)
        if code == "reviewer-manifest":
            body = {
                "id": self.reviewer_app_id,
                "slug": "kronos-reviewer",
                "pem": TEST_REVIEWER_PEM,
                "name": "Kronos Reviewer",
            }
            return self._json(body)
        return HttpResponse(404, {}, b'{"message":"Not Found"}')

    def _graphql(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        query = str(payload.get("query") or "")
        variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
        self._graphql_queries.append(query)
        if "createDiscussion" in query:
            self._create_discussion_variables = dict(variables)
            if variables.get("repositoryId") != self.repository_node_id:
                return self._json(
                    {"errors": [{"message": "Could not resolve to a node with the global id"}]}
                )
            if variables.get("categoryId") != self.general_category_id:
                return self._json(
                    {"errors": [{"message": "Could not resolve discussion category"}]}
                )
            number = self._next_discussion
            self._next_discussion += 1
            discussion = {
                "number": number,
                "url": f"https://github.com/{self.owner}/{self.repo}/discussions/{number}",
                "body": variables.get("body", ""),
                "title": variables.get("title", ""),
            }
            self._discussions.append(discussion)
            self._logical.append("create_discussion")
            return self._json({"data": {"createDiscussion": {"discussion": discussion}}})
        return self._json(
            {
                "data": {
                    "repository": {
                        "id": self.repository_node_id,
                        "discussionCategories": {
                            "nodes": [
                                {"id": self.general_category_id, "name": "General"},
                                {"id": "DIC_kwDO_ideas", "name": "Ideas"},
                            ]
                        },
                        "discussions": {
                            "nodes": list(self._discussions),
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                    }
                }
            }
        )

    def _list_issues(self, params: Mapping[str, str], request: HttpRequest) -> HttpResponse:
        self._page_fetches += 1
        per_page = int(params.get("per_page") or 10)
        page = int(params.get("page") or 1)
        etag = self._etag(self._issues)
        headers: dict[str, str] = {"ETag": etag}
        if self._etags_enabled:
            incoming = request.headers.get("If-None-Match")
            if incoming == etag:
                return HttpResponse(304, headers, b"")
        start = (page - 1) * per_page
        chunk = self._issues[start : start + per_page]
        if start + per_page < len(self._issues):
            next_url = (
                f"https://api.github.com/repos/{self.owner}/{self.repo}/issues"
                f"?page={page + 1}&per_page={per_page}&state=all"
            )
            headers["Link"] = f'<{next_url}>; rel="next"'
        return HttpResponse(200, headers, json.dumps(chunk).encode())

    def _create_issue(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        marker = str(payload.get("body") or "")
        for issue in self._issues:
            if marker and marker in str(issue.get("body") or ""):
                return self._json(issue)
        number = self._next_issue
        self._next_issue += 1
        labels = [str(item) for item in payload.get("labels") or []]
        issue = {
            "number": number,
            "title": payload.get("title"),
            "body": payload.get("body"),
            "html_url": f"https://github.com/{self.owner}/{self.repo}/issues/{number}",
            "labels": [{"name": name} for name in labels],
        }
        self._issues.append(issue)
        self._labels[number] = labels
        self._logical.append("create_issue")
        return self._json(issue)

    def _create_comment(self, number: int, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        body = str(payload.get("body") or "")
        for comment in self._comments.get(number, []):
            if body and body in str(comment.get("body") or ""):
                return self._json(comment)
        comment_id = self._next_comment
        self._next_comment += 1
        comment = {"id": comment_id, "body": body}
        self._comments.setdefault(number, []).append(comment)
        self._logical.append("add_issue_comment")
        return self._json(comment)

    def _add_labels(self, number: int, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        incoming = [str(item) for item in payload.get("labels") or []]
        current = self._labels.setdefault(number, [])
        added = False
        for name in incoming:
            if name not in current:
                current.append(name)
                added = True
        if added:
            self._logical.append("add_labels")
        return self._json([{"name": name} for name in current])

    def _create_pull(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        body = str(payload.get("body") or "")
        for pull in self._pulls:
            if body and body in str(pull.get("body") or ""):
                return self._json(pull)
        number = self._next_pull
        self._next_pull += 1
        head_name = str(payload.get("head") or "")
        base_name = str(payload.get("base") or "")
        pull = {
            "number": number,
            "title": payload.get("title"),
            "body": body,
            "draft": bool(payload.get("draft", True)),
            "html_url": f"https://github.com/{self.owner}/{self.repo}/pull/{number}",
            "head": {
                "ref": head_name,
                "sha": self._branches.get(head_name, DEFAULT_SHA),
            },
            "base": {
                "ref": base_name,
                "sha": self._branches.get(base_name, DEFAULT_SHA),
            },
        }
        self._pulls.append(pull)
        self._logical.append("open_draft_pr")
        return self._json(pull)

    def _create_ref(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        ref = str(payload.get("ref") or "")
        sha = str(payload.get("sha") or "")
        name = ref.removeprefix("refs/heads/")
        if name == self.default_branch:
            return HttpResponse(422, {}, b'{"message":"protected"}')
        self._branches[name] = sha
        self._ref_writes.append(name)
        source = (
            self.integration_branch if sha == self.integration_sha else self.default_branch
        )
        self._branch_source[name] = source
        self._logical.append("create_feature_branch")
        return self._json({"ref": ref, "object": {"sha": sha}})

    def _create_ruleset(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        ruleset_id = self._next_ruleset
        self._next_ruleset += 1
        payload["id"] = ruleset_id
        self._rulesets.append(payload)
        self._logical.append("apply_ruleset")
        return self._json(payload)

    def _update_ruleset(self, ruleset_id: int, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        payload["id"] = ruleset_id
        self._rulesets = [
            payload if item.get("id") == ruleset_id else item for item in self._rulesets
        ]
        if "apply_ruleset" not in self._logical:
            self._logical.append("apply_ruleset")
        return self._json(payload)

    def _create_check_run(self, request: HttpRequest) -> HttpResponse:
        payload = json.loads(request.body.decode() if request.body else "{}")
        role = self._last_token_role
        if role == "reviewer":
            app_id = self.reviewer_app_id
            slug = "kronos-reviewer"
            posted_by = "reviewer"
        elif role == "controller":
            app_id = self.controller_app_id
            slug = "kronos-controller"
            posted_by = "controller"
        else:
            app_id = None
            slug = None
            posted_by = "worker"
        check_id = self._next_check
        self._next_check += 1
        check = {
            "id": check_id,
            "name": payload.get("name"),
            "head_sha": payload.get("head_sha"),
            "status": payload.get("status", "completed"),
            "conclusion": payload.get("conclusion"),
            "app": None if app_id is None else {"id": app_id, "slug": slug},
            "posted_by": posted_by,
        }
        self._check_runs.append(check)
        self._logical.append("post_check_run")
        return HttpResponse(201, {}, json.dumps(check).encode())

    def _merge_pull(self, rest: str, request: HttpRequest) -> HttpResponse:
        number = int(rest.split("/")[2])
        pull = next((item for item in self._pulls if item["number"] == number), None)
        if pull is None:
            return HttpResponse(404, {}, b"{}")
        base_ref = str((pull.get("base") or {}).get("ref") or "")
        if base_ref == self.default_branch:
            return HttpResponse(422, {}, b'{"message":"protected"}')
        payload = json.loads(request.body.decode() if request.body else "{}")
        self._merges.append(number)
        self._logical.append("merge_pull")
        return self._json({"merged": True, "sha": payload.get("sha")})

    def _json(self, payload: object) -> HttpResponse:
        return HttpResponse(200, {}, json.dumps(payload).encode())

    def _maybe_etag(self, payload: object, request: HttpRequest) -> HttpResponse:
        if not self._etags_enabled:
            return self._json(payload)
        etag = self._etag(payload)
        headers = {"ETag": etag}
        incoming = request.headers.get("If-None-Match")
        if incoming == etag:
            return HttpResponse(304, headers, b"")
        return HttpResponse(200, headers, json.dumps(payload).encode())

    def _etag(self, payload: object) -> str:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return f'W/"{digest[:16]}"'

    def seed_issues(self, count: int) -> None:
        for _ in range(count):
            number = self._next_issue
            self._next_issue += 1
            self._issues.append(
                {
                    "number": number,
                    "title": f"seed-{number}",
                    "body": "seed",
                    "html_url": f"https://github.com/{self.owner}/{self.repo}/issues/{number}",
                    "labels": [],
                }
            )
            self._labels[number] = []

    def seed_ruleset(self, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.setdefault("id", self._next_ruleset)
        self._next_ruleset = max(self._next_ruleset, int(payload["id"]) + 1)
        self._rulesets.append(payload)

    def enable_etags(self) -> None:
        self._etags_enabled = True

    def queue_status(
        self,
        status: int,
        remaining: int | None = None,
        retry_after: int | None = None,
    ) -> None:
        self._status_queue.append(
            (
                status,
                None if remaining is None else str(remaining),
                None if retry_after is None else str(retry_after),
            )
        )

    def always_status(self, status: int) -> None:
        self._always_status = status

    def retried_after_status(self, status: int) -> bool:
        return status in self._retried

    def page_fetches(self) -> int:
        return self._page_fetches

    def last_request(self) -> HttpRequest:
        assert self._last_request is not None
        return self._last_request

    def last_status(self) -> int:
        return self._last_status

    def last_token_request_role(self) -> str | None:
        return self._last_token_role

    def last_mutating_headers(self) -> dict[str, str]:
        return dict(self._last_mutating_headers)

    def captured_logs(self) -> list[str]:
        return list(self._logs)

    def client_timeout_seconds(self) -> float:
        if self._last_request is None:
            return 0.0
        return self._last_request.timeout

    def count_issues(self) -> int:
        return len(self._issues)

    def count_comments(self) -> int:
        return sum(len(items) for items in self._comments.values())

    def count_discussions(self) -> int:
        return len(self._discussions)

    def count_pulls(self) -> int:
        return len(self._pulls)

    def count_ruleset_puts(self) -> int:
        return self._logical.count("apply_ruleset")

    def issue_labels(self, number: int) -> tuple[str, ...]:
        return tuple(self._labels.get(number, []))

    def logical_action_kinds(self) -> tuple[str, ...]:
        return tuple(self._logical)

    def ref_writes(self) -> list[str]:
        return list(self._ref_writes)

    def branch_created_from(self, name: str) -> str:
        return self._branch_source[name]

    def pulls(self) -> list[dict[str, Any]]:
        return list(self._pulls)

    def check_runs(self) -> list[dict[str, Any]]:
        return list(self._check_runs)

    def seed_check_run(
        self,
        *,
        name: str,
        head_sha: str,
        app_id: int | None,
        conclusion: str = "success",
        posted_by: str = "reviewer",
    ) -> None:
        slug = "kronos-reviewer" if posted_by == "reviewer" else posted_by
        self._check_runs.append(
            {
                "id": self._next_check,
                "name": name,
                "head_sha": head_sha,
                "status": "completed",
                "conclusion": conclusion,
                "app": None if app_id is None else {"id": app_id, "slug": slug},
                "posted_by": posted_by,
            }
        )
        self._next_check += 1

    def merge_calls(self) -> tuple[int, ...]:
        return tuple(self._merges)

    def branch_sha(self, name: str) -> str:
        return self._branches[name]

    def applied_ruleset(self) -> dict[str, Any] | None:
        return self._rulesets[-1] if self._rulesets else None

    def applied_ruleset_contexts(self) -> tuple[str, ...]:
        ruleset = self.applied_ruleset()
        if ruleset is None:
            return ()
        return tuple(
            str(check["context"])
            for rule in ruleset.get("rules") or []
            if rule.get("type") == "required_status_checks"
            for check in (rule.get("parameters") or {}).get("required_status_checks") or []
        )

    def applied_ruleset_strict(self) -> bool | None:
        ruleset = self.applied_ruleset()
        if ruleset is None:
            return None
        for rule in ruleset.get("rules") or []:
            if rule.get("type") == "required_status_checks":
                return bool(
                    (rule.get("parameters") or {}).get("strict_required_status_checks_policy")
                )
        return None

    def applied_ruleset_integration_ids(self) -> tuple[int, ...]:
        ruleset = self.applied_ruleset()
        if ruleset is None:
            return ()
        ids: list[int] = []
        for rule in ruleset.get("rules") or []:
            if rule.get("type") != "required_status_checks":
                continue
            for check in (rule.get("parameters") or {}).get("required_status_checks") or []:
                if check.get("context") == KRONOS_REVIEW_CHECK_NAME:
                    integration = check.get("integration_id")
                    if isinstance(integration, int):
                        ids.append(integration)
        return tuple(ids)

    def applied_ruleset_bypass_actors(self) -> list[object]:
        ruleset = self.applied_ruleset()
        if ruleset is None:
            return []
        bypass = ruleset.get("bypass_actors")
        return list(bypass) if isinstance(bypass, list) else []

    def ruleset_by_id(self, ruleset_id: int) -> dict[str, Any] | None:
        return next((item for item in self._rulesets if item.get("id") == ruleset_id), None)

    def ruleset_named(self, name: str) -> dict[str, Any] | None:
        return next((item for item in self._rulesets if item.get("name") == name), None)

    def graphql_queries(self) -> list[str]:
        return list(self._graphql_queries)

    def last_create_discussion_variables(self) -> dict[str, Any]:
        return dict(self._create_discussion_variables)


def controller_stack(
    *,
    secrets: InMemorySecretStore | None = None,
    sleep: object | None = None,
    rng: object | None = None,
    base_url: str = "https://api.github.com",
) -> tuple[GitHubForge, GitHubFixture, InstallationAuth]:
    store = secrets if secrets is not None else InMemorySecretStore()
    if secrets is None:
        store.put("github:controller:private_key", TEST_CONTROLLER_PEM)
        store.put("github:reviewer:private_key", TEST_REVIEWER_PEM)
    fixture = GitHubFixture()
    apps = {
        "controller": AppCredentials(
            app_id=1001, installation_id=2001, role="controller"
        ),
        "reviewer": AppCredentials(app_id=1002, installation_id=2002, role="reviewer"),
    }
    slept: list[float] = []

    def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    sleep_fn = fake_sleep if sleep is None else sleep
    auth = InstallationAuth(
        secrets=store,
        apps=apps,
        transport=fixture,
        sleep=sleep_fn,
        base_url=base_url,
    )
    client = GitHubClient(
        transport=fixture,
        auth=auth,
        role="controller",
        sleep=sleep_fn,
        base_url=base_url,
        rng=rng if rng is not None else None,
    )
    forge = GitHubForge(
        client=client,
        target=ForgeTarget(
            owner="acme",
            repo="app",
            integration_branch="integration",
            protected_branch="main",
        ),
    )
    return forge, fixture, auth
