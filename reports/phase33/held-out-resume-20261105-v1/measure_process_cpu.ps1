param([string]$Output)
$ErrorActionPreference='Stop'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class OakAttributionTimes {
 [DllImport("kernel32.dll")] public static extern bool GetSystemTimes(out long i,out long k,out long u);
 public static long[] Read(){long i,k,u;if(!GetSystemTimes(out i,out k,out u))throw new Exception("GetSystemTimes failed");return new long[]{i,k,u};}
}
"@
function Snapshot {
 $items=@{}
 foreach($p in Get-Process){
  try{$identity=$p.StartTime.ToUniversalTime().Ticks; $cpu=$p.TotalProcessorTime.TotalSeconds; $items[[string]$p.Id]=@{pid=$p.Id;name=$p.ProcessName;start_ticks=$identity;cpu=$cpu;working_set=$p.WorkingSet64}}catch{}
 }
 return $items
}
$records=@()
for($index=0;$index -lt 3;$index++){
 $before=Snapshot; $t0=[Diagnostics.Stopwatch]::GetTimestamp(); $system0=[OakAttributionTimes]::Read()
 Start-Sleep -Seconds 5
 $system1=[OakAttributionTimes]::Read();$elapsed=([Diagnostics.Stopwatch]::GetTimestamp()-$t0)/[Diagnostics.Stopwatch]::Frequency;$after=Snapshot
 $rows=@()
 foreach($key in $after.Keys){if($before.ContainsKey($key) -and $before[$key].start_ticks -eq $after[$key].start_ticks){$cores=($after[$key].cpu-$before[$key].cpu)/$elapsed;if($cores -ge 0){$rows += [PSCustomObject]@{pid=$after[$key].pid;name=$after[$key].name;start_ticks=$after[$key].start_ticks;cpu_core_equivalents=$cores;percent_of_host=100*$cores/[Environment]::ProcessorCount;working_set_bytes=$after[$key].working_set}}}}
 $total=($system1[1]-$system0[1])+($system1[2]-$system0[2]);$busy=100*(1-($system1[0]-$system0[0])/$total)
 $records += [PSCustomObject]@{sample=$index;interval_seconds=$elapsed;system_busy_percent=$busy;processes=@($rows|Sort-Object cpu_core_equivalents -Descending)}
}
$result=[PSCustomObject]@{recorded_utc=[DateTime]::UtcNow.ToString('o');logical_processors=[Environment]::ProcessorCount;samples=$records;limits='Current interval measurements only; inaccessible/new/exited processes may be missing. Does not establish the cause of the historical spike.'}
$result|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $Output -Encoding utf8
foreach($s in $records){Write-Output "Sample $($s.sample): host $($s.system_busy_percent)%";$s.processes|Select-Object -First 8 name,pid,cpu_core_equivalents,percent_of_host|Format-Table}
