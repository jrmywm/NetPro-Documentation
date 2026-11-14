#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdbool.h>
#include <string.h>
#include "quicFunctions.h"
char *getDomain(const uint8_t *, int, bool, QuicCryptoKeys *);
void quic_payload_crafter(const uint8_t *, uint8_t, const uint8_t *, uint8_t, uint8_t *, uint32_t *, QuicCryptoKeys *, bool);
int main(int argc, char **argv) {
    if (argc != 3 && argc != 4) return 2;
    FILE *f = fopen(argv[1], "rb"); if (!f) return 2;
    uint8_t data[65536]; size_t n = fread(data, 1, sizeof(data), f); fclose(f);
    QuicCryptoKeys keys = {0};
    char *name = getDomain(data, (int)n, true, &keys);
    if (!name) { puts("ORIGINAL_SNI=NULL"); return 1; }
    printf("ORIGINAL_SNI=%s\n", name);
    int good = strcmp(name, argv[2]) == 0;
    free(name);
    puts(good ? "ORIGINAL_PARSER=PASS" : "ORIGINAL_PARSER=FAIL");
    if (good && argc == 4) {
        uint8_t dcid_len=data[5], scid_len=data[6+dcid_len];
        uint8_t reply[2048]; uint32_t reply_len=0;
        derive_initial_keys(data+6,dcid_len,false,&keys);
        quic_payload_crafter(data+7+dcid_len,scid_len,data+6,dcid_len,reply,&reply_len,&keys,false);
        if (!reply_len || reply_len>sizeof(reply)) return 1;
        FILE *out=fopen("original-close.bin","wb"); if (!out) return 2;
        fwrite(reply,1,reply_len,out); fclose(out);
        printf("ORIGINAL_CLOSE_CRAFT=PASS BYTES=%u\n",reply_len);
    }
    if (good && argc == 4) {
        for (size_t i=0; i<n; ++i) {
            uint8_t *prefix=malloc(i ? i : 1); if (!prefix) return 2;
            memcpy(prefix,data,i); memset(&keys,0,sizeof(keys));
            name=getDomain(prefix,(int)i,true,&keys); free(prefix);
            if (name) {free(name); printf("Unexpected accepted prefix %zu\n",i); return 1;}
        }
        printf("PREFIX_REJECTIONS=%zu PASS\n",n);
        for (size_t i=0; i<256; ++i) {
            uint8_t *mutated=malloc(n); if (!mutated) return 2;
            memcpy(mutated,data,n); mutated[(i*37)%n]^=(uint8_t)(1u << (i%8));
            memset(&keys,0,sizeof(keys)); name=getDomain(mutated,(int)n,true,&keys);
            free(name); free(mutated);
        }
        puts("MUTATION_SAFETY=256 PASS");
    }
    return good ? 0 : 1;
}
