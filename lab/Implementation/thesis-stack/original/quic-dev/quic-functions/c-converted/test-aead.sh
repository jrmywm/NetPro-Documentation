#!/bin/bash

# Navigate to the project directory
cd "/Users/rijal/Documents/Codes/NetPro-Policy-Server/quic-functions/c-converted/" || exit 1

# Compile the program with OpenSSL
clang -w -I/opt/homebrew/Cellar/openssl@3/3.4.0/include \
      -I/your/additional/include/path \
      -L/opt/homebrew/Cellar/openssl@3/3.4.0/lib -lssl -lcrypto \
      aead-test.c -o aead-test

# Check if compilation was successful
if [ $? -eq 0 ]; then
    echo "Compilation successful. Running program..."
    time ./aead-test
else
    echo "Compilation failed."
    exit 1
fi