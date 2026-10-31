#!/usr/bin/env bash
set -eo pipefail
output="$1"
prefix="${2:?Supply the fresh installed runtime prefix}"
mkdir "$output"
temporary=$(mktemp -d /dev/shm/oak-timing-overhead.XXXXXX)
"$prefix/lib/oak_nav_trace/oak_trace_benchmark" > "$output/native-disabled.json"
OAK_TIMING_DIR="$temporary" "$prefix/lib/oak_nav_trace/oak_trace_benchmark" > "$output/native-enabled.json"
python3 - "$output" "$temporary" <<'PY'
import importlib.util,json,os,sys,time,statistics
from pathlib import Path
output,root=map(Path,sys.argv[1:])
spec=importlib.util.spec_from_file_location('timing','/mnt/d/Projects/OakGPT/robotics/ros2_ws/src/oak_mission/oak_mission/timing.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
summary={}
for enabled in [False,True]:
    if enabled: os.environ['OAK_TIMING_DIR']=str(root)
    else: os.environ.pop('OAK_TIMING_DIR',None)
    recorder=module.Timing(); samples=[]
    for i in range(20000):
        begin=time.clock_gettime_ns(time.CLOCK_BOOTTIME)
        recorder.record('overhead_probe',sequence=i)
        samples.append(time.clock_gettime_ns(time.CLOCK_BOOTTIME)-begin)
    samples.sort()
    summary[str(enabled)]={'samples':len(samples),'median_ns':samples[10000],'p99_ns':samples[19800],'max_ns':samples[-1],'errors':recorder.errors}
    if recorder.fd is not None: os.close(recorder.fd)
native=list(root.glob('native-*'))
assert len(native)==1
rows=[json.loads(line) for line in native[0].read_text().splitlines()]
assert len(rows)==20000
assert all(a['boot_ns']<=b['boot_ns'] and a['mono_ns']<=b['mono_ns'] for a,b in zip(rows,rows[1:]))
(output/'python.json').write_text(json.dumps(summary,indent=2))
(output/'semantics.json').write_text(json.dumps({'native_records':len(rows),'clock_order_passed':True,'clock_domains':'same Linux kernel BOOTTIME / MONOTONIC; no DDS clock subtraction'}))
PY
cp "$temporary"/*.jsonl "$output/"
