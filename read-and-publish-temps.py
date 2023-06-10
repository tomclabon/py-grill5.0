import asyncio
from bleak import BleakClient, BleakGATTCharacteristic, BleakScanner
import paho.mqtt.client as mqtt

bt_name = "Grill BT5.0"
UUID_NOTIFY_CHARACTERISTIC = "0000FFB2-0000-1000-8000-00805f9b34fb"

mqtt_host = "192.168.50.11"
mqtt_port = 1883
mqtt_user = "mqtt"
mqtt_pass = "mqtt"

def byteArrToShort(bArr, i) :
    return ((bArr[i + 1]) | (bArr[i] << 8))

async def bt_discover():
    while 1:
        for d in await BleakScanner.discover():
            if d.name == bt_name:
                print(f"Discovered {bt_name} at {d.address}")
                return d.address

async def bt_connect(mqtt_client, state):

    disconnected_event = asyncio.Event()

    def on_bt_disconnect(bleakClient: BleakClient):
        print(f"Disconnected from bluetooth device {bt_address}. Reconnecting")
        disconnected_event.set()

    def bt_callback(sender: BleakGATTCharacteristic, bytes: bytes):
        if len(bytes) > 0 and bytes[0] == 85 and bytes[1] == 0:
            for i in range(6):
                tempCShort = byteArrToShort(bytes, (i * 2) + 2)
                if tempCShort != 65535:
                    tempCFloat = tempCShort / 10.0
                    tempF = ((tempCFloat * 9) / 5) + 32
                    tempFString = f"{tempF:.1f}"
                    mqtt_client.publish(f"smoker/probe/{i+1}/connected", True, retain=False)
                    mqtt_client.publish(f"smoker/probe/{i+1}/temperature", tempFString, retain=False)
                    print(f"Probe {i+1}: {tempFString}")
                else:
                    mqtt_client.publish(f"smoker/probe/{i+1}/connected", False, retain=False)
                    mqtt_client.publish(f"smoker/probe/{i+1}/temperature", "0", retain=False)
                    print(f"Probe {i+1}: 0")

    def publish_bt_connected():
        try:
            print(f"Publish BT connected {state.bt_connected}")
            mqtt_client.publish("smoker/bt-connected", state.bt_connected, retain=False)
        except Exception as e:
            print("Failed to send bt_connected: ")
            print(e)

    bt_address = await bt_discover()

    async with BleakClient(bt_address, on_bt_disconnect) as client:
        print(f"Connected to bluetooth device {bt_address}. Subscribing to gatt characteristic {UUID_NOTIFY_CHARACTERISTIC}")
        await client.start_notify(UUID_NOTIFY_CHARACTERISTIC, bt_callback)
        state.bt_connected = True
        publish_bt_connected()
        # Wait forever
        await disconnected_event.wait()
        state.bt_connected = False
        publish_bt_connected()

async def mqtt_connect(mqtt_client, state):

    # The callback for when the client receives a CONNACK response from the server.
    def mqtt_on_connect(client, userdata, flags, rc):
        print("Connected to MQTT broker with result code "+str(rc))
        client.publish("smoker/bt-connected", state.bt_connected, 0, retain=False)

    def mqtt_on_disconnect(client, userdata, flags):
        print("Disconnected to MQTT broker, reconnecting")
        asyncio.create_task(mqtt_connect(client, state))

    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_disconnect = mqtt_on_disconnect
    mqtt_client.username_pw_set(mqtt_user, mqtt_pass)
    while 1:
        try:
            mqtt_client.connect(mqtt_host, mqtt_port, 60)
            return
        except Exception as e:
            print("Failed to connect to mqtt broker: ")
            print(e)

async def heartbeat_mqtt(mqtt_client):
    while 1:
        try:
            mqtt_client.publish("smoker/heartbeat", "", 0, False)
        except Exception as e:
            print("Failed to send mqtt heartbeat: ")
            print(e)
        await asyncio.sleep(10)

async def main():
    mqtt_client = mqtt.Client()
    state = type('', (), {})()
    state.bt_connected = False
    asyncio.create_task(mqtt_connect(mqtt_client, state))
    asyncio.create_task(heartbeat_mqtt(mqtt_client))
    while 1:
        await bt_connect(mqtt_client, state)

asyncio.run(main())