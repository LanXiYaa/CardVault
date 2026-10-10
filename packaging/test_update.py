"""Exercise a real 2.1 -> 2.2 installer update in an isolated directory."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cardvault.updater import stage_package, launch_update
import winreg
try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Microsoft\Windows\CurrentVersion\Uninstall\{1753D345-8BBB-4849-B0A2-914F0CCFF875}_is1'):
        raise SystemExit('An existing user installation must be preserved; skip destructive installer test.')
except FileNotFoundError:
    pass
folder=ROOT/'.test-data'/('升级测试-'+str(time.time_ns()))
app=folder/'CardVault';app.parent.mkdir(parents=True)
shutil.copytree(ROOT/'release/CardVault-2.1.0-Windows-x64',app)
state=folder/'state';state.mkdir()
(state/'keep.txt').write_text('preserve user history',encoding='utf-8')
package=stage_package(ROOT/'release/CardVault-2.2.1-Setup-x64.exe',app,current='2.1.0')
env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','QT_','PYSIDE','VIRTUAL_ENV','_PYI'))}
env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
env['QT_QPA_PLATFORM']='offscreen'
old=subprocess.Popen([str(app/'CardVault.exe'),'--self-test',str(folder/'old-test.json')],env=env,cwd=app)
report=folder/'new-test.json'
helper=launch_update(package,app,state,parent_pid=old.pid,restart_args=['--self-test',str(report)])
assert old.wait(timeout=60)==0
assert helper.wait(timeout=120)==0
for _ in range(200):
    if report.exists():break
    time.sleep(.1)
result=json.loads(report.read_text(encoding='utf-8'))
assert result['ok'] and result['version']=='2.2.1',result
assert result['verified_copies']==6
assert (state/'keep.txt').read_text(encoding='utf-8')=='preserve user history'
update=json.loads((app/'update/update-result.json').read_text(encoding='utf-8-sig'))
assert update['status']=='completed',update
result['update']=update
result['history_preserved']=True
result['installer_retained']=Path(package['package']).is_file()
(ROOT/'artifacts').mkdir(exist_ok=True)
(ROOT/'artifacts/2.2-update-test.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
# Only remove this isolated installation, never the user's installed application.
uninstall=subprocess.run([str(app/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],timeout=60)
assert uninstall.returncode==0
print(json.dumps({'update':'passed','version':result['version'],'verified_copies':result['verified_copies'],'history_preserved':True}))
