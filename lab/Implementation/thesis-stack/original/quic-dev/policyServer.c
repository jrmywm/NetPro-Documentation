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
#include <unistd.h>
#include <getopt.h>
#include <signal.h>
#include <stdbool.h>
#include <time.h>
#include <unistd.h>
#include <curl/curl.h>
#include <jansson.h>
#include <sqlite3.h>
#include <librdkafka/rdkafka.h>
#include "quic-processor/quicFunctions.h"
#include <execinfo.h>


// DPDK library
#include <rte_eal.h>
#include <rte_ethdev.h>
#include <rte_cycles.h>
#include <rte_lcore.h>
#include <rte_mbuf.h>
#include <rte_tcp.h>
#include <rte_pdump.h>
#include <rte_spinlock.h>
#include <rte_ethdev.h>
#include <rte_bus_pci.h>  // For PCI-specific functions
#include <rte_dev.h>


//#include "quic-processor/quicFunctions.h"

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
#define UDP_QUIC 312

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


static const char *db_path = "/home/ir-policyserver/Documents/policyserver/NetPro-Policy-Server/policy.db";

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

//QUIC VARIABLES ================================================
QuicCryptoKeys keys;
// DEBUG VARS========================================================
#include <rte_byteorder.h>
int quic_detected_count = 0;
uint16_t debug_pkt_type = 0;
bool boolean_debug = false;
uint16_t debug_udp_dst_port = 0;
uint16_t debug_udp_src_port = 0;
bool bool_udp_port_debug = false;
uint8_t udp_payload_0 = 0;

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
	uint64_t quicCount;

	uint64_t connectionClose;
	long int throughput;
	uint64_t err_rx;
	uint64_t err_tx;
	uint64_t mbuf_err;
} __rte_cache_aligned;
struct port_statistics_data port_statistics[RTE_MAX_ETHPORTS];
struct rte_eth_stats stats_0;
struct rte_eth_stats stats_1;

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

// Inline function to sleep for 5.65 milliseconds
inline void sleep_5_65ms() {
    struct timespec req;
    req.tv_sec = 0;               // 0 seconds
    req.tv_nsec = 5000000L;       // 5.65 milliseconds = 5,650,000 nanoseconds
    nanosleep(&req, NULL);
}

void segfault_handler(int sig) {
    void *array[10];
    size_t size;

    // Get void*'s for all entries on the stack
    size = backtrace(array, 10);

    // Print out all the frames to stderr
    fprintf(stderr, "Error: signal %d (segmentation fault) received.\n", sig);
    backtrace_symbols_fd(array, size, STDERR_FILENO);

    exit(1);
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
	}
	else if (strcmp(type_str, "delete") == 0)
	{
		query_len = snprintf(sql_query, sizeof(sql_query), "DELETE FROM policies WHERE id='%s';", id_str);
		memset(domain_cache, 0, sizeof(domain_cache));
		domainCacheSize = 0;
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


struct rte_device {
	TAILQ_ENTRY(rte_device) next; 
	const char *name;             
	const struct rte_driver *driver; 
	const struct rte_bus *bus;    
	int numa_node;                
	struct rte_devargs *devargs;  
	};
static void
print_stats()
{
	unsigned int portid;
    struct rte_eth_dev_info dev_info;
    char pci_addr[100];  // Buffer for PCI address string

	const char clr[] = {27, '[', '2', 'J', '\0'};
	const char topLeft[] = {27, '[', '1', ';', '1', 'H', '\0'};
	// Get current time and calculate uptime
    // Get current time and format timestamp
    time_t now = time(NULL);
    struct tm *t = localtime(&now);
    char timestamp[32];
    strftime(timestamp, sizeof(timestamp), "%Y-%m-%d %H:%M:%S", t);

    // Array of ANSI color codes (foreground colors 31-36: Red, Green, Yellow, Blue, Magenta, Cyan)
    int colors[] = {31, 32, 33, 34, 35, 36};
    int num_colors = sizeof(colors) / sizeof(colors[0]);

    // Function to get a random color code string
    // Note: Using a static buffer is simple for this example, but be mindful
    // in more complex scenarios as it's not thread-safe and subsequent calls
    // overwrite the buffer.
    char* getRandomColor() {
        static char color_code[8]; // Buffer for "\033[XXm" + null terminator
        int random_index = rand() % num_colors;
        sprintf(color_code, "\033[%dm", colors[random_index]);
        return color_code;
    }

	// Clear screen and move to top left
	printf("%s%s", clr, topLeft);
	// RAINBOW ASCII ART =============================================================================
    printf("%s      ___           ___           ___           ___           ___           ___     \n", getRandomColor());
	printf("     /\\  \\         /\\  \\         /\\  \\         /\\__\\         /\\  \\         /\\  \\    \n");
	printf("%s    /::\\  \\       /::\\  \\       /::\\  \\       /:/  /        /::\\  \\        \\:\\  \\   \n", getRandomColor());
	printf("   /:/\\:\\  \\     /:/\\:\\  \\     /:/\\:\\  \\     /:/__/        /:/\\:\\  \\        \\:\\  \\  \n");
	printf("%s  /::\\~\\:\\  \\   /::\\~\\:\\  \\   /:/  \\:\\  \\   /::\\__\\____   /::\\~\\:\\  \\       /::\\  \\ \n", getRandomColor());
	printf(" /:/\\:\\ \\:\\__\\ /:/\\:\\ \\:\\__\\ /:/__/ \\:\\__\\ /:/\\:::::\\__\\ /:/\\:\\ \\:\\__\\     /:/\\:\\__\\\n");
	printf("%s \\/__\\:\\/:/  / \\/__\\:\\/:/  / \\:\\  \\  \\/__/ \\/_|:|~~|~    \\:\\~\\:\\ \\/__/    /:/  \\/__/\n", getRandomColor());
	printf("      \\::/  /       \\::/  /   \\:\\  \\          |:|  |      \\:\\ \\:\\__\\     /:/  /     \n");
	printf("%s       \\/__/        /:/  /     \\:\\  \\         |:|  |       \\:\\ \\/__/     \\/__/      \n", getRandomColor());
	printf("                   /:/  /       \\:\\__\\        |:|  \\         \\:\\__\\                  \n");
	printf("%s                   \\/__/         \\/__/         \\|__|          \\/__/                  \n", getRandomColor());
	printf("      ___           ___           ___           ___           ___           ___     \n");
	printf("%s     /\\  \\         /\\  \\         /\\  \\         /\\__\\         /\\  \\         /\\  \\    \n", getRandomColor());
	printf("    /::\\  \\       /::\\  \\       /::\\  \\       /:/  /        /::\\  \\       /::\\  \\   \n");
	printf("%s   /:/\\:\\  \\     /:/\\:\\  \\     /:/\\:\\  \\     /:/__/        /:/\\:\\  \\     /:/\\:\\  \\  \n", getRandomColor());
	printf("  /::\\~\\:\\__\\   /:/  \\:\\  \\   /::\\~\\:\\  \\   /::\\__\\____   /::\\~\\:\\  \\   /::\\~\\:\\  \\ \n");
	printf("%s /:/\\:\\ \\:|__| /:/__/ \\:\\__\\ /:/\\:\\ \\:\\__\\ /:/\\:::::\\__\\ /:/\\:\\ \\:\\__\\ /:/\\:\\ \\:\\__\\\n", getRandomColor());
	printf(" \\:\\~\\:\\/:/  / \\:\\  \\ /:/  / \\/_|::\\/:/  / \\/_|:|~~|~    \\:\\~\\:\\ \\/__/ \\/_|::\\/:/  /\n");
	printf("%s  \\:\\ \\::/  /   \\:\\  /:/  /     |:|::/  /     |:|  |      \\:\\ \\:\\__\\      |:|::/  / \n", getRandomColor());
	printf("   \\:\\/:/  /     \\:\\/:/  /      |:|\\/__/      |:|  |       \\:\\ \\/__/      |:|\\/__/  \n");
	printf("%s    \\::/__/       \\::/  /       |:|  |        |:|  |        \\:\\__\\        |:|  |    \n", getRandomColor());
	printf("     ~~            \\/__/         \\|__|         \\|__|         \\/__/         \\|__|    \033[0m\n"); // Reset color at the end
	// =============================================================================================
		printf("\n\n\033[1;36mSTATISTICS DASHBOARD\033[0m");
		printf("\n\033[1;34m---------------------------------------------\033[0m");
		printf("\n\033[1mRefreshed every %d seconds   |   Send every %d minutes\033[0m",
			   TIMER_PERIOD_STATS, TIMER_PERIOD_SEND);
		printf("\n\033[1;34m---------------------------------------------\033[0m\n");
		
		for (portid = 0; portid < 2; portid++) {
			rte_eth_dev_info_get(portid, &dev_info);
			
			if (portid == 0) {
				printf("\n\033[1;32m╔═════════════════════════════════════════════╗\033[0m");
				printf("\n\033[1;32m║  RX STATISTICS - Port %u (%-16s)  ║\033[0m", 
					   portid, dev_info.device->name);
				printf("\n\033[1;32m╠═════════════════════════════════════════════╣\033[0m");
				printf("\n\033[1;37m│ Packets Received Count: %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].rx_count);
				printf("\n\033[1;37m│ Packets Received Size:  %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].rx_size);
				printf("\n\033[1;37m│ QUIC Packets Detected:  %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].quicCount);
				printf("\n\033[1;37m│ Packets Dropped:        %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].dropped);
				printf("\n\033[1;37m│ Packet Errors (RX):     %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].err_rx);
				printf("\n\033[1;32m╚═════════════════════════════════════════════╝\033[0m");
			} else {
				printf("\n\033[1;33m╔═════════════════════════════════════════════╗\033[0m");
				printf("\n\033[1;33m║  TX STATISTICS - Port %u (%-16s)  ║\033[0m", 
					   portid, dev_info.device->name);
				printf("\n\033[1;33m╠═════════════════════════════════════════════╣\033[0m");
				printf("\n\033[1;37m│ Packets Sent Count:     %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].tx_count);
				printf("\n\033[1;37m│ Packets Sent Size:      %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].tx_size);
				printf("\n\033[1;37m│ TCP RST to Client:      %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].rstClient);
				printf("\n\033[1;37m│ TCP RST to Server:      %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].rstServer);
				printf("\n\033[1;37m│ QUIC Connection Close:  %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].connectionClose);
				printf("\n\033[1;37m│ Packet Errors (TX):     %18" PRIu64 "  │\033[0m", 
					   port_statistics[portid].err_tx);
				printf("\n\033[1;33m╚═════════════════════════════════════════════╝\033[0m");
			}
		}
		
		printf("\n\n\033[1;34m═════════════════════════════════════════════\033[0m");
		printf("\n\033[1;35m System Start Time: %s\033[0m", start_time);
		printf("\n\033[1;35m System Start Time: %04d-%02d-%02dT%02d:%02d:%02d\033[0m",
			t->tm_year + 1900,
			t->tm_mon + 1,
			t->tm_mday,
			t->tm_hour,
			t->tm_min,
			t->tm_sec
		);		
		printf("\n\033[1;34m═════════════════════════════════════════════\033[0m\n");
		fflush(stdout);

// === LOG FOR PORT 0 (RX) ===
const char *csv_file_rx = "telemetry/packet_stats_port0.csv";
int file_exists_rx = access(csv_file_rx, F_OK) == 0;

rte_eth_dev_info_get(0, &dev_info);
FILE *log_rx = fopen(csv_file_rx, "a");
if (log_rx) {
    if (!file_exists_rx) {
        fprintf(log_rx, "Timestamp,PortID,Device,PacketCount,PacketSize,QUIC_RST_Count,Dropped,Err_RX\n");
    }
    fprintf(log_rx, "\"%s\",%d,%s,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
        timestamp, 0, dev_info.device->name,
        port_statistics[0].rx_count,
        port_statistics[0].rx_size,
        port_statistics[0].quicCount,
        port_statistics[0].dropped,
        port_statistics[0].err_rx);
    fclose(log_rx);
}

// === LOG FOR PORT 1 (TX) ===
const char *csv_file_tx = "telemetry/packet_stats_port1.csv";
int file_exists_tx = access(csv_file_tx, F_OK) == 0;

rte_eth_dev_info_get(1, &dev_info);
FILE *log_tx = fopen(csv_file_tx, "a");
if (log_tx) {
    if (!file_exists_tx) {
        fprintf(log_tx, "Timestamp,PortID,Device,PacketCount,PacketSize,QUIC_RST_Count,Err_TX\n");
    }
    fprintf(log_tx, "\"%s\",%d,%s,%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
        timestamp, 1, dev_info.device->name,
        port_statistics[1].tx_count,
        port_statistics[1].tx_size,
        port_statistics[1].rstClient + port_statistics[1].rstServer + port_statistics[1].connectionClose,
        port_statistics[1].err_tx);
    fclose(log_tx);
}
	
}

/**
 * This function writes the header row to the specified file in CSV format.
 * The header row contains the names of the different statistics fields.
 *
 * @param f The file pointer to write the header to.
 */
static void print_stats_csv_header(FILE *f)
{
	fprintf(f, "ps_id,rstClient,rstServer,connection_close,rx_http_count,tx_http_count,rx_http_size,tx_http_size,rx_http_drop,rx_http_error,tx_http_error,rx_http_mbuf,rx_tls_count,tx_tls_count,rx_tls_size,tx_tls_size,rx_tls_drop,rx_tls_error,tx_tls_error,rx_tls_mbuf,rx_o_count,tx_o_count,rx_o_size,tx_o_size,rx_o_drop,rx_o_error,tx_o_error,rx_o_mbuf,time,rx_i_http_throughput,rx_i_tls_throughput,tx_o_throughput\n"); // Header row
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
	// Write data to the CSV file
	fprintf(f, "%s,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%ld,%s,%ld,%ld,%ld\n",
			PS_ID, port_statistics[2].rstClient, port_statistics[2].rstServer,port_statistics[2].connectionClose, port_statistics[0].rx_count, port_statistics[0].tx_count, port_statistics[0].rx_size, port_statistics[0].tx_size, port_statistics[0].dropped, port_statistics[0].err_rx, port_statistics[0].err_tx,
			port_statistics[0].mbuf_err, port_statistics[1].rx_count, port_statistics[1].tx_count,
			port_statistics[1].rx_size, port_statistics[1].tx_size, port_statistics[1].dropped, port_statistics[1].err_rx, port_statistics[1].err_tx,
			port_statistics[1].mbuf_err, port_statistics[2].rx_count, port_statistics[2].tx_count, port_statistics[2].rx_size,
			port_statistics[2].tx_size, port_statistics[2].dropped, port_statistics[2].err_rx, port_statistics[2].err_tx, port_statistics[2].mbuf_err,
			timestamp, port_statistics[0].throughput, port_statistics[1].throughput, port_statistics[2].throughput);
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
	// Create object for the statistics
	json_t *jsonObject = json_object();

	// Populate the JSON object
	json_object_set(jsonObject, "ps_id", json_string(PS_ID));

	json_object_set(jsonObject, "rx_i_http_count", json_integer(port_statistics[0].rx_count));
	json_object_set(jsonObject, "tx_i_http_count", json_integer(port_statistics[0].tx_count));
	json_object_set(jsonObject, "rx_i_http_size", json_integer(port_statistics[0].rx_size));
	json_object_set(jsonObject, "tx_i_http_size", json_integer(port_statistics[0].tx_size));
	json_object_set(jsonObject, "rx_i_http_drop", json_integer(port_statistics[0].dropped));
	json_object_set(jsonObject, "rx_i_http_error", json_integer(port_statistics[0].err_rx));
	json_object_set(jsonObject, "tx_i_http_error", json_integer(port_statistics[0].err_tx));
	json_object_set(jsonObject, "rx_i_http_mbuf", json_integer(port_statistics[0].mbuf_err));

	json_object_set(jsonObject, "rx_i_tls_count", json_integer(port_statistics[1].rx_count));
	json_object_set(jsonObject, "tx_i_tls_count", json_integer(port_statistics[1].tx_count));
	json_object_set(jsonObject, "rx_i_tls_size", json_integer(port_statistics[1].rx_size));
	json_object_set(jsonObject, "tx_i_tls_size", json_integer(port_statistics[1].tx_size));
	json_object_set(jsonObject, "rx_i_tls_drop", json_integer(port_statistics[1].dropped));
	json_object_set(jsonObject, "rx_i_tls_error", json_integer(port_statistics[1].err_rx));
	json_object_set(jsonObject, "tx_i_tls_error", json_integer(port_statistics[1].err_tx));
	json_object_set(jsonObject, "rx_i_tls_mbuf", json_integer(port_statistics[1].mbuf_err));

	json_object_set(jsonObject, "rstClient", json_integer(port_statistics[2].rstClient));
	json_object_set(jsonObject, "rstServer", json_integer(port_statistics[2].rstServer));
	json_object_set(jsonObject, "rx_o_count", json_integer(port_statistics[2].rx_count));
	json_object_set(jsonObject, "tx_o_count", json_integer(port_statistics[2].tx_count));
	json_object_set(jsonObject, "rx_o_size", json_integer(port_statistics[2].rx_size));
	json_object_set(jsonObject, "tx_o_size", json_integer(port_statistics[2].tx_size));
	json_object_set(jsonObject, "rx_o_drop", json_integer(port_statistics[2].dropped));
	json_object_set(jsonObject, "rx_o_error", json_integer(port_statistics[2].err_rx));
	json_object_set(jsonObject, "tx_o_error", json_integer(port_statistics[2].err_tx));
	json_object_set(jsonObject, "rx_o_mbuf", json_integer(port_statistics[2].mbuf_err));

	json_object_set(jsonObject, "time", json_string(timestamp));
	json_object_set(jsonObject, "rx_i_http_throughput", json_integer(port_statistics[0].throughput));
	json_object_set(jsonObject, "rx_i_tls_throughput", json_integer(port_statistics[1].throughput));
	json_object_set(jsonObject, "tx_o_throughput", json_integer(port_statistics[2].throughput));

	// Append the JSON object to the JSON array
	json_array_append(jsonArray, jsonObject);
}
/**
 * This function retrieves statistics for each port using the `rte_eth_stats_get()` function.
 * It then updates the statistics in the `port_statistics` array based on the retrieved values.
 * After updating the statistics, it clears the statistics for each port using the `rte_eth_stats_reset()` function.
 * Finally, it calculates the throughput for each port by dividing the received or transmitted size by the timer period.
 */
static void
collect_stats()
{
	// Get the statistics
	rte_eth_stats_get(1, &stats_1);
	rte_eth_stats_get(0, &stats_0);

	// Update the statistics

	port_statistics[0].rx_count = stats_0.ipackets;
	port_statistics[0].tx_count = stats_0.opackets;
	port_statistics[0].rx_size = stats_0.ibytes;
	port_statistics[0].tx_size = stats_0.obytes;
	port_statistics[0].dropped = stats_0.imissed;
	port_statistics[0].err_rx = stats_0.ierrors;
	port_statistics[0].err_tx = stats_0.oerrors;
	port_statistics[0].mbuf_err = stats_0.rx_nombuf;

	port_statistics[1].rx_count = stats_1.ipackets;
	port_statistics[1].tx_count = stats_1.opackets;
	port_statistics[1].rx_size = stats_1.ibytes;
	port_statistics[1].tx_size = stats_1.obytes;
	port_statistics[1].dropped = stats_1.imissed;
	port_statistics[1].err_rx = stats_1.ierrors;
	port_statistics[1].err_tx = stats_1.oerrors;
	port_statistics[1].mbuf_err = stats_1.rx_nombuf;

	// Clear the statistics
	rte_eth_stats_reset(0);
	rte_eth_stats_reset(1);
	rstClient = 0;
	rstServer = 0;

	// Calculate the throughpuif
	port_statistics[1].throughput = port_statistics[1].tx_size / TIMER_PERIOD_STATS;
	port_statistics[0].throughput = port_statistics[0].rx_size / TIMER_PERIOD_STATS;
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



// Global variable for QUIC crypto keys

static inline char *extractDomainfromQUIC(struct rte_mbuf *pkt, bool isClient)
{
    // Extract Ethernet header
    struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(pkt, struct rte_ether_hdr *);

    if (eth_hdr->ether_type != rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4)) {
        return NULL;
    }

    // Extract IPv4 header
    struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);

    if (ip_hdr->next_proto_id != IPPROTO_UDP) {
        return NULL;
    }

    struct rte_udp_hdr *udp_hdr = (struct rte_udp_hdr *)((uint8_t *)ip_hdr + sizeof(struct rte_ipv4_hdr));
    uint16_t udp_payload_length = rte_be_to_cpu_16(udp_hdr->dgram_len) - sizeof(struct rte_udp_hdr);
    uint8_t *udp_payload = (uint8_t *)udp_hdr + sizeof(struct rte_udp_hdr);

    // Process QUIC packet and update keys if needed
    char *domain = getDomain(udp_payload, udp_payload_length, isClient, &keys);

    // // printf("===== AEAD Encryption Parameters in ps.c =====\n");

    // // Print server key
    // printf("Server Key (%zu bytes):\n", sizeof(keys.quic_key_server));
    // for (size_t i = 0; i < sizeof(keys.quic_key_server); i++) {
    //     printf("%02x", keys.quic_key_server[i]);
    //     if ((i + 1) % 16 == 0) printf("\n");
    //     else if ((i + 1) % 4 == 0) printf(" ");
    // }
    // printf("\n\n");


    return domain;
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
	int counter =combinedValue;
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
 * This function extracts the domain name from a packet based on the protocol.
 *
 * @param pkt A pointer to the packet from which to extract the domain name.
 * @param protocol The protocol of the packet (HTTP or HTTPS).
 * @return A pointer to the extracted domain name.
 */
 static inline void conn_close_quic_to_server(struct rte_mbuf *rx_pkt) {
    struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(rx_pkt, struct rte_ether_hdr *);
    
    if (eth_hdr->ether_type == rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4)) {
        struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
        struct rte_udp_hdr *udp_hdr = (struct rte_udp_hdr *)(ip_hdr + 1);
        uint8_t *udp_payload = (uint8_t *)(udp_hdr + 1);
        int udp_payload_len = rte_be_to_cpu_16(udp_hdr->dgram_len) - sizeof(struct rte_udp_hdr);


        // --- Modify QUIC Payload ---
        uint8_t dcid_len, scid_len;
        uint8_t *dcid = get_dcid(udp_payload, true, &dcid_len);
        uint8_t *scid = get_dcid(udp_payload, false, &scid_len);

		uint8_t reset_token_secret[16];
		RAND_bytes(reset_token_secret, sizeof(reset_token_secret)); 
		generate_quic_stateless_reset(dcid, dcid_len, reset_token_secret, 
			udp_payload, &udp_payload_len);

        //quic_payload_crafter(scid, scid_len, dcid, dcid_len, udp_payload, &udp_payload_len, &keys, true);

        // --- Update Packet Metadata ---
        // 1. Update UDP length
        udp_hdr->dgram_len = rte_cpu_to_be_16(udp_payload_len + sizeof(struct rte_udp_hdr));
        
        // 2. Update IP total length
        ip_hdr->total_length = rte_cpu_to_be_16(
            sizeof(struct rte_ipv4_hdr) + 
            sizeof(struct rte_udp_hdr) + 
            udp_payload_len
        );

        // 3. Update mbuf length
        rx_pkt->data_len = rx_pkt->pkt_len = (
            sizeof(struct rte_ether_hdr) + 
            sizeof(struct rte_ipv4_hdr) + 
            sizeof(struct rte_udp_hdr) + 
            udp_payload_len
        );

        // 4. Recalculate checksums
        ip_hdr->hdr_checksum = 0;
        ip_hdr->hdr_checksum = rte_ipv4_cksum(ip_hdr);
        udp_hdr->dgram_cksum = 0;  // Optional for UDP
    }
}

static inline void conn_close_quic_to_client(struct rte_mbuf *rx_pkt) {
    struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(rx_pkt, struct rte_ether_hdr *);
    
    if (eth_hdr->ether_type == rte_cpu_to_be_16(RTE_ETHER_TYPE_IPV4)) {
        struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
        struct rte_udp_hdr *udp_hdr = (struct rte_udp_hdr *)(ip_hdr + 1);
        uint8_t *udp_payload = (uint8_t *)(udp_hdr + 1);
        int udp_payload_len = rte_be_to_cpu_16(udp_hdr->dgram_len) - sizeof(struct rte_udp_hdr);

        // --- Swap L2/L3/L4 headers (original code) ---
        struct rte_ether_addr tmp_mac;
        rte_ether_addr_copy(&eth_hdr->dst_addr, &tmp_mac);
        rte_ether_addr_copy(&eth_hdr->src_addr, &eth_hdr->dst_addr);
        rte_ether_addr_copy(&tmp_mac, &eth_hdr->src_addr);

        uint32_t tmp_ip = ip_hdr->src_addr;
        ip_hdr->src_addr = ip_hdr->dst_addr;
        ip_hdr->dst_addr = tmp_ip;

        uint16_t tmp_port = udp_hdr->src_port;
        udp_hdr->src_port = udp_hdr->dst_port;
        udp_hdr->dst_port = tmp_port;

        // --- Modify QUIC Payload ---
        uint8_t dcid_len, scid_len;
        uint8_t *dcid = get_dcid(udp_payload, true, &dcid_len);
        uint8_t *scid = get_dcid(udp_payload, false, &scid_len);
		// printf("Quic iv server on ps.c: ");
		// for (int i = 0; i < sizeof(keys.quic_iv_server); i++) printf("%02x", keys.quic_iv_server[i]);
		// printf("\n");


		uint8_t reset_token_secret[16];
		RAND_bytes(reset_token_secret, sizeof(reset_token_secret)); 
		// quic_stateless_reset_crafter(scid, scid_len, 
		// 	udp_payload, &udp_payload_len, reset_token_secret);


        quic_payload_crafter(scid, scid_len, dcid, dcid_len, udp_payload, &udp_payload_len, &keys, false);

        // --- Update Packet Metadata ---
        // 1. Update UDP length
        udp_hdr->dgram_len = rte_cpu_to_be_16(udp_payload_len + sizeof(struct rte_udp_hdr));
        
        // 2. Update IP total length
        ip_hdr->total_length = rte_cpu_to_be_16(
            sizeof(struct rte_ipv4_hdr) + 
            sizeof(struct rte_udp_hdr) + 
            udp_payload_len
        );

        // 3. Update mbuf length
        rx_pkt->data_len = rx_pkt->pkt_len = (
            sizeof(struct rte_ether_hdr) + 
            sizeof(struct rte_ipv4_hdr) + 
            sizeof(struct rte_udp_hdr) + 
            udp_payload_len
        );

        // 4. Recalculate checksums
        ip_hdr->hdr_checksum = 0;
        ip_hdr->hdr_checksum = rte_ipv4_cksum(ip_hdr);
        udp_hdr->dgram_cksum = 0;  // Optional for UDP
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

				char *insert_sql = "INSERT OR IGNORE INTO policies (id, ip_address, domain) VALUES ('0001', '192.168.69.12', 'mysite.local');";
				if (sqlite3_exec(db, insert_sql, NULL, 0, NULL) != SQLITE_OK)
				{
					logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error inserting into 'policies': %s\n", sqlite3_errmsg(db));
					// Optional: exit or return an error code
				}
				else
				{
					logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Inserted policy: id=0001, ip=192.168.69.12, domain=mysite.local\n");
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
			strncpy(hitCount[hitCounter], ip_cache[i].id, sizeof(ip_cache[i].id));
			hitCounter++;
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
		strncpy(hitCount[hitCounter], id, sizeof(id));
		hitCounter++;
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
	debug_pkt_type = ip_hdr->next_proto_id;

	// Check if it's a TCP packet
	if (ip_hdr->next_proto_id == IPPROTO_TCP)
	{
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
	} else if (ip_hdr->next_proto_id == IPPROTO_UDP /*IPPROTO_UDP*/){
		// Parse UDP header
		struct rte_udp_hdr *udp_hdr = (struct rte_udp_hdr *)((uint8_t *)ip_hdr + sizeof(struct rte_ipv4_hdr));

		// Calculate UDP payload length
		uint16_t ip_total_length = rte_be_to_cpu_16(ip_hdr->total_length);
		uint16_t udp_payload_len = ip_total_length - sizeof(struct rte_ipv4_hdr) - sizeof(struct rte_udp_hdr);

		// Point to the UDP payload data
		char *udp_payload = (char *)udp_hdr + sizeof(struct rte_udp_hdr);
		char *udh_header_temp = (char *)udp_hdr;
		debug_udp_dst_port = udp_hdr->dst_port;
		debug_udp_src_port = udp_hdr->src_port;
		udp_payload_0 = (uint8_t)udp_payload[0];

		// Packet criteria: Dest. port is 80 or 443 and packet type is QUIC Initial
		if ((rte_be_to_cpu_16(udp_hdr->dst_port) == 443 ) && (((uint8_t)udp_payload[0] ^ 0xC0) & 0xF0) == 0) {
			boolean_debug = true;
			port_statistics[0].quicCount++;
			// Check if the payload contains a QUIC Initial packet
			return UDP_QUIC;
		}
		return 0;
	} else {
		return 0;
	}
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

		/* Get a burst of RX packets from the first port of the pair. */
		rte_spinlock_lock(&rx_lock);
		const uint16_t rx_count = rte_eth_rx_burst(0, 0, rx_bufs, BURST_SIZE);
		if (rx_count == 0)
		{
			rte_spinlock_unlock(&rx_lock);
			continue;
		}
		rte_spinlock_unlock(&rx_lock);

		for (uint16_t i = 0; i < rx_count; i++)
		{
			struct rte_mbuf *rx_pkt = rx_bufs[i];

			packet_type = packet_checker(rx_pkt);

			// function to check the packet type and send it to the right port
			if (packet_type == HTTP_GET)
			{
				domain_check = domain_checker(extractDomainfromHTTP(rx_pkt));
			}
			else if (packet_type == TLS_CLIENT_HELLO)
			{
				domain_check = domain_checker(extractDomainfromHTTPS(rx_pkt));
			}else if (packet_type == UDP_QUIC)
			{
				char* domain = extractDomainfromQUIC(rx_pkt, true);
				domain_check = domain_checker(domain);

			}
			else
			{
				rte_pktmbuf_free(rx_pkt);
				continue;
			}

			if (domain_check)
			{
				struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(rx_pkt, struct rte_ether_hdr *);
				if (eth_hdr->ether_type != rte_be_to_cpu_16(RTE_ETHER_TYPE_IPV4))
				{
					return;
				}
				struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
			
				if (ip_hdr->next_proto_id == IPPROTO_TCP)
				{
					// Create a copy of the received packet
					struct rte_mbuf *rst_pkt_client = rte_pktmbuf_copy(rx_pkt, rx_pkt->pool, 0, sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_tcp_hdr));
					if (rst_pkt_client == NULL)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Client\n");
						rte_pktmbuf_free(rx_pkt);
						continue; // Skip this packet
					}

					struct rte_mbuf *rst_pkt_server = rte_pktmbuf_copy(rx_pkt, rx_pkt->pool, 0, sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_tcp_hdr));
					if (rst_pkt_server == NULL)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Server\n");
						rte_pktmbuf_free(rx_pkt);
						continue; // Skip this packet
					}

					// Apply modifications to the packets
					reset_tcp_client(rst_pkt_client);
					reset_tcp_server(rst_pkt_server);

					// Acquire the lock before transmitting
					rte_spinlock_lock(&tx_lock);

					// Transmit modified packets
					const uint16_t rst_tx_count = rte_eth_tx_burst(1, 0, &rst_pkt_client, 1);
					if (rst_tx_count == 0)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error sending packet to client\n");
						rte_pktmbuf_free(rst_pkt_client);
					}
					else
					{
						port_statistics[1].rstClient++;
					}

					const uint16_t rst_server_tx_count = rte_eth_tx_burst(1, 0, &rst_pkt_server, 1);
					if (rst_server_tx_count == 0)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error sending packet to server\n");
						rte_pktmbuf_free(rst_pkt_server);
					}
					else
					{
						port_statistics[1].rstServer++;
					}

					// Release the lock after transmitting
					rte_spinlock_unlock(&tx_lock);
				}else if ( ip_hdr->next_proto_id == IPPROTO_UDP){
					// printf("QUIC packet detected\n");

					uint16_t udp_payload_len = rx_pkt->pkt_len - (sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr));
					struct rte_mbuf *conn_close_pkt_client = rte_pktmbuf_copy(
						rx_pkt,                      // Source packet
						rx_pkt->pool,                // Memory pool
						0,                           // Start offset (0 = from beginning)
						rx_pkt->pkt_len              // Copy entire packet (L2 + L3 + L4 + payload)
					);	
					// struct rte_mbuf *conn_close_pkt_server = rte_pktmbuf_copy(
					// 	rx_pkt,                      // Source packet
					// 	rx_pkt->pool,                // Memory pool
					// 	0,                           // Start offset (0 = from beginning)
					// 	rx_pkt->pkt_len              // Copy entire packet (L2 + L3 + L4 + payload)
					// );				
					// printf("conn_close_pkt_client mbuf dump:\n");
					// rte_pktmbuf_dump(stdout, conn_close_pkt_client, conn_close_pkt_client->pkt_len);
					if (conn_close_pkt_client == NULL)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Client\n");
						rte_pktmbuf_free(rx_pkt);
						continue; // Skip this packet
					}
						// if (conn_close_pkt_server == NULL)
						// {
						// 	logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error copying packet to RST Server\n");
						// 	rte_pktmbuf_free(rx_pkt);
						// 	continue; // Skip this packet
						// }

					struct rte_ether_hdr *eth_hdr = rte_pktmbuf_mtod(conn_close_pkt_client, struct rte_ether_hdr *);
					struct rte_ipv4_hdr *ip_hdr = (struct rte_ipv4_hdr *)(eth_hdr + 1);
					struct rte_udp_hdr *udp_hdr = (struct rte_udp_hdr *)(ip_hdr + 1);

					int udp_payload_len1 = rte_be_to_cpu_16(udp_hdr->dgram_len) - sizeof(struct rte_udp_hdr);
					uint8_t *udp_payload = rte_pktmbuf_mtod_offset(
						conn_close_pkt_client,
						uint8_t *,
						sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr)
					);
					// printf("UDP Payload (Length: %d bytes) before:\n", udp_payload_len);
					// for (int i = 0; i < udp_payload_len; i++) {
					// 	printf("%02x", udp_payload[i]);  // Print each byte as 2-digit hex
					// }
					// printf("\n");

					conn_close_quic_to_client(conn_close_pkt_client);
					// conn_close_quic_to_server(conn_close_pkt_server);


					udp_payload_len1 = rte_be_to_cpu_16(udp_hdr->dgram_len) - sizeof(struct rte_udp_hdr);
					uint8_t *udp_payload2 = rte_pktmbuf_mtod_offset(
						conn_close_pkt_client,
						uint8_t *,
						sizeof(struct rte_ether_hdr) + sizeof(struct rte_ipv4_hdr) + sizeof(struct rte_udp_hdr)
					);
					// printf("UDP Payload (Length: %d bytes) after:\n", udp_payload_len);
					// for (int i = 0; i < udp_payload_len; i++) {
					// 	printf("%02x", udp_payload2[i]);  // Print each byte as 2-digit hex
					// }
					// printf("\n");
					// printf("After conn close\n");
					// printf("conn_close_pkt_client mbuf dump after modified:\n");
					// rte_pktmbuf_dump(stdout, conn_close_pkt_client, conn_close_pkt_client->pkt_len);
					// Acquire the lock before transmitting
					rte_spinlock_lock(&tx_lock);
					// Transmit modified packets

					uint16_t rst_client_tx_count = rte_eth_tx_burst(1, 0, &conn_close_pkt_client, 1);
					// uint16_t rst_server_tx_count = rte_eth_tx_burst(1, 0, &conn_close_pkt_server, 1);
					if (rst_client_tx_count == 0)
					{
						logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error sending packet to client\n");
						rte_pktmbuf_free(conn_close_pkt_client);

					}
					else
					{
						port_statistics[1].connectionClose++;
					}
					// Release the lock after transmitting
					rte_spinlock_unlock(&tx_lock);

				}
			}
			
				rte_pktmbuf_free(rx_pkt);
			
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
	 signal(SIGSEGV, segfault_handler);
	 init_database();
	 OpenSSL_add_all_algorithms();

 
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
	 memset(port_statistics, 0, 32 * sizeof(struct port_statistics_data));
	 logMessage(LOG_LEVEL_INFO, __FILE__, __LINE__, "Port Statistic Cleared\n");
 
	 // count the number of ports to send and receive
	 nb_ports = rte_eth_dev_count_avail();
	 if (nb_ports != 2)
	 {
		 logMessage(LOG_LEVEL_ERROR, __FILE__, __LINE__, "Error: number of ports must be 3\n");
		 rte_exit(EXIT_FAILURE, "Error: number of ports must be 3\n");
	 }
 
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