# Run with: powershell.exe -NoProfile -File .\tests_windows_bridge.ps1
# AST parsing and validation functions only. No script invocation, no desktop input.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'windows_bridge.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count -ne 0) { throw "Bridge parse error: $($parseErrors | Out-String)" }
function Check([bool]$ok, [string]$message) { if (-not $ok) { throw $message } }
function Reject([scriptblock]$block, [string]$message) {
    $failed = $false
    try { & $block } catch { $failed = $true }
    Check $failed $message
}
$code = [IO.File]::ReadAllText($source)
$paramAst = $ast.ParamBlock
Check ($null -ne $paramAst -and $code.Contains("'capture','preview','move','execute'")) 'Explicit action modes missing'
Check ($code.Contains('if ($Action -in @(''move'',''execute'') -and -not $ConfirmExecution.IsPresent)')) 'Move/execute confirmation missing'
Check ($code.Contains('if ($Action -eq ''preview'')')) 'Preview branch missing'
$previewOffset = $code.IndexOf("if (`$Action -eq 'preview')")
$moveOffset = $code.IndexOf('[DesktopLocatorNative]::SetCursorPos($X,$Y)')
$clickOffset = $code.IndexOf('[DesktopLocatorNative]::LeftClickOnce()')
Check ($previewOffset -ge 0 -and $previewOffset -lt $moveOffset -and $moveOffset -lt $clickOffset) 'Input precedes preview/guard'
Check ($code.Contains('SetCursorPos($X,$Y)') -and $code.Contains('SendInput(2,events')) 'One-shot input missing'
Check ($code.Contains('if ($sent -ne 2)') -and $code.Contains('do not retry')) 'Partial click handling missing'
$definitions = @('Assert-That','Assert-Point','Assert-Window','Assert-Target','Assert-Fresh')
foreach ($name in $definitions) {
    $nodes = @($ast.FindAll({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true))
    Check ($nodes.Count -eq 1) "Expected one $name function"
    # The selected validation functions contain no Win32 calls and are not called until explicitly tested below.
    . ([scriptblock]::Create($nodes[0].Extent.Text))
}
$rect = @{ left=-500; top=40; right=800; bottom=640 }
$window = @{ handle='42'; pid=8; processStartTicks='123456789'; rect=$rect }
Assert-Window $window $window
Reject { Assert-Window $window @{handle='43';pid=8;processStartTicks='123456789';rect=$rect} } 'Wrong handle accepted'
Reject { Assert-Window $window @{handle='42';pid=8;processStartTicks='0';rect=$rect} } 'Reused process accepted'
Reject { Assert-Window $window @{handle='42';pid=8;processStartTicks='123456789';rect=@{left=-499;top=40;right=800;bottom=640}} } 'Changed window bounds accepted'
Assert-Point -400 100 -500 40 0 200
Reject { Assert-Point 0 100 -500 40 0 200 } 'Exclusive right edge accepted'
Reject { Assert-Point -400 100 -500 40 -500 200 } 'Empty box accepted'
# Virtual screen starts at negative X: screenshot (100,60) corresponds to absolute (-400,100).
$v = @{X=-500;Y=40;Width=1300;Height=600}
$m = @{ sha256=('a' * 64); foreground=$window }
$loc = @{ screenshot_token=('a' * 64); x=100; y=60;
    window_size=@{width=1300;height=600}; source='ax_exact_unique'; confidence=1 }
$X=-400; $Y=100; $TargetLeft=-415; $TargetTop=85; $TargetRight=-385; $TargetBottom=115
$RegionSpecified=[System.Management.Automation.SwitchParameter]::new($false)
Assert-Target $m $loc $v
$X=100
Reject { Assert-Target $m $loc $v } 'Screenshot offset confused with absolute coordinate'
$X=-400
$TargetRight=-400
Reject { Assert-Target $m $loc $v } 'Target outside exclusive bound accepted'
$TargetRight=-385
$loc.source='vision_openai_compatible'
Reject { Assert-Target $m $loc $v } 'Unselected vision result accepted'
$RegionSpecified=[System.Management.Automation.SwitchParameter]::new($true)
Assert-Target $m $loc $v
$loc.screenshot_token=('b' * 64)
Reject { Assert-Target $m $loc $v } 'Mismatched screenshot identity accepted'
$shot=Join-Path ([IO.Path]::GetTempPath()) ("bridge-static-"+[guid]::NewGuid().ToString('N'))
try {
    [IO.File]::WriteAllText($shot,'test bytes')
    $m.sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $shot).Hash.ToLowerInvariant()
    $m.path=$shot; $m.action='capture'; $m.stable=$true; $m.cursor=@{drawn=$true}
    $m.capturedUtc=[DateTime]::UtcNow.ToString('o')
    Assert-Fresh $m
    $m.capturedUtc=[DateTime]::UtcNow.AddSeconds(-10).ToString('o')
    Reject { Assert-Fresh $m } 'Stale screenshot accepted'
    $m.capturedUtc=[DateTime]::UtcNow.ToString('o'); $m.sha256=('a' * 64)
    Reject { Assert-Fresh $m } 'Tampered screenshot accepted'
} finally { Remove-Item -LiteralPath $shot -ErrorAction SilentlyContinue }
'PASS: parse, dry-run separation, unique/explicit bounds, offset, window identity, age and screenshot hash; no desktop actions'
