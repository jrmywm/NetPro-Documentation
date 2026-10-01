-- Read-only before/after report; intentionally no time-window filter.
-- Defaults: NPB baseline 176509, Policy baseline 174135.
-- Override as needed: psql -v npb_baseline=176509 -v ps_baseline=174135 -f telemetry.sql
SELECT packet_id, time, http_count, https_count, no_match,
       tx_o_http_count, tx_o_tls_count
FROM npb_packet
WHERE packet_id > :npb_baseline
  AND (http_count > 0 OR https_count > 0)
ORDER BY packet_id ASC;

SELECT packet_id, time, rx_i_http_count, rx_i_tls_count,
       "rstClient", "rstServer", tx_o_count
FROM ps_packet
WHERE packet_id > :ps_baseline
  AND (rx_i_http_count <> 0
       OR rx_i_tls_count <> 0
       OR "rstClient" <> 0
       OR "rstServer" <> 0)
ORDER BY packet_id ASC;

WITH npb AS (
    SELECT http_count, https_count, tx_o_http_count, tx_o_tls_count
    FROM npb_packet
    WHERE packet_id > :npb_baseline
      AND (http_count > 0 OR https_count > 0)
), policy AS (
    SELECT rx_i_http_count, rx_i_tls_count, "rstClient", "rstServer", tx_o_count
    FROM ps_packet
    WHERE packet_id > :ps_baseline
      AND (rx_i_http_count <> 0
           OR rx_i_tls_count <> 0
           OR "rstClient" <> 0
           OR "rstServer" <> 0)
), totals AS (
    SELECT
      (SELECT coalesce(sum(http_count), 0) FROM npb) AS npb_http_classified,
      (SELECT coalesce(sum(https_count), 0) FROM npb) AS npb_tls_classified,
      (SELECT coalesce(sum(tx_o_http_count), 0) FROM npb) AS npb_http_out,
      (SELECT coalesce(sum(tx_o_tls_count), 0) FROM npb) AS npb_tls_out,
      (SELECT coalesce(sum(rx_i_http_count), 0) FROM policy) AS policy_http_in,
      (SELECT coalesce(sum(rx_i_tls_count), 0) FROM policy) AS policy_tls_in,
      (SELECT coalesce(sum("rstClient"), 0) FROM policy) AS rst_client_total,
      (SELECT coalesce(sum("rstServer"), 0) FROM policy) AS rst_server_total,
      (SELECT coalesce(sum(tx_o_count), 0) FROM policy) AS policy_tx_out
)
SELECT npb_http_classified, npb_tls_classified,
       npb_http_out, npb_tls_out,
       policy_http_in, policy_tls_in,
       rst_client_total, rst_server_total, policy_tx_out
FROM totals;
