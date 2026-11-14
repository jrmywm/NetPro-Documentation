#include "inline_verdict.h"

#include <rte_eal.h>
#include <rte_mbuf.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int read_payload(const char *path, uint8_t *payload, size_t capacity,
			size_t *length)
{
	FILE *file = fopen(path, "rb");
	if (!file) return -1;
	*length = fread(payload, 1, capacity, file);
	int extra = fgetc(file);
	fclose(file);
	return extra == EOF && *length > 0 ? 0 : -1;
}

static struct rte_mbuf *make_packet(struct rte_mempool *pool,
				    const uint8_t *payload, size_t payload_len)
{
	if (payload_len + 42 > 2048) return NULL;
	struct rte_mbuf *packet = rte_pktmbuf_alloc(pool);
	if (!packet) return NULL;
	uint8_t *p = (uint8_t *)rte_pktmbuf_append(packet,
								    (uint16_t)(42 + payload_len));
	if (!p) {
		rte_pktmbuf_free(packet);
		return NULL;
	}
	memset(p, 0, 42 + payload_len);
	p[12] = 0x08; p[13] = 0x00;
	p[14] = 0x45;
	uint16_t ip_len = htons((uint16_t)(28 + payload_len));
	memcpy(p + 16, &ip_len, 2);
	p[22] = 64; p[23] = 17;
	inet_pton(AF_INET, "192.168.80.29", p + 26);
	inet_pton(AF_INET, "192.168.80.28", p + 30);
	uint16_t src_port = htons(49153), dst_port = htons(443);
	uint16_t udp_len = htons((uint16_t)(8 + payload_len));
	memcpy(p + 34, &src_port, 2);
	memcpy(p + 36, &dst_port, 2);
	memcpy(p + 38, &udp_len, 2);
	memcpy(p + 42, payload, payload_len);
	return packet;
}

int main(int argc, char **argv)
{
	if (argc != 2) return 2;
	char *eal[] = {"inline-verdict-test", "-l", "0", "--no-huge",
		       "--no-pci", "--no-shconf",
		       "--file-prefix=inline-verdict-test", NULL};
	if (rte_eal_init(7, eal) < 0) return 2;
	struct rte_mempool *pool = rte_pktmbuf_pool_create(
		"inline_verdict_test_pool", 127, 0, 0, 2048, SOCKET_ID_ANY);
	if (!pool) return 2;
	uint8_t payload[1500];
	size_t payload_len = 0;
	if (read_payload(argv[1], payload, sizeof(payload), &payload_len) != 0)
		return 2;
	struct rte_mbuf *packet = make_packet(pool, payload, payload_len);
	if (!packet) return 2;
	if (inline_verdict_init() != 0) {
		int disabled = inline_verdict_publish(packet, INLINE_VERDICT_ALLOW);
		uint64_t sent_count = 0, disabled_count = 0, error_count = 0;
		inline_verdict_get_counters(&sent_count, &disabled_count, &error_count);
		printf("PUBLISHER_DISABLED publish=%d sent=%llu disabled=%llu errors=%llu\n",
		       disabled, (unsigned long long)sent_count,
		       (unsigned long long)disabled_count,
		       (unsigned long long)error_count);
		rte_pktmbuf_free(packet);
		rte_mempool_free(pool);
		rte_eal_cleanup();
		return disabled == -1 && sent_count == 0 && disabled_count == 1 ? 3 : 1;
	}
	int allow = inline_verdict_publish(packet, INLINE_VERDICT_ALLOW);
	int deny = inline_verdict_publish(packet, INLINE_VERDICT_DENY);
	int unsupported = inline_verdict_publish(packet, INLINE_VERDICT_UNSUPPORTED);
	printf("PUBLISH_RESULTS %d %d %d\n", allow, deny, unsupported);
	rte_pktmbuf_free(packet);
	rte_mempool_free(pool);
	rte_eal_cleanup();
	return allow == 1 && deny == 1 && unsupported == 1 ? 0 : 1;
}
