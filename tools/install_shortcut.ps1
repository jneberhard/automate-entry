$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$applicationPath = Join-Path $projectDirectory 'dist\Royalty Entry\Royalty Entry.exe'
if (-not (Test-Path -LiteralPath $applicationPath -PathType Leaf)) {
    throw 'Build the desktop application before creating its shortcut.'
}
$applicationPath = (Resolve-Path -LiteralPath $applicationPath).Path
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
if (-not (Test-Path -LiteralPath $desktopDirectory -PathType Container)) {
    throw 'The Windows desktop directory could not be located.'
}
$shortcutPath = Join-Path $desktopDirectory 'Royalty Entry.lnk'
$shellObject = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $shortcutPath) {
    $existingShortcut = $shellObject.CreateShortcut($shortcutPath)
    if ($existingShortcut.TargetPath -ne $applicationPath) {
        throw 'A Royalty Entry shortcut already points to another application; it was left unchanged.'
    }
}
$shortcutObject = $shellObject.CreateShortcut($shortcutPath)
$shortcutObject.TargetPath = $applicationPath
$shortcutObject.WorkingDirectory = Split-Path -Parent $applicationPath
$shortcutObject.IconLocation = "$applicationPath,0"
$shortcutObject.Description = 'Royalty Entry - Excel and License Manager automation'
$shortcutObject.Save()
Write-Output "Desktop shortcut created: $shortcutPath"
