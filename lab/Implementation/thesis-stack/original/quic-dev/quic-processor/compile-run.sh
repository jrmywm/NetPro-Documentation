#!/bin/bash

# Navigate to the project directory
cd "/home/ir-policyserver/Documents/policyserver/NetPro-Policy-Server/quic-processor" || exit 1

# Compile the program with OpenSSL
gcc -w -I/opt/homebrew/Cellar/openssl@3/3.4.0/include \
      -I/your/additional/include/path \
      -L/opt/homebrew/Cellar/openssl@3/3.4.0/lib -lssl -lcrypto \
      packet-processor.c quicFunctions.c -o packet-processor \

# Check if compilation was successful
if [ $? -eq 0 ]; then
    echo "Compilation successful. Running program..."
    time ./packet-processor
else
    echo "Compilation failed."
    exit 1
fi