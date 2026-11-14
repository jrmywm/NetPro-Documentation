
#include "quic_initial_reassembly.h"
#include <assert.h>
#include <stdio.h>
static size_t read_fixture(const char *path,uint8_t *data) {
    FILE *f=fopen(path,"rb");
    assert(f);
    size_t n=fread(data,1,4096,f);
    fclose(f);
    return n;
}
int main(void) {
    uint8_t a[4096],b[4096],tuple[12]={0};
    QuicCryptoKeys keys;
    size_t an=read_fixture("initial-0.bin",a),bn=read_fixture("initial-1.bin",b);
    for (int reverse=0;reverse<2;reverse++) {
        ++tuple[0];
        uint8_t *first=reverse?b:a,*last=reverse?a:b;
        size_t firstn=reverse?bn:an,lastn=reverse?an:bn;
        assert(!quic_initial_sni(first,firstn,tuple,1,&keys));
        assert(!quic_initial_sni(first,firstn,tuple,2,&keys));
        char *sni=quic_initial_sni(last,lastn,tuple,3,&keys);
        assert(sni && !strcmp(sni,"mysite.local"));
        free(sni);
    }
    ++tuple[0];
    assert(!quic_initial_sni(a,an,tuple,1,&keys));
    b[100]^=1;
    assert(!quic_initial_sni(b,bn,tuple,2,&keys));
    puts("PASS captured Chromium Initials in order, reordered, duplicated, and tampered");
    return 0;
}
