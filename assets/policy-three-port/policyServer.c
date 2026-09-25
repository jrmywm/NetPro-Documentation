// ======================================================= THE LIBRARY =======================================================

// C library
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <inttypes.h>
#include <sys/types.h>
#include <sys/queue.h>
#include <setjmp.h>
#include <stdarg.h>
#include <ctype.h>
#include <errno.h>
#include <getopt.h>
#include <signal.h>
#include <stdbool.h>
#include <time.h>
#include <unistd.h>
#include <curl/curl.h>
#include <jansson.h>
#include <sqlite3.h>
#include <librdkafka/rdkafka.h>

// DPDK library
#include <rte_common.h>
#include <rte_eal.h>
#include <rte_ethdev.h>
#include <rte_cycles.h>
#include <rte_lcore.h>
#include <rte_mbuf.h>
#include <rte_tcp.h>
#include <rte_pdump.h>
#include <rte_spinlock.h>

#define CACHE_SIZE 20000
#define RTE_TCP_RST 0x04
#define MAX_STRINGS 64
#define KAFKA_TOPIC "dpdk-blocked-list"
#define KAFKA_BROKER "192.168.0.90:9092"
#define GMT 801
#define LOCAL 802

#define HTTP_GET_MAGIC "GET /"
#define HTTP_GET_MAGIC_LEN 5
#define TLS_MAGIC "\x16\x03\x01"
#define TLS_MAGIC_LEN 3
#define TLS_CLIENT_HELLO_MAGIC "\x01"
#define TLS_CLIENT_HELLO_MAGIC_LEN 1
#define HTTP_GET 112
#define TLS_CLIENT_HELLO 212

typedef enum
{
	LOG_LEVEL_INFO,
	LOG_LEVEL_WARNING,
	LOG_LEVEL_ERROR
} LogLevel;

uint32_t MAX_PACKET_LEN;
uint32_t RX_RING_SIZE;
uint32_t TX_RING_SIZE;
uint32_t NUM_MBUFS;
uint32_t MBUF_CACHE_SIZE;
uint32_t BURST_SIZE;
uint32_t MAX_TCP_PAYLOAD_LEN;
static uint32_t TIMER_PERIOD_STATS;
static uint32_t TIMER_PERIOD_SEND;


static const char *db_path = "/home/ubuntu/NetPro-Policy-Server/policy.db";

char PS_ID[200];
char STAT_FILE[100];
char STAT_FILE_EXT[100];
char HOSTNAME[100];
char hitCount[CACHE_SIZE][MAX_STRINGS];
uint64_t hitCounter = 0;
static sqlite3 *db;
clock_t start, end;

char log_file_name[256];
char *start_time;

// Define a spinlock
static rte_spinlock_t rx_lock = RTE_SPINLOCK_INITIALIZER;
static rte_spinlock_t tx_lock = RTE_SPINLOCK_INITIALIZER;
int countFlag = 0;
uint64_t rstServer = 0;
uint64_t rstClient = 0;
struct hit_counter
{
	char id[MAX_STRINGS];
	uint64_t hit_count;
};

struct port_statistics_data
{
	uint64_t tx_count;
	uint64_t rx_count;
	uint64_t tx_size;
	uint64_t rx_size;
	uint64_t dropped;
	uint64_t rstClient;
	uint64_t rstServer;
	long int throughput;
	uint64_t err_rx;
	uint64_t err_tx;
	uint64_t mbuf_err;
} __rte_cache_aligned;
struct port_statistics_data port_statistics[RTE_MAX_ETHPORTS];
static uint16_t http_port;
static uint16_t tls_port;
static uint16_t rst_port;

static volatile bool force_quit;
static struct hit_counter db_hit_count[CACHE_SIZE];

typedef struct
{
	char domain[MAX_STRINGS];
	char id[MAX_STRINGS];
} DomainCache;

static DomainCache domain_cache[CACHE_SIZE];
static int domainCacheSize = 0;
static int domainCacheCounter = 0;

typedef struct
{
	char ip_address[INET_ADDRSTRLEN];
	char id[MAX_STRINGS];
} IPCache;

static IPCache ip_cache[CACHE_SIZE];
static int ipCacheSize = 0;

/**
 * Returns the string representation of the given log level.
 *
 * @param level The log level to get the string representation for.
 * @return The string representation of the log level.
 */
const char *getLogLevelString(LogLevel level)
{
	switch (level)
	{
	case LOG_LEVEL_INFO:
		return "INFO";
	case LOG_LEVEL_WARNING:
		return "WARNING";
	case LOG_LEVEL_ERROR:
		return "ERROR";
	default:
		return "UNKNOWN";
	}
}

char *generate_string_time(int type)
{
	time_t now;
	struct tm *tm_info;
	char *time_str = (char *)calloc(100, sizeof(char));
	const char *format = "%Y-%m-%dT%H:%M:%S";

	// get the current time
	time(&now);

	if (type == GMT)
		tm_info = gmtime(&now);
	else if (type == LOCAL)
		tm_info = localtime(&now);

	// convert the time to string
	strftime(time_str, 100, format, tm_info);

	return time_str;
}

/**
 * Logs a message to a log file with the specified log level, filename, line number, and format.
 *
 * @param level The log level of the message.
 * @param filename The name of the file where the log message is called.
 * @param line The line number where the log message is called.
 * @param format The format string for the log message.
 * @param ... Additional arguments to be formatted according to the format string.
 *
 * @return void
 */
void logMessage(LogLevel level, const char *filename, int line, const char *format, ...)
{
	char *timestamp_log;

	// get the file name
	if (log_file_name == NULL || log_file_name[0] == '\0')
	{
		timestamp_log = generate_string_time(LOCAL);
		sprintf(log_file_name, "logs/%s.txt", timestamp_log);
		free(timestamp_log);
	}

	// Open file
	FILE *file = fopen(log_file_name, "a");

	// Check the size file and create new file if the size exceed 1000000 bytes
	fseek(file, 0, SEEK_END);
	long size = ftell(file);
	if (size > 100000)
	{
		// Clear the filename and close the file
		fclose(file);
		// create file name
		timestamp_log = generate_string_time(LOCAL);
		sprintf(log_file_name, "logs/%s.txt", timestamp_log);
		free(timestamp_log);
		// Open the file
		file = fopen(log_file_name, "a");
	}

	if (file == NULL)
	{
		printf("Error opening file %s\n", filename);
		return;
	}

	// Get the current time
	time_t rawtime;
	struct tm *timeinfo;
	char timestamp[20];
	time(&rawtime);
	timeinfo = localtime(&rawtime);
	strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", timeinfo);

	// Write the timestamp and log level to the file
	fprintf(file, "[%s] [%s] [%s:%d] - ", timestamp, getLogLevelString(level), filename, line);

	// Write the formatted message to the file
	va_list args;
	va_start(args, format);
	vfprintf(file, format, args);
	va_end(args);

	// Close the file
	fclose(file);
}
/**
 * Consumes a Kafka message and updates an SQLite database based on the message content.
 *
 * @param rkmessage A pointer to the Kafka message to consume.
 * @param db A pointer to the SQLite database.
 */
void msg_consume(rd_kafka_message_t *rkmessage, sqlite3 *db)
{
	if (rkmessage->err)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Kafka error: %s\n", rd_kafka_message_errstr(rkmessage));
		return;
	}

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Received message: %.*s\n", (int)rkmessage->len, (char *)rkmessage->payload);

	// Parse JSON message
	json_error_t error;
	json_t *root = json_loadb(rkmessage->payload, rkmessage->len, 0, &error);
	if (!root)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "JSON parsing error: %s\n", error.text);
		return;
	}

	const char *type_str = NULL;
	const char *createdBlockedListKey = NULL;

	// Check 'type' field
	json_t *type = json_object_get(root, "type");
	if (!type || !json_is_string(type))
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Key 'type' not found or not a string\n");
		goto cleanup;
	}
	type_str = json_string_value(type);
	if (!type_str)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to get 'type' value as string\n");
		goto cleanup;
	}

	// Check 'createdBlockedList' based on 'type'
	if (strcmp(type_str, "create") == 0)
		createdBlockedListKey = "createdBlockedList";
	else if (strcmp(type_str, "update") == 0)
		createdBlockedListKey = "updatedBlockedList";
	else if (strcmp(type_str, "delete") == 0)
		createdBlockedListKey = "deletedBlockedList";
	else
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Unsupported 'type' value: %s\n", type_str);
		goto cleanup;
	}

	// Extract 'createdBlockedList'
	json_t *createdBlockedList = json_object_get(root, createdBlockedListKey);
	if (!createdBlockedList || !json_is_object(createdBlockedList))
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Key '%s' not found or not an object\n", createdBlockedListKey);
		goto cleanup;
	}

	// Extract 'domain', 'ip_add', and 'id' fields
	json_t *domain = json_object_get(createdBlockedList, "domain");
	json_t *ip_add = json_object_get(createdBlockedList, "ip_add");
	json_t *id = json_object_get(createdBlockedList, "id");

	if (!domain || !json_is_string(domain) || !ip_add || !json_is_string(ip_add) || !id || !json_is_string(id))
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Missing or invalid keys in 'createdBlockedList'\n");
		goto cleanup;
	}

	const char *domain_str = json_string_value(domain);
	const char *ip_str = json_string_value(ip_add);
	const char *id_str = json_string_value(id);

	if (!domain_str || !ip_str || !id_str)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to get values from 'createdBlockedList'\n");
		goto cleanup;
	}

	// Update SQLite database
	char sql_query[256];
	int query_len = 0;

	if (strcmp(type_str, "create") == 0)
		query_len = snprintf(sql_query, sizeof(sql_query), "INSERT INTO policies (id, domain, ip_address) VALUES ('%s', '%s', '%s');", id_str, domain_str, ip_str);
	else if (strcmp(type_str, "update") == 0)
	{
		query_len = snprintf(sql_query, sizeof(sql_query), "UPDATE policies SET domain='%s', ip_address='%s' WHERE id='%s';", domain_str, ip_str, id_str);
		memset(domain_cache, 0, sizeof(domain_cache));
		domainCacheSize = 0;
		memset(ip_cache, 0, sizeof(ip_cache));
		ipCacheSize = 0;
	}
	else if (strcmp(type_str, "delete") == 0)
	{
		query_len = snprintf(sql_query, sizeof(sql_query), "DELETE FROM policies WHERE id='%s';", id_str);
		memset(domain_cache, 0, sizeof(domain_cache));
		domainCacheSize = 0;
		memset(ip_cache, 0, sizeof(ip_cache));
		ipCacheSize = 0;
	}
	else
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Unsupported 'type' value: %s\n", type_str);
		goto cleanup;
	}

	if (query_len <= 0 || query_len >= sizeof(sql_query))
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "SQL query creation error\n");
		goto cleanup;
	}

	char *errmsg = NULL;
	int sqlite_result = sqlite3_exec(db, sql_query, NULL, 0, &errmsg);
	if (sqlite_result != SQLITE_OK)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "SQL error: %s\n", errmsg);
		sqlite3_free(errmsg);
	}
	else
	{
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "%s updated to the database\n", domain_str);
	}

cleanup:
	if (root)
		json_decref(root);
}

/**
 * This function configures and starts an Ethernet port with the specified port number.
 * It sets up the receive (Rx) and transmit (Tx) queues, allocates memory for the queues,
 * and enables promiscuous mode for the port.
 *
 * @param port The port number to initialize.
 * @param mbuf_pool The memory pool to use for allocating mbufs.
 * @return 0 on success, a negative value on error.
 */

static inline int
port_init(uint16_t port, struct rte_mempool *mbuf_pool)
{
	// Declaration
	struct rte_eth_conf port_conf;
	const uint16_t rx_rings = 1, tx_rings = 1;
	uint16_t nb_rxd = RX_RING_SIZE;
	uint16_t nb_txd = TX_RING_SIZE;
	int retval;
	uint16_t q;
	struct rte_eth_dev_info dev_info;
	struct rte_eth_txconf txconf;

	// Check port validity
	if (!rte_eth_dev_is_valid_port(port))
		return -1;

	// Set memory for port configuration
	memset(&port_conf, 0, sizeof(struct rte_eth_conf));

	// Get the port info
	retval = rte_eth_dev_info_get(port, &dev_info);
	if (retval != 0)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error during getting device (port %u) info: %s\n",
				   port, strerror(-retval));
		return retval;
	}

	if (dev_info.tx_offload_capa & RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE)
		port_conf.txmode.offloads |=
			RTE_ETH_TX_OFFLOAD_MBUF_FAST_FREE;

	// Configure the Ethernet device
	retval = rte_eth_dev_configure(port, rx_rings, tx_rings, &port_conf);
	if (retval != 0)
		return retval;

	retval = rte_eth_dev_adjust_nb_rx_tx_desc(port, &nb_rxd, &nb_txd);
	if (retval != 0)
		return retval;

	// Allocate 1 Rx queue for each port
	for (q = 0; q < rx_rings; q++)
	{
		retval = rte_eth_rx_queue_setup(port, q, nb_rxd,
										rte_eth_dev_socket_id(port), NULL, mbuf_pool);
		if (retval < 0)
			return retval;
	}

	txconf = dev_info.default_txconf;
	txconf.offloads = port_conf.txmode.offloads;
	// Allocate 1 Tx queue for each port
	for (q = 0; q < tx_rings; q++)
	{
		retval = rte_eth_tx_queue_setup(port, q, nb_txd,
										rte_eth_dev_socket_id(port), &txconf);
		if (retval < 0)
			return retval;
	}

	// Starting the ethernet port
	retval = rte_eth_dev_start(port);
	if (retval < 0)
		return retval;

	// Display the MAC Addresses
	struct rte_ether_addr addr;
	retval = rte_eth_macaddr_get(port, &addr);
	if (retval != 0)
		return retval;

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Port %u MAC: %02" PRIx8 " %02" PRIx8 " %02" PRIx8 " %02" PRIx8 " %02" PRIx8 " %02" PRIx8 "\n",
			   port, RTE_ETHER_ADDR_BYTES(&addr));

	// SET THE PORT TO PROMOCIOUS
	retval = rte_eth_promiscuous_enable(port);
	if (retval != 0)
		return retval;

	return 0;
}

/**
 * Opens a file in append mode and returns a file pointer.
 *
 * @param filename The name of the file to be opened.
 * @return A file pointer to the opened file.
 * @throws An error message and exits the program if the file cannot be opened.
 */
static FILE *open_file(const char *filename)
{
	FILE *f = fopen(filename, "a+");
	if (f == NULL)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error opening file %s\n", filename);
		rte_exit(EXIT_FAILURE, "Error opening file %s\n", filename);
	}
	return f;
}

/**
 * This function resets the statistics data for all Ethernet ports by setting
 * the memory to zero.
 */
static void clear_stats(void)
{
	memset(port_statistics, 0, RTE_MAX_ETHPORTS * sizeof(struct port_statistics_data));
}

char *generate_filename()
{
	time_t now, rounded;
	struct tm *tm_info, *tm_rounded;
	char time_str_file[80];
	const char *format = "%Y-%m-%dT%H:%M:%S";
	char *filename = (char *)calloc(100, sizeof(char));

	// get the current time
	time(&now);
	tm_info = localtime(&now);

	// get the current minute and second
	int current_min = tm_info->tm_min;
	int current_sec = tm_info->tm_sec;

	// get the rounded time
	int remaining_seconds = current_min % TIMER_PERIOD_SEND * 60 + current_sec;
	rounded = now - remaining_seconds;
	tm_rounded = localtime(&rounded);

	// convert the time to string
	strftime(time_str_file, 100, format, tm_rounded);

	// create the filename
	strcat(filename, STAT_FILE);
	strcat(filename, time_str_file);
	strcat(filename, STAT_FILE_EXT);

	return filename;
}

static void
print_stats()
{
	unsigned int portid;

	const char clr[] = {27, '[', '2', 'J', '\0'};
	const char topLeft[] = {27, '[', '1', ';', '1', 'H', '\0'};

	// Clear screen and move to top left
	printf("%s%s", clr, topLeft);
	printf("PACKET BORKER\n");
	printf("\nRefreshed every %d seconds. "
		   "Send every %d minutes.\n",
		   TIMER_PERIOD_STATS, TIMER_PERIOD_SEND);
	printf("\nPort statistics ====================================");

	for (portid = 0; portid < 2; portid++)
	{
		printf("\nStatistics for port %u ------------------------------"
			   "\nPackets sent count: %18" PRIu64
			   "\nPackets sent size: %19" PRIu64
			   "\nPackets received count: %14" PRIu64
			   "\nPackets received size: %15" PRIu64
			   "\nPackets dropped: %21" PRIu64
			   "\nTCP RST to Client: %19" PRIu64
			   "\nTCP RST to Server: %19" PRIu64
			   "\nThroughput: %26" PRId64
			   "\nPacket errors rx: %20" PRIu64
			   "\nPacket errors tx: %20" PRIu64,
			   portid,
			   port_statistics[portid].tx_count,
			   port_statistics[portid].tx_size,
			   port_statistics[portid].rx_count,
			   port_statistics[portid].rx_size,
			   port_statistics[portid].dropped,
			   port_statistics[portid].rstClient,
			   port_statistics[portid].rstServer,
			   port_statistics[portid].throughput,
			   port_statistics[portid].err_rx,
			   port_statistics[portid].err_tx);
	}
	printf("\n=====================================================");
	printf("\nStart time: %s\n", start_time);
	fflush(stdout);
}

/**
 * This function writes the header row to the specified file in CSV format.
 * The header row contains the names of the different statistics fields.
 *
 * @param f The file pointer to write the header to.
 */
static void print_stats_csv_header(FILE *f)
{
	fprintf(f, "ps_id,rstClient,rstServer,rx_http_count,tx_http_count,rx_http_size,tx_http_size,rx_http_drop,rx_http_error,tx_http_error,rx_http_mbuf,rx_tls_count,tx_tls_count,rx_tls_size,tx_tls_size,rx_tls_drop,rx_tls_error,tx_tls_error,rx_tls_mbuf,rx_o_count,tx_o_count,rx_o_size,tx_o_size,rx_o_drop,rx_o_error,tx_o_error,rx_o_mbuf,time,rx_i_http_throughput,rx_i_tls_throughput,tx_o_throughput\n"); // Header row
}

/**
 * This function takes a file pointer and a timestamp as input and writes the statistics data to the CSV file.
 * The statistics data includes various metrics such as packet counts, packet sizes, errors, and throughput for different ports.
 *
 * @param f         The file pointer to the CSV file.
 * @param timestamp The timestamp to be included in the CSV file.
 */

static void print_stats_csv(FILE *f, char *timestamp)
{
        fprintf(f, "%s,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%s,%ld,%ld,%ld\n",
                PS_ID,
                port_statistics[rst_port].rstClient,
                port_statistics[rst_port].rstServer,

                port_statistics[http_port].rx_count,
                port_statistics[http_port].tx_count,
                port_statistics[http_port].rx_size,
                port_statistics[http_port].tx_size,
                port_statistics[http_port].dropped,
                port_statistics[http_port].err_rx,
                port_statistics[http_port].err_tx,
                port_statistics[http_port].mbuf_err,

                port_statistics[tls_port].rx_count,
                port_statistics[tls_port].tx_count,
                port_statistics[tls_port].rx_size,
                port_statistics[tls_port].tx_size,
                port_statistics[tls_port].dropped,
                port_statistics[tls_port].err_rx,
                port_statistics[tls_port].err_tx,
                port_statistics[tls_port].mbuf_err,

                port_statistics[rst_port].rx_count,
                port_statistics[rst_port].tx_count,
                port_statistics[rst_port].rx_size,
                port_statistics[rst_port].tx_size,
                port_statistics[rst_port].dropped,
                port_statistics[rst_port].err_rx,
                port_statistics[rst_port].err_tx,
                port_statistics[rst_port].mbuf_err,

                timestamp,
                port_statistics[http_port].throughput,
                port_statistics[tls_port].throughput,
                port_statistics[rst_port].throughput);
}



/**
 * This function reads the configuration file located at "config/config.cfg" and sets the values of various variables based on the key-value pairs in the file.
 * The function expects the configuration file to be in the format "key = value", where the key is a string and the value is an integer or a string.
 */

int load_config_file()
{
	FILE *configFile = fopen("config/config.cfg", "r");
	if (configFile == NULL)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Cannot open the config file\n");
		return 1;
	}

	char line[256];
	char key[256];
	char value[256];

	while (fgets(line, sizeof(line), configFile))
	{
		if (sscanf(line, "%255[^=]= %255[^\n]", key, value) == 2)
		{
			if (strcmp(key, "MAX_PACKET_LEN") == 0)
			{
				MAX_PACKET_LEN = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "MAX_PACKET_LEN: %d\n", MAX_PACKET_LEN);
			}
			else if (strcmp(key, "RX_RING_SIZE") == 0)
			{
				RX_RING_SIZE = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "RX_RING_SIZE: %d\n", RX_RING_SIZE);
			}
			else if (strcmp(key, "TX_RING_SIZE") == 0)
			{
				TX_RING_SIZE = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "TX_RING_SIZE: %d\n", TX_RING_SIZE);
			}
			else if (strcmp(key, "NUM_MBUFS") == 0)
			{
				NUM_MBUFS = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "NUM_MBUFS: %d\n", NUM_MBUFS);
			}
			else if (strcmp(key, "MBUF_CACHE_SIZE") == 0)
			{
				MBUF_CACHE_SIZE = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "MBUF_CACHE_SIZE: %d\n", MBUF_CACHE_SIZE);
			}
			else if (strcmp(key, "BURST_SIZE") == 0)
			{
				BURST_SIZE = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "BURST_SIZE: %d\n", BURST_SIZE);
			}
			else if (strcmp(key, "MAX_TCP_PAYLOAD_LEN") == 0)
			{
				MAX_TCP_PAYLOAD_LEN = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "MAX_TCP_PAYLOAD_LEN: %d\n", MAX_TCP_PAYLOAD_LEN);
			}
			else if (strcmp(key, "STAT_FILE") == 0)
			{
				strcpy(STAT_FILE, value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "STAT_FILE: %s\n", STAT_FILE);
			}
			else if (strcmp(key, "STAT_FILE_EXT") == 0)
			{
				strcpy(STAT_FILE_EXT, value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "STAT_FILE_EXT: %s\n", STAT_FILE_EXT);
			}
			else if (strcmp(key, "TIMER_PERIOD_STATS") == 0)
			{
				TIMER_PERIOD_STATS = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "TIMER_PERIOD_STATS: %d\n", TIMER_PERIOD_STATS);
			}
			else if (strcmp(key, "TIMER_PERIOD_SEND") == 0)
			{
				TIMER_PERIOD_SEND = atoi(value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "TIMER_PERIOD_SEND: %d\n", TIMER_PERIOD_SEND);
			}
			else if (strcmp(key, "ID_PS") == 0)
			{
				strcpy(PS_ID, value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "PS ID: %s\n", PS_ID);
			}
			else if (strcmp(key, "HOSTNAME") == 0)
			{
				strcpy(HOSTNAME, value);
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "HOSTNAME: %s\n", HOSTNAME);
			}
		}
	}

	fclose(configFile);
	return 0;
}

/**
 * This function is responsible for handling the SIGINT and SIGTERM signals. When either of these signals is received,
 * the function logs a message indicating the signal received and sets the `force_quit` flag to true, indicating that
 * the program should prepare to exit.
 */
static void
signal_handler(int signum)
{
	if (signum == SIGINT || signum == SIGTERM)
	{
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Signal %d received, preparing to exit...\n", signum);
		force_quit = true;
	}
}

/**
 * This function is used as a callback for the CURLOPT_WRITEFUNCTION option in a libcurl request.
 * It is called by libcurl whenever response data is received from the server.
 *
 * @param contents A pointer to the response data received from the server.
 * @param size The size of each element in the response data.
 * @param nmemb The number of elements in the response data.
 * @param userp A pointer to user-defined data passed to the CURLOPT_WRITEDATA option.
 *
 * @return The total number of bytes written.
 */
size_t write_callback(void *contents, size_t size, size_t nmemb, void *userp)
{
	size_t real_size = size * nmemb;
	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Response: %.*s \n", (int)real_size, (char *)contents);
	return real_size;
}

/**
 * This function iterates over the `db_hit_count` array and creates a JSON object for each entry
 * with a non-zero hit count. The JSON object contains the entry's ID and hit count. The JSON
 * objects are then appended to the provided JSON array.
 *
 * @param jsonArray A pointer to the JSON array to populate.
 */
static void populate_json_hitcount(json_t *jsonArray)
{
	for (int i = 0; i < CACHE_SIZE; i++)
	{
		// Only create and append objects if hit_count > 0
		if (db_hit_count[i].hit_count > 0)
		{
			// Create object for each entry with non-zero hit_count
			json_t *jsonObject = json_object();
			json_object_set(jsonObject, "id", json_string(db_hit_count[i].id));
			json_object_set(jsonObject, "hit_count", json_integer(db_hit_count[i].hit_count));
			// Append the JSON object to the JSON array
			json_array_append(jsonArray, jsonObject);
		}
	}
	memset(db_hit_count, 0, sizeof(db_hit_count));
}
/**
 * This function takes a JSON array and a timestamp as input and populates a JSON object with various statistics data.
 * The statistics data includes counts, sizes, errors, drops, and throughput for different types of HTTP and TLS traffic.
 * The populated JSON object is then appended to the JSON array.
 *
 * @param jsonArray A pointer to the JSON array to which the populated JSON object will be appended.
 * @param timestamp A pointer to the timestamp string to be included in the JSON object.
 */

static void
populate_json_stats(json_t *jsonArray, char *timestamp)
{
        json_t *jsonObject = json_object();

        json_object_set(jsonObject, "ps_id", json_string(PS_ID));

        /* HTTP and TLS input ports are both active. */
        json_object_set(jsonObject, "rx_i_http_count",
                        json_integer(port_statistics[http_port].rx_count));
        json_object_set(jsonObject, "tx_i_http_count",
                        json_integer(port_statistics[http_port].tx_count));
        json_object_set(jsonObject, "rx_i_http_size",
                        json_integer(port_statistics[http_port].rx_size));
        json_object_set(jsonObject, "tx_i_http_size",
                        json_integer(port_statistics[http_port].tx_size));
        json_object_set(jsonObject, "rx_i_http_drop",
                        json_integer(port_statistics[http_port].dropped));
        json_object_set(jsonObject, "rx_i_http_error",
                        json_integer(port_statistics[http_port].err_rx));
        json_object_set(jsonObject, "tx_i_http_error",
                        json_integer(port_statistics[http_port].err_tx));
        json_object_set(jsonObject, "rx_i_http_mbuf",
                        json_integer(port_statistics[http_port].mbuf_err));

        json_object_set(jsonObject, "rx_i_tls_count",
                        json_integer(port_statistics[tls_port].rx_count));
        json_object_set(jsonObject, "tx_i_tls_count",
                        json_integer(port_statistics[tls_port].tx_count));
        json_object_set(jsonObject, "rx_i_tls_size",
                        json_integer(port_statistics[tls_port].rx_size));
        json_object_set(jsonObject, "tx_i_tls_size",
                        json_integer(port_statistics[tls_port].tx_size));
        json_object_set(jsonObject, "rx_i_tls_drop",
                        json_integer(port_statistics[tls_port].dropped));
        json_object_set(jsonObject, "rx_i_tls_error",
                        json_integer(port_statistics[tls_port].err_rx));
        json_object_set(jsonObject, "tx_i_tls_error",
                        json_integer(port_statistics[tls_port].err_tx));
        json_object_set(jsonObject, "rx_i_tls_mbuf",
                        json_integer(port_statistics[tls_port].mbuf_err));

        /* RST traffic always uses its dedicated output port. */
        json_object_set(jsonObject, "rstClient",
                        json_integer(port_statistics[rst_port].rstClient));
        json_object_set(jsonObject, "rstServer",
                        json_integer(port_statistics[rst_port].rstServer));
        json_object_set(jsonObject, "rx_o_count",
                        json_integer(port_statistics[rst_port].rx_count));
        json_object_set(jsonObject, "tx_o_count",
                        json_integer(port_statistics[rst_port].tx_count));
        json_object_set(jsonObject, "rx_o_size",
                        json_integer(port_statistics[rst_port].rx_size));
        json_object_set(jsonObject, "tx_o_size",
                        json_integer(port_statistics[rst_port].tx_size));
        json_object_set(jsonObject, "rx_o_drop",
                        json_integer(port_statistics[rst_port].dropped));
        json_object_set(jsonObject, "rx_o_error",
                        json_integer(port_statistics[rst_port].err_rx));
        json_object_set(jsonObject, "tx_o_error",
                        json_integer(port_statistics[rst_port].err_tx));
        json_object_set(jsonObject, "rx_o_mbuf",
                        json_integer(port_statistics[rst_port].mbuf_err));

        json_object_set(jsonObject, "time", json_string(timestamp));
        json_object_set(jsonObject, "rx_i_http_throughput",
                        json_integer(port_statistics[http_port].throughput));
        json_object_set(jsonObject, "rx_i_tls_throughput",
                        json_integer(port_statistics[tls_port].throughput));
        json_object_set(jsonObject, "tx_o_throughput",
                        json_integer(port_statistics[rst_port].throughput));

        json_array_append(jsonArray, jsonObject);
}

/*This function retrieves statistics for each port using the `rte_eth_stats_get()` function.
 * It then updates the statistics in the `port_statistics` array based on the retrieved values.
 * After updating the statistics, it clears the statistics for each port using the `rte_eth_stats_reset()` function.
 * Finally, it calculates the throughput for each port by dividing the received or transmitted size by the timer period.
 */
static void
collect_stats()
{
	const uint16_t ports[] = {http_port, tls_port, rst_port};

	for (size_t i = 0; i < RTE_DIM(ports); i++)
	{
		const uint16_t port = ports[i];
		struct rte_eth_stats stats;
		struct port_statistics_data *port_stats = &port_statistics[port];

		if (rte_eth_stats_get(port, &stats) != 0)
		{
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__,
					   "Cannot read statistics for port %u\n", port);
			continue;
		}

		port_stats->rx_count = stats.ipackets;
		port_stats->tx_count = stats.opackets;
		port_stats->rx_size = stats.ibytes;
		port_stats->tx_size = stats.obytes;
		port_stats->dropped = stats.imissed;
		port_stats->err_rx = stats.ierrors;
		port_stats->err_tx = stats.oerrors;
		port_stats->mbuf_err = stats.rx_nombuf;
		port_stats->throughput = (port == rst_port ? stats.obytes : stats.ibytes)
								 / TIMER_PERIOD_STATS;

		if (rte_eth_stats_reset(port) != 0)
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__,
					   "Cannot reset statistics for port %u\n", port);
	}

	rstClient = 0;
	rstServer = 0;
}

static void print_stats_file(FILE **f_stat)
{
	int current_sec;

	char *filename;
	char *time_str_local;

	// check file
	if (!*f_stat)
	{
		// create the filename
		filename = generate_filename();
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Creating file %s\n", filename);
		*f_stat = open_file(filename);

		// print the header of the statistics file
		print_stats_csv_header(*f_stat);

		// clean memory allocation
		free(filename);
	}

	// print out the stats to csv
	time_str_local = generate_string_time(LOCAL);
	print_stats_csv(*f_stat, time_str_local);
	free(time_str_local);

	// flush the file
	fflush(*f_stat);
}
/**
 * Sends the hit count data to the server.
 *
 * @param jsonArray A pointer to the JSON array containing the hit count data.
 */
static void send_hitcount_to_server(json_t *jsonArray)
{
	if (countFlag == 1)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Count Exceeds Threshold, Failed to Send\n");
		if (jsonArray)
			json_array_clear(jsonArray);
		countFlag = 0;
		return;
	}
	CURL *curl;
	CURLcode res;
	struct curl_slist *headers = NULL;
	char *jsonString = json_dumps(jsonArray, 0);
	char url[256];

	sprintf(url, "%s/ps/blocked-list-count", HOSTNAME);

	curl_global_init(CURL_GLOBAL_DEFAULT);
	curl = curl_easy_init();

	if (!curl)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to initialize CURL\n");
		goto cleanup;
	}

	headers = curl_slist_append(headers, "Content-Type: application/json");
	if (!headers)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to create headers\n");
		goto cleanup;
	}

	curl_easy_setopt(curl, CURLOPT_URL, url);
	curl_easy_setopt(curl, CURLOPT_CUSTOMREQUEST, "PUT");
	curl_easy_setopt(curl, CURLOPT_POSTFIELDS, jsonString);
	curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);
	curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);

	res = curl_easy_perform(curl);
	if (res != CURLE_OK)
	{
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "curl_easy_perform() failed: %s\n", curl_easy_strerror(res));
		logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Send Count failed: %s\n", curl_easy_strerror(res));
		goto cleanup;
	}
	else
	{
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Send Count Success: %s\n", jsonString);
	}

cleanup:
	if (headers)
		curl_slist_free_all(headers);

	if (curl)
		curl_easy_cleanup(curl);

	if (jsonString)
		free(jsonString);

	if (jsonArray)
		json_array_clear(jsonArray);

	curl_global_cleanup();
}

/**
 * This function checks the current time and sends the statistics to the server
 * if the current minute is divisible by `TIMER_PERIOD_SEND` and is different
 * from the last time the statistics were sent.
 *
 * @param jsonArray A pointer to a JSON array containing the statistics data.
 * @param last_run_send A pointer to an integer representing the last minute
 *                      the statistics were sent.
 */
static void
send_stats(json_t *jsonArray)
{
	CURL *curl;
	CURLcode res;
	struct curl_slist *headers = curl_slist_append(headers, "Content-Type: application/json");
	long res_code = 0;
	char *jsonString = json_dumps(jsonArray, 0);
	char url[256];
	size_t size = json_array_size(jsonArray);

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Start sending %d statistics to server\n", json_array_size(jsonArray));

	sprintf(url, "%s/ps/ps-packet", HOSTNAME);

	curl_global_init(CURL_GLOBAL_DEFAULT);
	curl = curl_easy_init();

	if (curl)
	{
		headers = curl_slist_append(headers, "Content-Type: application/json");

		curl_easy_setopt(curl, CURLOPT_URL, url);
		curl_easy_setopt(curl, CURLOPT_POSTFIELDS, jsonString);
		curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

		res = curl_easy_perform(curl);
		curl_easy_getinfo(curl, CURLINFO_RESPONSE_CODE, &res_code);

		if (res != CURLE_OK)
		{
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Send %d Stats failed: %s\n", size, curl_easy_strerror(res));
		}
		else if (res_code != 200)
		{
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Send %d Stats failed: connection error with code %d\n", size, res_code);
		}
		else
		{
			if (size < (60 * TIMER_PERIOD_SEND))
			{
				logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Stats data is not normal\n");
			}
			logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Send %d Stats success\n", size);
			free(jsonString);
		}

		if (res_code == 200)
		{
			json_array_clear(jsonArray);
		}

		curl_slist_free_all(headers);
		curl_easy_cleanup(curl);
	}

	curl_global_cleanup();
}

/**
 * This function extracts the domain name from an HTTPS packet.
 *
 * @param pkt A pointer to the packet from which to extract the domain name.
 * @return A pointer to the extracted domain name.
 */
static inline char *extractDomainfromHTTPS(struct rte_mbuf *pkt)
{
	// Extract Ethernet header
	struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(pkt, struct rte_ether_hdr *);

	if (eth_hdr->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
	{
		return NULL;
	}

	// Extract IPv4 header
	struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);

	if (ip_hdr->next_proto_id != IPPROTO_TCP)
	{
		return NULL;
	}

	// Extract TCP header
	struct rte_tcp_hdr *tcp_hdr = (struct rte_tcp_hdr *)((uint8_t *)ip_hdr + sizeof(struct rte_ipv4_hdr));

	// Calculate the offset to the TLS header (if TLS is in use)
	int tls_offset = (tcp_hdr->data_off & 0xf0) >> 2;

	if (tls_offset <= 0)
	{
		return NULL;
	}

	// Calculate the total length of the TLS payload
	int tls_payload_length = ntohs(ip_hdr->total_length) - (sizeof(struct rte_ipv4_hdr) + (tcp_hdr->data_off >> 4) * 4);

	if (tls_payload_length <= 0)
	{
		return NULL;
	}

	int start_offset = 76;
	int end_offset = 77;

	if (start_offset < 0 || end_offset >= tls_payload_length)
	{
		return NULL;
	}

	// Extract the TLS payload as a pointer to uint8_t
	uint8_t *tls_payload = (uint8_t *)tcp_hdr + tls_offset;
	uint16_t combinedValue = (uint16_t)tls_payload[start_offset] << 8 | (uint16_t)tls_payload[end_offset];

	// Process the specific range of bytes in the TLS payload
	int counter = 82 + combinedValue;
	char extractedName[256]; // Assuming a maximum name length of 256 characters
	int nameIndex = 0;		 // Index for the extractedName array

	while (1)
	{
		uint16_t type = (uint16_t)tls_payload[counter] << 8 | (uint16_t)tls_payload[counter + 1];

		if (type == 0)
		{
			uint16_t namelength = (uint16_t)tls_payload[counter + 7] << 8 | (uint16_t)tls_payload[counter + 8];

			for (int i = 0; i < namelength; i++)
			{
				extractedName[nameIndex] = (char)tls_payload[counter + 9 + i];
				nameIndex++;
			}
			extractedName[nameIndex] = '\0';

			// Dynamically allocate memory for the string to return
			char *result = (char *)malloc(strlen(extractedName) + 1);
			strcpy(result, extractedName);

			return result;
		}
		else
		{
			uint16_t length = (uint16_t)tls_payload[counter + 2] << 8 | (uint16_t)tls_payload[counter + 3];
			counter += length + 4;
		}
	}
}

/**
 * This function extracts the domain name from an HTTP packet.
 *
 * @param pkt A pointer to the packet from which to extract the domain name.
 * @return A pointer to the extracted domain name.
 */
static inline char *extractDomainfromHTTP(struct rte_mbuf *pkt)
{
	struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(pkt, struct rte_ether_hdr *);

	if (eth_hdr->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
	{
		return NULL;
	}

	struct rte_ipv4_hdr *ipv4_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);

	if (ipv4_hdr->next_proto_id != IPPROTO_TCP)
	{
		return NULL;
	}

	struct rte_tcp_hdr *tcp_hdr = (struct rte_tcp_hdr *)((unsigned char *)ipv4_hdr + sizeof(struct rte_ipv4_hdr));

	// Calculate the offset to the HTTP payload
	int payload_offset = ((tcp_hdr->data_off & 0xf0) >> 2);

	if (payload_offset <= 0)
	{
		return NULL;
	}

	// Pointer to the HTTP payload
	char *payload = (char *)tcp_hdr + payload_offset;

	char *host_start = strstr(payload, "Host:");
	if (host_start != NULL)
	{
		// Increment the pointer to skip "Host: "
		host_start += 6;
		char *host_end = strchr(host_start, '\r');
		if (host_end != NULL)
		{
			// Calculate host length
			int host_length = host_end - host_start;

			// Allocate memory for host
			char *host = (char *)malloc((host_length + 1) * sizeof(char)); // +1 for null terminator
			if (host == NULL)
			{
				return NULL;
			}

			// Copy host from payload
			strncpy(host, host_start, host_length);
			host[host_length] = '\0'; // Null-terminate the string
			return host;
		}
	}

	return NULL; // Return NULL if the HTTP host is not found or an error occurs.
}

/**
 * This function extracts the domain name from a packet based on the protocol.
 *
 * @param pkt A pointer to the packet from which to extract the domain name.
 * @param protocol The protocol of the packet (HTTP or HTTPS).
 * @return A pointer to the extracted domain name.
 */
static inline void reset_tcp_client(struct rte_mbuf *rx_pkt)
{
	struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(rx_pkt, struct rte_ether_hdr *);

	// Check if it's an IPv4 packet
	if (eth_hdr->ether_type == rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
	{
		struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
		struct rte_tcp_hdr *tcp_hdr = (struct rte_tcp_hdr *)(ip_hdr + 1);

		// Swap MAC addresses
		struct rte_ether_addr tmp_mac;
		rte_ether_addr_copy(&eth_hdr->dst_addr, &tmp_mac);
		rte_ether_addr_copy(&eth_hdr->src_addr, &eth_hdr->dst_addr);
		rte_ether_addr_copy(&tmp_mac, &eth_hdr->src_addr);

		// Swap IP addresses
		uint32_t tmp_ip = ip_hdr->src_addr;
		ip_hdr->src_addr = ip_hdr->dst_addr;
		ip_hdr->dst_addr = tmp_ip;

		// Swap TCP ports
		uint16_t tmp_port = tcp_hdr->src_port;
		tcp_hdr->src_port = tcp_hdr->dst_port;
		tcp_hdr->dst_port = tmp_port;

		// Set TCP header length
		tcp_hdr->data_off = (sizeof(struct rte_tcp_hdr) / 4) << 4; // Divide by 4 for 32-bit words

		// Set TCP flags to reset (RST)
		tcp_hdr->tcp_flags = RTE_TCP_RST;

		ip_hdr->total_length = rte_cpu_to_be_16(sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_tcp_hdr));

		// Extract the acknowledgment number from the TCP header
		uint32_t ack_number = rte_be_to_cpu_32(tcp_hdr->recv_ack);

		// Set the sequence number in the TCP header to the received acknowledgment number
		tcp_hdr->sent_seq = rte_cpu_to_be_32(ack_number);

		tcp_hdr->recv_ack = 0;

		// Calculate and set the new IP and TCP checksums (optional)
		tcp_hdr->cksum = 0;
		tcp_hdr->cksum = rte_ipv4_udptcp_cksum(ip_hdr, tcp_hdr);

		ip_hdr->hdr_checksum = 0;
		ip_hdr->hdr_checksum = rte_ipv4_cksum(ip_hdr);
	}
}

/**
 * This function resets the TCP server by sending a TCP RST packet in response to a received packet.
 *
 * @param rx_pkt A pointer to the received packet.
 */
static inline void reset_tcp_server(struct rte_mbuf *rx_pkt)
{
	struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(rx_pkt, struct rte_ether_hdr *);

	if (eth_hdr->ether_type == rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4))
	{
		struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
		struct rte_tcp_hdr *tcp_hdr = (struct rte_tcp_hdr *)(ip_hdr + 1);

		// Increment the sequence number by 1
		tcp_hdr->sent_seq = rte_cpu_to_be_32(rte_be_to_cpu_32(tcp_hdr->sent_seq) + 1);

		// Set acknowledgment number to 0
		tcp_hdr->recv_ack = rte_cpu_to_be_32(0);

		// Set TCP flags to reset (RST)
		tcp_hdr->tcp_flags = RTE_TCP_RST;

		// Set TCP header length
		tcp_hdr->data_off = (sizeof(struct rte_tcp_hdr) / 4) << 4; // Divide by 4 for 32-bit words

		// Set IP total length to 40 (TCP RST packets have no payload)
		ip_hdr->total_length = rte_cpu_to_be_16(40);

		// Calculate and set the new IP and TCP checksums
		ip_hdr->hdr_checksum = 0;
		tcp_hdr->cksum = 0;
		ip_hdr->hdr_checksum = rte_ipv4_cksum(ip_hdr);
		tcp_hdr->cksum = rte_ipv4_udptcp_cksum(ip_hdr, tcp_hdr);
	}
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
void countStrings(char strings[CACHE_SIZE][MAX_STRINGS], int numStrings)
{

	for (int i = 0; i < numStrings; i++)
	{
		// Use a flag to track if the string is found
		int found = 0;

		// Iterate over the existing db_hit_count entries
		for (int j = 0; j < CACHE_SIZE; j++)
		{
			// If the string is found, increment the hit_count
			if (strcmp(strings[i], db_hit_count[j].id) == 0)
			{
				db_hit_count[j].hit_count++;
				found = 1;
				break;
			}
			// If an empty slot is found, add the string as a new entry
			else if (db_hit_count[j].hit_count == 0)
			{
				strcpy(db_hit_count[j].id, strings[i]);
				db_hit_count[j].hit_count = 1;
				found = 1;
				break;
			}
		}

		// If the string wasn't found and no empty slots are available, stop
		if (!found)
		{
			break;
		}
	}

	memset(hitCount, 0, sizeof(hitCount));
	hitCounter = 0;
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
void init_database()
{
	// Check if the database file exists
	if (access(db_path, F_OK) != -1)
	{
		// Database file exists, open it
		if (sqlite3_open(db_path, &db) != SQLITE_OK)
		{
			// Handle database opening error
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error opening the database: %s\n", sqlite3_errmsg(db));
			// You may want to exit or return an error code here
		}
	}
	else
	{
		// Database file does not exist, create it
		if (sqlite3_open(db_path, &db) != SQLITE_OK)
		{
			// Handle database creation error
			logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error creating the database: %s\n", sqlite3_errmsg(db));
			// You may want to exit or return an error code here
		}
	}

	// Check if the 'policies' table exists
	char *check_table_sql = "SELECT count(*) FROM sqlite_master WHERE type='table' AND name='policies';";
	sqlite3_stmt *stmt;
	int result = sqlite3_prepare_v2(db, check_table_sql, -1, &stmt, NULL);

	if (result == SQLITE_OK)
	{
		if (sqlite3_step(stmt) == SQLITE_ROW)
		{
			int table_count = sqlite3_column_int(stmt, 0);
			if (table_count == 0)
			{
				// 'policies' table does not exist, create it
				char *create_table_sql = "CREATE TABLE policies (id TEXT PRIMARY KEY, ip_address TEXT, domain TEXT);";
				if (sqlite3_exec(db, create_table_sql, NULL, 0, NULL) != SQLITE_OK)
				{
					logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error creating the 'policies' table: %s\n", sqlite3_errmsg(db));
					// You may want to exit or return an error code here
				}
				else
				{
					logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Created 'policies' table.\n");
				}
			}
			else
			{
				logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "'policies' table already exists.\n");
			}
		}
	}
	else
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error checking for 'policies' table: %s\n", sqlite3_errmsg(db));
	}

	sqlite3_finalize(stmt); // Finalize the prepared statement
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
void delete_database()
{
	// Close the database if it's open
	if (db)
	{
		sqlite3_close(db);
		db = NULL;
	}

	// Delete the database file
	if (remove(db_path) != 0)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error deleting the database file.\n");
		return;
	}

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Database file deleted successfully.\n");
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
static inline bool ip_checker(struct rte_mbuf *rx_pkt)
{
	if (!db)
	{
		// Database is not initialized
		return false;
	}

	// Extract the destination IP address from the received packet (assuming IPv4)
	struct rte_ipv4_hdr *ip_hdr = rte_pktmbuf_mtod_offset(rx_pkt, struct rte_ipv4_hdr *, sizeof(struct rte_ether_hdr));
	char dest_ip_str[INET_ADDRSTRLEN];
	inet_ntop(AF_INET, &ip_hdr->dst_addr, dest_ip_str, INET_ADDRSTRLEN);

	// Check the cache first
	for (int i = 0; i < ipCacheSize; ++i)
	{
		if (strcmp(ip_cache[i].ip_address, dest_ip_str) == 0)
		{
			// Found in cache, update hit count and return true
			if (hitCounter < CACHE_SIZE)
			{
				strncpy(hitCount[hitCounter], ip_cache[i].id, MAX_STRINGS - 1);
				hitCount[hitCounter][MAX_STRINGS - 1] = '\0';
				hitCounter++;
			}
			else
			{
				countFlag = 1;
				logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to update Hitcount\n");
			}
			return true;
		}
	}

	// Prepare an SQL query to check if the IP address exists in the database
	char query[256];
	snprintf(query, sizeof(query), "SELECT id FROM policies WHERE ip_address = '%s'", dest_ip_str);

	// Execute the SQL query
	sqlite3_stmt *stmt;
	int result = sqlite3_prepare_v2(db, query, -1, &stmt, NULL);

	if (result != SQLITE_OK)
	{
		return false; // Error in preparing statement
	}

	// Execute the query and check if the IP address exists in the database
	char id[MAX_STRINGS] = {0}; // Assuming ID is a string of 36 characters
	if (sqlite3_step(stmt) == SQLITE_ROW)
	{
		// Retrieve the ID from the result
		strncpy(id, (const char *)sqlite3_column_text(stmt, 0), sizeof(id));
	}

	// Finalize the statement
	sqlite3_finalize(stmt);

	if (strlen(id) > 0)
	{
		// Add to cache
		if (ipCacheSize < CACHE_SIZE)
		{
			strncpy(ip_cache[ipCacheSize].ip_address, dest_ip_str, sizeof(ip_cache[ipCacheSize].ip_address));
			strncpy(ip_cache[ipCacheSize].id, id, sizeof(ip_cache[ipCacheSize].id));
			ipCacheSize++;
		}

		// Update hit count
		if (hitCounter < CACHE_SIZE)
		{
			strncpy(hitCount[hitCounter], id, MAX_STRINGS - 1);
			hitCount[hitCounter][MAX_STRINGS - 1] = '\0';
			hitCounter++;
		}
		else
		{
			countFlag = 1;
			logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to update Hitcount\n");
		}
		return true;
	}

	return false;
}

unsigned int hash_function(const char *str)
{
	unsigned int hash = 5381;
	int c;

	while ((c = *str++))
	{
		hash = ((hash << 5) + hash) + c; /* hash * 33 + c */
	}

	return hash % CACHE_SIZE;
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
static inline bool domain_checker(char *domain)
{

	if (domain == NULL || domain[0] == '\0')
	{
		return false;
	}

	// Use a hash table for faster lookup in the cache
	unsigned int hash = hash_function(domain);
	for (int i = 0; i < domainCacheSize; ++i)
	{
		if (strcmp(domain_cache[hash].domain, domain) == 0)
		{
			// Found in cache, update hit count and return true
			if (hitCounter < CACHE_SIZE)
			{
				strncpy(hitCount[hitCounter], domain_cache[hash].id, sizeof(domain_cache[hash].id));
				hitCounter++;
			}
			else
			{
				countFlag = 1;
				logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to update Hitcount\n");
			}

			return true;
		}
		hash = (hash + 1) % CACHE_SIZE; // Linear probing for collision resolution
	}

	if (!db)
	{
		// Database is not initialized
		return false;
	}

	// Prepare an SQL query to check if the domain exists in the database
	char query[256];
	snprintf(query, sizeof(query), "SELECT id FROM policies WHERE domain = '%s'", domain);

	// Execute the SQL query
	sqlite3_stmt *stmt;
	int result = sqlite3_prepare_v2(db, query, -1, &stmt, NULL);

	if (result != SQLITE_OK)
	{
		return false; // Error in preparing statement
	}

	// Execute the query and check if the domain exists in the database
	char id[MAX_STRINGS] = {0}; // Assuming ID is a string of 36 characters
	if (sqlite3_step(stmt) == SQLITE_ROW)
	{
		// Retrieve the ID from the result
		strncpy(id, (const char *)sqlite3_column_text(stmt, 0), sizeof(id));
	}

	// Finalize the statement
	sqlite3_finalize(stmt);

	if (strlen(id) > 0)
	{
		strncpy(domain_cache[hash].domain, domain, sizeof(domain_cache[hash].domain));
		strncpy(domain_cache[hash].id, id, sizeof(domain_cache[hash].id));
		// Add to cache
		if (domainCacheSize < CACHE_SIZE)
		{
			domainCacheSize++;
		}

		// Update hit count
		if (hitCounter < CACHE_SIZE)
		{
			strncpy(hitCount[hitCounter], id, sizeof(id));
			hitCounter++;
		}
		else
		{
			countFlag = 1;
			logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Failed to update Hitcount\n");
		}

		return true;
	}

	return false;
}

static void
runner_scheduler(int *run_stats, int *run_send, int *run_file, int *last_run_stats, int *last_run_send, int *last_run_file)
{
	time_t rawtime;
	struct tm *timeinfo;
	time(&rawtime);
	timeinfo = localtime(&rawtime);

	int current_sec = timeinfo->tm_sec;
	int current_min = timeinfo->tm_min;

	if (current_sec % TIMER_PERIOD_STATS == 0 && current_sec != *last_run_stats)
	{
		*run_stats = 1;
		*last_run_stats = current_sec;
	}

	if (current_min % TIMER_PERIOD_SEND == 0 && current_min != *last_run_send)
	{
		*run_send = 1;
		*last_run_send = current_min;
	}

	if (current_min % TIMER_PERIOD_SEND == 0 && current_sec == 59 && current_min != *last_run_file)
	{
		*run_file = 1;
		*last_run_file = current_min;
	}
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
static inline void
lcore_stats_process(void)
{
	// Variable declaration
	int run_stats = 0, run_send = 0, run_file = 0;				  // run flags
	int last_run_stats = 0, last_run_send = 0, last_run_file = 0; // last run flags
	FILE *f_stat = NULL;										  // File pointer for statistics
	json_t *jsonStats = json_array();
	json_t *jsonHitCount = json_array(); // JSON array for statistics

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Starting stats process in %d\n", rte_lcore_id());

	while (!force_quit)
	{
		runner_scheduler(&run_stats, &run_send, &run_file, &last_run_stats, &last_run_send, &last_run_file);

		countStrings(hitCount, hitCounter);

		// Collect data
		if (run_stats)
		{
			// Check Scheduler
			collect_stats();
		}

		// Check scheduler
		if (run_send)
		{
			populate_json_hitcount(jsonHitCount);

			send_hitcount_to_server(jsonHitCount);
		}

		// Check scheduler
		if (run_stats)
		{
			// Print Statistcs to file
			print_stats_file(&f_stat);
		}

		// Check Scheduler
		if (run_stats)
		{
			char *time_str_gmt;

			// populate the stats to json array
			time_str_gmt = generate_string_time(GMT);
			populate_json_stats(jsonStats, time_str_gmt);
			free(time_str_gmt);
		}

		if (run_stats)
		{
			// Print the statistics
			print_stats();
			// clear the stats
			clear_stats();
		}

		if (run_file)
		{
			// Close the file
			fclose(f_stat);
			f_stat = NULL;
		}

		if (run_send)
		{
			// Send stats
			send_stats(jsonStats);
		}

		// Reset Scheduler
		run_stats = 0;
		run_send = 0;
		run_file = 0;
	}

	// Close the file
	if (f_stat)
	{
		fclose(f_stat);
	}
}

static int packet_checker(struct rte_mbuf *pkt)
{
	// Parse Ethernet header
	struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(pkt, struct rte_ether_hdr *);

	// Check if it's an IP packet
	if (eth_hdr->ether_type != rte_be_to_cpu_16(RTE_ETHER_TYPE_IPV4))
	{
		return 0;
	}

	// Parse IP header
	struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);

	// Check if it's a TCP packet
	if (ip_hdr->next_proto_id != IPPROTO_TCP)
	{
		return 0;
	}

	// Parse TCP header
	struct rte_tcp_hdr *tcp_hdr = (struct rte_tcp_hdr *)((uint8_t *)ip_hdr + sizeof(struct rte_ipv4_hdr));

	// Calculate TCP payload length
	uint16_t ip_total_length = rte_be_to_cpu_16(ip_hdr->total_length);
	uint8_t tcp_header_length = (tcp_hdr->data_off >> 4) * 4;
	uint16_t tcp_payload_len = ip_total_length - sizeof(struct rte_ipv4_hdr) - tcp_header_length;

	// Point to the TCP payload data
	char *tcp_payload = (char *)tcp_hdr + tcp_header_length;

	// Check for HTTP GET request
	if (tcp_payload_len >= HTTP_GET_MAGIC_LEN && strncmp(tcp_payload, HTTP_GET_MAGIC, HTTP_GET_MAGIC_LEN) == 0)
	{
		return HTTP_GET;
	}

	// Check if the payload contains a TLS handshake message
	if (tcp_payload_len >= TLS_MAGIC_LEN && memcmp(tcp_payload, TLS_MAGIC, TLS_MAGIC_LEN) == 0 && tcp_payload_len > 5 && tcp_payload[5] == 1)
	{
		return TLS_CLIENT_HELLO;
	}

	// Return if there is no matching payload
	return 0;
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */

static inline void lcore_main_process(void)
{
	uint16_t port;
	uint64_t packet_type;
	bool domain_check;
	/*
	 * Check that the port is on the same NUMA node as the polling thread
	 * for best performance.
	 */
	RTE_ETH_FOREACH_DEV(port)
	if (rte_eth_dev_socket_id(port) >= 0 &&
		rte_eth_dev_socket_id(port) !=
			(int)rte_socket_id())
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "WARNING, port %u is on remote NUMA node to "
													   "polling thread.\n\tPerformance will "
													   "not be optimal.\n",
				   port);

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Core %u forwarding packets. [Ctrl+C to quit]\n",
			   rte_lcore_id());

	struct rte_mbuf *rx_bufs[BURST_SIZE];
	// Main work of application loop
	while (!force_quit)
	{
		const uint16_t input_ports[] = {http_port, tls_port};
		for (size_t input_index = 0; input_index < RTE_DIM(input_ports); input_index++)
		{
			const uint16_t input_port = input_ports[input_index];

			/* Poll both classifier inputs before returning to the first one. */
			rte_spinlock_lock(&rx_lock);
			const uint16_t rx_count = rte_eth_rx_burst(input_port, 0, rx_bufs, BURST_SIZE);
			rte_spinlock_unlock(&rx_lock);
			if (rx_count == 0)
				continue;

			for (uint16_t i = 0; i < rx_count; i++)
			{
				struct rte_mbuf *rx_pkt = rx_bufs[i];
				char *domain = NULL;

				packet_type = packet_checker(rx_pkt);

				/*
				 * Check the destination IP first; the domain parser is the
				 * fallback when the policy's IP does not match this packet.
				 */
				if (input_port == http_port && packet_type == HTTP_GET)
				{
					domain_check = ip_checker(rx_pkt);
					if (!domain_check)
					{
						domain = extractDomainfromHTTP(rx_pkt);
						domain_check = domain_checker(domain);
						free(domain);
					}
				}
				else if (input_port == tls_port && packet_type == TLS_CLIENT_HELLO)
				{
					domain_check = ip_checker(rx_pkt);
					if (!domain_check)
					{
						domain = extractDomainfromHTTPS(rx_pkt);
						domain_check = domain_checker(domain);
						free(domain);
					}
				}
				else
				{
					rte_pktmbuf_free(rx_pkt);
					continue;
				}

				if (domain_check)
				{
					const uint32_t header_len = sizeof(struct rte_ether_hdr) +
										  sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_tcp_hdr);
					struct rte_mbuf *rst_pkt_client =
						rte_pktmbuf_copy(rx_pkt, rx_pkt->pool, 0, header_len);
					if (rst_pkt_client == NULL)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Client\n");
						rte_pktmbuf_free(rx_pkt);
						continue;
					}

					struct rte_mbuf *rst_pkt_server =
						rte_pktmbuf_copy(rx_pkt, rx_pkt->pool, 0, header_len);
					if (rst_pkt_server == NULL)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Server\n");
						rte_pktmbuf_free(rst_pkt_client);
						rte_pktmbuf_free(rx_pkt);
						continue;
					}

					reset_tcp_client(rst_pkt_client);
					reset_tcp_server(rst_pkt_server);

					rte_spinlock_lock(&tx_lock);
					const uint16_t client_tx = rte_eth_tx_burst(rst_port, 0, &rst_pkt_client, 1);
					if (client_tx == 0)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error sending packet to client\n");
						rte_pktmbuf_free(rst_pkt_client);
					}
					else
					{
						port_statistics[rst_port].rstClient++;
					}

					const uint16_t server_tx = rte_eth_tx_burst(rst_port, 0, &rst_pkt_server, 1);
					if (server_tx == 0)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error sending packet to server\n");
						rte_pktmbuf_free(rst_pkt_server);
					}
					else
					{
						port_statistics[rst_port].rstServer++;
					}
					rte_spinlock_unlock(&tx_lock);
				}

				rte_pktmbuf_free(rx_pkt);
			}
		}
	}
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
static inline void
lcore_heartbeat_process()
{
	CURL *curl;
	CURLcode res;
	char post_fields[256];
	char url[256];
	char timestamp_str[25];
	time_t timestamp;
	struct tm *tm_info;
	struct curl_slist *headers = NULL;

	sprintf(url, "%s/ps/heartbeat", HOSTNAME);

	curl_global_init(CURL_GLOBAL_DEFAULT);
	curl = curl_easy_init();

	if (curl)
	{
		headers = curl_slist_append(headers, "Content-Type: application/json");

		while (!force_quit)
		{
			timestamp = time(NULL);
			tm_info = gmtime(&timestamp);
			strftime(timestamp_str, 25, "%Y-%m-%dT%H:%M:%S.000Z", tm_info);

			sprintf(post_fields, "[{\"ps_id\": \"%s\", \"time\": \"%s\"}]", PS_ID, timestamp_str);

			logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Post Fields : %s\n", post_fields);
			curl_easy_setopt(curl, CURLOPT_URL, url);
			curl_easy_setopt(curl, CURLOPT_POSTFIELDS, post_fields);
			curl_easy_setopt(curl, CURLOPT_HTTPHEADER, headers);

			curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, write_callback);

			res = curl_easy_perform(curl);

			if (res != CURLE_OK)
			{
				logMessage(LOG_LEVEL_WARNING, __FILE__, __LINE__, "Heartbeat failed: %s\n", curl_easy_strerror(res));
			}
			sleep(5);
		}

		curl_slist_free_all(headers);
		curl_easy_cleanup(curl);
	}

	curl_global_cleanup();
}

/**
 * This function creates a Kafka consumer, subscribes to a Kafka topic, opens an SQLite database,
 * and starts consuming messages from the topic. The consumed messages are then stored in the database.
 * The function continues to consume messages until the `force_quit` flag is set to true.
 */
static inline void
lcore_sync_database()
{
	rd_kafka_t *rk;			 // Kafka handle
	rd_kafka_conf_t *conf;	 // Kafka configuration
	rd_kafka_resp_err_t err; // Kafka error handler
	rd_kafka_topic_t *topic; // Kafka topic

	// Kafka configuration
	conf = rd_kafka_conf_new();
	if (rd_kafka_conf_set(conf, "bootstrap.servers", KAFKA_BROKER, NULL, 0) != RD_KAFKA_CONF_OK)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Failed to set Kafka broker configuration\n");
		return;
	}

	// Create Kafka consumer
	rk = rd_kafka_new(RD_KAFKA_CONSUMER, conf, NULL, 0);
	if (!rk)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Failed to create Kafka consumer\n");
		return;
	}

	// Subscribe to Kafka topic
	topic = rd_kafka_topic_new(rk, KAFKA_TOPIC, NULL);
	if (!topic)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Failed to create Kafka topic object\n");
		rd_kafka_destroy(rk);
		return;
	}

	// Open SQLite database
	if (sqlite3_open(db_path, &db) != SQLITE_OK)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Can't open database: %s\n", sqlite3_errmsg(db));
		rd_kafka_topic_destroy(topic);
		rd_kafka_destroy(rk);
		return;
	}

	// Start consuming messages
	if (rd_kafka_consume_start(topic, 0, RD_KAFKA_OFFSET_BEGINNING) == -1)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Failed to start consuming messages\n");
		rd_kafka_topic_destroy(topic);
		rd_kafka_destroy(rk);
		sqlite3_close(db);
		return;
	}

	// Loop to consume messages
	while (!force_quit)
	{
		rd_kafka_message_t *rkmessage;
		rkmessage = rd_kafka_consume(topic, 0, 1000); // 1 second timeout
		if (rkmessage)
		{
			msg_consume(rkmessage, db);
			rd_kafka_message_destroy(rkmessage);
		}
	}

	// Cleanup
	rd_kafka_consume_stop(topic, 0);
	rd_kafka_topic_destroy(topic);
	rd_kafka_destroy(rk);
	sqlite3_close(db);
}

static uint16_t resolve_policy_port(const char *role, const char *env_name,
							const char *default_pci)
{
	const char *pci = getenv(env_name);
	uint16_t port;

	if (pci == NULL || *pci == '\0')
		pci = default_pci;

	if (rte_eth_dev_get_port_by_name(pci, &port) != 0)
		rte_exit(EXIT_FAILURE, "%s adapter %s is not a DPDK Ethernet port\n",
				 role, pci);

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__,
			   "%s adapter %s mapped to DPDK port %u\n", role, pci, port);
	return port;
}

/**
 * This function is responsible for handling the received packets.
 *
 * @param rx_pkt A pointer to the received packet.
 */
int main(int argc, char *argv[])
{
	struct rte_mempool *mbuf_pool;
	unsigned nb_ports;
	uint16_t portid;
	unsigned lcore_id, lcore_stats = 0, lcore_db = 0;
	start_time = generate_string_time(LOCAL);
	init_database();

	// load the config file
	if (load_config_file())
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Cannot load the config file\n");
		rte_exit(EXIT_FAILURE, "Cannot load the config file\n");
	}

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Configuration File Successfully Updated\n");

	// Initializion the Environment Abstraction Layer (EAL)
	int ret = rte_eal_init(argc, argv);
	if (ret < 0)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error with EAL initialization\n");
		rte_exit(EXIT_FAILURE, "Error with EAL initialization\n");
	}

	argc -= ret;
	argv += ret;

	// force quit handler
	force_quit = false;
	signal(SIGINT, signal_handler);
	signal(SIGTERM, signal_handler);

	// clean the data
	memset(port_statistics, 0, sizeof(port_statistics));
	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Port Statistic Cleared\n");

	// Require both classifier inputs and the dedicated RST output.
	nb_ports = rte_eth_dev_count_avail();
	if (nb_ports != 3)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error: number of ports must be 3\n");
		rte_exit(EXIT_FAILURE, "Error: number of ports must be 3\n");
	}

	http_port = resolve_policy_port("HTTP input", "NETPRO_HTTP_PCI", "0000:0b:00.0");
	tls_port = resolve_policy_port("TLS input", "NETPRO_TLS_PCI", "0000:13:00.0");
	rst_port = resolve_policy_port("RST output", "NETPRO_RST_PCI", "0000:1b:00.0");
	if (http_port == tls_port || http_port == rst_port || tls_port == rst_port)
		rte_exit(EXIT_FAILURE, "HTTP, TLS, and RST must use distinct DPDK ports\n");

	// allocates the mempool to hold the mbufs
	mbuf_pool = rte_pktmbuf_pool_create("MBUF_POOL", NUM_MBUFS * nb_ports,
										MBUF_CACHE_SIZE, 0, RTE_MBUF_DEFAULT_BUF_SIZE, rte_socket_id());

	// check the mempool allocation
	if (mbuf_pool == NULL)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Cannot create mbuf pool\n");
		rte_exit(EXIT_FAILURE, "Cannot create mbuf pool\n");
	}
	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Successfully Created Mbuf Pool\n");

	// initializing ports
	RTE_ETH_FOREACH_DEV(portid)
	if (port_init(portid, mbuf_pool) != 0)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Cannot init port %" PRIu16 "\n", portid);
		rte_exit(EXIT_FAILURE, "Cannot init port %" PRIu16 "\n", portid);
	}

	// count the number of lcores
	unsigned int lcore_count = rte_lcore_count();
	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Number of lcores: %d\n", lcore_count);
	if (lcore_count < 4)
	{
		logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "lcore must be more than 3\n");
		rte_exit(EXIT_FAILURE, "lcore must be more than 3\n");
	}

	// Calculate the number of lcore_main
	unsigned int num_lcore_main = lcore_count - 3;
	unsigned int lcore_main[num_lcore_main];
	unsigned int lcore_main_index = 0;

	RTE_LCORE_FOREACH_WORKER(lcore_id)
	{
		if (lcore_main_index < num_lcore_main)
		{
			lcore_main[lcore_main_index++] = lcore_id;
			logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Core %u Assigned to Main Tasks\n", lcore_id);
			continue;
		}
		if (lcore_stats == 0)
		{
			lcore_stats = lcore_id;
			logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Stats Core Assigned On Core %u\n", lcore_id);
			continue;
		}
		if (lcore_db == 0)
		{
			lcore_db = lcore_id;
			logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Kafka Core Assigned On Core %u\n", lcore_id);
			continue;
		}
	}

	// run the lcore main function for each lcore_main
	for (unsigned int i = 0; i < lcore_main_index; ++i)
	{
		logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Initiating Main Core %u\n", lcore_main[i]);
		rte_eal_remote_launch((lcore_function_t *)lcore_main_process,
							  NULL, lcore_main[i]);
	}

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Initiating Kafka Core\n");
	rte_eal_remote_launch((lcore_function_t *)lcore_sync_database,
						  NULL, lcore_db);

	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Initiating Statistic Core\n");
	rte_eal_remote_launch((lcore_function_t *)lcore_stats_process,
						  NULL, lcore_stats);

	// run the heartbeat
	logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Initiating Heartbeat Mechanism\n");

	lcore_heartbeat_process();

	// wait all lcore stopped
	RTE_LCORE_FOREACH_WORKER(lcore_id)
	{
		if (rte_eal_wait_lcore(lcore_id) < 0)
			return -1;
	}
	// clean up the EAL
	delete_database();
	rte_eal_cleanup();
}
