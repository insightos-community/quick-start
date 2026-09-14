param([Parameter(Mandatory=$true)][string]$Root, [Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
trap { [Console]::Error.WriteLine($_.ToString()+[Environment]::NewLine+$_.InvocationInfo.PositionMessage+[Environment]::NewLine+$_.ScriptStackTrace); exit 1 }
$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::OutputEncoding = $utf8
$Root = [IO.Path]::GetFullPath($Root).TrimEnd('\')
$sha = [Security.Cryptography.SHA256]::Create()
$id = ([BitConverter]::ToString($sha.ComputeHash($utf8.GetBytes($Root)))).Replace('-', '').ToLower().Substring(0,12)
$state = [IO.File]::ReadAllText((Join-Path $Root 'install.json'), $utf8) | ConvertFrom-Json
function Plain([string]$Path) {
    $item = $Path
    while ($item) {
        if ((Test-Path -LiteralPath $item) -and ((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "Shortcut path contains a reparse point: $item" }
        $item = [IO.Path]::GetDirectoryName($item)
    }
}
$release = Join-Path $Root "releases\$Version"
$icon = Join-Path $Root 'bin\Semantic.ico'
Plain $icon
Add-Type -AssemblyName System.Drawing
$image = [Drawing.Image]::FromFile((Join-Path $release 'assets\ios.png'))
$bitmap = New-Object Drawing.Bitmap(256,256)
$graphics = [Drawing.Graphics]::FromImage($bitmap)
$graphics.Clear([Drawing.Color]::White)
$graphics.InterpolationMode = [Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$height = [int](256*$image.Height/$image.Width)
$graphics.DrawImage($image, 0, [int]((256-$height)/2), 256, $height)
# PNG-compressed ICO supports full-size 256px icons without GDI handle conversion.
$png = New-Object IO.MemoryStream
$bitmap.Save($png, [Drawing.Imaging.ImageFormat]::Png)
$stream = [IO.File]::Create($icon)
$writer = New-Object IO.BinaryWriter($stream)
try {
    $writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]1)
    $writer.Write([byte[]]@(0,0,0,0)); $writer.Write([uint16]1); $writer.Write([uint16]32)
    $writer.Write([uint32]$png.Length); $writer.Write([uint32]22); $writer.Write($png.ToArray())
} finally { $writer.Dispose(); $png.Dispose(); $graphics.Dispose(); $bitmap.Dispose(); $image.Dispose() }
$shell = New-Object -ComObject WScript.Shell
$records = @{}
$programs = [Environment]::GetFolderPath('Programs')
$desktop = [Environment]::GetFolderPath('DesktopDirectory')
foreach ($directory in @($programs, $desktop)) {
    if (!$directory) { continue }
    try { Plain $directory } catch { continue }
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    foreach ($action in @('open', 'uninstall')) {
        $title = if ($action -eq 'open') { 'Semantic' } else { 'Uninstall Semantic' }
        $path = Join-Path $directory "$title ($id).lnk"
        try { Plain $path } catch { continue }
        if (Test-Path -LiteralPath $path) {
            $old = if ($state.PSObject.Properties['native_shortcuts']) { $state.native_shortcuts.PSObject.Properties[$path] } else { $null }
            if (!$old -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -ne $old.Value) { continue }
        }
        $link = $shell.CreateShortcut($path)
        $targetPath = [IO.Path]::Combine($release, 'python', 'python.exe')
        if (!(Test-Path -LiteralPath $targetPath -PathType Leaf)) { throw "Shortcut executable is missing: $targetPath" }
        $link.TargetPath = [string]$targetPath
        $link.Arguments = '-I -B "'+(Join-Path $release 'manager.py')+'" --dir "'+$Root+'" '+$action+' --interactive'
        $link.WorkingDirectory = [IO.Path]::GetTempPath()
        $link.IconLocation = "$icon,0"
        $link.Description = "$title - $Root"
        $link.Save()
        $records[$path] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower()
    }
}
$key = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Semantic-$id"
if ((Test-Path $key) -and (Get-ItemProperty $key).InstallLocation -ne $Root) { throw 'Foreign uninstall registration exists' }
New-Item $key -Force | Out-Null
$properties = @{DisplayName="Semantic ($id)"; DisplayVersion=$Version; Publisher='InsightOS'; InstallLocation=$Root; DisplayIcon=$icon;
  UninstallString='"'+(Join-Path $release 'python\python.exe')+'" -I -B "'+(Join-Path $release 'manager.py')+'" --dir "'+$Root+'" uninstall --interactive'}
$properties.GetEnumerator() | ForEach-Object { New-ItemProperty $key -Name $_.Key -Value $_.Value -PropertyType String -Force | Out-Null }
foreach ($name in @('NoModify','NoRepair')) { New-ItemProperty $key -Name $name -Value 1 -PropertyType DWord -Force | Out-Null }
@{native_shortcuts=$records; uninstall_registry=$key} | ConvertTo-Json -Depth 5 -Compress
