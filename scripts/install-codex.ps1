param(
    [string]$Repository = "https://github.com/1622352030/lab-equipment-mcp.git",
    [string]$Revision = "main",
    [string]$ServerName = "lab-equipment"
)

$ErrorActionPreference = "Stop"

function Resolve-Executable {
    param([string[]]$Names)

    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    return $null
}

$codex = Resolve-Executable @("codex.cmd", "codex")
if (-not $codex) {
    throw "Codex CLI was not found. Install Codex and reopen PowerShell."
}

$uvx = Resolve-Executable @("uvx.exe", "uvx")
if (-not $uvx) {
    throw "uvx was not found. Install uv from https://docs.astral.sh/uv/ and reopen PowerShell."
}

$source = "git+$Repository@$Revision"

& $codex mcp get $ServerName *> $null
if ($LASTEXITCODE -eq 0) {
    & $codex mcp remove $ServerName
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to remove the existing '$ServerName' MCP configuration."
    }
}

& $codex mcp add $ServerName -- $uvx --from $source start-lab-equipment-mcp
if ($LASTEXITCODE -ne 0) {
    throw "Codex could not register the '$ServerName' MCP server."
}

Write-Host ""
Write-Host "Installed Codex MCP server '$ServerName'." -ForegroundColor Green
Write-Host "Source: $source"
Write-Host "Restart Codex Desktop completely, then create a new task."
Write-Host "Test prompt: Call lab-equipment dpo2012b_diagnose_setup and report ready."
