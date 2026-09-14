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
    [IO.File]::WriteAllText($Result+'.started', 'started', $utf8)
    [Console]::WriteLine('Cleanup helper started')
    $Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
    if ($Root -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\') -or $Root -eq [Environment]::GetFolderPath('UserProfile')) { throw 'Dedicated installation directory required' }
    Plain $Root
    [Console]::WriteLine('Installation path validated')
    # Hold one native handle while checking creation time and waiting. A lazy
    # Diagnostics.Process.StartTime query can become null as the parent exits.
    Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
public static class SemanticCleanupParent {
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern IntPtr OpenProcess(uint access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool GetProcessTimes(IntPtr process, out long created, out long exited, out long kernel, out long user);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll")]
    static extern bool CloseHandle(IntPtr handle);
    public static void Wait(int pid, string expectedCreated) {
        IntPtr handle = OpenProcess(0x00100000 | 0x1000, false, pid);
        if (handle == IntPtr.Zero) {
            int error = Marshal.GetLastWin32Error();
            if (error == 87) return; // PID no longer exists.
            throw new Win32Exception(error);
        }
        try {
            long created, exited, kernel, user;
            if (!GetProcessTimes(handle, out created, out exited, out kernel, out user))
                throw new Win32Exception(Marshal.GetLastWin32Error());
            if (((ulong)created).ToString("x16") != expectedCreated) return; // Reused PID.
            Console.WriteLine("Waiting for installer PID " + pid);
            uint result = WaitForSingleObject(handle, 120000);
            if (result == 258) throw new Exception("Installer process has not exited; no files removed");
            if (result != 0) throw new Win32Exception(Marshal.GetLastWin32Error());
        } finally { CloseHandle(handle); }
    }
}
'@
    [SemanticCleanupParent]::Wait($ParentPid, $ParentCreated)
    Plain (Join-Path $Root '.semantic-management.lock')
    [Console]::WriteLine('Acquiring installation lock')
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
    [Console]::WriteLine('Cleanup targets validated')
    # Remove only unchanged shortcuts belonging to this exact installation.
    $sha = [Security.Cryptography.SHA256]::Create()
    $id = ([BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($Root.TrimEnd('\'))))).Replace('-', '').ToLower().Substring(0,12)
    if ($state.PSObject.Properties['native_shortcuts']) {
        foreach ($record in $state.native_shortcuts.PSObject.Properties) {
            $path = $record.Name
            $parent = [IO.Path]::GetDirectoryName($path)
            $name = [IO.Path]::GetFileName($path)
            if ($parent -notin @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('DesktopDirectory')) -or $name -notin @("Semantic ($id).lnk", "Uninstall Semantic ($id).lnk")) { continue }
            Plain $path
            if ((Test-Path -LiteralPath $path -PathType Leaf) -and (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -eq $record.Value) { [IO.File]::Delete($path) }
        }
    }
    $key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Semantic-$id"
    if ((Test-Path $key) -and (Get-ItemProperty $key).InstallLocation -eq $Root) { Remove-Item $key -Recurse }
    foreach ($target in $targets) { RemoveTree $target }
    if (!$Purge) {
        $state.ready = $false
        $state.uninstalling = $false
        $state | Add-Member -NotePropertyName uninstalled_at -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
        $temporary = Join-Path $Root '.uninstall-state.json'
        [IO.File]::WriteAllText($temporary, ($state | ConvertTo-Json -Depth 30), $utf8)
        # Windows PowerShell 5.1 binds $null to an empty string for this overload.
        $backup = Join-Path $Root ('.uninstall-state-'+$Nonce+'.bak')
        Plain $backup
        [IO.File]::Replace($temporary, $statePath, $backup)
        [IO.File]::Delete($backup)
    }
    $lock.Dispose(); $lock = $null
    if ($Purge) {
        [IO.File]::Delete((Join-Path $Root '.semantic-management.lock'))
        [IO.Directory]::Delete($Root, $false)
    }
    [IO.File]::WriteAllText($Result, (@{success=$true; purge=[bool]$Purge; root=$Root} | ConvertTo-Json), $utf8)
} catch {
    [IO.File]::WriteAllText($Result, (@{success=$false; error=$_.Exception.Message; location=$_.InvocationInfo.PositionMessage; root=$Root} | ConvertTo-Json), $utf8)
    exit 1
} finally {
    if ($lock) { $lock.Dispose() }
}
