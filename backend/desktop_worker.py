"""Source-bounded MCP bridge. Starting it lists capabilities, not screen contents."""
import os,sys,json,asyncio,threading
from pathlib import Path
os.environ['ANONYMIZED_TELEMETRY']='false'
os.environ['WINDOWS_MCP_WATCHDOG']='false'
import psutil

ALLOWED={'Snapshot','Screenshot','Click','Type','Scroll','Move','Shortcut','App'}
SERVER=Path(__file__).with_name('desktop_server.py')
DIRECT_LAUNCH={
    'notepad':'notepad.exe','记事本':'notepad.exe',
    'calculator':'calc.exe','calc':'calc.exe','计算器':'calc.exe',
    'file explorer':'explorer.exe','explorer':'explorer.exe','文件资源管理器':'explorer.exe','资源管理器':'explorer.exe','此电脑':'explorer.exe','我的电脑':'explorer.exe','文件夹':'explorer.exe',
    'paint':'mspaint.exe','mspaint':'mspaint.exe','画图':'mspaint.exe',
    'snipping tool':'snippingtool.exe','截图工具':'snippingtool.exe','截图':'snippingtool.exe',
    'settings':'ms-settings:','设置':'ms-settings:','系统设置':'ms-settings:',
    'microsoft edge':'msedge.exe','edge':'msedge.exe','微软浏览器':'msedge.exe','edge浏览器':'msedge.exe','浏览器':'msedge.exe',
    'google chrome':'chrome.exe','chrome':'chrome.exe','谷歌浏览器':'chrome.exe','chrome浏览器':'chrome.exe',
    'firefox':'firefox.exe','火狐浏览器':'firefox.exe',
    'quark':'quark.exe','夸克':'quark.exe','夸克浏览器':'quark.exe',
}

def kill_owned_servers():
    # Never kill applications opened by the user or by App. Only our helper.
    try:
        for process in psutil.Process().children(recursive=True):
            try:
                if any(str(SERVER).lower()==str(x).lower() for x in process.cmdline()):process.terminate()
            except (psutil.Error,OSError):pass
    except psutil.Error:pass

def output(value):print(json.dumps(value,ensure_ascii=False,separators=(',',':')),flush=True)

def direct_launch(app_name):
    target=DIRECT_LAUNCH.get(app_name.lower())
    if target and hasattr(os,'startfile'):
        try:
            os.startfile(target)
            return True
        except OSError:
            pass
    return False

def dispatch_app(app_name):
    if direct_launch(app_name):
        return {'status':'submitted'}
    from windows_mcp.desktop.service import Desktop
    # Desktop.app also searches the UI Automation tree after launch.
    # This process only submits the request. The host verifies the window.
    try:
        _,status,_=Desktop().launch_app(app_name)
    except Exception as error:
        code=getattr(error,'hresult',None)
        if code is None and error.args:
            code=error.args[0]
        if code==-2147220991:
            return {'status':'unverified'}
        raise
    return {'status':'failed' if status else 'submitted'}

def normalize(result, tool):
    content=[]
    for block in getattr(result,'content',[]):
        data=block.model_dump(by_alias=True,exclude_none=True) if hasattr(block,'model_dump') else dict(block)
        if data.get('type')=='text':
            value=str(data.get('text',''))
            # Some MCP transports package Snapshot's list of strings as JSON text.
            # Decode before applying the UI-tree size limit so the focus header survives.
            if tool=='Snapshot' and value.lstrip().startswith('['):
                try: parts=json.loads(value)
                except ValueError: parts=None
                if isinstance(parts,list) and parts and all(isinstance(part,str) for part in parts):
                    value='\n'.join(parts)
            content.append({'type':'text','text':value[:18000]})
        elif data.get('type')=='image' and len(data.get('data',''))<=6*1024*1024:content.append({'type':'image','data':data['data'],'mimeType':data.get('mimeType','image/png')})
    return {'content':content,'isError':bool(getattr(result,'is_error',getattr(result,'isError',False)))}

async def main():
    from fastmcp import Client
    from fastmcp.client.transports import PythonStdioTransport
    queue=asyncio.Queue();loop=asyncio.get_running_loop()
    def read():
        for line in sys.stdin:
            try:value=json.loads(line)
            except (ValueError,TypeError):continue
            loop.call_soon_threadsafe(queue.put_nowait,value)
        kill_owned_servers();loop.call_soon_threadsafe(queue.put_nowait,None)
    threading.Thread(target=read,daemon=True).start()
    transport=PythonStdioTransport(SERVER,python_cmd=sys.executable,env={'ANONYMIZED_TELEMETRY':'false','WINDOWS_MCP_WATCHDOG':'false','PYTHONUTF8':'1'},keep_alive=False)
    try:
        async with Client(transport,timeout=35,init_timeout=35) as client:
            tools=[{'name':t.name,'description':t.description[:280] if t.description else '', 'inputSchema':t.inputSchema} for t in await client.list_tools() if t.name in ALLOWED]
            output({'event':'ready','tools':tools})
            while True:
                request=await queue.get()
                if request is None:break
                try:
                    name=request.get('tool');arguments=request.get('arguments',{})
                    if name not in ALLOWED or not isinstance(arguments,dict):raise ValueError('unsupported tool')
                    if name=='App' and (arguments.get('mode') or 'launch')=='launch':
                        app_name=str(arguments.get('name') or '').strip()
                        if direct_launch(app_name):
                            output({'id':request['id'],'result':{'content':[{'type':'text','text':f'{app_name} launched.'}],'isError':False}})
                            continue
                    result=await client.call_tool(name,arguments)
                    norm=normalize(result,name)
                    if name=='App' and any('not found in start menu' in c.get('text','').lower() or 'invalid app identifier' in c.get('text','').lower() for c in norm.get('content',[])):
                        norm['isError']=True
                    output({'id':request['id'],'result':norm})
                except Exception as error:output({'id':request.get('id'),'error':type(error).__name__+': '+str(error)[:300]})
    finally:kill_owned_servers()

if __name__=='__main__':
    sys.stdin.reconfigure(encoding='utf8');sys.stdout.reconfigure(encoding='utf8');sys.stderr.reconfigure(encoding='utf8')
    if len(sys.argv)==3 and sys.argv[1]=='dispatch':
        output(dispatch_app(json.loads(sys.argv[2])))
    else:
        asyncio.run(main())
