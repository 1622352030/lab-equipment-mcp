# Contribution Workflow

## External Contributor

1. Fork `https://github.com/1622352030/lab-equipment-mcp` to the contributor's account.
2. Clone the fork:

```powershell
git clone https://github.com/<account>/lab-equipment-mcp.git
cd lab-equipment-mcp
git remote add upstream https://github.com/1622352030/lab-equipment-mcp.git
```

3. Synchronize and branch:

```powershell
git fetch upstream
git switch main
git pull --ff-only upstream main
git switch -c feat/<vendor>-<model>
```

4. Develop and test on the feature branch.
5. Push to the fork:

```powershell
git push -u origin feat/<vendor>-<model>
```

6. Open a pull request from the fork branch to `1622352030/lab-equipment-mcp:main`.

## Repository Owner or Authorized Collaborator

Create a feature branch in the owner repository. Do not edit or push directly to `main`:

```powershell
git switch main
git pull --ff-only
git switch -c feat/<vendor>-<model>
```

Push the branch and open a pull request unless the user explicitly authorizes a direct merge.

## Commit Scope

- Keep transport refactors separate from device feature commits when practical.
- Do not commit `.venv`, caches, build artifacts, waveform captures, manuals, credentials, or
  device serial numbers.
- Use concise commit messages such as `feat: add Keysight model LAN driver` or
  `test: cover RS-232 session settings`.
- Rebase or merge current upstream `main` before final acceptance and rerun the full suite.

## Contribution Report

State:

- Manuals and revisions used
- Interfaces implemented and interfaces tested on hardware
- Driver/runtime versions and verification date
- Test commands and results
- Safety restrictions
- Unsupported or unverified behavior

