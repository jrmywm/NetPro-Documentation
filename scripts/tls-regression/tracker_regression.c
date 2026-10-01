#include <assert.h>
#include <stdio.h>
#include "tls_record_tracker.h"

int main(void)
{
	struct tls_flow_tracker tracker;
	const struct tls_flow_key key = {0x01020304u, 0x05060708u, 47000u, 8443u};
	struct tls_flow_entry *entry = &tracker.entries[0];
	tls_tracker_init(&tracker, 100u);
	assert(tls_tracker_begin(&tracker, &key, 0xfffffff0u, 8u, 20u, 1u) == 1);
	assert(tls_tracker_continuation(&tracker, &key, 0x00000004u, 5u, 2u) == 1);
	assert(entry->covered_bytes == 13u && entry->complete == 0);
	assert(tls_tracker_continuation(&tracker, &key, 0xfffffff8u, 12u, 3u) == 1);
	assert(entry->covered_bytes == 25u && entry->complete == 1);
	assert(tls_tracker_continuation(&tracker, &key, 0xfffffff8u, 8u, 4u) == 1);
	assert(entry->covered_bytes == 25u);
	puts("PASS tracker: out-of-order gap remains incomplete, wrap fills gap, retransmission is idempotent");
	tls_tracker_end(&tracker, &key);
	assert(tls_tracker_continuation(&tracker, &key, 0xfffffff8u, 8u, 5u) == 0);
	puts("PASS tracker: ended flow no longer matches continuation");
	return 0;
}
