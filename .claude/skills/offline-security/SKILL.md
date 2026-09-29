---
name: offline-security
description: Mandatory offline and security rules for this repository. The tool runs on locked-down machines - nothing may be sent to the internet, no program may be started, and everything must work locally. Use for ANY change, review or new feature in Legends.panel or PlaceResource, any new dependency or import, any file read/write, any dialog or logging change, and whenever looking up documentation or reference material for this project.
---

# Offline and security rules

The tool runs on machines with tight security. These rules override convenience, other skills and repo habits. If a request can only be met by breaking one, stop and say so. Don't look for a workaround.

## Rules for the tool's code (`Legends.panel`, `PlaceResource/lib`, `PlaceResource/config`)

1. **No network.** Nothing may open a connection:
   - Python: `socket`, `ssl`, `http`, `urllib*`, `requests`, `httpx`, `aiohttp`, `ftplib`, `smtplib`, `xmlrpc`, `websocket*`, `asyncio`
   - .NET: `System.Net.*`, `WebClient`, `HttpClient`, `WebRequest`, `TcpClient`
2. **No URLs in deployed files.** That covers Python strings, JSON (including `$schema` / `$id`, which some editors fetch), YAML and text files. URLs in comments are allowed, as are README links in the repo root.
3. **No network paths.** No UNC paths (`\\server\share`) and no mapped-drive assumptions. Files live under `PlaceResource` or the user's own Documents/OneDrive folder, which syncs through the company client and not through this tool.
4. **No starting programs or scripts.** No `subprocess`, `os.system`, `os.popen`, `os.startfile`, `os.exec*`, `os.spawn*`, `System.Diagnostics.Process`, `webbrowser` or `multiprocessing`. To "open" a file, show its path.
5. **No dynamic code.** No `eval`, `exec`, `__import__`, `compile` on strings, and no loading code from files outside `PlaceResource/lib`.
6. **No new dependencies.** Only the Python standard library, pyRevit (`pyrevit.revit`, `pyrevit.script`, `pyrevit.DB`), the Revit API and .NET `System` / `System.Windows.Forms` / `System.Drawing`. No `pip`, no vendored packages, no downloads at runtime or install time.
7. **No telemetry or reporting out.** Logs go to the pyRevit output window and logger only. No crash reporting, analytics, "check for updates" or version pings.
8. **Local writes only, in known places:**
   - `PlaceResource/config/user_settings_path.txt`
   - `PlaceResource/config/registries/*.json`
   - the settings file the user picks
   - Extensible Storage inside the Revit model

   Nothing else is written. Nothing goes to temp folders, the registry or environment variables.
9. **No secrets.** No passwords, tokens, keys, user names or machine names in code, config or reports. Element ids and view/sheet names are fine.
10. **No ctypes / winreg / native calls**, and no changes to system settings.

## Check before every commit

Run the local checker from the repo root:

```bash
python .claude/skills/offline-security/scripts/check_offline.py
```

It scans the deployed folders for rules 1 to 6 and 10, and exits 1 on any finding. The unit test `PlaceResource/tests/test_offline.py` runs the same scan, so `python -m unittest discover -s tests` from `PlaceResource` fails too. Rules 7 to 9 need a manual read of the diff.

Never weaken the checker or skip its test to get a change through. If a finding is a false positive, rewrite the code so it doesn't match.

## Rules for Claude while working on this repo

- **Don't use the internet for this project.** No `WebFetch`, `WebSearch`, `curl`, `wget`, `pip install`, `npm install` or package downloads.
- **Don't paste project code, model data or file paths into any external service.**
- **API questions:** use the local references in `.claude/skills/revit-api/` and `.claude/skills/pyrevit/`. If something isn't there, mark it **(verify)** and ask the user to check the local Revit SDK help (`RevitAPI.chm` from the Revit SDK), rather than looking it up online.
- **Don't add CI, webhooks, auto-update or anything that calls out,** even for development.
- **Be honest about the session:** the Claude Code session itself runs in Anthropic's cloud and uses GitHub for the repo. These rules govern the tool and Claude's actions, not the hosting of the session. If the user needs fully local development, say that it requires Claude Code running on their own machine, under their company's policy.

## Review checklist

- [ ] `check_offline.py` passes
- [ ] No new import outside the allowed list (rule 6)
- [ ] No new file write outside the list in rule 8
- [ ] No URL, UNC path, secret or user/machine name added
- [ ] Nothing starts a process, opens a browser or sends a report
- [ ] Docs and messages don't tell the user to download anything
