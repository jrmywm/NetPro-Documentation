/* Test-file adapter, not DPDK enforcement. */
#include "quic_initial.h"
#include "quicFunctions.h"
int main(int argc,char **argv){
 if(argc!=3)return 2;
 unsigned char in[4096],out[2048];FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(in,1,sizeof(in),f);int extra=fgetc(f);fclose(f);
 if(extra!=EOF||n<7)return 2;
 quic_sni_result r=quic_initial_extract_sni(in,n);
 printf("sni_status=%d hostname=%s\n",r.status,r.hostname);
 if(r.status!=QUIC_SNI_MATCH||strcmp(r.hostname,"netpro-quic.test"))return 3;
 size_t o=5;unsigned dl=in[o++];if(dl>20||!dl||o+dl+1>n)return 3;
 const unsigned char *dcid=in+o;o+=dl;unsigned sl=in[o++];
 if(sl>20||!sl||o+sl>n)return 3;const unsigned char *scid=in+o;
 QuicCryptoKeys k={0};uint32_t bytes=0;
 derive_initial_keys(dcid,dl,true,&k);derive_initial_keys(dcid,dl,false,&k);
 quic_payload_crafter(scid,sl,dcid,dl,out,&bytes,&k,false);
 if(bytes>sizeof(out)||!bytes)return 3;
 f=fopen(argv[2],"wb");if(!f)return 2;size_t wrote=fwrite(out,1,bytes,f);fclose(f);
 printf("close_bytes=%u\n",bytes);return wrote==bytes?0:2;
}
