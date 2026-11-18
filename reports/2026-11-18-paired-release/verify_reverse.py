from pathlib import Path
import subprocess,json
BASE=Path('/tmp/kit-paired-release-20261118');UV='/usr/local/bin/uv';rows=[]
for short,old in [('sentinel','1.3.1'),('cmds','0.3.1'),('nav','0.3.1'),('idle','0.3.1')]:
 name='aiogram-'+short;target=BASE/'installs'/(name+'-old-sdk');py=str(target/'bin/python')
 def run(args):
  r=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode:raise RuntimeError(r.stdout)
  return r.stdout
 run([UV,'venv','--clear','--python','3.12',str(target)])
 run([UV,'pip','install','--python',py,name+'=='+old,str(next((BASE/'artifacts'/(name+'-native')).glob('*.whl')))])
 run([UV,'pip','check','--python',py])
 loader={'sentinel':'from aiogram_sentinel.native import load_native as call','cmds':'from aiogram_cmds.engines import native_engine; call=lambda:native_engine("rust")','nav':'from aiogram_nav.engine import require_engine; call=lambda:require_engine("rust")','idle':'from aiogram_idle.engines import require_engine; call=lambda:require_engine("rust")'}[short]
 run([py,'-I','-c',loader+'''\ntry:call()
except Exception as e:assert 'incompatible' in str(e).lower() or 'matching' in str(e).lower(), str(e)
else:raise AssertionError('Old SDK accepted a newer companion')
'''])
 rows.append({'package':name,'sdk':old,'native':'1.3.2' if short=='sentinel' else '0.3.2','result':'rejected as expected'})
 print(name,'PASS',flush=True)
(BASE/'reverse-version-verification.json').write_text(json.dumps(rows,indent=2)+'\n')
