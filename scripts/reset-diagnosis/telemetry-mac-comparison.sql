SELECT packet_id, time,
       rx_i_http_count, rx_i_tls_count,
       "rstClient", "rstServer", tx_o_count
FROM ps_packet
WHERE packet_id > 173055
  AND (rx_i_http_count <> 0
       OR rx_i_tls_count <> 0
       OR "rstClient" <> 0
       OR "rstServer" <> 0)
ORDER BY packet_id ASC;
