const generateConfigFileContent = (npbId, psId, ip_add, periodStats, periodSend) => {
  // Define the configuration content with dynamic and hardcoded values
  const configFileContent = `# Packet Processor settings
MAX_PACKET_LEN= 1500
RX_RING_SIZE= 1024
TX_RING_SIZE= 1024
NUM_MBUFS= 8191
MBUF_CACHE_SIZE= 250
BURST_SIZE= 32
MAX_TCP_PAYLOAD_LEN= 1024

# Settings
ID_NPB= ${npbId}
ID_PS= ${psId}
HOSTNAME= ${ip_add}

# Statsd settings
STAT_FILE= stats/stats
STAT_FILE_EXT= .csv

# Timer settings (MUST SYNC WITH AGGREGATOR)
TIMER_PERIOD_STATS= ${periodStats} # in seconds
TIMER_PERIOD_SEND= ${periodSend} # in minutes
`;

  return configFileContent;
};

export default generateConfigFileContent;
