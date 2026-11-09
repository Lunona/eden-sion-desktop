"""Private stdio desktop server. No listener, startup task, shell or telemetry."""
import os,sys,runpy
os.environ['ANONYMIZED_TELEMETRY']='false'
os.environ['WINDOWS_MCP_WATCHDOG']='false'
sys.argv=['windows-mcp','serve','--transport','stdio','--tools','Snapshot,Screenshot,Click,Type,Scroll,Move,Shortcut,App']
runpy.run_module('windows_mcp',run_name='__main__')
