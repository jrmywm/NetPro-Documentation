import paho.mqtt.client as mqtt
import json
import random
import time

# MQTT broker configuration
broker_address = "172.16.0.176"
broker_port = 1883
topic = "home/energy"

# Set static values for voltage and energy_today
voltage = 230
energy_today = 1000

# Connect to the MQTT broker
client = mqtt.Client()
client.connect(broker_address, broker_port)

try:
    while True:
        # Generate a random power value between 1000 and 1500
        power = random.randint(1000, 1500)
        
        # Prepare data payload
        data = {
            "power": power,
            "voltage": voltage,
            "energy_today": energy_today
        }
        
        # Convert data to JSON format
        payload = json.dumps(data)
        
        # Publish the message to the MQTT topic
        client.publish(topic, payload)
        
        # Print the data being sent
        print(f"Sent: {payload}")
        
        # Wait for 1 second before sending the next message
        time.sleep(1)

except KeyboardInterrupt:
    print("MQTT publishing stopped.")

finally:
    client.disconnect()
