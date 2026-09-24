# This replaces the old ASI staging action. A blocked check never installs files.
function Invoke-NativeInstallDesign {
    Invoke-WorkflowAction {
        if (-not $script:currentProject) {throw 'Create or open a design first.'}
        if (-not $script:gameFolder) {throw 'Select the installed Resynced game folder first.'}
        if (Get-Process -Name 'ACBlackFlag','ACBlackFlag_Plus' -ErrorAction SilentlyContinue) {
            throw 'Close the game before installing a design.'
        }
        Save-NativeDesign
        Set-DesignProgress 'Checking installation...' 15 'Checking the design and Resynced build.'
        Invoke-UiRefresh
        try {
            $backend=Join-Path $appRoot 'tools\anvil_install.py'
            $resultText=& python $backend install --design $script:currentProject --game $script:gameFolder 2>&1
            $exitCode=$LASTEXITCODE
            $result=($resultText -join "`n") | ConvertFrom-Json
            if ($result.status -ne 'installed' -or $exitCode -ne 0) {
                $reason=@($result.reasons) -join "`n`n"
                Set-DesignProgress 'Installation not ready.' 0 'Your design remains saved in Workshop.'
                Set-UiText $footer 'Installation not performed. See the remaining requirements.'
                [Windows.MessageBox]::Show($reason,'Design installation') | Out-Null
                return
            }
            Set-DesignProgress 'Design installed.' 100 'The verified patch files are installed.'
            Set-UiText $footer 'Design installed. Select the Workshop cosmetic in the game.'
        } catch {
            Set-DesignProgress 'Installation stopped.' 0 'Check the error before trying again.'
            throw
        }
    }
}

$installControl=$window.FindName('InjectDesign')
$installControl.IsEnabled=$true
$installControl.ToolTip='Check and install this saved design using an Anvil patch. Requires verified support for your game build.'
if ($installControl.Content -is [Windows.Controls.StackPanel]) {
    $installControl.Content.Children[$installControl.Content.Children.Count-1].Text='Install design'
}
if ($rollbackInjection) {
    $rollbackInjection.IsEnabled=$false
    $rollbackInjection.Header='Uninstall design (not available yet)'
    $rollbackInjection.ToolTip='No verified Anvil installation has been made yet.'
}
