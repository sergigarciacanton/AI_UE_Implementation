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


logger = logging.getLogger('')
logger.setLevel(logging.INFO)
logger.addHandler(logging.FileHandler('ue.log', mode='w', encoding='utf-8'))
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColoredFormatter())
logger.addHandler(stream_handler)

system_os = 'Windows'
best_mac = ""
client_socket = socket.socket()
connected = False
fec_id = -1
user_id = 1
my_vnf = None
previous_node = -1


def wireless_conn_manager():
    global best_mac
    while True:
        new_mac = get_mac_to_connect()
        if new_mac != best_mac:
            best_mac = new_mac
            if connected:
                handover(best_mac)

        time.sleep(2)


wireless_conn_thread = threading.Thread(target=wireless_conn_manager)


def get_mac_to_connect():
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


def handover(mac):
    logger.info('[I] Performing handover to ' + mac)
    disconnect(False)
    connect(mac)


def disconnect(starting):
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
    except ConnectionResetError:
        logger.critical('[!] Trying to reuse killed connection!')
    except Exception as e:
        logger.exception(e)


def connect(mac):
    global connected
    global server_thread
    if system_os == 'Windows':
        while not connected:
            # FEC 1: '90:E8:68:83:FA:DD'
            # FEC 2: '90:E8:68:84:3B:97'
            process_connect = subprocess.Popen(
                'C:\\Archivos_de_programa\\WifiInfoView\\WifiInfoView.exe /ConnectAP "Test301" "' + mac + '"',
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
                kill_process(process_connect)
                time.sleep(5)
    else:
        logger.critical('[!] System OS not supported! Please, stop program...')

    # Thread controlling communications with server on FEC
    server_thread = threading.Thread(target=server_conn)
    server_thread.daemon = True
    server_thread.start()


def server_conn():
    global client_socket
    global fec_id
    global my_vnf
    host = '10.0.0.1'
    port = 5010  # socket server port number
    try:
        client_socket = socket.socket()
        ready = False
        while not ready:
            try:
                client_socket.connect((host, port))  # connect to the server
                ready = True
            except OSError:
                time.sleep(1)
        message = json.dumps(dict(type="auth", user_id=1))  # take input

        client_socket.send(message.encode())  # send message
        data = client_socket.recv(1024).decode()  # receive response
        json_data = json.loads(data)
        if json_data['res'] == 200:
            logger.info('[I] Response from FEC: ' + str(json_data))
            fec_id = json_data['id']
        else:
            logger.error('[!] Error ' + json_data['res'] + ' when authenticating to FEC!')

        input('[*] Press enter to send a VNF...')

        if my_vnf is None:
            target = int(input('[*] Introduce the target position: '))
            gpu = int(input('[*] Introduce the needed GPU GB: '))
            ram = int(input('[*] Introduce the needed RAM GB: '))
            bw = int(input('[*] Introduce the needed bandwidth (Mbps): '))
            rtt = int(input('[*] Introduce the needed RTT (ms): '))

            my_vnf = VNF(dict(source=fec_id, target=target, gpu=gpu, ram=ram, bw=bw, rtt=rtt, previous_node=-1,
                              current_node=fec_id, fec_linked=fec_id, user_id=user_id))
        else:
            my_vnf.previous_node = previous_node
            my_vnf.current_node = fec_id
        message = json.dumps(dict(type="vnf", data=my_vnf.__dict__))  # take input
        client_socket.send(message.encode())  # send message
        data = client_socket.recv(1024).decode()  # receive response
        json_data = json.loads(data)
        if json_data['res'] == 200:
            # MAKE CAR MOVE TOWARDS ACTION DIRECTION
            logger.info('[I] Response from server: ' + str(json_data['action']))  # NOT IMPLEMENTED!
            if json_data['action'] == 'e':
                logger.info('[I] Car reached target!')
                key_in = input('[?] Want to send a new VNF? Y/n: (Y) ')
                if key_in != 'n':
                    target = int(input('[*] Introduce the target position: '))
                    gpu = int(input('[*] Introduce the needed GPU GB: '))
                    ram = int(input('[*] Introduce the needed RAM GB: '))
                    bw = int(input('[*] Introduce the needed bandwidth (Mbps): '))
                    rtt = int(input('[*] Introduce the needed RTT (ms): '))

                    my_vnf = VNF(
                        dict(source=fec_id, target=target, gpu=gpu, ram=ram, bw=bw, rtt=rtt, previous_node=-1,
                             current_node=fec_id, fec_linked=fec_id, user_id=user_id))
                    message = json.dumps(dict(type="vnf", data=my_vnf.__dict__))  # take input
                    client_socket.send(message.encode())  # send message
                    data = client_socket.recv(1024).decode()  # receive response
                    json_data = json.loads(data)
                    if json_data['res'] == 200:
                        logger.info('[I] Response from server: ' + str(json_data['action']))  # NOT IMPLEMENTED!
                    else:
                        logger.error('[!] Error ' + json_data['res'] + ' when sending VNF to FEC!')
        else:
            logger.error('[!] Error ' + json_data['res'] + ' when sending VNF to FEC!')
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


def kill_process(process_kill):
    process_kill.kill()
    process_kill.communicate()


def kill_thread(thread_id):
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
    global best_mac
    global wireless_conn_thread
    global system_os
    global user_id
    try:
        user_id = int(input('[*] Introduce your user ID: '))

        system_os = platform.system()

        # In case of being connected to a network, disconnect
        disconnect(True)

        # Get the best FEC int terms of power and connect to it
        while best_mac == "":
            time.sleep(2)
            best_mac = get_mac_to_connect()
        connect(best_mac)

        # Thread controlling RX power from all AP and performing handovers
        wireless_conn_thread = threading.Thread(target=wireless_conn_manager)
        wireless_conn_thread.daemon = True
        wireless_conn_thread.start()

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info('[!] Ending...')
        disconnect(False)
        if connected:
            kill_thread(wireless_conn_thread.ident)
            wireless_conn_thread.join()
    except Exception as e:
        logger.exception(e)


if __name__ == '__main__':
    main()
