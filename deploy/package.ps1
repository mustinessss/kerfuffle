param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputPath) {
    $OutputPath = Join-Path $repositoryRoot "mustiness-kerfuffle-package.zip"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)
if (Test-Path $OutputPath) {
    throw "Package already exists: $OutputPath. Choose another OutputPath or move the existing file."
}

$temporaryRoot = Join-Path $env:TEMP ("mustiness-package-" + [guid]::NewGuid().ToString("N"))
$packageRoot = Join-Path $temporaryRoot "mustiness-kerfuffle"
$includedPaths = @(
    ".gitignore",
    "README.md",
    "PROJECT_STATUS.md",
    "backend",
    "database",
    "deploy",
    "frontend",
    "keycloak"
)
$excludedDirectories = @(
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    ".vite",
    "coverage",
    "dist",
    "node_modules",
    "venv"
)

try {
    New-Item -ItemType Directory -Path $packageRoot -Force | Out-Null
    foreach ($relativePath in $includedPaths) {
        $sourcePath = Join-Path $repositoryRoot $relativePath
        if (-not (Test-Path -LiteralPath $sourcePath)) {
            throw "Required package path is missing: $relativePath"
        }

        if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) {
            Copy-Item -LiteralPath $sourcePath -Destination $packageRoot
            continue
        }

        $sourceDirectory = (Resolve-Path -LiteralPath $sourcePath).Path
        Get-ChildItem -LiteralPath $sourceDirectory -File -Recurse -Force |
            Where-Object {
                $relativeFile = $_.FullName.Substring($sourceDirectory.Length).TrimStart("\")
                $segments = $relativeFile -split '[\\/]'
                $hasExcludedDirectory = @(
                    $segments | Where-Object { $excludedDirectories -contains $_ }
                ).Count -gt 0
                $isEnvironmentFile = $_.Name -eq ".env" -or (
                    $_.Name.StartsWith(".env.") -and $_.Name -ne ".env.example"
                )
                $isCacheFile = $_.Extension -in @(".pyc", ".pyo", ".log", ".sqlite", ".db") -or
                    $_.Name.EndsWith(".tsbuildinfo")
                -not $hasExcludedDirectory -and -not $isEnvironmentFile -and -not $isCacheFile
            } |
            ForEach-Object {
                $relativeFile = $_.FullName.Substring($sourceDirectory.Length).TrimStart("\")
                $destination = Join-Path (Join-Path $packageRoot $relativePath) $relativeFile
                $destinationDirectory = Split-Path -Parent $destination
                New-Item -ItemType Directory -Path $destinationDirectory -Force | Out-Null
                Copy-Item -LiteralPath $_.FullName -Destination $destination
            }
    }

    $outputDirectory = Split-Path -Parent $OutputPath
    if (-not (Test-Path $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
    }
    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::Open(
        $OutputPath,
        [System.IO.Compression.ZipArchiveMode]::Create
    )
    try {
        Get-ChildItem -LiteralPath $packageRoot -File -Recurse -Force |
            ForEach-Object {
                $relativeFile = $_.FullName.Substring($packageRoot.Length).TrimStart("\")
                $entryName = "mustiness-kerfuffle/" + $relativeFile.Replace("\", "/")
                $null = [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $archive,
                    $_.FullName,
                    $entryName,
                    [System.IO.Compression.CompressionLevel]::Optimal
                )
            }
    }
    finally {
        $archive.Dispose()
    }
    Write-Host "Created package: $OutputPath"
    Write-Host "Local .env files, virtual environments, node_modules, and build caches were excluded."
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
