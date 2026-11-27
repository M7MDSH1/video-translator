"""Looks on GitHub for a newer version of this app and installs it. Standard library only.

The check is one anonymous request that names only the commit this copy was built from; nothing about the user or their videos is sent.
"""
import io,json,re,shutil,subprocess,sys,tempfile,time,urllib.error,urllib.request,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPO='M7MDSH1/video-translator'
SHA=re.compile(r'[0-9a-f]{40}')

def download(url):
    request=urllib.request.Request(url,headers={'User-Agent':'video-translator','Accept':'application/vnd.github+json'})
    try:
        with urllib.request.urlopen(request,timeout=8) as reply:return reply.read()
    except urllib.error.HTTPError as error:
        if error.code==404:raise LookupError(url) from None
        raise

def fetch(url):return json.loads(download(url))

def git_head(root=ROOT):
    """The checked-out commit of a git copy, or None."""
    try:out=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).stdout.strip()
    except (OSError,subprocess.SubprocessError):return None
    return out if SHA.fullmatch(out) else None

def installed(root=ROOT):
    """(commit, from_zip). A ZIP download carries its commit in VERSION, which git fills in when GitHub makes the archive."""
    try:text=(Path(root)/'VERSION').read_text(encoding='utf-8').strip()
    except OSError:text=''
    return (text,True) if SHA.fullmatch(text) else (git_head(root),False)

def check(root=ROOT,fetch=fetch):
    """{'sha','message'} when GitHub has a newer desktop app than this copy, else None. Never raises: no network just means no news."""
    mine,from_zip=installed(root)
    if not mine:return None
    try:reply=fetch(f'https://api.github.com/repos/{REPO}/compare/{mine}...main')
    except LookupError:
        # GitHub does not know this commit. For a git copy that is unpushed local work; a ZIP copy is simply too old to compare.
        return {'sha':'main','message':''} if from_zip else None
    except (OSError,ValueError):return None
    try:
        commits=reply['commits']
        # A push that only touched the phone app (or its build) is not a desktop update.
        if not reply['ahead_by'] or all(f['filename'].startswith(('android/','.github/')) for f in reply['files']):return None
        return {'sha':commits[-1]['sha'],'message':commits[-1]['commit']['message'].splitlines()[0]}
    except (KeyError,IndexError,TypeError,AttributeError):return None

def apply(sha,root=ROOT):
    """Brings this copy up to [sha]. Only files that are part of the app are written; projects, exports, models and the Python environment are not in the download."""
    root=Path(root)
    if (root/'.git').exists():
        # A git copy may hold the owner's own changes: let git merge, never overwrite.
        subprocess.run(['git','pull','--ff-only','origin','main'],cwd=root,check=True);return
    if sha!='main' and not SHA.fullmatch(sha):raise ValueError('Unknown version')
    data=download(f'https://github.com/{REPO}/archive/{sha}.zip')
    before=(root/'requirements.txt').read_bytes() if (root/'requirements.txt').exists() else b''
    with tempfile.TemporaryDirectory() as temp:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:archive.extractall(temp)  # whole download unpacked before anything is replaced
        top=next(Path(temp).iterdir())
        shutil.copytree(top,root,dirs_exist_ok=True)
    if (root/'requirements.txt').read_bytes()!=before:
        subprocess.run([sys.executable,'-m','pip','install','-r',str(root/'requirements.txt')],cwd=root,check=True)

def main():
    """Run in its own console by the app's Update button: update, then start the app again."""
    try:
        print('Updating Video Translator...',flush=True);time.sleep(2)  # let the app finish closing
        apply(sys.argv[1]);print('Updated. Starting the app...',flush=True)
    except Exception as error:
        print(f'\nThe update did not finish: {error}\nNothing you made was touched. You can try again from the app.',flush=True);input('Press Enter to close.');return
    subprocess.Popen([str(ROOT/'.venv'/'Scripts'/'pythonw.exe'),'-m','videotranslator.app'],cwd=ROOT)

if __name__=='__main__':main()
