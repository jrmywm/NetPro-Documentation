#ifndef TLS_RECORD_TRACKER_H
#define TLS_RECORD_TRACKER_H

/* Small allocation-free tracker for the first TLS record in a TCP flow. */
#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define TLS_TRACKER_CAPACITY 128u
#define TLS_TRACKER_MAX_RECORD 4096u

struct tls_flow_key {
	uint32_t src_addr; /* network byte order */
	uint32_t dst_addr; /* network byte order */
	uint16_t src_port; /* host byte order */
	uint16_t dst_port; /* host byte order */
};

struct tls_flow_entry {
	struct tls_flow_key key;
	uint32_t start_seq;
	uint32_t end_seq;
	uint64_t last_seen;
	uint16_t record_total;
	uint16_t covered_bytes;
	uint8_t coverage[TLS_TRACKER_MAX_RECORD / 8u];
	uint8_t used;
	uint8_t complete;
};

struct tls_flow_tracker {
	struct tls_flow_entry entries[TLS_TRACKER_CAPACITY];
	uint64_t timeout_ticks;
};

static inline int tls_flow_key_equal(const struct tls_flow_key *a,
									 const struct tls_flow_key *b)
{
	return a->src_addr == b->src_addr && a->dst_addr == b->dst_addr &&
		   a->src_port == b->src_port && a->dst_port == b->dst_port;
}

/* TCP sequence comparisons are valid for spans shorter than 2^31 bytes. */
static inline int tls_seq_after(uint32_t a, uint32_t b)
{
	uint32_t distance = a - b;
	return distance != 0 && distance < 0x80000000u;
}

static inline void tls_tracker_init(struct tls_flow_tracker *tracker,
									uint64_t timeout_ticks)
{
	unsigned int i;
	for (i = 0; i < TLS_TRACKER_CAPACITY; ++i)
		tracker->entries[i].used = 0;
	tracker->timeout_ticks = timeout_ticks;
}

/*
 * Register the packet that matched the TLS ClientHello signature. record_len
 * is the TLS record payload length from the two-byte record header field.
 * Returns zero when the record is already complete or invalid, one when a
 * bounded flow entry was installed, and -1 if the table is full.
 */
static inline int tls_tracker_begin(struct tls_flow_tracker *tracker,
									const struct tls_flow_key *key,
									uint32_t seq,
									size_t payload_len,
									uint16_t record_len,
									uint64_t now)
{
	unsigned int i, free_slot = TLS_TRACKER_CAPACITY;
	uint32_t record_total;

	if (record_len < 4 || (uint32_t)record_len + 5u > TLS_TRACKER_MAX_RECORD ||
		payload_len >= (uint32_t)record_len + 5u)
		return 0;
	record_total = (uint32_t)record_len + 5u;
	for (i = 0; i < TLS_TRACKER_CAPACITY; ++i) {
		struct tls_flow_entry *entry = &tracker->entries[i];
		if (entry->used && now - entry->last_seen > tracker->timeout_ticks)
			entry->used = 0;
		if (entry->used && tls_flow_key_equal(&entry->key, key)) {
			free_slot = i;
			break;
		}
		if (!entry->used && free_slot == TLS_TRACKER_CAPACITY)
			free_slot = i;
	}
	if (free_slot == TLS_TRACKER_CAPACITY)
		return -1;
	tracker->entries[free_slot].key = *key;
	tracker->entries[free_slot].start_seq = seq;
	tracker->entries[free_slot].end_seq = seq + record_total;
	tracker->entries[free_slot].last_seen = now;
	tracker->entries[free_slot].record_total = (uint16_t)record_total;
	tracker->entries[free_slot].covered_bytes = (uint16_t)payload_len;
	memset(tracker->entries[free_slot].coverage, 0,
		   sizeof(tracker->entries[free_slot].coverage));
	{
		size_t byte;
		for (byte = 0; byte < payload_len; ++byte)
			tracker->entries[free_slot].coverage[byte >> 3] |=
				(uint8_t)(1u << (byte & 7u));
	}
	tracker->entries[free_slot].complete = 0;
	if (tracker->entries[free_slot].covered_bytes >= record_total)
		tracker->entries[free_slot].complete = 1;
	tracker->entries[free_slot].used = 1;
	return 1;
}

/*
 * Match/record a same-direction segment. A fixed bitmap tracks byte coverage,
 * so gaps and out-of-order segments cannot falsely complete the record, while
 * retransmitted overlaps do not double-count bytes. Completed flows remain
 * available for the timeout window to catch retransmissions.
 */
static inline int tls_tracker_continuation(struct tls_flow_tracker *tracker,
										 const struct tls_flow_key *key,
										 uint32_t seq,
										 size_t payload_len,
										 uint64_t now)
{
	unsigned int i;
	for (i = 0; i < TLS_TRACKER_CAPACITY; ++i) {
		struct tls_flow_entry *entry = &tracker->entries[i];
		uint32_t record_offset;
		size_t bytes_to_mark = payload_len, byte;
		if (!entry->used)
			continue;
		if (now - entry->last_seen > tracker->timeout_ticks) {
			entry->used = 0;
			continue;
		}
		if (!tls_flow_key_equal(&entry->key, key))
			continue;
		/* Clip packet bytes to the tracked [start_seq, end_seq) range. */
		if (tls_seq_after(entry->start_seq, seq)) {
			uint32_t leading = entry->start_seq - seq;
			if (leading >= payload_len)
				return 0;
			bytes_to_mark -= leading;
			record_offset = 0;
		} else {
			record_offset = seq - entry->start_seq;
			if (record_offset >= entry->record_total)
				return 0;
		}
		if (bytes_to_mark > entry->record_total - record_offset)
			bytes_to_mark = entry->record_total - record_offset;
		if (bytes_to_mark == 0)
			return 0;
		entry->last_seen = now;
		for (byte = 0; byte < bytes_to_mark; ++byte) {
			uint32_t offset = record_offset + (uint32_t)byte;
			uint8_t mask = (uint8_t)(1u << (offset & 7u));
			if ((entry->coverage[offset >> 3] & mask) == 0) {
				entry->coverage[offset >> 3] |= mask;
				++entry->covered_bytes;
			}
		}
		if (entry->covered_bytes >= entry->record_total) {
			entry->complete = 1;
		}
		return 1;
	}
	return 0;
}

static inline void tls_tracker_end(struct tls_flow_tracker *tracker,
								   const struct tls_flow_key *key)
{
	unsigned int i;
	for (i = 0; i < TLS_TRACKER_CAPACITY; ++i) {
		if (tracker->entries[i].used &&
			tls_flow_key_equal(&tracker->entries[i].key, key))
			tracker->entries[i].used = 0;
	}
}

#endif
