$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot) 'scripts/free-host-lib.ps1')
function Assert-Condition { param([bool]$Condition, [string]$Message) if (-not $Condition) { throw $Message } }
$empty = Get-StudyspaceServeState ('{}' | ConvertFrom-Json) 'http://127.0.0.1:8503'
Assert-Condition (-not $empty.HasRoute) 'Fresh settings must be recognized.'
$fixture = '{"TCP":{"443":{"HTTPS":true}},"Web":{"pc.example.ts.net:443":{"Handlers":{"/":{"Proxy":"http://127.0.0.1:8503"}}}}}' | ConvertFrom-Json
$valid = Get-StudyspaceServeState $fixture 'http://127.0.0.1:8503'
Assert-Condition ($valid.Matches -and -not $valid.Public) 'Expected private route did not match.'
$other = Get-StudyspaceServeState $fixture 'http://127.0.0.1:9999'
Assert-Condition ($other.HasRoute -and -not $other.Matches) 'Other apps must not be overwritten.'
$fixture.Web.'pc.example.ts.net:443'.Handlers | Add-Member -NotePropertyName '/other' -NotePropertyValue @{ Proxy = 'http://127.0.0.1:9000' }
Assert-Condition (-not (Get-StudyspaceServeState $fixture 'http://127.0.0.1:8503').Matches) 'Additional routes must be preserved.'
$fixture | Add-Member -NotePropertyName AllowFunnel -NotePropertyValue ([pscustomobject]@{'pc.example.ts.net:443'=$true})
Assert-Condition ((Get-StudyspaceServeState $fixture 'http://127.0.0.1:8503').Public) 'Public Funnel must be detected.'
$tokens = $null; $syntaxErrors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path (Split-Path $PSScriptRoot) 'Start-Free.ps1'), [ref]$tokens, [ref]$syntaxErrors) | Out-Null
Assert-Condition ($syntaxErrors.Count -eq 0) 'Start-Free.ps1 has syntax errors.'
Write-Host 'Free-host checks passed: private route detection, collision protection, Funnel detection and script syntax.'
