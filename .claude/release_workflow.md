# Release Workflow

## How to cut a release

### 1. Bump the version

Edit `pyproject.toml`:

```toml
[project]
version = "0.2.8"
```

### 2. Commit and push

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.2.8"
git push origin main
```

### 3. Tag and push

```bash
git tag v0.2.8
git push origin v0.2.8
```

That's it. The rest is automated.

---

## What happens automatically

The `.github/workflows/release.yml` workflow triggers on every `v*` tag push and runs four steps:

| Step | What it does |
|---|---|
| **Build** | `uv build` — produces `dist/*.whl` and `dist/*.tar.gz` |
| **GitHub Release** | Creates a GitHub Release named after the tag, attaches the dist artifacts, and auto-generates release notes from commits since the previous tag |
| **PyPI publish** | `uv publish` — pushes to PyPI via OIDC trusted publishing (no token stored in secrets) |

---

## Prerequisites (one-time setup)

PyPI trusted publishing must be configured once in your PyPI project settings:

1. Go to [https://pypi.org/manage/project/mykg/settings/publishing/](https://pypi.org/manage/project/mykg/settings/publishing/)
2. Add a new trusted publisher with these values:

| Field | Value |
|---|---|
| Owner | `SenolIsci` |
| Repository | `mykg` |
| Workflow | `release.yml` |
| Environment | `pypi` |

Once configured, no API tokens are needed — GitHub's OIDC identity is used directly.

---

## Verify the release

After pushing the tag:

- **GitHub Actions**: [https://github.com/SenolIsci/mykg/actions](https://github.com/SenolIsci/mykg/actions)
- **GitHub Releases**: [https://github.com/SenolIsci/mykg/releases](https://github.com/SenolIsci/mykg/releases)
- **PyPI**: [https://pypi.org/project/mykg/](https://pypi.org/project/mykg/)
