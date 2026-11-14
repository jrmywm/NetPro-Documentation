/* Branch-function benchmark. Destination adapted to isolated loopback receiver. */
#include <stdio.h>
#include <stdint.h>
#include <inttypes.h>
#include <stdlib.h>
#include <time.h>
static char PS_ID[64];
int send_trap(uint16_t portid, uint64_t dropped_packets) {
 char command[512];
 snprintf(command,sizeof(command),"snmptrap -v 2c -c public udp:127.0.0.1:11621 '' 1.3.6.1.4.1.8072.9999.1 1.3.6.1.4.1.8072.9999.1 s \"%s port %u sent %" PRIu64 " packets\"",PS_ID,portid,dropped_packets);
 return system(command)==0;
}
int main(int argc,char **argv) {
 if(argc!=3)return 2;
 unsigned count=(unsigned)strtoul(argv[1],NULL,10);
 unsigned trial=(unsigned)strtoul(argv[2],NULL,10);
 if(count>10000||trial>10)return 2;
 snprintf(PS_ID,sizeof(PS_ID),"replication-trial-%u",trial);
 struct timespec begin,end;clock_gettime(CLOCK_MONOTONIC,&begin);
 unsigned sent=0;
 for(unsigned i=1;i<=count;i++)sent+=send_trap(0,i);
 clock_gettime(CLOCK_MONOTONIC,&end);
 double elapsed=end.tv_sec-begin.tv_sec+(end.tv_nsec-begin.tv_nsec)/1e9;
 printf("{\"trial\":%u,\"attempted\":%u,\"command_success\":%u,\"elapsed_s\":%.9f}\n",trial,count,sent,elapsed);
 return sent==count?0:1;
}
