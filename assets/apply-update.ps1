param([Parameter(Mandatory=$true)][string]$Manifest)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$folder = Split-Path -Parent $Manifest
$resultPath = Join-Path $folder 'update-result.json'
function Save-Result($status, $message) {
    @{status=$status;message=$message;version=$config.version;time=(Get-Date).ToString('s')} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
try {
    Save-Result 'waiting' 'Waiting for CardVault to close and save tasks'
    $owner = Get-Process -Id $config.parent_pid -ErrorAction SilentlyContinue
    if ($owner -and -not $owner.WaitForExit(120000)) { throw 'CardVault did not close; no files were replaced' }
    $root = [IO.Path]::GetFullPath($config.root)
    $package = [IO.Path]::GetFullPath($config.package)
    if ((Split-Path -Parent $package) -ne (Join-Path $root 'update')) { throw 'Invalid update location' }
    $stream = [IO.File]::OpenRead($package)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $digest = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
    if ($digest -ne $config.sha256) { throw 'Installer hash mismatch' }
    Save-Result 'installing' 'Installing update into the existing application directory'
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/SP-','/NORESTART','/NORESTARTAPPLICATIONS','/NOCLOSEAPPLICATIONS','/RESTARTEXITCODE=3010',('/DIR="' + $root + '"'),('/LOG="' + (Join-Path $folder 'installer.log') + '"'))
    $installer = Start-Process -FilePath $package -ArgumentList $arguments -WindowStyle Hidden -PassThru -Wait
    if ($installer.ExitCode -eq 3010) { throw 'Windows restart required to finish updating; restart Windows before launching CardVault' }
    if ($installer.ExitCode -ne 0) { throw ('Installer failed with exit code ' + $installer.ExitCode + '; see update/installer.log') }
    $exe = Join-Path $root 'CardVault.exe'
    $actual = [Diagnostics.FileVersionInfo]::GetVersionInfo($exe).ProductVersion.Trim()
    if ([Version]$actual -ne [Version]$config.version) { throw 'Installed version does not match the selected package' }
    # JSON stores arguments separately; Windows paths cannot contain literal quotes.
    $restartArguments = @($config.restart_args | ForEach-Object { '"' + $_ + '"' })
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    Start-Process -FilePath $exe -ArgumentList $restartArguments -WorkingDirectory $root -WindowStyle Hidden
    Save-Result 'completed' 'Update installed and CardVault restarted'
} catch {
    Save-Result 'failed' $_.Exception.Message
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'CardVault update') | Out-Null
    exit 1
}
