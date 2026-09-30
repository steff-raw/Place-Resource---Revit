# -*- coding: utf-8 -*-
"""Scan the deployed tool for anything that could reach the internet or start a process.

Usage (from the repository root):
    python .claude/skills/offline-security/scripts/check_offline.py

Exit code 0 when clean, 1 when a finding is reported. Uses only the Python
standard library and never opens a network connection itself.
"""

import ast
import os
import re
import sys

# Folders that are copied to user machines. Tests and docs are not deployed.
SCAN_ROOTS = ("Legends.panel", os.path.join("PlaceResource", "lib"), os.path.join("PlaceResource", "config"))
TEXT_EXTENSIONS = (".py", ".json", ".yaml", ".yml", ".txt")

# Python modules that open connections, send mail, start processes or install code.
FORBIDDEN_MODULES = {
    "socket", "ssl", "http", "urllib", "urllib2", "urllib3", "requests", "httpx", "aiohttp",
    "ftplib", "smtplib", "poplib", "imaplib", "nntplib", "telnetlib", "xmlrpc", "socketserver",
    "webbrowser", "subprocess", "multiprocessing", "pty", "paramiko", "websocket", "websockets",
    "pip", "ensurepip", "asyncio", "ctypes", "winreg", "_winreg",
}

# .NET namespaces and calls with the same risk, reached through pythonnet / clr.
FORBIDDEN_TEXT = (
    (r"\bSystem\.Net\b", ".NET networking namespace"),
    (r"\bWebClient\b|\bHttpClient\b|\bWebRequest\b|\bTcpClient\b|\bUdpClient\b", ".NET network client"),
    (r"\bSystem\.Diagnostics\.Process\b|\bProcess\.Start\b", ".NET process start"),
    (r"\bos\.(system|popen|startfile|exec\w*|spawn\w*)\b", "process start through os"),
    (r"(?<![\w.])(eval|exec)\s*\(", "dynamic code execution"),
    (r"\b__import__\s*\(", "dynamic import"),
    (r"(?i)\b(https?|ftp|wss?)://", "URL"),
    (r"(?i)\\\\\\\\[A-Za-z0-9_.-]+\\\\", "UNC network path"),
)


def _python_findings(path, source):
    findings = []
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as ex:
        return ["{0}:{1}: could not parse ({2})".format(path, ex.lineno, ex.msg)]
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if root in FORBIDDEN_MODULES:
                findings.append("{0}:{1}: imports '{2}'".format(path, node.lineno, name))
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "AddReference":
            for argument in node.args:
                value = getattr(argument, "value", None)
                if isinstance(value, str) and (value.startswith("System.Net") or "Http" in value):
                    findings.append("{0}:{1}: clr.AddReference('{2}')".format(path, node.lineno, value))
    return findings


def _text_findings(path, source):
    findings = []
    for number, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        if path.endswith(".py") and stripped.startswith("#"):
            continue
        for pattern, reason in FORBIDDEN_TEXT:
            if re.search(pattern, line):
                findings.append("{0}:{1}: {2}: {3}".format(path, number, reason, stripped[:120]))
    return findings


def scan(repo_root):
    """Return a list of findings for the deployed folders under ``repo_root``."""
    findings = []
    for relative in SCAN_ROOTS:
        base = os.path.join(repo_root, relative)
        if not os.path.isdir(base):
            continue
        for folder, _dirs, files in os.walk(base):
            for name in sorted(files):
                if not name.lower().endswith(TEXT_EXTENSIONS):
                    continue
                path = os.path.join(folder, name)
                with open(path, "r", encoding="utf-8-sig", errors="replace") as handle:
                    source = handle.read()
                display = os.path.relpath(path, repo_root)
                if name.endswith(".py"):
                    findings.extend(_python_findings(display, source))
                findings.extend(_text_findings(display, source))
    return findings


def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    findings = scan(repo_root)
    if findings:
        print("Offline check FAILED. {0} finding(s):".format(len(findings)))
        for item in findings:
            print("  " + item)
        return 1
    print("Offline check passed: no network, process-start or dynamic-code use in {0}.".format(", ".join(SCAN_ROOTS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
