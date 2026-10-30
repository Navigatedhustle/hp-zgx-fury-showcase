"""Fail closed on remote network connects in the Python runtime services."""
import ipaddress,os,socket
_installed=False
connects={'loopback':0,'blocked':0}
def is_local(address):
 if not isinstance(address,tuple):return True # Unix sockets
 host=address[0]
 if host=='localhost':return True
 try:return ipaddress.ip_address(host.split('%',1)[0]).is_loopback
 except ValueError:return False
def install():
 global _installed
 if _installed:return
 os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_IMPLICIT_TOKEN='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1')
 original=socket.socket.connect;original_ex=socket.socket.connect_ex
 def guard(self,address):
  if self.family in (socket.AF_INET,socket.AF_INET6) and not is_local(address):connects['blocked']+=1;raise OSError('Atlas runtime permits loopback connections only')
  connects['loopback']+=1;return original(self,address)
 def guard_ex(self,address):
  if self.family in (socket.AF_INET,socket.AF_INET6) and not is_local(address):connects['blocked']+=1;return 13
  connects['loopback']+=1;return original_ex(self,address)
 socket.socket.connect=guard;socket.socket.connect_ex=guard_ex;_installed=True
