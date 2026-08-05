param(
    [Parameter(Mandatory = $true)]
    [string]$Root,
    [Parameter(Mandatory = $true)]
    [string]$Output,
    [string]$DatabaseService = "postgres",
    [string]$DatabaseUser = "court4",
    [string]$DatabaseName = "court4"
)

$ErrorActionPreference = "Stop"
$resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
function Get-Court4RelativePath([string]$Base, [string]$Path) {
    return $Path.Substring($Base.Length).TrimStart('\', '/').Replace("\", "/")
}
$query = @"
SELECT aa.analysis_id,
       aa.storage_key,
       aa.size_bytes,
       aa.checksum_sha256,
       aa.state,
       CASE WHEN a.owner_user_id = aa.owner_user_id THEN '1' ELSE '0' END
FROM analysis_artifacts aa
JOIN analyses a ON a.id = aa.analysis_id
WHERE aa.storage_provider = 'local'
ORDER BY aa.analysis_id, aa.storage_key;
"@
$rows = @(docker compose exec -T $DatabaseService psql -U $DatabaseUser -d $DatabaseName -A -t -F "`t" -c $query)
if ($LASTEXITCODE -ne 0) {
    throw "Storage reconciliation could not read PostgreSQL metadata."
}

$missing = [System.Collections.Generic.List[string]]::new()
$orphans = [System.Collections.Generic.List[string]]::new()
$checksums = [System.Collections.Generic.List[string]]::new()
$sizes = [System.Collections.Generic.List[string]]::new()
$unavailable = [System.Collections.Generic.List[string]]::new()
$invalid = [System.Collections.Generic.List[string]]::new()
$crossOwner = [System.Collections.Generic.List[string]]::new()
$keys = [System.Collections.Generic.List[string]]::new()
$expectedFiles = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
$databaseBytes = [long]0
$matched = 0

foreach ($row in $rows) {
    if ([string]::IsNullOrWhiteSpace($row)) { continue }
    $parts = $row -split "`t", 6
    if ($parts.Count -ne 6) { throw "Storage reconciliation received an invalid metadata row." }
    $analysisId, $storageKey, $sizeText, $expectedHash, $state, $ownerMatches = $parts
    $reference = "$analysisId/$storageKey"
    $keys.Add($reference)
    $databaseBytes += [long]$sizeText
    if ($ownerMatches -ne "1") { $crossOwner.Add($reference) }
    $normalizedKey = $storageKey.Replace("\", "/")
    $unsafe = [System.IO.Path]::IsPathRooted($storageKey) -or
        [string]::IsNullOrWhiteSpace($storageKey) -or
        (($normalizedKey -split "/") -contains "..") -or
        $analysisId.Contains("/") -or $analysisId.Contains("\")
    if ($unsafe) {
        $invalid.Add($reference)
        continue
    }
    $path = Join-Path (Join-Path $resolvedRoot $analysisId) ($normalizedKey.Replace("/", [System.IO.Path]::DirectorySeparatorChar))
    $resolvedParent = [System.IO.Path]::GetFullPath($path)
    if (-not $resolvedParent.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        $invalid.Add($reference)
        continue
    }
    $relative = Get-Court4RelativePath $resolvedRoot $resolvedParent
    [void]$expectedFiles.Add($relative)
    if (-not (Test-Path -LiteralPath $resolvedParent -PathType Leaf)) {
        $missing.Add($reference)
        if ($state -eq "available") { $unavailable.Add($reference) }
        continue
    }
    $item = Get-Item -LiteralPath $resolvedParent
    $mismatch = $false
    if ($item.Length -ne [long]$sizeText) {
        $sizes.Add($reference)
        $mismatch = $true
    }
    $actualHash = (Get-FileHash -LiteralPath $resolvedParent -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        $checksums.Add($reference)
        $mismatch = $true
    }
    if (-not $mismatch) { $matched += 1 }
}

$allFiles = @(Get-ChildItem -LiteralPath $resolvedRoot -Recurse -File)
$temporary = @($allFiles | Where-Object {
    (Get-Court4RelativePath $resolvedRoot $_.FullName).StartsWith("_uploads/")
} | ForEach-Object { Get-Court4RelativePath $resolvedRoot $_.FullName } | Sort-Object)
$legacy = @($allFiles | Where-Object Name -eq "job.json" | ForEach-Object {
    Get-Court4RelativePath $resolvedRoot $_.FullName
} | Sort-Object)
$excluded = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
foreach ($path in @($temporary) + @($legacy)) { [void]$excluded.Add($path) }
foreach ($file in $allFiles) {
    $relative = Get-Court4RelativePath $resolvedRoot $file.FullName
    if (-not $expectedFiles.Contains($relative) -and -not $excluded.Contains($relative) -and -not $relative.StartsWith("_quarantine/")) {
        $orphans.Add($relative)
    }
}
$duplicates = @($keys | Group-Object | Where-Object Count -gt 1 | Select-Object -ExpandProperty Name | Sort-Object)
$uploadRoot = Join-Path $resolvedRoot "_uploads"
$abandoned = if (Test-Path -LiteralPath $uploadRoot -PathType Container) {
    @(Get-ChildItem -LiteralPath $uploadRoot -Directory | ForEach-Object {
        Get-Court4RelativePath $resolvedRoot $_.FullName
    } | Sort-Object)
} else { @() }
$filesystemBytes = [long](($allFiles | Measure-Object Length -Sum).Sum)
$findingCount = $missing.Count + $orphans.Count + $duplicates.Count + $checksums.Count +
    $sizes.Count + $temporary.Count + $invalid.Count + $crossOwner.Count
$report = [ordered]@{
    scanned_database_records = $rows.Count
    scanned_files = $allFiles.Count
    matched_records = $matched
    missing_files = @($missing | Sort-Object)
    orphan_files = @($orphans | Sort-Object)
    duplicate_storage_keys = $duplicates
    checksum_mismatches = @($checksums | Sort-Object)
    size_mismatches = @($sizes | Sort-Object)
    unavailable_marked_available = @($unavailable | Sort-Object)
    temporary_files = $temporary
    abandoned_upload_directories = $abandoned
    legacy_files = $legacy
    invalid_relative_paths = @($invalid | Sort-Object)
    cross_owner_inconsistencies = @($crossOwner | Sort-Object)
    database_bytes = $databaseBytes
    filesystem_bytes = $filesystemBytes
    recommended_action = if ($findingCount -eq 0) {
        "No action required; retain the report with deployment evidence."
    } else {
        "Review every finding; reconcile or quarantine explicitly before any deletion."
    }
}
$outputParent = Split-Path -Parent $Output
if ($outputParent) { New-Item -ItemType Directory -Force -Path $outputParent | Out-Null }
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Output -Encoding utf8
