"""Content tagging utility for prompt injection defense.

Provides lightweight, importable tools for any agent to tag untrusted content
and scan for common injection patterns without depending on Guardian.
"""

import re

# ─── Compiled Injection Patterns ──────────────────────────────────────────────

INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"ignore\s+(?:all\s+)?(?:previous|above|prior)\s+instructions", re.IGNORECASE), "ignore_previous_instructions"),
    (re.compile(r"ignore\s+all\s+prior", re.IGNORECASE), "ignore_all_prior"),
    (re.compile(r"disregard\s+(?:all|your|the\s+)?(?:above|previous|prior|rules|instructions|guidelines)", re.IGNORECASE), "disregard_above"),
    (re.compile(r"do\s+not\s+follow", re.IGNORECASE), "do_not_follow"),
    (re.compile(r"new\s+instructions:", re.IGNORECASE), "new_instructions"),
    (re.compile(r"(?:^|\n)\s*system\s*:", re.IGNORECASE), "system_role"),
    (re.compile(r"(?:^|\n)\s*assistant\s*:", re.IGNORECASE), "assistant_role"),
    (re.compile(r"\n\nHuman:", re.DOTALL), "human_role_switch"),
    (re.compile(r"\n\nAssistant:", re.DOTALL), "assistant_role_switch"),
    (re.compile(r"</system>", re.IGNORECASE), "system_tag_close"),
    (re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE), "inst_tags"),
    (re.compile(r"<\|im_start\|>|<\|im_end\|>"), "chatml_tags"),
    (re.compile(r"you\s+are\s+now\s+(?:a|an)\s+", re.IGNORECASE), "role_override"),
    (re.compile(r"new\s+system\s+prompt", re.IGNORECASE), "new_system_prompt"),
    (re.compile(r"override\s+(?:your|the)\s+(?:system|instructions)", re.IGNORECASE), "override_instructions"),
    (re.compile(r"forget\s+(?:all|everything|your)\s+(?:previous|prior)", re.IGNORECASE), "forget_previous"),
    (re.compile(r"(?:^|\s)(?:aW1wb3J0|aWdub3Jl|c3lzdGVt)", re.ASCII), "base64_suspicious"),  # base64 for import/ignore/system
]

# Role-switching markers to strip during sanitization
_ROLE_SWITCH_RE = re.compile(
    r"(\n\nHuman:|\n\nAssistant:|<\|im_start\|>(?:system|user|assistant)|<\|im_end\|>|\[INST\]|\[/INST\]|</system>)",
    re.IGNORECASE,
)


def tag_untrusted(content: str, source: str) -> str:
    """Wrap *content* in ``<untrusted_content>`` delimiters."""
    return f'<untrusted_content source="{source}">\n{content}\n</untrusted_content>'


def quick_scan(text: str) -> list[str]:
    """Return a list of matched injection pattern names (pure regex, no LLM)."""
    found: list[str] = []
    for pattern, name in INJECTION_PATTERNS:
        if pattern.search(text):
            found.append(name)
    return found


def strip_role_markers(text: str) -> str:
    """Neutralize the most dangerous role-switching markers in *text*."""
    return _ROLE_SWITCH_RE.sub("[REDACTED_ROLE_MARKER]", text)
