from pathlib import Path
import subprocess,json,hashlib,time,shutil
ROOT=Path('/Users/armanavanesyan/oss/own/aiogram-kit')
BASE=Path('/tmp/kit-paired-release-20261118')
UV='/usr/local/bin/uv'
rows=json.loads((BASE/"install-verification.json").read_text()) if (BASE/"install-verification.json").exists() else []

def run(args,cwd=None):
 r=subprocess.run(args,cwd=cwd or BASE,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError(f'{args}:\n{r.stdout}')
 return r.stdout

def env(name,artifacts,python='3.12'):
 target=BASE/'installs'/name
 run([UV,'venv','--clear','--python',python,str(target)])
 py=str(target/'bin/python')
 run([UV,'pip','install','--python',py,*map(str,artifacts)])
 run([UV,'pip','check','--python',py])
 return py

for short,new,old in [('sentinel','1.3.2','1.3.1'),('cmds','0.3.2','0.3.1'),('nav','0.3.2','0.3.1'),('idle','0.3.2','0.3.1')]:
 if any(r['package']=='aiogram-'+short and r['profile']=='native-source-rebuild-install' for r in rows):continue
 name='aiogram-'+short;mod=name.replace('-','_');native_mod='_'+mod+'_native' if short in ('sentinel','cmds') else mod+'_native'
 directory=BASE/'artifacts'/name;native_dir=BASE/'artifacts'/(name+'-native')
 wheel=next(directory.glob('*.whl'));sdist=next(directory.glob('*.tar.gz'));native=next(native_dir.glob('*.whl'));nsdist=next(native_dir.glob('*.tar.gz'))
 loader={'sentinel':'import aiogram_sentinel.native as loader; call=loader.load_native','cmds':'import aiogram_cmds.engines as loader; call=lambda:loader.native_engine("rust")','nav':'import aiogram_nav.engine as loader; call=lambda:loader.require_engine("rust")','idle':'import aiogram_idle.engines as loader; call=lambda:loader.require_engine("rust")'}[short]
 common=f'''import importlib, importlib.util, importlib.metadata as md, json, sys
assert md.version({name!r}) == {new!r}
module=importlib.import_module({mod!r});assert module.__version__ == {new!r}
assert '/site-packages/' in module.__file__
for absent in ['redis']+[p for p in ['aiogram_sentinel','aiogram_cmds','aiogram_nav','aiogram_idle'] if p!={mod!r}]:
 assert importlib.util.find_spec(absent) is None, absent
{loader}
'''
 for kind,artifact in [('wheel',wheel),('sdist',sdist)]:
  py=env(name+'-'+kind,[artifact]);code=common+'''try:call()
except (RuntimeError,ValueError,ImportError) as error:assert 'native' in str(error).lower()
else:raise AssertionError('Rust selection without companion must fail')
print(json.dumps({'version':md.version('''+repr(name)+'''), 'module':module.__file__}))
'''
  # ConfigurationError may be a library-specific Exception hierarchy.
  code=code.replace('except (RuntimeError,ValueError,ImportError) as error:','except Exception as error:')
  data=json.loads(run([py,'-I','-c',code]));rows.append({'package':name,'profile':'standalone-'+kind,'result':'pass',**data});print(name,kind,'PASS',flush=True)
 py=env(name+'-native-only',[native]);data=run([py,'-I','-c',f'''import importlib,importlib.util,importlib.metadata as md,json
assert importlib.util.find_spec({mod!r}) is None
m=importlib.import_module({native_mod!r});assert md.version({name+'-native'!r})=={new!r}
assert not md.requires({name+'-native'!r})
print(json.dumps({{'version':md.version({name+'-native'!r}),'module':m.__file__}}))''']);rows.append({'package':name,'profile':'native-only','result':'pass',**json.loads(data)})
 py=env(name+'-paired',[wheel,native]);fakever={'sentinel':f'fake.capabilities=lambda:({name+"-native"!r},1,{old!r})','cmds':f'fake.version=lambda:{old!r}','nav':f'fake.ENGINE_VERSION={old!r}','idle':f'fake.ENGINE_VERSION={old!r}'}[short]
 code=common+f'''call()
n=importlib.import_module({(native_mod+'.'+('_'+mod+'_native') if short in ('nav','idle') else native_mod)!r})
from types import SimpleNamespace
fake=SimpleNamespace(**vars(n))
{fakever}
sys.modules[{(native_mod+'.'+('_'+mod+'_native') if short in ('nav','idle') else native_mod)!r}]=fake
'''+('loader._load_native.cache_clear()\n' if short=='cmds' else 'loader.native_core.cache_clear()\n' if short in ('nav','idle') else '')+'''try:call()
except Exception as error:assert 'incompatible' in str(error).lower() or 'matching' in str(error).lower()
else:raise AssertionError('Previous native version must be rejected')
print(json.dumps({'version':module.__version__, 'module':module.__file__}))
'''
 data=json.loads(run([py,'-I','-c',code]));rows.append({'package':name,'profile':'paired-and-previous-version-rejection','result':'pass',**data});print(name,'paired/native-only PASS',flush=True)
 # Build from the source archive outside the workspace with its own Cargo.lock.
 destination=BASE/'native-sdist-wheels'/name;destination.mkdir(parents=True,exist_ok=True)
 run([UV,'build','--wheel','--out-dir',str(destination),str(nsdist)])
 py=env(name+'-native-sdist',[next(destination.glob('*.whl'))]);run([py,'-I','-c',f'import importlib,importlib.metadata as md;importlib.import_module({native_mod!r});assert md.version({name+"-native"!r})=={new!r}'])
 rows.append({'package':name,'profile':'native-source-rebuild-install','result':'pass'});print(name,'native source PASS',flush=True)
 (BASE/'install-verification.json').write_text(json.dumps(rows,indent=2)+'\n')
print('ALL',len(rows),'PROFILES PASSED')
