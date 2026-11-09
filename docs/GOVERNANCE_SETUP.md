# Code Governance Setup for Ai-Vacuwise

These tools run on the laptop server (`~/ai-vacuwise`) and on GitHub. None of them run while the system is serving evacuees, so they do not affect the prototype's performance.

## What each file does

| File | Purpose |
| --- | --- |
| `CLAUDE.md` | Rules Claude reads before editing the repo: structure, security, testing |
| `ruff.toml` | Lint, security (bandit rules), and formatting settings |
| `.pre-commit-config.yaml` | Blocks a commit if it has secrets, lint errors, or failing tests |
| `.github/workflows/ci.yml` | Runs the same checks on GitHub after every push |
| `requirements-dev.txt` | The development tools: ruff, pre-commit, pip-audit, alembic |
| `docs/REFACTOR_PLAN.md` | Step-by-step plan to split `main.py` into routers |

## Compatibility and resource impact

| Tool | Compatibility with the laptop | RAM while running | Disk |
| --- | --- | --- | --- |
| ruff | Fully Compatible | under 50 MB, for a few seconds | about 30 MB |
| pre-commit + gitleaks | Fully Compatible | under 150 MB, only during `git commit` | about 100 MB of cached hooks |
| pip-audit | Fully Compatible (needs internet to check advisories) | under 100 MB | about 20 MB |
| alembic | Fully Compatible | under 50 MB, only when migrating | under 5 MB |
| GitHub Actions | Runs on GitHub's servers | none on the laptop | none |

All are free and open source and suitable for an 8 GB RAM laptop.

## Installation

1. Copy the files into the repo. From the folder where you extracted the zip:
   ```bash
   cp -r bilislikas2.0/. ~/ai-vacuwise/
   cd ~/ai-vacuwise
   ```
2. Activate the virtual environment (the prompt must show `(venv)`):
   ```bash
   source venv/bin/activate
   ```
3. Install the tools:
   ```bash
   pip install -r requirements-dev.txt
   ```
4. Make sure the backend dependencies are listed, so GitHub can install them:
   ```bash
   ls requirements.txt || pip freeze > requirements.txt
   ```
   If you create it this way, open it and remove lines you do not need on the server (for example `face_recognition` or `dlib` if they were only for the Pi).
5. Turn on the commit checks and update the hooks to their newest versions:
   ```bash
   pre-commit install
   pre-commit autoupdate
   ```
6. Run everything once on the whole codebase:
   ```bash
   ruff check . --fix
   ruff format .
   ruff check .
   pytest -q
   ```
   The first `ruff check .` may list many issues in older code. Fix real problems (unused imports, undefined names, security warnings). For a warning that is a deliberate choice, add `# noqa: <code>` on that line with a short reason.
7. Scan for secrets already in the history:
   ```bash
   pre-commit run gitleaks --all-files
   ```
   If it finds anything, rotate that secret (database password, JWT secret, SYNC_KEY, Gmail App Password). Removing it from the files is not enough, because it stays in old commits.
8. Commit the governance files and the formatting changes separately:
   ```bash
   git add CLAUDE.md ruff.toml .pre-commit-config.yaml .github requirements-dev.txt requirements.txt docs
   git commit -m "Add code governance: CLAUDE.md, ruff, pre-commit, CI"
   git add -A && git status
   git commit -m "Format codebase with ruff"
   git push
   ```
9. On GitHub, open the repository, go to **Settings > Code security**, and turn on **Dependabot alerts** and **Secret scanning** (if available for private repositories on your plan).

## Verification

1. `pre-commit run --all-files` shows every hook as Passed.
2. On GitHub, the **Actions** tab shows a green check for your last push.
3. Test the secret blocker: run `printf 'api_key = "sk_live_%s"\n' "$(openssl rand -hex 12)" > leak_test.py && git add leak_test.py && git commit -m test`, confirm gitleaks blocks it, then clean up with `git restore --staged leak_test.py && rm leak_test.py`.

## Common mistakes and troubleshooting

| Problem | Cause | Fix |
| --- | --- | --- |
| `externally-managed-environment` | venv not active | `source venv/bin/activate` |
| pytest hook fails with "venv/bin/pytest not found" | Committing from another folder or venv missing | Commit from `~/ai-vacuwise` |
| Commit is very slow the first time | pre-commit is downloading hooks | Normal, only happens once |
| CI fails at import with a missing setting | Dummy variable names in `ci.yml` differ from your `.env` names | Edit the `env:` block in `ci.yml` to use your real variable names (dummy values only) |
| CI fails with `ModuleNotFoundError` | Package missing from `requirements.txt` | Add it, commit, push |
| You need to commit urgently and a hook is failing | | `git commit --no-verify`, then fix it in the next commit. Use rarely |

## What comes next

1. Follow `docs/REFACTOR_PLAN.md` on a branch, one router per commit.
2. Set up Alembic (Step 4 of the plan) before the next schema change, such as adding coordinates to evacuation centers.
3. Every few features, ask Claude in a fresh session to review a router for security issues and duplicated logic.
4. For the defense, these tools are evidence for the ISO/IEC 25010 Maintainability (modularity, analyzability, testability) and Security characteristics.
