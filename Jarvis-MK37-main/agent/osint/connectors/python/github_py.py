"""
GitHub — profil utilisateur + repos publics.
Cibles : USERNAME | sans clé (60 req/h), GITHUB_TOKEN pour 5000 req/h.
"""
from __future__ import annotations
import os, time
from agent.osint.connectors.base import Connector, ConnectorResult, Finding, get_registry
from agent.osint.connectors.python._http import async_get
from agent.osint.target import Target, TargetType

_KEY_ENV = "GITHUB_TOKEN"
_BASE    = "https://api.github.com"


class GitHubConnector(Connector):
    name         = "github_py"
    supports     = {TargetType.USERNAME, TargetType.PSEUDONYM}
    requires_key = False
    rate_limit   = 60
    backend      = "python"

    def _headers(self) -> dict:
        token = os.environ.get(_KEY_ENV, "")
        h = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def query(self, target: Target) -> ConnectorResult:
        t0 = time.monotonic()
        username = target.normalized
        h = self._headers()
        resp = await async_get(f"{_BASE}/users/{username}", headers=h, timeout=10.0)
        elapsed = int((time.monotonic() - t0) * 1000)
        if resp["status"] == 404:
            return ConnectorResult(connector=self.name, target=target, success=True,
                                   findings=[], elapsed_ms=elapsed)
        if not resp["ok"]:
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error=f"github {resp['status']}: {str(resp['data'])[:120]}",
                                   elapsed_ms=elapsed)
        u = resp["data"]
        if not isinstance(u, dict):
            return ConnectorResult(connector=self.name, target=target, success=False,
                                   error="github: unexpected response", elapsed_ms=elapsed)
        findings = [Finding(
            type="account",
            source="github",
            url=u.get("html_url", ""),
            extracted={
                "username":      username,
                "name":          u.get("name", ""),
                "email":         u.get("email", ""),
                "bio":           u.get("bio", ""),
                "company":       u.get("company", ""),
                "location":      u.get("location", ""),
                "blog":          u.get("blog", ""),
                "twitter":       u.get("twitter_username", ""),
                "public_repos":  u.get("public_repos", 0),
                "public_gists":  u.get("public_gists", 0),
                "followers":     u.get("followers", 0),
                "following":     u.get("following", 0),
                "created_at":    u.get("created_at", ""),
                "updated_at":    u.get("updated_at", ""),
                "avatar_url":    u.get("avatar_url", ""),
                "profile_url":   u.get("html_url", ""),
            },
            confidence=0.95,
        )]
        # Repos récents
        resp2 = await async_get(f"{_BASE}/users/{username}/repos",
                                params={"sort": "updated", "per_page": 5}, headers=h, timeout=8.0)
        if resp2["ok"] and isinstance(resp2["data"], list):
            for repo in resp2["data"][:5]:
                findings.append(Finding(
                    type="github_repo",
                    source="github",
                    url=repo.get("html_url", ""),
                    extracted={
                        "username":     username,
                        "repo":         repo.get("name", ""),
                        "description":  repo.get("description", ""),
                        "language":     repo.get("language", ""),
                        "stars":        repo.get("stargazers_count", 0),
                        "forks":        repo.get("forks_count", 0),
                        "updated_at":   repo.get("updated_at", ""),
                        "topics":       repo.get("topics", []),
                    },
                    confidence=0.9,
                ))
        return ConnectorResult(connector=self.name, target=target, success=True,
                               findings=findings, elapsed_ms=int((time.monotonic()-t0)*1000))


get_registry().register(GitHubConnector())
