param([ValidateSet('dev','frontend','backend','build','test','setup')][string]$Mode='dev')
& (Join-Path $PSScriptRoot 'run-local.cmd') $Mode
exit $LASTEXITCODE
