#define _POSIX_C_SOURCE 200809L
#include "inline_verdict.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/stat.h>

#define VERDICT_WIRE_LEN 134u
#define VERDICT_SIGNED_LEN 102u
#define VERDICT_PORT 19191u
#define VERDICT_TTL_MS 2000u
#define KEY_BYTES 32u
#define SESSION_BYTES 16u
#define ETH_LEN 14u
#define IPV4_MIN_LEN 20u
#define UDP_LEN 8u
#define HASH_CHUNK 1024u

static pthread_once_t init_once = PTHREAD_ONCE_INIT;
static int init_status = -1;
static int verdict_fd = -1;
static struct sockaddr_in verdict_peer;
static uint8_t hmac_key[KEY_BYTES];
static uint8_t session_id[SESSION_BYTES];
static atomic_uint_fast64_t publication_seq;
static atomic_uint_fast64_t sent_count;
static atomic_uint_fast64_t disabled_count;
static atomic_uint_fast64_t error_count;

static int hex_nibble(char c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

static bool decode_hex(const char *text, uint8_t *out, size_t bytes)
{
	if (!text || strlen(text) != bytes * 2) return false;
	for (size_t i = 0; i < bytes; ++i) {
		int hi = hex_nibble(text[2 * i]);
		int lo = hex_nibble(text[2 * i + 1]);
		if (hi < 0 || lo < 0) return false;
		out[i] = (uint8_t)((hi << 4) | lo);
	}
	return true;
}

static bool read_key_file(const char *path, uint8_t key[KEY_BYTES])
{
	if (!path || !*path) return false;
	int fd = open(path, O_RDONLY | O_CLOEXEC);
	if (fd < 0) return false;
	struct stat st;
	if (fstat(fd, &st) < 0 || (st.st_mode & 0077) != 0) {
		close(fd);
		return false;
	}
	char data[66];
	size_t used = 0;
	while (used < sizeof(data)) {
		ssize_t got = read(fd, data + used, sizeof(data) - used);
		if (got < 0 && errno == EINTR) continue;
		if (got <= 0) break;
		used += (size_t)got;
	}
	close(fd);
	if (used == 65 && data[64] == '\n') used = 64;
	if (used != 64) return false;
	data[64] = '\0';
	return decode_hex(data, key, KEY_BYTES);
}

static void initialize_once(void)
{
	const char *key_file = getenv("NETPRO_VERDICT_HMAC_KEY_FILE");
	const char *key_hex = getenv("NETPRO_VERDICT_HMAC_KEY");
	const char *session_hex = getenv("NETPRO_VERDICT_SESSION_ID");
	const char *bind_ip = getenv("NETPRO_VERDICT_BIND_IPV4");
	const char *peer_ip = getenv("NETPRO_VERDICT_PEER_IPV4");
	if ((!key_file || !*key_file) && (!key_hex || !*key_hex)) return;
	if (key_file && *key_file) {
		if (!read_key_file(key_file, hmac_key)) goto fail;
	} else if (!decode_hex(key_hex, hmac_key, sizeof(hmac_key))) goto fail;
	if (!decode_hex(session_hex, session_id, sizeof(session_id)) ||
	    !bind_ip || !peer_ip) goto fail;
	memset(&verdict_peer, 0, sizeof(verdict_peer));
	verdict_peer.sin_family = AF_INET;
	verdict_peer.sin_port = htons(VERDICT_PORT);
	if (inet_pton(AF_INET, peer_ip, &verdict_peer.sin_addr) != 1) goto fail;
	struct sockaddr_in local;
	memset(&local, 0, sizeof(local));
	local.sin_family = AF_INET;
	if (inet_pton(AF_INET, bind_ip, &local.sin_addr) != 1) goto fail;
	verdict_fd = socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (verdict_fd < 0 || bind(verdict_fd, (struct sockaddr *)&local,
				    sizeof(local)) < 0) goto fail;
	init_status = 0;
	return;
fail:
	if (verdict_fd >= 0) close(verdict_fd);
	verdict_fd = -1;
	OPENSSL_cleanse(hmac_key, sizeof(hmac_key));
	OPENSSL_cleanse(session_id, sizeof(session_id));
}

int inline_verdict_init(void)
{
	(void)pthread_once(&init_once, initialize_once);
	return init_status;
}

static void put_u16(uint8_t *p, uint16_t value)
{
	p[0] = (uint8_t)(value >> 8);
	p[1] = (uint8_t)value;
}

static void put_u64(uint8_t *p, uint64_t value)
{
	for (unsigned i = 0; i < 8; ++i) p[i] = (uint8_t)(value >> (56u - 8u * i));
}

static bool hash_udp_payload(const struct rte_mbuf *packet, size_t offset,
			     size_t length, uint8_t digest[32])
{
	EVP_MD_CTX *ctx = EVP_MD_CTX_new();
	if (!ctx) return false;
	bool ok = EVP_DigestInit_ex(ctx, EVP_sha256(), NULL) == 1;
	uint8_t chunk[HASH_CHUNK];
	while (ok && length) {
		size_t take = length < sizeof(chunk) ? length : sizeof(chunk);
		const uint8_t *part = rte_pktmbuf_read(packet, (uint32_t)offset,
						       (uint32_t)take, chunk);
		if (!part || EVP_DigestUpdate(ctx, part, take) != 1) {
			ok = false;
			break;
		}
		offset += take;
		length -= take;
	}
	unsigned int out_len = 0;
	if (ok) ok = EVP_DigestFinal_ex(ctx, digest, &out_len) == 1 && out_len == 32;
	EVP_MD_CTX_free(ctx);
	return ok;
}

int inline_verdict_publish(const struct rte_mbuf *packet,
			   enum inline_verdict_decision decision)
{
	if (!packet || (decision != INLINE_VERDICT_ALLOW &&
			decision != INLINE_VERDICT_DENY &&
			decision != INLINE_VERDICT_UNSUPPORTED)) return -1;
	uint8_t ethbuf[ETH_LEN];
	const uint8_t *eth = rte_pktmbuf_read(packet, 0, sizeof(ethbuf), ethbuf);
	if (!eth || eth[12] != 0x08 || eth[13] != 0x00) return 0;
	uint8_t ipbuf[60];
	const uint8_t *ip = rte_pktmbuf_read(packet, ETH_LEN, IPV4_MIN_LEN, ipbuf);
	if (!ip || (ip[0] >> 4) != 4 || ip[9] != 17) return 0;
	size_t ip_hlen = (size_t)(ip[0] & 0x0f) * 4u;
	if (ip_hlen < IPV4_MIN_LEN || ip_hlen > sizeof(ipbuf) ||
	    ETH_LEN + ip_hlen + UDP_LEN > packet->pkt_len) return 0;
	ip = rte_pktmbuf_read(packet, ETH_LEN, (uint32_t)ip_hlen, ipbuf);
	if (!ip) return 0;
	uint16_t frag = (uint16_t)(((uint16_t)ip[6] << 8) | ip[7]);
	if ((frag & 0x3fffu) != 0) return 0;
	uint16_t ip_total_len = (uint16_t)(((uint16_t)ip[2] << 8) | ip[3]);
	if (ip_total_len < ip_hlen + UDP_LEN ||
	    ETH_LEN + ip_total_len > packet->pkt_len) return 0;
	uint32_t src_ip, dst_ip;
	memcpy(&src_ip, ip + 12, 4);
	memcpy(&dst_ip, ip + 16, 4);
	struct in_addr expected_src, expected_dst;
	if (inet_pton(AF_INET, "192.168.80.29", &expected_src) != 1 ||
	    inet_pton(AF_INET, "192.168.80.28", &expected_dst) != 1 ||
	    src_ip != expected_src.s_addr || dst_ip != expected_dst.s_addr) return 0;
	uint8_t udpbuf[UDP_LEN];
	const uint8_t *udp = rte_pktmbuf_read(packet, ETH_LEN + (uint32_t)ip_hlen,
						 sizeof(udpbuf), udpbuf);
	if (!udp) return 0;
	uint16_t src_port, dst_port, udp_len;
	memcpy(&src_port, udp, 2);
	memcpy(&dst_port, udp + 2, 2);
	memcpy(&udp_len, udp + 4, 2);
	if (ntohs(dst_port) != 443 || ntohs(udp_len) < UDP_LEN ||
	    ntohs(udp_len) > ip_total_len - ip_hlen) return 0;
	size_t payload_len = ntohs(udp_len) - UDP_LEN;
	size_t payload_offset = ETH_LEN + ip_hlen + UDP_LEN;
	if (payload_len > UINT16_MAX || payload_offset + payload_len > packet->pkt_len)
		return 0;
	(void)pthread_once(&init_once, initialize_once);
	if (init_status != 0) {
		atomic_fetch_add_explicit(&disabled_count, 1, memory_order_relaxed);
		return -1;
	}
	uint8_t wire[VERDICT_WIRE_LEN] = {0};
	memcpy(wire, "NPV1", 4);
	wire[4] = 1;
	wire[5] = 1;
	wire[6] = (uint8_t)decision;
	memcpy(wire + 8, session_id, sizeof(session_id));
	uint64_t seq = atomic_fetch_add_explicit(&publication_seq, 1,
						 memory_order_relaxed) + 1;
	put_u64(wire + 24, seq);
	put_u64(wire + 32, 0); /* no synchronized policy-generation source yet */
	struct timespec now;
	if (clock_gettime(CLOCK_REALTIME, &now) != 0) goto send_error;
	uint64_t issued_ms = (uint64_t)now.tv_sec * 1000u +
		(uint64_t)now.tv_nsec / 1000000u;
	put_u64(wire + 40, issued_ms);
	put_u64(wire + 48, issued_ms + VERDICT_TTL_MS);
	memcpy(wire + 56, &src_ip, 4);
	memcpy(wire + 60, &dst_ip, 4);
	memcpy(wire + 64, &src_port, 2);
	memcpy(wire + 66, &dst_port, 2);
	put_u16(wire + 68, (uint16_t)payload_len);
	if (!hash_udp_payload(packet, payload_offset, payload_len, wire + 70))
		goto send_error;
	unsigned int mac_len = 0;
	if (!HMAC(EVP_sha256(), hmac_key, (int)sizeof(hmac_key), wire,
		  VERDICT_SIGNED_LEN, wire + VERDICT_SIGNED_LEN, &mac_len) ||
	    mac_len != 32) goto send_error;
	ssize_t sent = sendto(verdict_fd, wire, sizeof(wire), MSG_DONTWAIT,
			      (struct sockaddr *)&verdict_peer, sizeof(verdict_peer));
	OPENSSL_cleanse(wire, sizeof(wire));
	if (sent != VERDICT_WIRE_LEN) goto send_error;
	atomic_fetch_add_explicit(&sent_count, 1, memory_order_relaxed);
	return 1;
send_error:
	OPENSSL_cleanse(wire, sizeof(wire));
	atomic_fetch_add_explicit(&error_count, 1, memory_order_relaxed);
	return -1;
}

void inline_verdict_get_counters(uint64_t *sent, uint64_t *disabled,
				 uint64_t *errors)
{
	if (sent) *sent = atomic_load_explicit(&sent_count, memory_order_relaxed);
	if (disabled) *disabled = atomic_load_explicit(&disabled_count, memory_order_relaxed);
	if (errors) *errors = atomic_load_explicit(&error_count, memory_order_relaxed);
}
