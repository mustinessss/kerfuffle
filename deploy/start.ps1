$ErrorActionPreference = "Stop"

$deployDirectory = $PSScriptRoot
$repositoryRoot = (Resolve-Path (Join-Path $deployDirectory "..")).Path
$environmentFile = Join-Path $deployDirectory ".env"
$exampleFile = Join-Path $deployDirectory ".env.example"
$composeFile = Join-Path $deployDirectory "compose.yaml"

function New-RandomHexSecret {
    param([int]$ByteCount = 32)

    $bytes = New-Object byte[] $ByteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $generator.GetBytes($bytes)
    }
    finally {
        $generator.Dispose()
    }
    return ([BitConverter]::ToString($bytes)).Replace("-", "")
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop is required. Install and start Docker Desktop, then rerun this script."
}

if (-not (Test-Path $environmentFile)) {
    $content = [System.IO.File]::ReadAllText($exampleFile)
    $content = $content.Replace(
        "POSTGRES_PASSWORD=generate-on-first-start",
        "POSTGRES_PASSWORD=$(New-RandomHexSecret)"
    )
    $content = $content.Replace(
        "APP_DB_PASSWORD=generate-on-first-start",
        "APP_DB_PASSWORD=$(New-RandomHexSecret)"
    )
    $content = $content.Replace(
        "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD=generate-on-first-start",
        "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD=$(New-RandomHexSecret)"
    )
    $content = $content.Replace(
        "ACCESS_CODE_HASH_SECRET=generate-on-first-start",
        "ACCESS_CODE_HASH_SECRET=$(New-RandomHexSecret)"
    )
    [System.IO.File]::WriteAllText(
        $environmentFile,
        $content,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Created deploy/.env with random local secrets."
}

$requiredSecrets = @(
    "POSTGRES_PASSWORD",
    "APP_DB_PASSWORD",
    "KEYCLOAK_BOOTSTRAP_ADMIN_PASSWORD",
    "ACCESS_CODE_HASH_SECRET"
)
$environmentContent = [System.IO.File]::ReadAllText($environmentFile)
foreach ($name in $requiredSecrets) {
    $pattern = "(?m)^$([regex]::Escape($name))=([A-Fa-f0-9]{64})\s*$"
    if ($environmentContent -notmatch $pattern) {
        throw "deploy/.env must contain a 64-character hexadecimal value for $name."
    }
}

Push-Location $repositoryRoot
try {
    & docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is installed but its engine is not running."
    }

    & docker compose --env-file $environmentFile -f $composeFile --project-directory $repositoryRoot up --build -d
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed. Inspect the error above, then check logs with: docker compose --env-file deploy/.env -f deploy/compose.yaml logs"
    }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Kerfuffle containers started."
Write-Host "Web app:   http://localhost:5173"
Write-Host "Keycloak:  http://localhost:8080"
Write-Host "Local credentials are stored in deploy/.env; do not share or package that file."
Write-Host "Stop without deleting data: docker compose --env-file deploy/.env -f deploy/compose.yaml down"
