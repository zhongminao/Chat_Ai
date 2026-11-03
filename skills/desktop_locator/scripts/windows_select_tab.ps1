param(
    [Parameter(Mandatory=$true)][string]$Name,
    [Parameter(Mandatory=$true)][string]$ExpectedWindowTitle,
    [switch]$Execute
)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$browser=Get-Process firefox -ErrorAction Stop | Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero -and $_.MainWindowTitle -eq $ExpectedWindowTitle }
if (@($browser).Count -ne 1) { throw 'Firefox foreground/window identity ambiguous or changed' }
$native=@'
using System; using System.Runtime.InteropServices;
public static class ActiveWindowCheck { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); }
'@
Add-Type -TypeDefinition $native
if ([ActiveWindowCheck]::GetForegroundWindow() -ne $browser.MainWindowHandle) { throw 'Firefox not foreground' }
$root=[System.Windows.Automation.AutomationElement]::FromHandle($browser.MainWindowHandle)
$condition=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty,[System.Windows.Automation.ControlType]::TabItem)
$items=$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$condition)
$matches=@(for($i=0;$i -lt $items.Count;$i++){ $item=$items.Item($i);if($item.Current.Name -ceq $Name){$item} })
if($matches.Count -ne 1){throw "Expected exactly one matching tab, got $($matches.Count)"}
$target=$matches[0];$r=$target.Current.BoundingRectangle
if($r.IsEmpty -or $r.Width -le 0 -or $r.Height -le 0 -or $target.Current.IsOffscreen -or -not $target.Current.IsEnabled){throw 'Tab unavailable'}
if(-not $Execute){@{status='preview-only';name=$Name;rect=@{x=$r.X;y=$r.Y;width=$r.Width;height=$r.Height}}|ConvertTo-Json;exit 0}
if ([ActiveWindowCheck]::GetForegroundWindow() -ne $browser.MainWindowHandle){throw 'Foreground changed'}
# UI Automation Select does not move pointer, avoiding competition with a human mouse.
$p=$target.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern)
if($null -eq $p){throw 'Tab selection pattern unavailable'}
$p.Select()
Start-Sleep -Milliseconds 200
if (-not $p.Current.IsSelected){throw 'Selection not confirmed'}
@{status='selected';name=$Name;window=$browser.MainWindowTitle}|ConvertTo-Json
