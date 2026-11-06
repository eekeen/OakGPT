param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = "Stop"
if (Test-Path -LiteralPath $Output) { throw "Refusing to overwrite host measurements" }
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class OakHostTimes {
  [DllImport("kernel32.dll", SetLastError=true)]
  public static extern bool GetSystemTimes(out long idle, out long kernel, out long user);
  public static long[] Read() {
    long idle, kernel, user;
    if (!GetSystemTimes(out idle, out kernel, out user)) throw new Exception("GetSystemTimes failed");
    return new long[] { idle, kernel, user };
  }
}
"@
$phase33Selected = @(Get-Process | Where-Object { $_.Name -in @("TFTClient-Win64-Shipping", "VirtualBoxVM", "Discord") } | Select-Object -ExpandProperty Id)
$phase33Results = @()
for ($phase33Index=0; $phase33Index -lt 3; $phase33Index++) {
  $phase33Before = [OakHostTimes]::Read()
  $phase33Processes = @()
  foreach ($phase33Pid in $phase33Selected) {
    try {
      $phase33P = [Diagnostics.Process]::GetProcessById($phase33Pid)
      $phase33Processes += [PSCustomObject]@{pid=$phase33Pid; cpu=$phase33P.TotalProcessorTime.TotalSeconds; stamp=[Diagnostics.Stopwatch]::GetTimestamp()}
    } catch {}
  }
  Start-Sleep -Seconds 5
  $phase33After = [OakHostTimes]::Read()
  $phase33Total = ($phase33After[1]-$phase33Before[1])+($phase33After[2]-$phase33Before[2])
  $phase33Busy = 100*(1-($phase33After[0]-$phase33Before[0])/$phase33Total)
  $phase33External = 0.0
  foreach ($phase33Sample in $phase33Processes) {
    try {
      $phase33P=[Diagnostics.Process]::GetProcessById($phase33Sample.pid)
      $phase33Cpu=$phase33P.TotalProcessorTime.TotalSeconds
      $phase33Interval=([Diagnostics.Stopwatch]::GetTimestamp()-$phase33Sample.stamp)/[Diagnostics.Stopwatch]::Frequency
      $phase33External += ($phase33Cpu-$phase33Sample.cpu)/$phase33Interval
    } catch {}
  }
  $phase33Results += [PSCustomObject]@{sample=$phase33Index; system_busy_percent=$phase33Busy; selected_external_core_equivalents=$phase33External}
}
$phase33Quiet = (@($phase33Results | Where-Object { $_.system_busy_percent -ge 20 -or $_.selected_external_core_equivalents -ge 0.5 }).Count -eq 0)
$phase33Record=[PSCustomObject]@{recorded_utc=[DateTime]::UtcNow.ToString("o"); logical_processors=[Environment]::ProcessorCount; samples=$phase33Results; quiet_baseline=$phase33Quiet; criterion="All three five-second samples: system busy <20%, selected unrelated workload <0.5 CPU cores"; limits="Short baseline, not a scheduling bound. Selected external process names and command lines intentionally omitted. Recheck during trials."}
$phase33Record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding UTF8
$phase33Record | ConvertTo-Json -Depth 5
