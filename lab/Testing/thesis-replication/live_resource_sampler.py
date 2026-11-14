"""One-second process CPU/RSS and guest CPU samples, not historical ps averages."""
import os,time,json,signal,threading,sys
from pathlib import Path
pid=int(sys.argv[1]);out=Path(sys.argv[2]);stop=threading.Event()
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
hz=os.sysconf('SC_CLK_TCK');cores=os.cpu_count();previous=None
with out.open('w',encoding='utf-8') as log:
 while not stop.is_set():
  try:
   now=time.monotonic();p=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split();ticks=int(p[11])+int(p[12]);rss=int(p[21])*os.sysconf('SC_PAGE_SIZE')/1024
   cpu=[int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]];total=sum(cpu);idle=cpu[3]+cpu[4]
  except FileNotFoundError:break
  row={'monotonic':now,'pid':pid,'guest_cores':cores,'rss_kib':rss,'process_cpu_ticks':ticks,'guest_total_ticks':total,'guest_idle_ticks':idle}
  if previous:
   dt=now-previous[0];value=(ticks-previous[1])/hz/dt*100
   row.update(process_cpu_percent_one_core=value,process_cpu_percent_guest_capacity=value/cores,guest_cpu_percent=(1-(idle-previous[3])/(total-previous[2]))*100 if total!=previous[2] else None)
  log.write(json.dumps(row)+'\n');log.flush();previous=(now,ticks,total,idle)
  if stop.wait(1):break
