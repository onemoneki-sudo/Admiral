# Contributing to Admiral

Thank you for helping. Admiral is small on purpose: it reads what Claude Code and git already write, builds one board,
and shows it in the status line and the sidebar. Changes that keep it that way are the easiest to take.

## Before you start

- **A bug**: open an issue with the bug template. If you can, show it on the demo fleet (`admiral demo`), so nothing of
  yours has to be shared.
- **A feature**: open an issue first and say what problem it solves for someone running many sessions. The roadmap in
  the README says where Admiral is going; ideas outside it are welcome too, and an issue is the cheapest place to
  settle whether one fits.

## Set up

```sh
git clone https://github.com/onemoneki-sudo/Admiral.git
cd Admiral
python3 -m unittest discover -s tests      # Python 3.11 or newer; the same run GitHub Actions does on Linux and macOS
claude plugin validate plugin              # if you touch the sidebar or the playbook
claude --plugin-dir plugin                 # a session with the sidebar loaded from your working tree
admiral demo                               # a made-up fleet of 54 sessions to try changes on (bin/admiral from the clone)
```

## What a change needs

- **Tests.** A change in behaviour comes with a test that fails without it. Tests use made-up sessions, names and
  repositories only.
- **Only the standard library.** Admiral runs on Python's standard library and the `gh` CLI. A change that needs a
  dependency should say why in its issue first.
- **Both languages.** Every word the board, status line or sidebar shows has an English and a Chinese form
  (`admiral/words.py`, and the plugin's text). Add both; if you cannot write one, say so in the PR and it will be filled.
- **The code around it.** Match the naming, comments and idiom of the file you change. A comment says why, not what.
- **A changelog line** under `Unreleased` in `CHANGELOG.md` for anything a user would notice.
- **A Claude Code version** in the PR when the change follows a change in Claude Code's internal files: they are not
  an API, and the next reader will want to know which release moved.

## Keep private things out

Admiral reads transcripts, session names, task notes, branch and PR titles: things that belong to someone's work. Never
put real ones in an issue, a PR, a test fixture or a screenshot. Replace them with invented names, or reproduce on
`admiral demo`. The bug template asks for board output; redact it first.

## Pull requests

One concern per PR. Say what changed and why, and how you checked it (the tests you ran, the demo fleet, a real
session). CI runs the tests on Linux and macOS; a PR is merged once it passes and has been reviewed.

## Security

Please do not open a public issue for a vulnerability: see [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contribution is licensed under the MIT License, as Admiral is.
