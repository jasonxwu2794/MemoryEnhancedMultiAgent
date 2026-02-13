"""Centralized secret detection patterns — single source of truth.

Used by Guardian agent, GitOps pre-commit scanning, and the pre-commit hook.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class SecretFinding(NamedTuple):
    pattern_name: str
    matched_text: str
    location: str


# Compiled patterns: (regex, human-readable description)
SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'sk-[a-zA-Z0-9]{20,}'), "API key (sk-...)"),
    (re.compile(r'sk-or-[a-zA-Z0-9]{20,}'), "OpenRouter API key"),
    (re.compile(r'sk-ant-[a-zA-Z0-9]{20,}'), "Anthropic API key"),
    (re.compile(r'ghp_[a-zA-Z0-9]{36}'), "GitHub personal access token"),
    (re.compile(r'gho_[a-zA-Z0-9]{36}'), "GitHub OAuth token"),
    (re.compile(r'github_pat_[a-zA-Z0-9_]{80,}'), "GitHub fine-grained token"),
    (re.compile(r'glpat-[a-zA-Z0-9\-]{20,}'), "GitLab personal access token"),
    (re.compile(r'xox[boaprs]-[a-zA-Z0-9\-]{10,}'), "Slack token"),
    (re.compile(r'AKIA[0-9A-Z]{16}'), "AWS access key"),
    (re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'), "Private key"),
    (re.compile(r'-----BEGIN PGP PRIVATE KEY BLOCK-----'), "PGP private key"),
    (re.compile(r'(?:postgres|mysql|mongodb)://\w+:[^@\s]+@'), "Database connection string with credentials"),
    (re.compile(r'(?:password|passwd|pwd)\s*[=:]\s*["\'][^"\']{8,}["\']', re.IGNORECASE), "Hardcoded password"),
    (re.compile(r'(?:secret|token|key)\s*[=:]\s*["\'][a-zA-Z0-9+/=]{16,}["\']', re.IGNORECASE), "Hardcoded secret"),
]

# Grep-friendly raw patterns for shell scripts (pre-commit hook)
SECRET_PATTERN_STRINGS: list[tuple[str, str]] = [
    (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
    (r'sk-ant-[a-zA-Z0-9\-]{20,}', "Anthropic API key"),
    (r'ghp_[a-zA-Z0-9]{36,}', "GitHub personal access token"),
    (r'github_pat_[a-zA-Z0-9_]{20,}', "GitHub fine-grained PAT"),
    (r'gho_[a-zA-Z0-9]{36,}', "GitHub OAuth token"),
    (r'glpat-[a-zA-Z0-9\-]{20,}', "GitLab personal access token"),
    (r'xoxb-[a-zA-Z0-9\-]+', "Slack bot token"),
    (r'xoxp-[a-zA-Z0-9\-]+', "Slack user token"),
    (r'AKIA[0-9A-Z]{16}', "AWS access key"),
]


def scan_for_secrets(text: str, location: str = "unknown") -> list[SecretFinding]:
    """Scan text for potential secrets. Returns list of findings."""
    findings: list[SecretFinding] = []
    for pattern, description in SECRET_PATTERNS:
        matches = pattern.findall(text)
        real_matches = [m for m in matches if len(m) > 10 and m not in ("true", "false", "null")]
        if real_matches:
            findings.append(SecretFinding(
                pattern_name=description,
                matched_text=real_matches[0][:20] + "...",
                location=location,
            ))
    return findings
