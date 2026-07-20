param([string]$ServerName = "lab-equipment")

$ErrorActionPreference = "Stop"
$codex = Get-Command codex.cmd -ErrorAction SilentlyContinue
if (-not $codex) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
}
if (-not $codex) {
    throw "Codex CLI was not found."
}

& $codex.Source mcp remove $ServerName
if ($LASTEXITCODE -ne 0) {
    throw "Codex could not remove the '$ServerName' MCP server."
}

Write-Host "Removed Codex MCP server '$ServerName'." -ForegroundColor Green
