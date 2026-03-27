# Publishing to PyPI

This project publishes to PyPI through GitHub Actions using PyPI Trusted
Publishing with GitHub's OpenID Connect (OIDC) integration.

The release workflow is defined in `.github/workflows/pypi-publish.yml`.
It runs when a Git tag matching `v*` is pushed, for example `v0.1.2`.

## Release Checklist

1. Make sure the version in `pyproject.toml` is correct.

   This repository stores the version in both:

   - `[project].version`
   - `[tool.poetry].version`

   Update both fields to the new version before releasing.

2. Run the local release checks:

   ```bash
   poetry install --no-interaction
   ./scripts/format.sh --check
   poetry run pytest -v --tb=short
   poetry build
   ```

3. Commit and push the release-ready changes to `main`:

   ```bash
   git add .
   git commit -m "Release 0.1.2"
   git push origin main
   ```

4. Create and push the Git tag that triggers the PyPI publish workflow:

   ```bash
   git tag -a v0.1.2 -m "Release v0.1.2"
   git push origin v0.1.2
   ```

5. Watch the GitHub Actions run for `Publish to PyPI`.

   The workflow will:

   - run formatting checks
   - run the test suite
   - build the source distribution and wheel
   - publish the package to PyPI

6. Verify the published release on PyPI:

   - `https://pypi.org/project/jawafdehi-mcp/`

## Trusted Publishing Notes

This repository is configured to publish without storing a long-lived PyPI
token in GitHub secrets.

Instead, GitHub Actions requests a short-lived identity token and PyPI trusts
that identity for this specific project. This is the recommended PyPI setup for
GitHub-hosted releases.

If publishing fails at the final PyPI upload step, check these first:

- the GitHub workflow is running from the expected repository
- the tag name matches `v*`
- the PyPI project has this GitHub repository configured as a Trusted Publisher
- the GitHub Actions job still has `id-token: write` permission

PyPI documentation:

- `https://docs.pypi.org/trusted-publishers/using-a-publisher/`

