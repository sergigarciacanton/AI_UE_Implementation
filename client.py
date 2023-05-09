import configparser
import platform
import subprocess
import socket
import threading
import time
from test_rssi import get_BSSI
import json
import ctypes
import logging
import sys
from colorlog import ColoredFormatter


class VNF:
    def __init__(self, json_data):
        self.source = json_data['source']
        self.target = json_data['target']
        self.gpu = json_data['gpu']
        self.ram = json_data['ram']
        self.bw = json_data['bw']
        self.rtt = json_data['rtt']
        self.previous_node = json_data['previous_node']
        self.current_node = json_data['current_node']
        self.fec_linked = json_data['fec_linked']
        self.user_id = json_data['user_id']


# Import settings from configuration file
config = configparser.ConfigParser()
config.read('C:\\Users\\Usuario\\Documents\\UNI\\2022 - 23 Q2\\Work\\Codes\\7b659cf16faa821bdd80\\ue.ini')
general = config['general']
# Logging configuration
logger = logging.getLogger('')
logger.setLevel(int(general['log_level']))
logger.addHandler(logging.FileHandler(general['log_file_name'], mode='w', encoding='utf-8'))
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColoredFormatter())
logger.addHandler(stream_handler)

# Global variables
system_os = 'Windows'
best_mac = ""
client_socket = socket.socket()
connected = False
fec_id = -1
user_id = 1
my_vnf = None
previous_node = -1


def get_data_by_console(data_type, message):
    # Function that reads a console entry asking for data to store into a variable
    valid = False
    output = None
    if data_type == int:
        while not valid:
            try:
                output = int(input(message))
                valid = True
            except ValueError:
                logger.warning('[!] Error in introduced data! Must use int values. Try again...')
                valid = False
            except Exception as e:
                logger.warning('[!] Unexpected error ' + str(e) + '! Try again...')
                valid = False
    elif data_type == float:
        while not valid:
            try:
                output = float(input(message))
                valid = True
            except ValueError:
                logger.warning('[!] Error in introduced data! Must use float values. Try again...')
                valid = False
            except Exception as e:
                logger.warning('[!] Unexpected error ' + str(e) + '! Try again...')
                valid = False
    else:
        logger.error('[!] Data type getter not implemented!')
    return output


def get_mac_to_connect():
    # Function that returns the wireless_conn_manager the mac of the best FEC to connect.
    # Takes into account a hysteresis margin of 5 dB for changing FEC
    if system_os == 'Windows':
        json_data = json.loads(str(get_BSSI()).replace("'", "\""))
        if len(json_data) > 0:
            best_pow = -100
            best_val = -1
            val = 0
            current_pow = -100
            while val < len(json_data):
                logger.debug('[D] ' + str(json_data[str(val)]))
                if int(json_data[str(val)][2]) > best_pow:
                    best_pow = int(json_data[str(val)][2])
                    best_val = val
                if best_mac == json_data[str(val)][0]:
                    current_pow = int(json_data[str(val)][2])
                val += 1
            if current_pow < int(json_data[str(best_val)][2]) - 5:
                return json_data[str(best_val)][0]
            else:
                return best_mac
        else:
            return best_mac
    else:
        logger.critical('[!] System OS not supported! Please, stop program...')
        return


def handover(mac):
    # Function that handles handovers. First disconnects from current FEC and after connects to the new one
    logger.info('[I] Performing handover to ' + mac)
    disconnect(False)
    connect(mac)


def disconnect(starting):
    # Disconnects from current FEC
    global connected
    global previous_node
    try:
        if not starting and connected:
            message = json.dumps(dict(type="bye"))  # take input
            client_socket.send(message.encode())  # send message
            client_socket.recv(1024).decode()  # receive response
            kill_thread(server_thread.ident)
            server_thread.join()
        previous_node = fec_id
        if system_os == 'Windows':
            process_disconnect = subprocess.Popen(
                'netsh wlan disconnect',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            process_disconnect.communicate()
            connected = False
        else:
            logger.critical('[!] System OS not supported! Please, stop program...')
            return
    except ConnectionResetError:
        logger.critical('[!] Trying to reuse killed connection!')
    except Exception as e:
        logger.exception(e)


def connect(mac):
    # This function manages connecting to a new FEC given its MAC address
    global connected
    global server_thread
    if system_os == 'Windows':
        while not connected:
            process_connect = subprocess.Popen(
                general['wifi_handler_file'] + ' /ConnectAP "' + general['wifi_ssid'] + '" "' + mac + '"',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            process_connect.communicate()
            time.sleep(2)
            if "Test301" in str(subprocess.check_output("netsh wlan show interfaces")):
                logger.info('[I] Connected!')
                connected = True
            else:
                logger.warning('[!] Connection not established! Killing query and trying again...')
                process_connect.kill()
                process_connect.communicate()
                time.sleep(5)
    else:
        logger.critical('[!] System OS not supported! Please, stop program...')
        return

    # Thread controlling communications with server on FEC
    server_thread = threading.Thread(target=server_conn)
    server_thread.daemon = True
    server_thread.start()


def generate_vnf():
    # This function returns a new VNF object whose fields are given by console
    target = get_data_by_console(int, '[*] Introduce the target position: ')
    gpu = get_data_by_console(int, '[*] Introduce the needed GPU GB: ')
    ram = get_data_by_console(int, '[*] Introduce the needed RAM GB: ')
    bw = get_data_by_console(int, '[*] Introduce the needed bandwidth (Mbps): ')
    rtt = get_data_by_console(float, '[*] Introduce the needed RTT (ms): ')

    return VNF(dict(source=fec_id, target=target, gpu=gpu, ram=ram, bw=bw, rtt=rtt, previous_node=-1,
                    current_node=fec_id, fec_linked=fec_id, user_id=user_id))


def server_conn():
    # This function is running on a second thread as long as being connected to a FEC.
    # It sends data to the sockets server and waits for responses
    global client_socket
    global fec_id
    global my_vnf
    global user_id
    host = general['fec_ip']
    port = int(general['fec_port'])  # socket server port number
    try:
        client_socket = socket.socket()
        ready = False
        while not ready:
            try:
                client_socket.connect((host, port))  # connect to the server
                ready = True
            except OSError:
                time.sleep(1)
        auth_valid = False
        while not auth_valid:
            message = json.dumps(dict(type="auth", user_id=user_id))  # take input

            client_socket.send(message.encode())  # send message
            data = client_socket.recv(1024).decode()  # receive response
            json_data = json.loads(data)
            if json_data['res'] == 200:
                logger.info('[I] Successfully authenticated to FEC ' + str(json_data['id']) + '!')
                fec_id = json_data['id']
                auth_valid = True
                if my_vnf is not None:
                    my_vnf.fec_linked = fec_id
            else:
                logger.error('[!] Error ' + str(json_data['res']) + ' when authenticating to FEC!')
                user_id = get_data_by_console(int, '[*] Introduce a valid user ID: ')

        input('[*] Press enter to send a VNF...')

        valid_vnf = False
        while not valid_vnf:
            if my_vnf is None:
                my_vnf = generate_vnf()
            else:
                my_vnf.previous_node = previous_node
                my_vnf.current_node = fec_id
            message = json.dumps(dict(type="vnf", data=my_vnf.__dict__))  # take input
            client_socket.send(message.encode())  # send message
            data = client_socket.recv(1024).decode()  # receive response
            json_data = json.loads(data)
            if json_data['res'] == 200:
                valid_vnf = True
                # MAKE CAR MOVE TOWARDS ACTION DIRECTION
                logger.info('[I] Response from server: ' + str(json_data['action']))  # NOT IMPLEMENTED!
                if json_data['action'] == 'e':
                    logger.info('[I] Car reached target!')
                    key_in = input('[?] Want to send a new VNF? Y/n: (Y) ')
                    if key_in != 'n':
                        valid_new_vnf = False
                        while not valid_new_vnf:
                            my_vnf = generate_vnf()

                            message = json.dumps(dict(type="vnf", data=my_vnf.__dict__))  # take input
                            client_socket.send(message.encode())  # send message
                            data = client_socket.recv(1024).decode()  # receive response
                            json_data = json.loads(data)
                            if json_data['res'] == 200:
                                valid_new_vnf = True
                                logger.info('[I] Response from server: ' + str(json_data['action']))  # NOT IMPLEMENTED!
                            elif json_data['res'] == 403:
                                logger.error(
                                    '[!] Error! Required resources are not available on current FEC. Ask for less '
                                    'resources.')
                            elif json_data['res'] == 404:
                                logger.error('[!] Error! Required target does not exist. Ask for an existing target.')
                            else:
                                logger.error('[!] Error ' + str(json_data['res']) + ' when sending VNF to FEC!')
            elif json_data['res'] == 403:
                my_vnf = None
                logger.error('[!] Error! Required resources are not available on current FEC. Ask for less resources.')
            elif json_data['res'] == 404:
                my_vnf = None
                logger.error('[!] Error! Required target does not exist. Ask for an existing target.')
            else:
                my_vnf = None
                logger.error('[!] Error ' + str(json_data['res']) + ' when sending VNF to FEC!')
        while True:
            time.sleep(1)

    except ConnectionRefusedError:
        logger.error('[!] FEC server not available! Please, press enter to stop client.')
    except SystemExit:
        message = json.dumps(dict(type="bye"))  # take input
        client_socket.send(message.encode())  # send message
        client_socket.close()  # close the connection
    except Exception as e:
        logger.exception(e)


server_thread = threading.Thread(target=server_conn)


def kill_thread(thread_id):
    # This functions kills a thread. It is used for stopping the program or disconnecting from a FEC
    try:
        ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), ctypes.py_object(SystemExit))
        # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
        if ret == 0:
            raise ValueError("Thread ID " + str(thread_id) + " does not exist!")
        elif ret > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
        logger.info("[I] Successfully killed thread " + str(thread_id))
    except Exception as e:
        logger.exception(e)


def main():
    # Main function
    # Global variables
    global best_mac
    global system_os
    global user_id
    global best_mac
    try:
        # Get user_id
        user_id = get_data_by_console(int, '[*] Introduce your user ID: ')

        # Get Operative System
        system_os = platform.system()

        # In case of being connected to a network, disconnect
        disconnect(True)

        # Get the best FEC in terms of power and connect to it
        while best_mac == "":
            time.sleep(2)
            best_mac = get_mac_to_connect()
        connect(best_mac)

        # Loop asking for best FEC to connect and managing handovers
        while True:
            new_mac = get_mac_to_connect()
            if new_mac != best_mac:
                best_mac = new_mac
                if connected:
                    handover(best_mac)

            time.sleep(2)
    except KeyboardInterrupt:
        logger.info('[!] Ending...')
        disconnect(False)
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    main()
