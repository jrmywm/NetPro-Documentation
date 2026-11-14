import asyncio
from aioquic.asyncio import connect
from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated

# Define a protocol class to handle QUIC events
class QUICClientProtocol(QuicConnectionProtocol):
    def quic_event_received(self, event):
        if isinstance(event, ConnectionTerminated):
            print("Connection closed by server")

async def send_connection_close(protocol):
    # Send a CONNECTION_CLOSE frame with an error code (0x1 - generic error)
    protocol._quic.send_connection_close(error_code=0x1, frame_type=0x1, reason_phrase="Closing connection automatically")
    print("Sent CONNECTION_CLOSE packet")
    await asyncio.sleep(1)  # Ensure packet is sent

async def periodic_close_connection(protocol, interval=3):
    while True:
        await send_connection_close(protocol)  # Send the CONNECTION_CLOSE packet
        await asyncio.sleep(interval)  # Wait for the next interval

async def main():
    # QUIC Configuration
    configuration = QuicConfiguration(is_client=True)
    
    # Connect to a QUIC server (change the address and port if needed)
    async with connect("localhost", 4433, configuration=configuration, create_protocol=QUICClientProtocol) as protocol:
        # Start sending the CONNECTION_CLOSE packet every 3 seconds
        await periodic_close_connection(protocol, interval=3)

# Run the asyncio event loop
if __name__ == "__main__":
    asyncio.run(main())
