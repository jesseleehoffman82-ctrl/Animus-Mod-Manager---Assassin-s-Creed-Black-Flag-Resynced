# Existing named controls are moved in XAML, so their import/generation handlers survive.
$script:generationDrawerOpen=$false
$window.FindName('GenerationDrawerToggle').Add_Click({
    $shell=$window.FindName('GenerationDrawerShell')
    $from=$shell.ActualHeight
    $script:generationDrawerOpen=-not $script:generationDrawerOpen
    $to=if($script:generationDrawerOpen){258.0}else{0.0}
    $shell.BeginAnimation([Windows.FrameworkElement]::HeightProperty,$null)
    $shell.Height=$to
    if([Windows.SystemParameters]::ClientAreaAnimation){
        $animation=[Windows.Media.Animation.DoubleAnimation]::new($from,$to,[Windows.Duration]::new([TimeSpan]::FromMilliseconds(220)))
        $animation.EasingFunction=[Windows.Media.Animation.CubicEase]::new()
        $animation.EasingFunction.EasingMode='EaseInOut'
        $shell.BeginAnimation([Windows.FrameworkElement]::HeightProperty,$animation)
    }
    $window.FindName('GenerationDrawerToggle').Content=if($script:generationDrawerOpen){'3D Gen Studio  ·  Close'}else{'3D Gen Studio  ·  Open'}
    if($script:generationDrawerOpen){$window.FindName('AiPromptInput').Focus()|Out-Null}
})
