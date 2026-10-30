# Verifying releases

Each package file pykit releases carries a build provenance attestation: a
signed statement of which repository and workflow built it. Each GitHub Release
also attaches a [CycloneDX](https://cyclonedx.org/) SBOM listing the package's
locked third-party dependencies. This guide shows how to check a file's origin
and read the SBOM. Verification needs the [GitHub CLI](https://cli.github.com/)
(`gh`).

## Verify a PyPI file

Download the file without installing it, then verify it:

```bash
pip download rn-forge-commons==0.8.0 --no-deps -d dl
gh attestation verify dl/rn_forge_commons-0.8.0-py3-none-any.whl --repo rn-forge/pykit
```

A pass prints the repository, the workflow and the commit the file was built
from. PyPI also shows the PEP 740 provenance on each file's page.

## Verify a GitHub Release file

```bash
gh release download rn-forge-commons-v0.8.0 --repo rn-forge/pykit --dir dl
gh attestation verify dl/rn_forge_commons-0.8.0-py3-none-any.whl --repo rn-forge/pykit
```

## A modified file fails

Verification checks the file's digest against the attestation. Any change to the
file makes it fail, and `gh` exits non-zero:

```bash
echo x >> dl/rn_forge_commons-0.8.0-py3-none-any.whl
gh attestation verify dl/rn_forge_commons-0.8.0-py3-none-any.whl --repo rn-forge/pykit
```

## Read the SBOM

The release attaches `rn-forge-commons-0.8.0.cdx.json`, and it carries an
attestation too. List its components with `jq`:

```bash
gh release download rn-forge-commons-v0.8.0 --repo rn-forge/pykit --pattern '*.cdx.json' --dir dl
gh attestation verify dl/rn-forge-commons-0.8.0.cdx.json --repo rn-forge/pykit
jq -r '.components[] | "\(.name) \(.version)"' dl/rn-forge-commons-0.8.0.cdx.json
```

## What is not covered

A `git+…@<tag>` install builds from source, so it has no attested file to check,
and tags are not signed. Install from PyPI to get a verifiable file.
