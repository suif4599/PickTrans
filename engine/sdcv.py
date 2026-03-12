

from __future__ import annotations

import re
from html import escape

from .engine import TranslationEngine


class SDCVEngine(TranslationEngine):
    def __init__(
        self,
        executable: str,
        path: str,
        prompt: str,
        timeout: int,
        errorprompt: str | None = None,
    ) -> None:
        import pexpect
        self.child = pexpect.spawn(f'{executable} -2 {path}', encoding='utf-8', timeout=timeout)
        self.executable = executable
        self.prompt = prompt
        self.errorprompt = (errorprompt or "").strip()
        self.child.expect(self.prompt)

    @staticmethod
    def _to_display_html(raw_body: str) -> str:
        """Render dictionary body as HTML; fallback to escaped preformatted text."""
        body = raw_body.strip()
        if not body:
            return "<div style='color:#666'>No definition</div>"

        # Most StarDict entries already contain HTML. Remove external CSS links.
        cleaned = re.sub(r"<link\\b[^>]*>", "", body, flags=re.IGNORECASE)
        if re.search(r"</?[a-zA-Z][^>]*>", cleaned):
            return cleaned

        escaped = escape(cleaned).replace("\n", "<br>")
        return f"<div style='white-space:normal;line-height:1.45'>{escaped}</div>"

    @staticmethod
    def _parse_entries(output: str, query: str) -> tuple[str, list[tuple[str, str, str]]]:
        """Split sdcv output into optional header and dictionary entries."""
        normalized = output.replace("\r\n", "\n").replace("\r", "\n")
        lines = normalized.split("\n")

        # Drop echoed command if terminal echo is enabled.
        while lines and not lines[0].strip():
            lines.pop(0)
        if lines and lines[0].strip() == query.strip():
            lines.pop(0)

        entries: list[tuple[str, str, str]] = []
        preface_lines: list[str] = []
        i = 0
        n = len(lines)

        while i < n:
            if lines[i].startswith("-->") and i + 1 < n and lines[i + 1].startswith("-->"):
                dict_name = lines[i][3:].strip()
                headword = lines[i + 1][3:].strip()
                i += 2

                while i < n and not lines[i].strip():
                    i += 1

                body_lines: list[str] = []
                while i < n:
                    is_next_entry = (
                        lines[i].startswith("-->")
                        and i + 1 < n
                        and lines[i + 1].startswith("-->")
                    )
                    if is_next_entry:
                        break
                    body_lines.append(lines[i])
                    i += 1

                entries.append((dict_name, headword, "\n".join(body_lines).strip()))
                continue

            if not entries:
                preface_lines.append(lines[i])
            i += 1

        return "\n".join(preface_lines).strip(), entries

    def __str__(self) -> str:
        return f"SDCV({self.executable})"
    
    def translate(self, input_text: str) -> str:
        import pexpect
        input_text = input_text.strip()
        if not input_text:
            return "<div style='color:#b00020'>Empty input</div>"
        if input_text.count(" ") > 4:
            raise ValueError("Not a word or short phrase.")
        self.child.sendline(input_text)
        index = self.child.expect([self.prompt, pexpect.EOF, pexpect.TIMEOUT])
        if index == 0:
            output = self.child.before
            if not isinstance(output, str):
                raise RuntimeError("Unexpected non-string output from sdcv process.")

            if self.errorprompt and self.errorprompt in output:
                raise RuntimeError(f"SDCV lookup failed: matched error prompt '{self.errorprompt}'")

            preface, entries = self._parse_entries(output, input_text)

            if entries:
                blocks: list[str] = []
                for dict_name, headword, raw_body in entries:
                    blocks.append(
                        "<section style='margin-bottom:14px'>"
                        f"<div style='font-weight:600'>{escape(dict_name)}</div>"
                        f"<div style='color:#666;margin-bottom:6px'>{escape(headword)}</div>"
                        f"{self._to_display_html(raw_body)}"
                        "</section>"
                    )
                return "".join(blocks)

            fallback = preface.strip() or output.strip()
            return (
                "<div style='color:#444'>"
                f"{escape(fallback).replace(chr(10), '<br>')}"
                "</div>"
            )
        raise RuntimeError("SDCV lookup failed: no prompt detected")
