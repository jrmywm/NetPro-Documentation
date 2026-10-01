# get TRex APIs
import stl_path
from trex.stl.api import *
import os
import threading
from datetime import datetime
import argparse

# global variable
stop_thread = False
def send_packet(c, p_size, p_pps, p_id, stats_list):
    global stop_thread
    stop_thread = False

    def stop_after_10s():
        global stop_thread
        time.sleep(8)
        stop_thread = True
    try:
        # prepare the ports
        c.reset(ports = [0,1])

        # clear statistics on ports 0,1
        c.clear_stats(ports = [0,1])
        
        # create random src port and IP for every packet
        vm = STLVM()
        vm.var(name = "src_port", min_value = 1025, max_value = 65000, size = 2, op = "random")
        vm.write(fv_name = "src_port", pkt_offset = "TCP.sport")

        # Create the STL packet
        pkt = STLPktBuilder(pkt ="pcap/https_583B_single.pcap",vm=vm)

        # first stream 's1'
        s1 = STLStream(packet=pkt,
                    mode=STLTXCont(pps=p_pps),
                    flow_stats=STLFlowLatencyStats(pg_id=1),
                    mac_src_override_by_pkt=False,
                    mac_dst_override_mode=0)

        # add the streams
        c.add_streams([s1], ports = [0])

        # setup promiscuous mode
        c.set_port_attr([0,1], promiscuous = True) 

        print("(Cleaning Up)", end="")
        time.sleep(1)

        # Wait until the current time's microseconds and milliseconds parts are 00
        while datetime.now().microsecond != 0 or datetime.now().strftime('%f')[0:2] != '00':
            pass

        # Collect start time
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # start traffic
        c.start(ports = [0])

        # start the counter
        timer_thread = threading.Thread(target=stop_after_10s)
        timer_thread.start()

        # hold until traffic ends
        print("(Running)",end="")
        while not stop_thread:
            print(".", end="")
            sys.stdout.flush()
            time.sleep(0.5)
        
        # stop traffic
        c.stop(ports = [0,1])

        # collect end time
        end_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        print("(Cleaning Up)", end="")
        time.sleep(1)

        # read the stats
        stats = c.get_stats()

        # insert the metadata
        metadata = {"metadata": {"id": p_id, "size": p_size, "pps": p_pps, "start_time": start_time, "end_time": end_time}}
        stats = {**metadata, **stats}
        
        # append the stats to the list
        stats_list.append(stats)

    except STLError as e:
        print(e)

    except KeyboardInterrupt:
        print("Interrupted by user. Stopping traffic.")
        c.stop(ports = [0,1])

def main():
    # argument
    parser = argparse.ArgumentParser(description="Process some integers.")
    parser.add_argument('--sizes', nargs='+', type=int, default=[256,512,1024],
                        help='a list of sizes')
    parser.add_argument('--pps_values', nargs='+', type=int, default=[10000, 50000, 10000], 
                        help='a list of pps values')
    
    args = parser.parse_args()

    sizes = args.sizes
    pps_values = list(range(args.pps_values[0], args.pps_values[1], args.pps_values[2]))

    # Use list comprehension to create combinations
    combinations = [(id, size, pps) for id, (size, pps) in enumerate([(size, pps) for size in sizes for pps in pps_values], start=1)]

    # connect to the core
    c = STLClient(server = '127.0.0.1')
    c.connect()

    stats_list = []
    # send packet
    try:
        for id, size, pps in combinations:
            print(f"Starting Job {id} with size {size}, pps {pps}")
            send_packet(c, size, pps, id, stats_list)
            print("(Finished)")
    except KeyboardInterrupt:
        print("Interrupted by user. Exiting loop.")

    # Convert the list of dictionaries to a JSON string
    stats_json = json.dumps(stats_list)

    # Get the current date and time
    now = datetime.now()

    # Format the current date and time as a string
    timestamp = now.strftime("%Y-%m-%dT%H:%M:%S")

    # Create a directory
    os.makedirs("output/https", exist_ok=True)

    # Open a file in the new directory for writing
    with open(f"output/https/{timestamp}.json", "w") as file:
        # Write the JSON string to the file
        file.write(stats_json)

    # disconnect from the server
    c.disconnect()

if __name__ == "__main__":
    main()
