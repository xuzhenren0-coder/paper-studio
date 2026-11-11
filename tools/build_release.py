"""Allowlist-only distribution builder. Never includes the working .local DB or papers."""
import argparse,hashlib,importlib.util,importlib.metadata,json,os,shutil,sys,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VERSION='0.1.2'
PY_VERSION='3.14.10'
PY_URL=f'https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip'
PY_SHA='90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
FILES=['evidence_feedback.py','server.py','learning_flow.py','discovery.py','discovery_learning.py','discovery_venues.py','start.ps1','stop.ps1','launcher-common.ps1','启动研读.cmd','停止研读.cmd','requirements.txt','LICENSE','NOTICE','THIRD_PARTY_NOTICES.md','.gitignore']
WEB=['evidence-anchor.js','feedback-view.js','index.html','workspace.js','learning-flow.js','study.css','reader.js','reader.css','text-layer.css','discovery-ui.js','discovery-enhancements.js','discovery.css','members.html','members.js','members.css']
MAILING=['__init__.py','core.py','aliyun.py','store.py','demo.py','README.md','member_bridge.py','secret_config.py']

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
def safe_extract(archive,target):
    target=target.resolve()
    with zipfile.ZipFile(archive) as z:
        if any(not (target/n).resolve().is_relative_to(target) for n in z.namelist()):raise ValueError('Archive contains unsafe paths')
        z.extractall(target)
def archive(folder,target):
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6,strict_timestamps=False) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(folder.parent))
def build(pdfjs,output):
    output=output.resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Build outputs must remain within this workspace')
    output.mkdir(parents=True,exist_ok=True)
    staging=output/f'PaperStudio-{VERSION}-windows-x64'
    # No deletion: a rerun gets its own staging directory, preserving earlier results.
    if staging.exists():
        import time
        staging=output/(staging.name+'-'+str(time.time_ns()))
    staging.mkdir()
    for name in FILES:copy(ROOT/name,staging/name)
    copy(ROOT/('README-release.md' if (ROOT/'README-release.md').exists() else 'README.md'),staging/'README.md')
    copy(ROOT/'RELEASE_NOTES.md',staging/'RELEASE_NOTES.md')
    for name in WEB:copy(ROOT/'web'/name,staging/'web'/name)
    for name in MAILING:copy(ROOT/'mailing'/name,staging/'mailing'/name)
    copy(ROOT/'tools/preview_morning_mail.py',staging/'tools/preview_morning_mail.py')
    if not pdfjs.is_dir():raise ValueError('Provide pdfjs-dist 5.6.205 via --pdfjs')
    metadata=json.loads((pdfjs/'package.json').read_text(encoding='utf-8'))
    if metadata['version']!='5.6.205':raise ValueError('Expected pdfjs-dist 5.6.205')
    for name in ['LICENSE','package.json','build/pdf.mjs','build/pdf.worker.mjs']:copy(pdfjs/name,staging/'vendor/pdfjs'/name)
    for name in ['cmaps','standard_fonts','wasm','iccs']:
        shutil.copytree(pdfjs/name,staging/'vendor/pdfjs'/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    package=Path(importlib.util.find_spec('pypdf').origin).parent
    if importlib.metadata.version('pypdf')!='6.10.0':raise ValueError('Expected pypdf 6.10.0')
    license_file=package.parent/'pypdf-6.10.0.dist-info/licenses/LICENSE'
    copy(license_file,staging/'licenses/pypdf-LICENSE.txt')
    # Source distribution has no embedded interpreter, personal assets, or private history.
    source=output/f'paper-studio-{VERSION}-source'
    if source.exists():
        import time
        source=output/(source.name+'-'+str(time.time_ns()))
    shutil.copytree(staging,source)
    copy(ROOT/'tools/build_release.py',source/'tools/build_release.py')
    copy(ROOT/'tools/verify_release.py',source/'tools/verify_release.py')
    for name in ['test_server.py','test_evidence_feedback.py','test_evidence_anchor.mjs','test_discovery.py','test_discovery_learning.py','test_learning_flow.py','test_morning_mail.py','preview_discovery.py']:
        copy(ROOT/'tests'/name,source/'tests'/name)
    copy(ROOT/'tests/fixtures/evidence_learning_cases.json',source/'tests/fixtures/evidence_learning_cases.json')
    # Publish authored subscription and cloud modules without machine-local configuration.
    for path in sorted((ROOT/'mailing').glob('*.py')):
        copy(path,source/'mailing'/path.name)
    for directory in ['app','components','hooks','lib','scripts','worker','drizzle','db','vendor','public']:
        folder=ROOT/'subscription-web'/directory
        if folder.exists():
            for path in sorted(folder.rglob('*')):
                if path.is_file() and path.suffix in ('.ts','.tsx','.mts','.mjs','.js','.css','.sql','.json','.sh','.svg','.LICENSE'):
                    copy(path,source/'subscription-web'/path.relative_to(ROOT/'subscription-web'))
    for name in ['package.json','pnpm-lock.yaml','pnpm-workspace.yaml','next.config.ts','vite.config.ts','tsconfig.json','eslint.config.mjs','postcss.config.ts','postcss.config.mjs','drizzle.config.ts','.gitignore']:
        path=ROOT/'subscription-web'/name
        if path.is_file():copy(path,source/'subscription-web'/name)
    copy(ROOT/'README-subscription.md',source/'subscription-web/README.md')
    copy(ROOT/'README-subscription.md',source/'README-subscription.md')
    hosting=source/'subscription-web/.openai/hosting.json'
    hosting.parent.mkdir(parents=True,exist_ok=True)
    hosting.write_text(json.dumps({'d1':'DB','r2':None},indent=2)+'\n',encoding='utf-8')
    download=ROOT/'build/downloads'/f'python-{PY_VERSION}-embed-amd64.zip'
    download.parent.mkdir(parents=True,exist_ok=True)
    if not download.exists():
        with urllib.request.urlopen(PY_URL,timeout=60) as r:download.write_bytes(r.read(40*1024*1024))
    if sha(download)!=PY_SHA:raise ValueError('Official Python archive SHA256 mismatch; will not execute')
    safe_extract(download,staging/'runtime')
    (staging/'runtime/python314._pth').write_text('python314.zip\n.\nLib/site-packages\n..\n',encoding='ascii')
    target=staging/'runtime/Lib/site-packages'
    shutil.copytree(package,target/'pypdf',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copytree(package.parent/'pypdf-6.10.0.dist-info',target/'pypdf-6.10.0.dist-info')
    provenance={'version':VERSION,'python':PY_VERSION,'python_url':PY_URL,'python_sha256':PY_SHA,'pypdf':'6.10.0','pdfjs':'5.6.205','license':'PolyForm-Noncommercial-1.0.0'}
    (staging/'BUILD-INFO.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
    for folder in [source,staging]:
        manifest={str(p.relative_to(folder)).replace('\\','/'):sha(p) for p in sorted(folder.rglob('*')) if p.is_file()}
        (folder/'SHA256-MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf-8')
    portable_zip=output/f'PaperStudio-{VERSION}-windows-x64.zip';source_zip=output/f'paper-studio-{VERSION}-source.zip'
    archive(staging,portable_zip);archive(source,source_zip)
    (output/'SHA256SUMS.txt').write_text('\n'.join(f'{sha(p)}  {p.name}' for p in [portable_zip,source_zip])+'\n',encoding='ascii')
    print(json.dumps({'portable':str(portable_zip),'source':str(source_zip),'staging':str(staging),'source_staging':str(source),'sha256':sha(portable_zip)},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--pdfjs',type=Path,default=ROOT/'vendor/pdfjs');parser.add_argument('--output',type=Path,default=ROOT/'dist');args=parser.parse_args()
    build(args.pdfjs,args.output)
