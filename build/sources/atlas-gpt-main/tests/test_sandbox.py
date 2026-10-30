from atlas.sandbox import run

def test_real_sql_and_no_database_writes():
    result=run('SELECT COUNT(*) AS accounts FROM accounts','sql')
    assert result['success'] and result['table'][0]['accounts']>0
    rejected=run('DELETE FROM accounts','sql')
    assert not rejected['success'] and 'readonly' in rejected['stderr']

def test_kernel_socket_denial_cannot_be_monkeypatched():
    result=run('import socket; socket.socket()')
    assert not result['success'] and 'Operation not permitted' in result['stderr']

def test_host_filesystem_and_process_denial():
    result=run('open("/etc/shadow").read()')
    assert not result['success'] and 'Permission denied' in result['stderr']
    result=run('import subprocess; subprocess.run(["/bin/true"])')
    assert not result['success']

def test_timeout_and_memory_limit():
    result=run('while True: pass',timeout=.3)
    assert result['timeout'] and not result['success']
    result=run('x=bytearray(700*1024*1024)')
    assert not result['success'] and 'MemoryError' in result['stderr']
