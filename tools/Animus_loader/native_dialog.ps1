param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('folder', 'open')]
    [string]$Mode,

    [ValidateSet('all', 'mod', 'pack')]
    [string]$Kind = 'all',

    [string]$InitialDirectory = ''
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()

if (-not $InitialDirectory -or -not (Test-Path -LiteralPath $InitialDirectory -PathType Container)) {
    $InitialDirectory = [Environment]::GetFolderPath('MyComputer')
}

if ($Mode -eq 'folder') {
    $dialog = [System.Windows.Forms.FolderBrowserDialog]::new()
    $dialog.Description = 'Select the Assassin''s Creed Black Flag Resynced game folder'
    $dialog.ShowNewFolderButton = $false
    if ($InitialDirectory) {
        $dialog.SelectedPath = $InitialDirectory
    }
} else {
    $dialog = [System.Windows.Forms.OpenFileDialog]::new()
    $dialog.Multiselect = $false
    $dialog.InitialDirectory = $InitialDirectory
    $dialog.RestoreDirectory = $true
    if ($Kind -eq 'mod') {
        $dialog.Title = 'Select an Animus or Nexus mod archive'
        $dialog.Filter = 'Supported mod archives (*.jmod;*.zip)|*.jmod;*.zip|Animus Package (*.jmod)|*.jmod|Nexus ZIP Archive (*.zip)|*.zip|All files (*.*)|*.*'
    } elseif ($Kind -eq 'pack') {
        $dialog.Title = 'Select an outfit, weapon, or crew texture pack'
        $dialog.Filter = 'Supported packs (*.zip;*.7z;*.rar;*.tar;*.tgz;*.dds;*.png)|*.zip;*.7z;*.rar;*.tar;*.tgz;*.dds;*.png|Archive packs (*.zip;*.7z;*.rar)|*.zip;*.7z;*.rar|All files (*.*)|*.*'
    } else {
        $dialog.Filter = 'All files (*.*)|*.*'
    }
}

$owner = [System.Windows.Forms.Form]::new()
$owner.ShowInTaskbar = $false
$owner.TopMost = $true
$owner.Opacity = 0
$owner.Width = 1
$owner.Height = 1
$owner.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen

try {
    $owner.Show()
    $owner.Activate()
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        $selected = if ($Mode -eq 'folder') { $dialog.SelectedPath } else { $dialog.FileName }
        [Console]::Out.Write($selected)
    }
} finally {
    $dialog.Dispose()
    $owner.Close()
    $owner.Dispose()
}
