from pathlib import Path
import subprocess,json,hashlib,concurrent.futures
BASE=Path('/tmp/kit-paired-release-20261118');UV='/usr/local/bin/uv'
def verify(short):
 name='aiogram-'+short;version='1.3.2' if short=='sentinel' else '0.3.2';mod=name.replace('-','_');native_mod='_'+mod+'_native' if short in ('sentinel','cmds') else mod+'_native';rows=[]
 sdk=next((BASE/'artifacts'/name).glob('*.whl'));native=next((BASE/'reviewed-release-artifacts'/(name+'-native')).glob('*macosx*_x86_64.whl'));sdist=next((BASE/'reviewed-release-artifacts'/(name+'-native')).glob('*.tar.gz'))
 def run(args):
  r=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
  if r.returncode:raise RuntimeError(f'{name}: {args}\n{r.stdout}')
  return r.stdout
 def env(suffix,files):
  target=BASE/'installs'/(name+suffix);run([UV,'venv','--clear','--python','3.12',str(target)]);py=str(target/'bin/python');run([UV,'pip','install','--python',py,*map(str,files)]);run([UV,'pip','check','--python',py]);return py
 loader={'sentinel':'from aiogram_sentinel.native import load_native; load_native()','cmds':'from aiogram_cmds.engines import native_engine; native_engine("rust")','nav':'from aiogram_nav.engine import require_engine; require_engine("rust")','idle':'from aiogram_idle.engines import require_engine; require_engine("rust")'}[short]
 for suffix,files,source in [('-ci-native-only',[native],native),('-ci-paired',[sdk,native],native),('-ci-source',[sdist],sdist)]:
  py=env(suffix,files);code=f'import importlib,importlib.util,importlib.metadata as m; importlib.import_module({native_mod!r}); assert m.version({name+"-native"!r})=={version!r}; assert not m.requires({name+"-native"!r})\n'
  if suffix=='-ci-paired':code+=f'assert m.version({name!r})=={version!r}\n'+loader+'\n'
  else:code+=f'assert importlib.util.find_spec({mod!r}) is None\n'
  code+='assert importlib.util.find_spec("redis") is None\n'
  run([py,'-I','-c',code]);rows.append({'package':name,'profile':suffix,'result':'pass','artifact':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()})
  print(name,suffix,'PASS',flush=True)
 source=next((BASE/'artifacts'/name).glob('*.tar.gz'));py=str(BASE/'installs'/(name+'-sdist')/'bin/python');run([UV,'pip','install','--reinstall','--python',py,str(source)])
 run([py,'-I','-c',f'import importlib,importlib.util,importlib.metadata as m; assert m.version({name!r})=={version!r}; assert importlib.util.find_spec("redis") is None; assert importlib.util.find_spec({native_mod!r}) is None; importlib.import_module({mod!r})'])
 rows.append({'package':name,'profile':'final-sdk-source-archive','result':'pass','artifact':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()});return rows
rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for result in pool.map(verify,['sentinel','cmds','nav','idle']):rows.extend(result)
(BASE/'shipping-install-verification.json').write_text(json.dumps(rows,indent=2)+'\n');print('ALL',len(rows),'SHIPPING PROFILES PASS')
