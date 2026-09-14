# Runs from the user's temporary directory after the installed Python exits.
param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Nonce,
    [Parameter(Mandatory=$true)][int]$ParentPid,
    [Parameter(Mandatory=$true)][string]$ParentCreated,
    [Parameter(Mandatory=$true)][string]$Result,
    [switch]$Purge
)
$ErrorActionPreference = 'Stop'
$utf8 = New-Object System.Text.UTF8Encoding($false)
$lock = $null
function Plain([string]$Path) {
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if (([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Reparse point: $current" }
        }
        $parent = [IO.Directory]::GetParent($current)
        $current = if ($parent) { $parent.FullName } else { $null }
    }
}
function CheckTree([string]$Path) {
    Plain $Path
    if ([IO.Directory]::Exists($Path)) {
        foreach ($child in [IO.Directory]::EnumerateFileSystemEntries($Path)) { CheckTree $child }
    }
}
function RemoveTree([string]$Path) {
    Plain $Path
    if ([IO.Directory]::Exists($Path)) {
        foreach ($child in [IO.Directory]::EnumerateFileSystemEntries($Path)) { RemoveTree $child }
        [IO.Directory]::Delete($Path, $false)
    } elseif ([IO.File]::Exists($Path)) {
        [IO.File]::SetAttributes($Path, [IO.FileAttributes]::Normal)
        [IO.File]::Delete($Path)
    }
}
try {
    $Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($Root -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\') -or $Root -eq [Environment]::GetFolderPath('UserProfile')) { throw 'Dedicated installation directory required' }
    Plain $Root
    $parent = $null
    try { $parent = [Diagnostics.Process]::GetProcessById($ParentPid) } catch [ArgumentException] {}
    if ($parent) {
        try {
            if ($parent.StartTime.ToUniversalTime().ToFileTimeUtc().ToString('x16') -eq $ParentCreated) {
                if (!$parent.WaitForExit(120000)) { throw 'Installer process has not exited; no files removed' }
            }
        } finally { $parent.Dispose() }
    }
    Plain (Join-Path $Root '.semantic-management.lock')
    $lock = [IO.File]::Open((Join-Path $Root '.semantic-management.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    if (!(Test-Path -LiteralPath (Join-Path $Root '.semantic-install-root') -PathType Leaf)) { throw 'Ownership marker missing' }
    $statePath = Join-Path $Root 'install.json'
    $state = [IO.File]::ReadAllText($statePath, $utf8) | ConvertFrom-Json
    if ($state.platform -ne 'windows-amd64' -or !$state.uninstalling -or $state.uninstall_nonce -ne $Nonce) { throw 'Uninstall authorization state changed' }
    $services = Join-Path $Root 'run/services.json'
    if (Test-Path -LiteralPath $services) {
        $records = [IO.File]::ReadAllText($services, $utf8) | ConvertFrom-Json
        if (@($records.PSObject.Properties).Count -ne 0) { throw 'Service ownership records are not empty' }
    }
    $targets = @('releases','python','runtime-envs','runtime-packs','bin') | ForEach-Object { Join-Path $Root $_ }
    if ($Purge) { $targets = @([IO.Directory]::EnumerateFileSystemEntries($Root) | Where-Object { [IO.Path]::GetFileName($_) -ne '.semantic-management.lock' }) }
    # Validate the whole selected tree before the first deletion.
    foreach ($target in $targets) { CheckTree $target }
    foreach ($target in $targets) { RemoveTree $target }
    if (!$Purge) {
        $state.ready = $false
        $state.uninstalling = $false
        $state | Add-Member -NotePropertyName uninstalled_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
        $temporary = Join-Path $Root '.uninstall-state.json'
        [IO.File]::WriteAllText($temporary, ($state | ConvertTo-Json -Depth 30), $utf8)
        [IO.File]::Replace($temporary, $statePath, $null)
    }
    $lock.Dispose(); $lock = $null
    if ($Purge) {
        [IO.File]::Delete((Join-Path $Root '.semantic-management.lock'))
        [IO.Directory]::Delete($Root, $false)
    }
    [IO.File]::WriteAllText($Result, (@{success=$true; purge=[bool]$Purge; root=$Root} | ConvertTo-Json), $utf8)
} catch {
    [IO.File]::WriteAllText($Result, (@{success=$false; error=$_.Exception.Message; root=$Root} | ConvertTo-Json), $utf8)
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
