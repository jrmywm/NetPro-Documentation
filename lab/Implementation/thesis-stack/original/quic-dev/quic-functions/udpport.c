
int main() {
    char udp_hdr[] = {0xdd, 0x9d, 0x01, 0xbb, 0x05, 0x55, 0x6a, 0xfd};  // Example UDP payload
    char *udp_header = udp_hdr;  // Pass as a char pointer

    // Start timing
    clock_t start_time = clock();

    // Iterate through the ports
    for (int i = 0; i <= 2; i += 2) { // Iterate for source and destination ports
        uint16_t port_value = ntohs(*(uint16_t *)(udp_header + i));  // Convert each 2-byte segment
        // Check and print
        if (port_value == 80 || port_value == 443) {
            printf("Port: %d\n", port_value);
        } else {
            printf("Port not 80 or 443\n");
    }
}

    // End timing
    clock_t end_time = clock();

    // Calculate and print the elapsed time in seconds
    double elapsed_time = (double)(end_time - start_time) / CLOCKS_PER_SEC;
    printf("Elapsed time: %f seconds\n", elapsed_time);

    return 0;
}
