function Get-StudyspaceProperty {
    param($Object, [string]$Name)
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

function Get-StudyspaceServeState {
    param($Configuration, [string]$Target)
    $tcp = Get-StudyspaceProperty (Get-StudyspaceProperty $Configuration 'TCP') '443'
    $web = Get-StudyspaceProperty $Configuration 'Web'
    $sites = @()
    if ($web) { $sites = @($web.PSObject.Properties | Where-Object { $_.Name.EndsWith(':443') }) }
    $funnel = Get-StudyspaceProperty $Configuration 'AllowFunnel'
    $public = $false
    if ($funnel) {
        $public = @($funnel.PSObject.Properties | Where-Object { $_.Name.EndsWith(':443') -and $_.Value -eq $true }).Count -gt 0
    }
    $matches = $false
    if ($sites.Count -eq 1 -and (Get-StudyspaceProperty $tcp 'HTTPS') -eq $true) {
        $handlers = Get-StudyspaceProperty $sites[0].Value 'Handlers'
        if ($handlers -and @($handlers.PSObject.Properties).Count -eq 1) {
            $proxy = Get-StudyspaceProperty (Get-StudyspaceProperty $handlers '/') 'Proxy'
            $matches = $proxy -eq $Target
        }
    }
    [pscustomobject]@{ HasRoute = ($null -ne $tcp -or $sites.Count -gt 0); Matches = $matches; Public = $public }
}
