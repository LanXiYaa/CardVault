param([Parameter(Mandatory=$true)][string]$Manifest)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json
$folder = [IO.Path]::GetFullPath((Split-Path -Parent $Manifest))
$root = [IO.Path]::GetFullPath($config.root)
$resultPath = Join-Path $folder 'update-result.json'
$journal = New-Object Collections.Generic.List[object]
$lock = $null
$archive = $null
$committed = $false
$closed = $false
function Save-Result($status, $message) {
    @{status=$status;message=$message;version=$config.version;time=(Get-Date).ToString('s')} | ConvertTo-Json | Set-Content -LiteralPath $resultPath -Encoding UTF8
}
function Hash-File($path) {
    $stream = [IO.File]::OpenRead($path)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Safe-Path($base, $relative) {
    $parts = $relative.Split('/')
    if (-not $relative -or $relative.Length -gt 240) { throw 'Invalid update path' }
    foreach ($part in $parts) {
        if (-not $part -or $part -eq '.' -or $part -eq '..' -or $part -match '[<>:"\\|?*\x00-\x1f]' -or $part -match '[ .]$' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') { throw 'Unsafe update path' }
    }
    $path = [IO.Path]::GetFullPath((Join-Path $base $relative))
    if (-not $path.StartsWith($base.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Path escapes application' }
    $current = $path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Update path contains a link' }
        }
        $current = Split-Path -Parent $current
    }
    return $path
}
function Restart-App {
    $exe = Join-Path $root 'CardVault.exe'
    $arguments = @($config.restart_args | ForEach-Object { '"' + $_ + '"' })
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $root -WindowStyle Normal
}
try {
    if ($folder -ne (Join-Path $root 'update')) { throw 'Invalid update directory' }
    $null = Safe-Path $root 'update/lock'
    $lock = [IO.File]::Open((Join-Path $folder 'apply.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    Save-Result 'waiting' 'Waiting for CardVault to close and save tasks'
    $owner = Get-Process -Id $config.parent_pid -ErrorAction SilentlyContinue
    if ($owner -and -not $owner.WaitForExit(120000)) { throw 'CardVault did not close; no files replaced' }
    $closed = $true
    $package = [IO.Path]::GetFullPath($config.package)
    if ((Split-Path -Parent $package) -ne $folder -or [IO.Path]::GetExtension($package) -ne '.upd') { throw 'Invalid update location' }
    if ((Hash-File $package) -ne $config.sha256) { throw 'Update archive hash mismatch' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($package)
    $entry = $archive.GetEntry('manifest.json')
    if (-not $entry -or $entry.Length -gt 8388608) { throw 'Invalid manifest' }
    $reader = New-Object IO.StreamReader($entry.Open())
    try { $metadata = $reader.ReadToEnd() | ConvertFrom-Json } finally { $reader.Dispose() }
    if ($metadata.format -ne 'CardVault.Update' -or $metadata.schema -ne 1 -or $metadata.product -ne 'CardVault' -or $metadata.version -ne $config.version) { throw 'Update identity mismatch' }
    $files = @($metadata.files.PSObject.Properties)
    if ($files.Count -eq 0 -or $files.Count -gt 19999 -or -not $metadata.files.'CardVault.exe') { throw 'Missing payload' }
    $expected = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    $null = $expected.Add('manifest.json')
    [long]$total = 0
    foreach ($file in $files) {
        $name = $file.Name
        if ($name -cne 'CardVault.exe' -and $name -cne '发行版说明.txt' -and $name -cne 'THIRD_PARTY_NOTICES.txt' -and -not $name.StartsWith('_internal/') -and -not $name.StartsWith('licenses/')) { throw 'Protected path in update' }
        $null = Safe-Path $root $name
        if (-not $expected.Add('payload/' + $name)) { throw 'Duplicate update path' }
        if ($file.Value.sha256 -notmatch '^[a-f0-9]{64}$' -or $file.Value.size -lt 0) { throw 'Invalid payload metadata' }
        $total += $file.Value.size
    }
    if ($total -gt 4294967296 -or $archive.Entries.Count -ne $expected.Count) { throw 'Invalid update size or contents' }
    foreach ($item in $archive.Entries) {
        if (-not $expected.Remove($item.FullName)) { throw 'Unexpected or duplicate archive entry' }
        if ((($item.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Archive links are not allowed' }
    }
    $work = Join-Path $folder ('transaction-' + [Guid]::NewGuid().ToString('N'))
    $staged = Join-Path $work 'new'
    $backup = Join-Path $work 'backup'
    $null = New-Item -ItemType Directory -Path $staged, $backup
    Save-Result 'extracting' 'Checking and extracting all files before replacement'
    foreach ($file in $files) {
        $dest = Safe-Path $staged $file.Name
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force
        $item = $archive.GetEntry('payload/' + $file.Name)
        if ($item.Length -ne $file.Value.size) { throw 'Payload size mismatch' }
        $inputStream = $item.Open()
        $outputStream = [IO.File]::Open($dest, 'CreateNew', 'Write', 'None')
        try { $inputStream.CopyTo($outputStream); $outputStream.Flush($true) }
        finally { $inputStream.Dispose(); $outputStream.Dispose() }
        if ((Hash-File $dest) -ne $file.Value.sha256) { throw 'Payload hash mismatch' }
    }
    $archive.Dispose(); $archive = $null
    $actual = [Diagnostics.FileVersionInfo]::GetVersionInfo((Join-Path $staged 'CardVault.exe')).ProductVersion.Trim()
    if ([Version]$actual -ne [Version]$config.version) { throw 'Executable version does not match manifest' }
    Save-Result 'replacing' 'Replacing application files; original files retained for rollback'
    foreach ($file in $files) {
        $dest = Safe-Path $root $file.Name
        $old = Safe-Path $backup $file.Name
        $new = Safe-Path $staged $file.Name
        $existed = [IO.File]::Exists($dest)
        if ($existed) {
            $null = New-Item -ItemType Directory -Path (Split-Path -Parent $old) -Force
            [IO.File]::Copy($dest, $old)
        }
        $journal.Add(@{path=$file.Name;existed=$existed})
        @($journal.ToArray()) | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $work 'rollback.json') -Encoding UTF8
        $null = New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force
        if ($existed) { [IO.File]::Replace($new, $dest, [NullString]::Value) }
        else { [IO.File]::Move($new, $dest) }
    }
    Restart-App
    $committed = $true
    Save-Result 'completed' 'Update applied and CardVault restarted; rollback copies retained in update folder'
} catch {
    $reason = $_.Exception.Message
    $rollbackErrors = @()
    if (-not $committed) {
        for ($i = $journal.Count - 1; $i -ge 0; $i--) {
            try {
                $record = $journal[$i]
                $dest = Safe-Path $root $record.path
                if ($record.existed) {
                    $original = Safe-Path $backup $record.path
                    if (-not [IO.File]::Exists($dest) -or (Hash-File $dest) -ne (Hash-File $original)) {
                        [IO.File]::Copy($original, $dest, $true)
                    }
                }
                elseif ([IO.File]::Exists($dest)) { [IO.File]::Delete($dest) }
            } catch { $rollbackErrors += $_.Exception.Message }
        }
    }
    if ($rollbackErrors.Count) { $reason += '; rollback needs attention: ' + ($rollbackErrors -join '; ') }
    Save-Result 'failed' $reason
    if ($closed -and -not $committed -and $rollbackErrors.Count -eq 0) {
        try { Restart-App } catch { Save-Result 'failed' ($reason + '; could not restart: ' + $_.Exception.Message) }
    }
    exit 1
} finally {
    if ($archive) { $archive.Dispose() }
    if ($lock) { $lock.Dispose() }
}
