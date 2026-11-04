"""Verify the actual ZIP using its embedded interpreter and isolated learning data."""
import hashlib,json,os,subprocess,tempfile,time,urllib.request,zipfile
from pathlib import Path
from build_release import VERSION

ROOT=Path(__file__).resolve().parents[1]
def main():
    directory=Path(tempfile.mkdtemp(prefix='发布包 验证 ',dir=ROOT/'test-results'))
    archive=ROOT/f'dist/PaperStudio-{VERSION}-windows-x64.zip'
    with zipfile.ZipFile(archive) as z:
        paths=z.namelist()
        assert not any('/.local/' in n or '/backups/' in n or '/samples/' in n or n.lower().endswith(('.pdf','.sqlite3')) for n in paths)
        assert all((directory/n).resolve().is_relative_to(directory.resolve()) for n in paths)
        z.extractall(directory)
    app=next(p for p in directory.iterdir() if p.is_dir())
    manifest=json.loads((app/'SHA256-MANIFEST.json').read_text(encoding='utf-8'))
    for path,expected in manifest.items():assert hashlib.sha256((app/path).read_bytes()).hexdigest()==expected,path
    env=dict(os.environ,PAPER_DATA_DIR=str(directory/'隔离学习数据'),PAPER_NODE_MODULES=str(directory/'不存在的Node目录'),PYTHONPATH=str(directory/'不存在的系统Python'))
    python=app/'runtime/python.exe'
    check=subprocess.run([str(python),'-c','import sys,pypdf,server; print(sys.version); print(pypdf.__version__); print(server.PDFJS_ROOT)'],cwd=app,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
    assert check.returncode==0,check.stderr
    powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    def launcher(script):
        print('Checking '+script,flush=True)
        # Detached Windows children can inherit PIPE handles; use a file so EOF cannot hang the harness.
        with (directory/'launcher-test.log').open('ab') as log:
            result=subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(app/script),'-Port','8767','-DataDirectory',env['PAPER_DATA_DIR'],*(['-NoBrowser'] if script=='start.ps1' else [])],cwd=app,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,timeout=45)
        assert result.returncode==0,(directory/'launcher-test.log').read_bytes().decode(errors='replace')
        return result
    def request(path,body=None,raw=False):
        headers={'X-Local-Request':'1','Content-Type':'application/pdf' if raw else 'application/json'}
        data=body if raw else json.dumps(body).encode() if body is not None else None
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8767'+path,data=data,headers=headers),timeout=15) as r:
            content=r.read();return content if raw else json.loads(content)
    launcher('start.ps1')
    try:
        assert request('/api/health')['instance']
        assert request('/api/papers')==[]
        for name in ['/vendor/pdf.mjs','/vendor/pdf.worker.mjs','/vendor/wasm/openjpeg.wasm','/vendor/standard_fonts/FoxitSerif.pfb','/vendor/cmaps/Adobe-GB1-UCS2.bcmap']:
            assert len(request(name,raw=True))>100,name
        paper=request('/api/upload',(ROOT/'samples/vehicle-control.pdf').read_bytes(),raw=True)
        # raw=True returns bytes; the upload response is JSON.
        paper=json.loads(paper)
        assert len(paper['pages'])==14
        request('/api/notes',{'paper_id':paper['id'],'body':{'personalNotes':'便携包保存验证'}})
        launcher('start.ps1') # idempotent start reuses only this exact app+data instance
        launcher('stop.ps1');launcher('start.ps1')
        assert request('/api/papers/'+paper['id']+'/notes')['body']['personalNotes']=='便携包保存验证'
        launcher('stop.ps1')
        # Run a moved/extracted update against the same data; never migrate user data silently.
        with zipfile.ZipFile(archive) as z:z.extractall(directory/'新版程序')
        app=next(p for p in (directory/'新版程序').iterdir() if p.is_dir())
        launcher('start.ps1')
        assert request('/api/papers/'+paper['id']+'/notes')['body']['personalNotes']=='便携包保存验证'
        report={'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'app':str(app),'data':env['PAPER_DATA_DIR'],'pdf_pages':len(paper['pages']),'file_hashes_verified':len(manifest),'result':'PASS','checks':['embedded Python + pypdf without Codex/Node','Chinese and space paths','launch and idempotent reuse','PDF.js fonts/CMap/WASM resources','real 14-page PDF upload','notes survive restart and new version folder','no bundled personal data']}
        (ROOT/'dist/verification.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:launcher('stop.ps1')

if __name__=='__main__':main()
