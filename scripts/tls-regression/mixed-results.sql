-- Read-only paired mixed-load report.
-- Override with: psql -v npb_baseline=157326 -v ps_baseline=154953 -f mixed-results.sql
SELECT packet_id, time, http_count, https_count, no_match, rx_i_count,
       tx_o_http_count, tx_o_tls_count
FROM npb_packet
WHERE packet_id > :npb_baseline
  AND (http_count > 0 OR https_count > 0)
ORDER BY packet_id;

SELECT packet_id, time, rx_i_http_count, rx_i_tls_count,
       "rstClient", "rstServer", rx_o_count, tx_o_count
FROM ps_packet
WHERE packet_id > :ps_baseline
  AND (rx_i_http_count > 0 OR rx_i_tls_count > 0)
ORDER BY packet_id;

WITH npb AS (
    SELECT http_count, https_count, no_match, tx_o_http_count, tx_o_tls_count
    FROM npb_packet
    WHERE packet_id > :npb_baseline
      AND (http_count > 0 OR https_count > 0)
), policy AS (
    SELECT rx_i_http_count, rx_i_tls_count, "rstClient", "rstServer", rx_o_count, tx_o_count
    FROM ps_packet
    WHERE packet_id > :ps_baseline
      AND (rx_i_http_count > 0 OR rx_i_tls_count > 0)
), totals AS (
    SELECT
      (SELECT coalesce(sum(http_count), 0) FROM npb) AS npb_http_classified,
      (SELECT coalesce(sum(https_count), 0) FROM npb) AS npb_tls_classified,
      (SELECT coalesce(sum(no_match), 0) FROM npb) AS npb_no_match,
      (SELECT coalesce(sum(tx_o_http_count), 0) FROM npb) AS npb_http_out,
      (SELECT coalesce(sum(tx_o_tls_count), 0) FROM npb) AS npb_tls_out,
      (SELECT coalesce(sum(rx_i_http_count), 0) FROM policy) AS policy_http_in,
      (SELECT coalesce(sum(rx_i_tls_count), 0) FROM policy) AS policy_tls_in,
      (SELECT coalesce(sum("rstClient"), 0) FROM policy) AS rst_client_total,
      (SELECT coalesce(sum("rstServer"), 0) FROM policy) AS rst_server_total,
      (SELECT coalesce(sum(rx_o_count), 0) FROM policy) AS policy_rx_out,
      (SELECT coalesce(sum(tx_o_count), 0) FROM policy) AS policy_tx_out
)
SELECT npb_http_classified, npb_tls_classified, npb_no_match,
       npb_http_out, policy_http_in,
       npb_http_out - policy_http_in AS http_forwarding_delta,
       npb_tls_out, policy_tls_in,
       npb_tls_out - policy_tls_in AS tls_forwarding_delta,
       rst_client_total, rst_server_total,
       rst_client_total + rst_server_total AS resets_total,
       policy_rx_out, policy_tx_out
FROM totals;
