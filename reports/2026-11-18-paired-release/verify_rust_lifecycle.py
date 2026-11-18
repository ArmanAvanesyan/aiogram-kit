import json,subprocess
from pathlib import Path
base=Path('/tmp/kit-paired-release-20261118');data=json.loads(Path('/Users/armanavanesyan/oss/own/aiogram-kit/reports/2026-11-18-native-parallel-qualification/standalone-final-verification.json').read_text());rows=[]
for r in data['results']:
 code=r['script'].split('checks = asyncio.run(smoke())',1)[0]
 code=code.replace('config=IdleConfig(enabled=True), storage_format=3','config=IdleConfig(enabled=True, engine="rust"), storage_format=3').replace('MemoryNavigationRepository(clock=ManualClock(1000), storage_format=3)','MemoryNavigationRepository(clock=ManualClock(1000), engine="rust", storage_format=3)')
 code+='checks = asyncio.run(smoke())\nprint(json.dumps(checks))\n'
 py=base/'installs'/(r['package']+'-paired')/'bin/python';result=subprocess.run([str(py),'-I','-c',code],cwd=base,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 rows.append({'package':r['package'],'profile':'public-rust-memory-lifecycle','script':code,'exit_code':result.returncode,'output':result.stdout});print(r['package'],result.returncode,flush=True)
 if result.returncode:raise SystemExit(result.stdout)
(base/'public-rust-lifecycle-verification.json').write_text(json.dumps(rows,indent=2)+'\n')
