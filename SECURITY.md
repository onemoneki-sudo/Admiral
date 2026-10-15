# Security

## Supported versions

Security fixes go into the latest release. Update with `git -C ~/admiral pull`.

## Reporting a vulnerability

Please report it privately, not in a public issue: on this repository's **Security** tab, choose **Report a
vulnerability**. Include what an attacker could do, the steps to reproduce, and the Admiral (`admiral --version`) and
Claude Code (`claude --version`) versions. Leave out real transcripts, session names and repository names; invented ones
or the demo fleet (`admiral demo`) are enough.

You will get an answer within a week, best effort. Once a fix is released, the advisory is published with credit to you
unless you ask otherwise.

## What Admiral touches

Knowing this helps judge a report. Admiral runs locally as you. It reads Claude Code's files under `~/.claude`, `ps`
and `git` (read-only); it writes only its state directory, its config, the locks you take and, at install, its
background job, a link on your PATH and a note in the clone of which Python to use; it sends nothing but `gh` calls to GitHub, as you. It never edits Claude Code's
settings and never types into a session. The status line runs the `base` command from your own config, through the
shell, as your previous status line did.
