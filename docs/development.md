# Development checks

Run `setup.ps1` to create the application environment first, then:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup-dev.ps1
```

The development setup installs `requirements-dev.txt`, runs `npm ci` against the
committed lockfile, and installs `.git/hooks/pre-commit`. Each checkout needs this
hook installation. It does not reinstall PyTorch. A compatible global Node can
be used; otherwise setup downloads pinned Node 24 LTS into ignored
`runtime/tools/node/` and verifies its SHA-256 checksum against the official release.
The local runtime does not change your system PATH. Node is only a linting tool;
the frontend still has no build step and the application runs entirely in Python.

| Files | Linter | Formatter | Configuration |
| --- | --- | --- | --- |
| Python source, maintenance scripts, tests | Ruff | Ruff | `pyproject.toml` |
| Browser JavaScript | ESLint recommended rules | Prettier | `eslint.config.mjs`, `.prettierrc.json` |
| CSS | Stylelint standard rules | Prettier | `stylelint.config.mjs`, `.prettierrc.json` |
| HTML | HTML-Validate recommended rules | Prettier | `.htmlvalidate.json`, `.prettierrc.json` |

The JavaScript configuration declares the shared globals supplied by the ordered
classic scripts. CSS IDs follow the existing camelCase DOM convention, while
classes use kebab-case. Descending-specificity checks are disabled for component
and responsive overrides. HTML void-tag and doctype styles match Prettier.

```powershell
.\lint.ps1
.\lint.ps1 -Fix
.\lint.ps1 -Tool Python
.\lint.ps1 -Tool JavaScript
.\lint.ps1 -Tool CSS
.\lint.ps1 -Tool HTML
.\.venv-system\Scripts\python.exe -m pre_commit run --all-files
```

The Git hook checks staged files and blocks a commit if a check fails. It uses the
same tools and settings as `lint.ps1`, without separate hook-managed dependencies.
Checks do not rewrite files during commits. `-Fix` enables safe Ruff/ESLint/Stylelint
fixes and formatting; HTML structure and non-fixable errors require manual edits.
Warnings also fail frontend lint checks. Generated files, environments, Node
packages, and model downloads are excluded. Desktop configuration values are not
changed by linting.

When intentionally upgrading frontend tool versions, edit `package.json`, run
`setup-dev.ps1 -UpdateLock`, then check and commit `package-lock.json` with the
configuration changes. Python lint-tool versions are pinned in both
`requirements-dev.txt` and the `dev` extra in `pyproject.toml`; keep them aligned.
Run the existing unit and integration checks listed in the README after changes
that affect behavior. Formatting alone should preserve behavior.

References: [Ruff](https://docs.astral.sh/ruff/integrations/),
[ESLint flat configuration](https://eslint.org/docs/latest/use/configure/configuration-files),
[Stylelint](https://stylelint.io/user-guide/get-started/),
[HTML-Validate](https://html-validate.org/usage/cli.html),
[Prettier](https://prettier.io/docs/install.html), and
[pre-commit](https://pre-commit.com/).
