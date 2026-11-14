import os,sys,paramiko
c=paramiko.SSHClient()
c.load_host_keys(os.path.expanduser('~/.ssh/known_hosts'))
c.connect('192.168.31.'+sys.argv[1],username='netpro',password=os.environ['NETPRO_LAB_PASSWORD'],timeout=10)
try:
    _,out,err=c.exec_command(sys.stdin.read(),timeout=30)
    print(out.read().decode(errors='replace'))
    print(err.read().decode(errors='replace'))
    sys.exit(out.channel.recv_exit_status())
finally:c.close()
