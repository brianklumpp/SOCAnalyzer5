param(
    [Parameter(Mandatory=$true, Position=0)]
    [ValidateSet('start','stop','restart','status','down','rebuild','rebuild-nocache','rebuild-hard','logs','help')]
    [string]$Command
)

$ErrorActionPreference = 'Stop'

function Require-Docker() {
    $docker = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $docker) {
        Write-Error "Docker CLI not found. Please install Docker Desktop / Engine and ensure 'docker' is on PATH."
    }
    try {
        # Ensure daemon is reachable; this will throw if Docker Desktop/Engine is not running
        $null = & docker version --format '{{.Server.Version}}' 2>$null
    } catch {
        Write-Error "Docker daemon not running. Please start Docker Desktop/Engine and retry."
    }
}

function Compose-Exec([string[]]$ComposeArgs) {
    Push-Location $PSScriptRoot
    try {
        Write-Host ("Running: docker compose {0}" -f ($ComposeArgs -join ' ')) -ForegroundColor Cyan
        & docker compose @ComposeArgs
    } finally {
        Pop-Location
    }
}

function Show-Status() {
    $services = @('socanalyzer-frontend','socanalyzer-backend','socanalyzer-postgres','socanalyzer-redis')
    Write-Host ("{0,-24} {1,-20} {2}" -f "CONTAINER","STATUS","PORTS") -ForegroundColor Cyan
    foreach ($s in $services) {
        $line = & docker ps -a --filter "name=$s" --format "{{.Names}}|{{.Status}}|{{.Ports}}" | Select-Object -First 1
        if ([string]::IsNullOrWhiteSpace($line)) {
            Write-Host ("{0,-24} {1}" -f $s, "not found") -ForegroundColor DarkGray
            continue
        }
        $parts = $line -split '\|',3
        $name = $parts[0]
        $status = $parts[1]
        $ports = if ($parts.Count -ge 3) { $parts[2] } else { '' }
        # Color by running/exited
        if ($status -match 'Up') {
            Write-Host ("{0,-24} {1,-20} {2}" -f $name, $status, $ports) -ForegroundColor Green
        } elseif ($status -match 'Exited') {
            Write-Host ("{0,-24} {1,-20} {2}" -f $name, $status, $ports) -ForegroundColor Yellow
        } else {
            Write-Host ("{0,-24} {1,-20} {2}" -f $name, $status, $ports)
        }
    }
}

function Show-Help() {
    @"
SOCAnalyzer helper
Usage: .\socanalyzer.ps1 <command>

Commands:
    start    Start containers in background (no rebuild)
    stop     Stop running containers (do not remove)
    restart  Restart running containers (no rebuild)
    status   Show per-container status and port mappings
    rebuild  Rebuild images and start containers (build, then up -d)
    rebuild-nocache  Force full rebuild without cache (build --no-cache --pull; up -d)
    rebuild-hard     Down (remove orphans), full rebuild, then up -d
    logs     Tail backend and frontend logs
    down     Stop and remove containers (preserves volumes)
  help     Show this help

Notes:
- Frontend: http://localhost:3000 (container)
- Backend:  http://localhost:8000 (container)
- Requires Docker Compose v2 (docker compose ...)
"@ | Write-Host
}

try {
    switch ($Command) {
        'start'   { Require-Docker; Compose-Exec @('up','-d'); Show-Status }
        'stop'    { Require-Docker; Compose-Exec @('stop'); Show-Status }
        'restart' { Require-Docker; Compose-Exec @('restart'); Show-Status }
        'status'  { Require-Docker; Show-Status }
        'rebuild' { Require-Docker; Compose-Exec @('build'); Compose-Exec @('up','-d'); Show-Status }
        'rebuild-nocache' { Require-Docker; Compose-Exec @('build','--no-cache','--pull'); Compose-Exec @('up','-d'); Show-Status }
        'rebuild-hard' { Require-Docker; Compose-Exec @('down','--remove-orphans'); Compose-Exec @('build','--no-cache','--pull'); Compose-Exec @('up','-d'); Show-Status }
        'logs'    { Require-Docker; Compose-Exec @('logs','-f','--tail=200','backend','frontend') }
        'down'    { Require-Docker; Compose-Exec @('down'); Show-Status }
        'help'    { Show-Help }
        default   { Show-Help; exit 1 }
    }
} catch {
    Write-Error $_
    exit 1
}
