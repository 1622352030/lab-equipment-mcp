<#
.SYNOPSIS
    Install this repository's Agent Skills into the local skill directories.

.DESCRIPTION
    install-codex.ps1 registers the MCP *server*; it does not install skills. A skill that
    lives in this repository therefore stays invisible to an Agent until its folder is copied
    into the directory that runtime scans. This script does that copy, for every Agent runtime
    present on the machine.

    A skill is any directory under skills\ that contains SKILL.md (the layout used by
    add-lab-equipment-device and operate-itech-it8813-load: SKILL.md + agents\ + references\).

    Targets:
      dsh     %APPDATA%\dsh-desktop\harness\skills
      codex   %USERPROFILE%\.codex\skills

    A destination that does not exist is reported and skipped - this script never creates an
    Agent runtime's directory tree for it.

    By default every skill is (re)installed, so the copies on disk always match the repository.
    Use -SkipExisting to leave already-installed skills untouched.

    -Uninstall requires an explicit -Skill list: removing every skill by default could delete a
    skill the user installed from somewhere else.

.PARAMETER Skill
    Names of skills under skills\ to act on. Defaults to all of them. Required with -Uninstall.

.PARAMETER Target
    Which local skill directory to act on: all (default), dsh, or codex.

.PARAMETER SkipExisting
    Do not overwrite a skill that is already installed in the destination.

.PARAMETER Uninstall
    Remove the named skills from the destination instead of installing them.

.EXAMPLE
    scripts\install-skills.ps1

.EXAMPLE
    scripts\install-skills.ps1 -Skill operate-itech-it8813-load

.EXAMPLE
    scripts\install-skills.ps1 -Uninstall -Skill operate-itech-it8813-load -Target codex
#>
param(
    [string[]]$Skill,
    [ValidateSet("all", "dsh", "codex")]
    [string]$Target = "all",
    [switch]$SkipExisting,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$skillsRoot = Join-Path $repoRoot "skills"

$targets = [ordered]@{
    dsh   = Join-Path $env:APPDATA "dsh-desktop\harness\skills"
    codex = Join-Path (Join-Path $env:USERPROFILE ".codex") "skills"
}
$destinations = if ($Target -eq "all") { @($targets.Values) } else { @($targets[$Target]) }

if (-not (Test-Path $skillsRoot)) {
    throw "Skills directory not found: $skillsRoot"
}
$available = @(
    Get-ChildItem $skillsRoot -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") }
)
if ($available.Count -eq 0) {
    throw "No skill found under $skillsRoot (a skill is a directory containing SKILL.md)."
}

if ($Skill) {
    $unknown = @($Skill | Where-Object { $_ -notin $available.Name })
    if ($unknown.Count -gt 0) {
        throw "Unknown skill(s): $($unknown -join ', '). Available: $($available.Name -join ', ')"
    }
    $chosen = @($available | Where-Object { $_.Name -in $Skill })
}
else {
    if ($Uninstall) {
        throw "-Uninstall requires -Skill <name>; refusing to remove every installed skill."
    }
    $chosen = $available
}

Write-Host ""
Write-Host "$(if ($Uninstall) { 'Uninstalling' } else { 'Installing' }) $($chosen.Count) skill(s): $($chosen.Name -join ', ')" -ForegroundColor Cyan
Write-Host ""

$results = foreach ($destination in $destinations) {
    $destinationExists = Test-Path $destination
    foreach ($item in $chosen) {
        $installedAt = Join-Path $destination $item.Name
        $alreadyThere = Test-Path $installedAt

        if (-not $destinationExists) {
            [pscustomobject]@{
                Skill       = $item.Name
                Destination = $destination
                Action      = "skipped (directory not present)"
            }
            continue
        }

        if ($Uninstall) {
            if ($alreadyThere) {
                Remove-Item $installedAt -Recurse -Force
                $action = "removed"
            }
            else {
                $action = "not installed"
            }
        }
        elseif ($alreadyThere -and $SkipExisting) {
            $action = "kept (already installed)"
        }
        else {
            if ($alreadyThere) {
                Remove-Item $installedAt -Recurse -Force
                $action = "updated"
            }
            else {
                $action = "installed"
            }
            Copy-Item $item.FullName $installedAt -Recurse -Force
        }

        [pscustomobject]@{
            Skill       = $item.Name
            Destination = $destination
            Action      = $action
        }
    }
}

# Emit the table as text, not as formatting objects: piping a script that ends in
# `Format-Table` into Select-Object or a redirection makes PowerShell fail with
# "FormatEntryData ... not in the correct sequence".
Write-Output (($results | Format-Table -AutoSize | Out-String -Width 200).TrimEnd())

$changed = @($results | Where-Object { $_.Action -in @("installed", "updated", "removed") })
Write-Host "$($changed.Count) change(s) applied." -ForegroundColor Green
if ($changed.Count -gt 0 -and -not $Uninstall) {
    Write-Host "Restart the Agent runtime (or open a new task) so it rescans its skills directory."
}
