#ifndef INLINE_VERDICT_H
#define INLINE_VERDICT_H

#include <stdint.h>
#include <stdbool.h>
#include <rte_mbuf.h>

enum inline_verdict_decision {
	INLINE_VERDICT_ALLOW = 1,
	INLINE_VERDICT_DENY = 2,
	INLINE_VERDICT_UNSUPPORTED = 3
};

static inline enum inline_verdict_decision
inline_verdict_policy_result(bool denied, bool lookup_valid)
{
	if (denied) return INLINE_VERDICT_DENY;
	return lookup_valid ? INLINE_VERDICT_ALLOW : INLINE_VERDICT_UNSUPPORTED;
}

int inline_verdict_init(void);
int inline_verdict_publish(const struct rte_mbuf *packet,
			   enum inline_verdict_decision decision);
void inline_verdict_get_counters(uint64_t *sent, uint64_t *disabled,
				 uint64_t *errors);

#endif
