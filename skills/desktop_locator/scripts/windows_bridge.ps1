param(
    [Parameter(Mandatory=$true)][ValidateSet('capture','preview','move','execute')][string]$Action,
    [string]$Output = (Join-Path $env:TEMP 'desktop-locator-capture.png'),
    [string]$Metadata = '',
    [string]$CaptureMetadata = '',
    [int]$X = -2147483648,
    [int]$Y = -2147483648,
    [int]$TargetLeft = -2147483648,
    [int]$TargetTop = -2147483648,
    [int]$TargetRight = -2147483648,
    [int]$TargetBottom = -2147483648,
    [switch]$RegionSpecified,
    [switch]$ConfirmExecution,
    [string]$ActionPermit = ''
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$native = @'
using System;
using System.Runtime.InteropServices;
public static class DesktopLocatorNative {
 [StructLayout(LayoutKind.Sequential)] public struct PT { public int X,Y; }
 [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize,flags; public IntPtr hCursor; public PT ptScreenPos; }
 [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left,Top,Right,Bottom; }
 [StructLayout(LayoutKind.Sequential)] public struct ICONINFO { [MarshalAs(UnmanagedType.Bool)] public bool fIcon; public int xHotspot,yHotspot; public IntPtr hbmMask,hbmColor; }
 [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
 [DllImport("user32.dll")] public static extern bool GetCursorInfo(ref CURSORINFO info);
 [DllImport("user32.dll")] public static extern bool GetCursorPos(out PT point);
 [DllImport("user32.dll", SetLastError=true)] public static extern bool SetCursorPos(int x,int y);
 [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx,dy; public uint mouseData,dwFlags,time; public IntPtr dwExtraInfo; }
 [StructLayout(LayoutKind.Sequential)] public struct INPUT { public int type; public MOUSEINPUT mi; }
 [DllImport("user32.dll", SetLastError=true)] public static extern uint SendInput(uint count, [In] INPUT[] inputs, int size);
 public static uint LeftClickOnce() {
   var events = new INPUT[2]; events[0].mi.dwFlags=0x0002; events[1].mi.dwFlags=0x0004;
   return SendInput(2,events,Marshal.SizeOf(typeof(INPUT)));
 }
 [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
 [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out RECT rect);
 [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
 [DllImport("user32.dll")] public static extern bool GetIconInfo(IntPtr icon, out ICONINFO info);
 [DllImport("gdi32.dll")] public static extern bool DeleteObject(IntPtr handle);
 [DllImport("user32.dll")] public static extern bool DrawIconEx(IntPtr hdc,int x,int y,IntPtr icon,int w,int h,int step,IntPtr brush,int flags);
 public static PT Cursor() { PT p; if(!GetCursorPos(out p)) throw new Exception("GetCursorPos failed"); return p; }
 public static CURSORINFO CursorInfo() { var ci = new CURSORINFO(); ci.cbSize=Marshal.SizeOf(typeof(CURSORINFO)); if(!GetCursorInfo(ref ci)) throw new Exception("GetCursorInfo failed"); return ci; }
 public static RECT WindowRect(IntPtr h) { RECT r; if(!GetWindowRect(h,out r)) throw new Exception("GetWindowRect failed"); return r; }
}
'@
Add-Type -TypeDefinition $native
if (-not [DesktopLocatorNative]::SetProcessDPIAware()) { throw 'Cannot establish DPI-aware coordinate system' }
function Foreground {
    $h = [DesktopLocatorNative]::GetForegroundWindow()
    if ($h -eq [IntPtr]::Zero) { throw 'No foreground window' }
    [uint32]$pidValue = 0
    [void][DesktopLocatorNative]::GetWindowThreadProcessId($h,[ref]$pidValue)
    if ($pidValue -eq 0) { throw 'Foreground process unavailable' }
    $started = (Get-Process -Id $pidValue -ErrorAction Stop).StartTime.ToUniversalTime().Ticks
    $r = [DesktopLocatorNative]::WindowRect($h)
    return @{ handle = $h.ToInt64().ToString(); pid = [int]$pidValue; processStartTicks = [string]$started; rect = @{left=$r.Left;top=$r.Top;right=$r.Right;bottom=$r.Bottom} }
}
if ($Action -eq 'capture') {
    $v = [System.Windows.Forms.SystemInformation]::VirtualScreen
    $ci = [DesktopLocatorNative]::CursorInfo()
    $before = Foreground
    $captureStartUtc = [DateTime]::UtcNow
    $bmp = New-Object System.Drawing.Bitmap($v.Width,$v.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bmp)
    try {
        $graphics.CopyFromScreen([System.Drawing.Point]::new($v.X,$v.Y),[System.Drawing.Point]::Empty,$v.Size)
        $cursorDrawn = $false
        if (($ci.flags -band 1) -ne 0 -and $ci.hCursor -ne [IntPtr]::Zero) {
            $iconinfo = New-Object DesktopLocatorNative+ICONINFO
            if (-not [DesktopLocatorNative]::GetIconInfo($ci.hCursor,[ref]$iconinfo)) { throw 'GetIconInfo failed' }
            try {
                $hdc = $graphics.GetHdc()
                try {
                    $cursorDrawn = [DesktopLocatorNative]::DrawIconEx($hdc,
                        ($ci.ptScreenPos.X-$v.X-$iconinfo.xHotspot),
                        ($ci.ptScreenPos.Y-$v.Y-$iconinfo.yHotspot),$ci.hCursor,0,0,0,[IntPtr]::Zero,3)
                } finally { $graphics.ReleaseHdc($hdc) }
            } finally {
                if ($iconinfo.hbmMask -ne [IntPtr]::Zero) { [void][DesktopLocatorNative]::DeleteObject($iconinfo.hbmMask) }
                if ($iconinfo.hbmColor -ne [IntPtr]::Zero) { [void][DesktopLocatorNative]::DeleteObject($iconinfo.hbmColor) }
            }
            if (-not $cursorDrawn) { throw 'Cursor composition failed' }
        }
        if (-not $cursorDrawn) { throw 'Cursor is not visible; capture aborted' }
        $bmp.Save($Output,[System.Drawing.Imaging.ImageFormat]::Png)
    } finally { $graphics.Dispose();$bmp.Dispose() }
    $after = Foreground
    $now = [DesktopLocatorNative]::Cursor()
    $result = @{ action='capture'; path=[IO.Path]::GetFullPath($Output); sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $Output).Hash.ToLowerInvariant();
        capturedUtc=$captureStartUtc.ToString('o'); virtualScreen=@{x=$v.X;y=$v.Y;width=$v.Width;height=$v.Height};
        cursor=@{x=$ci.ptScreenPos.X;y=$ci.ptScreenPos.Y;drawn=$cursorDrawn};
        stable=($before.handle -eq $after.handle -and $before.pid -eq $after.pid -and
            $before.processStartTicks -eq $after.processStartTicks -and
            $before.rect.left -eq $after.rect.left -and $before.rect.top -eq $after.rect.top -and
            $before.rect.right -eq $after.rect.right -and $before.rect.bottom -eq $after.rect.bottom -and
            $ci.ptScreenPos.X -eq $now.X -and $ci.ptScreenPos.Y -eq $now.Y);
        foreground=$after }
    if (-not $Metadata) { $Metadata = "$Output.json" }
    if (-not $result.stable) { Remove-Item -LiteralPath $Output -ErrorAction SilentlyContinue; throw 'Capture changed during composition; metadata not issued' }
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $Metadata -Encoding UTF8
    $result | ConvertTo-Json -Depth 7
    exit 0
}
# Locator x/y are screenshot-relative; X/Y and target bounds are absolute screen pixels.
function Assert-That([bool]$ok, [string]$reason) {
    if (-not $ok) { throw $reason }
}
function Assert-Window($expected, $actual) {
    Assert-That ($null -ne $expected -and $null -ne $actual) 'Missing foreground identity'
    Assert-That ([string]$expected.handle -eq [string]$actual.handle -and
        [int]$expected.pid -eq [int]$actual.pid -and
        [string]$expected.processStartTicks -eq [string]$actual.processStartTicks -and
        [long]$expected.rect.left -eq [long]$actual.rect.left -and
        [long]$expected.rect.top -eq [long]$actual.rect.top -and
        [long]$expected.rect.right -eq [long]$actual.rect.right -and
        [long]$expected.rect.bottom -eq [long]$actual.rect.bottom) 'Foreground identity or bounds changed'
}
function Assert-Point([long]$px,[long]$py,[long]$left,[long]$top,[long]$right,[long]$bottom) {
    Assert-That ($right -gt $left -and $bottom -gt $top -and $px -ge $left -and
        $px -lt $right -and $py -ge $top -and $py -lt $bottom) 'Point outside bounds'
}
function Assert-Fresh($m) {
    Assert-That ($m.action -eq 'capture' -and $m.stable -eq $true -and $m.cursor.drawn -eq $true) 'Unstable capture'
    $dt = [DateTime]::MinValue
    Assert-That ([DateTime]::TryParseExact([string]$m.capturedUtc, 'o',
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind, [ref]$dt)) 'Invalid capture time'
    $age = ([DateTime]::UtcNow - $dt.ToUniversalTime()).TotalSeconds
    Assert-That ($age -ge 0 -and $age -le 5) 'Capture not fresh (maximum 5 seconds)'
    Assert-That ([string]$m.sha256 -cmatch '^[a-f0-9]{64}$') 'Invalid screenshot hash'
    Assert-That ([IO.Path]::IsPathRooted([string]$m.path)) 'Screenshot must have absolute path'
    Assert-That ((Get-FileHash -Algorithm SHA256 -LiteralPath $m.path).Hash.ToLowerInvariant() -ceq $m.sha256) 'Screenshot hash mismatch'
}
function Assert-Screen($m) {
    $v = [System.Windows.Forms.SystemInformation]::VirtualScreen
    Assert-That ([long]$m.virtualScreen.x -eq $v.X -and [long]$m.virtualScreen.y -eq $v.Y -and
        [long]$m.virtualScreen.width -eq $v.Width -and [long]$m.virtualScreen.height -eq $v.Height) 'Virtual screen changed'
    Assert-That ($v.Width -gt 0 -and $v.Height -gt 0) 'Invalid virtual screen'
    return $v
}
function Assert-Cursor([long]$px, [long]$py) {
    $cursorNow = [DesktopLocatorNative]::Cursor()
    Assert-That ($cursorNow.X -eq $px -and $cursorNow.Y -eq $py) 'Pointer contention or human takeover; abort'
}
function Assert-Target($m, $loc, $v) {
    Assert-That ($X -ne -2147483648 -and $Y -ne -2147483648) 'X and Y required'
    Assert-That ($TargetLeft -ne -2147483648 -and $TargetTop -ne -2147483648 -and
        $TargetRight -ne -2147483648 -and $TargetBottom -ne -2147483648) 'Explicit target bounds required'
    Assert-That ([string]$loc.screenshot_token -ceq [string]$m.sha256) 'Locator screenshot identity differs from capture'
    Assert-That ([long]$loc.window_size.width -eq $v.Width -and [long]$loc.window_size.height -eq $v.Height) 'Locator image dimensions differ from screen'
    Assert-That ($loc.x -is [int] -and $loc.y -is [int]) 'Locator coordinates must be integers'
    Assert-That ([long]$loc.x -eq ([long]$X - [long]$v.X) -and
        [long]$loc.y -eq ([long]$Y - [long]$v.Y)) 'Absolute coordinates differ from screenshot offsets'
    Assert-That (($loc.source -ceq 'ax_exact_unique' -and [double]$loc.confidence -eq 1) -or
        ($loc.source -ceq 'vision_openai_compatible' -and $RegionSpecified.IsPresent)) 'Only unique AX target or explicitly selected vision region allowed'
    Assert-Point $X $Y $v.X $v.Y ([long]$v.X+$v.Width) ([long]$v.Y+$v.Height)
    Assert-Point $X $Y $TargetLeft $TargetTop $TargetRight $TargetBottom
    Assert-Point $TargetLeft $TargetTop $v.X $v.Y ([long]$v.X+$v.Width) ([long]$v.Y+$v.Height)
    Assert-Point ([long]$TargetRight-1) ([long]$TargetBottom-1) $v.X $v.Y ([long]$v.X+$v.Width) ([long]$v.Y+$v.Height)
    Assert-Point $X $Y $m.foreground.rect.left $m.foreground.rect.top $m.foreground.rect.right $m.foreground.rect.bottom
    Assert-Point $TargetLeft $TargetTop $m.foreground.rect.left $m.foreground.rect.top $m.foreground.rect.right $m.foreground.rect.bottom
    Assert-Point ([long]$TargetRight-1) ([long]$TargetBottom-1) $m.foreground.rect.left $m.foreground.rect.top $m.foreground.rect.right $m.foreground.rect.bottom
}
if (-not $CaptureMetadata -or -not $Metadata) { throw 'preview/execute requires -CaptureMetadata and -Metadata (locator JSON)' }
if ($Action -in @('move','execute') -and -not $ConfirmExecution.IsPresent) { throw 'move/execute requires explicit -ConfirmExecution' }
if ($Action -eq 'preview' -and $ConfirmExecution.IsPresent) { throw 'ConfirmExecution is only valid for move/execute' }
if ($Action -in @('move','execute') -and -not $ActionPermit) { throw 'move/execute requires in-memory task action permit JSON' }
$m = Get-Content -LiteralPath $CaptureMetadata -Raw | ConvertFrom-Json
$loc = Get-Content -LiteralPath $Metadata -Raw | ConvertFrom-Json
Assert-Fresh $m
$v = Assert-Screen $m
Assert-Target $m $loc $v
if ($Action -in @('move','execute')) {
    $permit = $ActionPermit | ConvertFrom-Json
    $expectedAction = if ($Action -eq 'execute') { 'click' } else { 'move' }
    Assert-That ([string]$permit.task_id -cmatch '^[A-Za-z0-9_-]{32}$') 'Invalid task ID'
    if ($loc.source -ceq 'vision_openai_compatible') {
        Assert-That ($null -ne $permit.reviewed_region -and $RegionSpecified.IsPresent) 'Vision action requires reviewed region'
        Assert-That ([long]$TargetLeft -eq ([long]$permit.reviewed_region.left + [long]$v.X) -and
            [long]$TargetTop -eq ([long]$permit.reviewed_region.top + [long]$v.Y) -and
            [long]$TargetRight -eq ([long]$permit.reviewed_region.right + [long]$v.X) -and
            [long]$TargetBottom -eq ([long]$permit.reviewed_region.bottom + [long]$v.Y)) 'Target bounds differ from reviewed region'
    }
    Assert-That ($permit.action -ceq $expectedAction -and $permit.status -ceq 'requires_windows_bridge' -and
        $permit.screenshot_token -ceq $m.sha256 -and $permit.coordinate.source -ceq $loc.source -and
        $permit.coordinate.x -eq $loc.x -and $permit.coordinate.y -eq $loc.y) 'Task action permit does not match the latest locator result'
}
Assert-Window $m.foreground (Foreground)
Assert-Cursor $m.cursor.x $m.cursor.y
if ($Action -eq 'preview') {
    @{ action='preview'; status='dry-run/no-input'; x=$X; y=$Y;
        targetBounds=@{left=$TargetLeft;top=$TargetTop;right=$TargetRight;bottom=$TargetBottom};
        coordinateSystem='absolute-screen'; source=$loc.source; screenshotToken=$m.sha256 } | ConvertTo-Json -Depth 5
    exit 0
}
# One-shot execution: no retry even if SendInput's outcome is uncertain.
Start-Sleep -Milliseconds 40
Assert-Cursor $m.cursor.x $m.cursor.y
Assert-Fresh $m
[void](Assert-Screen $m)
Assert-Window $m.foreground (Foreground)
if (-not [DesktopLocatorNative]::SetCursorPos($X,$Y)) { throw 'SetCursorPos failed; no click sent' }
Assert-Cursor $X $Y
Start-Sleep -Milliseconds 40
Assert-Cursor $X $Y
Assert-Window $m.foreground (Foreground)
[void](Assert-Screen $m)
Assert-Fresh $m
Assert-Cursor $X $Y
if ($Action -eq 'move') {
    @{action='move';status='pointer-moved-not-verified-semantic';x=$X;y=$Y;coordinateSystem='absolute-screen';screenshotToken=$m.sha256} | ConvertTo-Json
    exit 0
}
$sent = [DesktopLocatorNative]::LeftClickOnce()
if ($sent -ne 2) { throw "SendInput sent $sent of 2 events; outcome unknown; do not retry" }
@{action='execute';status='click-input-sent-once';x=$X;y=$Y;
    coordinateSystem='absolute-screen';screenshotToken=$m.sha256} | ConvertTo-Json
