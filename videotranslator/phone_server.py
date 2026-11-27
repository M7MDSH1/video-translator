"""Phone mode: receive a video from the phone app over Wi-Fi, translate it here, and serve the result.

Standard library only. One job at a time. Every request except the hello and pairing needs a token,
which the phone gets by sending the six-digit code shown on this PC.
"""
import json,os,re,secrets,shutil,socket,subprocess,sys,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .project import ROOT,LANGUAGES,new_project,save_project,load_project
from .models import local_models

PORT=8756
CHUNK=1<<20
STAGES=('receive','recognize','translate','export','done')
CREATE_NO_WINDOW=0x08000000 if os.name=='nt' else 0

def lan_address():
    """This PC's address on the local network. Connecting a UDP socket sends nothing; it only picks the route."""
    probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:probe.connect(('192.168.0.1',9));return probe.getsockname()[0]
    except OSError:return '127.0.0.1'
    finally:probe.close()

def safe_name(name):
    """A plain file name from whatever the phone sent: no folders, no reserved characters."""
    name=re.sub(r'[\\/:*?"<>|\x00-\x1f]','_',Path(str(name).replace('\\','/')).name).strip(' .')[:80]
    return name if Path(name).suffix.lower() in ('.mp4','.mkv','.mov','.avi','.webm','.m4v') else (name or 'video')+'.mp4'

class PhoneServer:
    def __init__(self,root=ROOT,port=PORT,host='0.0.0.0'):
        self.root=Path(root);self.code=f'{secrets.randbelow(10**6):06d}';self.lock=threading.Lock()
        self.token_file=self.root/'runtime'/'phone_tokens.json'
        try:self.tokens=set(json.loads(self.token_file.read_text(encoding='utf-8')))
        except (OSError,ValueError):self.tokens=set()
        self.failed=0;self.locked_until=0.;self.proc=None
        # Each job has its own stop flag, so a cancel can never be undone by the next upload. [busy] stays set until
        # the job's worker has cleaned up: a cancelled job that is still stopping must not share the PC with a new one.
        self.stop_flag=threading.Event();self.busy=False
        self.job={'state':'idle','stage':'','progress':0,'message':'','name':'','size':0,'id':''}
        server=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            timeout=60  # a phone that drops off Wi-Fi mid-upload must not hold the job forever
            def log_message(self,*a):pass
            def do_GET(self):server.route(self,'GET')
            def do_POST(self):server.route(self,'POST')
            def do_PUT(self):server.route(self,'PUT')
        self.httpd=ThreadingHTTPServer((host,port),Handler);self.httpd.daemon_threads=True
        self.port=self.httpd.server_address[1]
    def start(self):threading.Thread(target=self.httpd.serve_forever,daemon=True).start();return self
    def stop(self):
        self.cancel();self.httpd.shutdown();self.httpd.server_close()
    def address(self):return f'{lan_address()}:{self.port}'

    # --- replies
    def send(self,h,status,body=None):
        data=json.dumps(body or {}).encode()
        h.send_response(status);h.send_header('Content-Type','application/json');h.send_header('Content-Length',str(len(data)));h.end_headers();h.wfile.write(data)
    def set(self,**changes):
        with self.lock:self.job.update(changes)
    def status(self):
        with self.lock:return {k:v for k,v in self.job.items() if k!='result'}  # the PC's file path stays on the PC

    def route(self,h,method):
        url=urlparse(h.path);query={k:v[0] for k,v in parse_qs(url.query).items()};path=url.path
        try:
            if (method,path)==('GET','/'):return self.send(h,200,{'app':'video-translator','api':1,'name':socket.gethostname()})
            if (method,path)==('POST','/pair'):return self.pair(h)
            if h.headers.get('Authorization','')[7:] not in self.tokens or not h.headers.get('Authorization','').startswith('Bearer '):
                return self.send(h,401,{'error':'Not paired with this PC. Enter the code shown on the PC.'})
            if (method,path)==('GET','/status'):return self.send(h,200,self.status())
            if (method,path)==('GET','/options'):
                return self.send(h,200,{'languages':[{'name':name,'code':code} for name,code in LANGUAGES.items()],'models':['auto']+local_models(),'model':'auto'})  # 'auto': the PC picks per language
            if (method,path)==('PUT','/upload'):return self.upload(h,query)
            if (method,path)==('GET','/result'):return self.result(h,query.get('id'))
            if (method,path)==('POST','/cancel'):self.cancel();return self.send(h,200,self.status())
            self.send(h,404,{'error':'Unknown request'})
        except (ConnectionError,TimeoutError):pass  # the phone went away mid-transfer; the job state already says so

    def pair(self,h):
        length=int(h.headers.get('Content-Length') or 0)
        if length>1000:return self.send(h,413,{'error':'Request too large'})
        try:code=str(json.loads(h.rfile.read(length) or b'{}').get('code',''))
        except ValueError:code=''
        if time.time()<self.locked_until:return self.send(h,429,{'error':'Too many wrong codes. Wait a minute and try again.'})
        if not secrets.compare_digest(code,self.code):
            self.failed+=1
            if self.failed>=5:self.failed=0;self.locked_until=time.time()+60
            return self.send(h,403,{'error':'Wrong code. Check the code shown on the PC.'})
        self.failed=0;token=secrets.token_urlsafe(32);self.tokens.add(token)
        self.token_file.parent.mkdir(parents=True,exist_ok=True);self.token_file.write_text(json.dumps(sorted(self.tokens)),encoding='utf-8')
        self.send(h,200,{'token':token,'name':socket.gethostname()})

    def upload(self,h,query):
        size=int(h.headers.get('Content-Length') or 0)
        mode=query.get('mode','speech');target=query.get('target','ar');source=query.get('source','auto');model=query.get('model','')
        if mode not in ('speech','ocr') or target not in LANGUAGES.values() or target=='auto' or source not in LANGUAGES.values():return self.send(h,400,{'error':'Unknown mode or language'})
        if not re.fullmatch(r'[\w.:/-]{0,200}',model):return self.send(h,400,{'error':'Unknown translation model'})
        if size<=0:return self.send(h,411,{'error':'Empty upload'})
        # Room for the upload, the working files and the export.
        if shutil.disk_usage(self.root).free<size*3+(1<<30):return self.send(h,507,{'error':'Not enough free disk space on the PC for this video.'})
        with self.lock:
            if self.job['state'] in ('receiving','working') or self.busy:busy=True
            else:
                busy=False;self.busy=True;stop=self.stop_flag=threading.Event();name=safe_name(query.get('name','video.mp4'))
                job_id=time.strftime('%Y%m%d-%H%M%S')
                if job_id==self.job.get('id'):job_id+='-2'  # two uploads in one second must not share a job
                self.job={'state':'receiving','stage':'receive','progress':0,'message':'Receiving video','name':name,'size':size,'id':job_id}
        if busy:return self.send(h,409,{'error':'The PC is still busy with a video. Wait for it to finish or stop, then send this one.'})
        folder=self.root/'projects'/('phone-'+job_id);folder.mkdir(parents=True,exist_ok=True);video=folder/name;got=0
        try:
            with video.open('wb') as out:
                while got<size:
                    block=h.rfile.read(min(CHUNK,size-got))
                    if not block:raise ConnectionError('upload stopped')
                    # Cancelled, or replaced by a newer upload: stop taking bytes for a job nobody wants.
                    if stop.is_set():raise InterruptedError
                    out.write(block);got+=len(block);self.set(progress=round(got/size*100,1))
            with self.lock:
                # Checked again under the lock, so a cancel that lands on the last block still wins.
                if stop.is_set():raise InterruptedError
                self.job.update(state='working',stage='recognize',progress=0,message='Starting')
        except InterruptedError:
            video.unlink(missing_ok=True);self.busy=False;raise ConnectionError  # the job state already says cancelled
        except (ConnectionError,TimeoutError,OSError):
            video.unlink(missing_ok=True);self.busy=False
            self.set(state='error',message='The upload stopped before the whole video arrived. Send it again.');raise ConnectionError
        threading.Thread(target=self.work,args=(video,mode,target,source,model,stop),daemon=True).start()
        self.send(h,200,self.status())

    def launch(self,stop,args,**options):
        """Starts one of a job's processes, unless the job was cancelled. Cancel takes the same lock, so it either
        prevents the start or sees the process and stops it; it can never slip between the check and the start."""
        with self.lock:
            if stop.is_set():raise InterruptedError
            self.proc=subprocess.Popen(args,creationflags=CREATE_NO_WINDOW,**options);return self.proc

    def work(self,video,mode,target,source='auto',model='',stop=None):
        stop=stop or self.stop_flag
        try:
            from .engine import probe
            # On-screen text needs to know its alphabet; without a chosen language it is read as English.
            p=new_project(str(video),probe(video));p.update(mode=mode,target=target,source=source,ocr_script='en' if source=='auto' else source)
            # Reading subtitles off the picture also finds where they are, so the translation can cover them instead of sitting on top.
            p['appearance']='replace' if mode=='ocr' else 'add'
            if model:p['model']=model
            project=video.parent/'project.json';save_project(p,project)
            if mode=='ocr' and p['ocr_script'] not in ('en','ar'):
                # English and Arabic readers come with the app; any other is downloaded once (setup_models skips what is already there).
                self.set(message='Getting the text reader for this language')
                setup=self.launch(stop,[sys.executable,str(ROOT/'setup_models.py'),'--ocr',p['ocr_script']],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                if setup.wait():raise RuntimeError('The PC could not get the text reader for this language. Check its internet connection and try again.')
            engine=self.launch(stop,[sys.executable,'-m','videotranslator.engine','phone',str(project)],cwd=self.root,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace')
            message=''
            for line in engine.stdout:
                try:event=json.loads(line)
                except ValueError:continue
                if 'stage' in event:self.set(stage=event['stage'],progress=0)
                else:message=str(event.get('message',''));self.set(progress=event.get('progress',0),message=message)
            code=engine.wait()
            if stop.is_set():return  # cancelled at the last moment: the state already says so
            if code==0:
                result=load_project(project).get('last_export')
                if result and Path(result).is_file():
                    return self.set(state='done',stage='done',progress=100,message='Ready',result=result,result_size=Path(result).stat().st_size)
                message='Error: the export finished without a video file.'
            self.set(state='error',message=message.removeprefix('Error: ') or 'The translation stopped unexpectedly.')
        except InterruptedError:pass
        except Exception as exc:
            if not stop.is_set():self.set(state='error',message=str(exc))
        finally:
            with self.lock:
                if self.proc and self.proc.stdout:self.proc.stdout.close()
                self.proc=None;self.busy=False

    def cancel(self):
        with self.lock:
            self.stop_flag.set();proc=self.proc  # flag first: the job thread sees it before the engine dies
            if self.job['state'] in ('receiving','working'):self.job.update(state='error',message='Cancelled.')
        if proc and proc.poll() is None:
            # Stop the engine and the ffmpeg it started; terminate() alone would leave ffmpeg encoding on Windows.
            if os.name=='nt':subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=CREATE_NO_WINDOW)
            else:proc.terminate()

    def result(self,h,job_id=None):
        with self.lock:job=dict(self.job)
        path=Path(job.get('result',''))
        if job['state']!='done' or not path.is_file():return self.send(h,404,{'error':'No finished video to download.'})
        # A phone resuming a dropped download names its job; if the PC has finished another one since, it must not get that video's bytes.
        if job_id is not None and job_id!=job['id']:return self.send(h,404,{'error':'That video is no longer on the PC. Send it again.'})
        size=path.stat().st_size;start=0
        match=re.fullmatch(r'bytes=(\d+)-',h.headers.get('Range',''))  # resume after a dropped download
        if match:
            start=int(match.group(1))
            if start>=size:h.send_response(416);h.send_header('Content-Range',f'bytes */{size}');h.send_header('Content-Length','0');h.end_headers();return
        h.send_response(206 if match else 200);h.send_header('Content-Type','video/mp4');h.send_header('Accept-Ranges','bytes')
        h.send_header('Content-Length',str(size-start))
        if match:h.send_header('Content-Range',f'bytes {start}-{size-1}/{size}')
        h.end_headers()
        with path.open('rb') as source:
            source.seek(start)
            while block:=source.read(CHUNK):h.wfile.write(block)

def main():
    server=PhoneServer().start()
    print(f'Phone mode is on.\n  PC address: {server.address()}\n  Code:       {server.code}\nKeep this window open. Press Ctrl+C to stop.',flush=True)
    try:
        while True:time.sleep(1)
    except KeyboardInterrupt:server.stop()

if __name__=='__main__':main()
