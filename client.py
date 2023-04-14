import subprocess
import socket
import threading
import time
from get_rx_rssi import get_BSSI
import json
import ctypes


def get_rssi():
    # print('RSSI')
    global best_mac
    while True:
        new_mac = get_mac_to_connect()
        if new_mac != best_mac:
            best_mac = new_mac
            if connected:
                handover(best_mac)

        time.sleep(2)


def get_mac_to_connect():
    # print('MAC')
    json_data = json.loads(str(get_BSSI()).replace("'", "\""))
    if len(json_data) > 0:
        best_pow = -100
        best_val = -1
        val = 0
        current_pow = -100
        while val < len(json_data):
            print(json_data[str(val)])
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


def handover(mac):
    print('[I] Performing handover to ' + mac)
    client_socket.close()
    disconnect(False)
    connect(mac)


def disconnect(starting):
    # print('Disconnect')
    global connected
    if not starting:
        kill_thread(server_thread.ident)
        server_thread.join()
    process_disconnect = subprocess.Popen(
        'netsh wlan disconnect',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    process_disconnect.communicate()
    connected = False


def connect(mac):
    # print('Connect')
    global connected
    global server_thread
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
            print('[I] Connected!')
            connected = True
        else:
            print('[!] Connection not established! Killing query and trying again...')
            kill_process(process_connect)
            time.sleep(5)

    # Thread controlling communications with server on FEC
    server_thread = threading.Thread(target=server_conn)
    server_thread.daemon = True
    server_thread.start()


def server_conn():
    # print('Server')
    global client_socket
    host = '10.0.0.1'
    port = 5010  # socket server port number
    try:
        client_socket = socket.socket()
        client_socket.connect((host, port))  # connect to the
        message = json.dumps(dict(type="auth", user_id=1))  # take input

        client_socket.send(message.encode())  # send message
        data = client_socket.recv(1024).decode()  # receive response

        print('[I] Received from server: ' + data)  # show in terminal

        # message = input(" -> ")  # again take input
        while True:
            time.sleep(1)

    except ConnectionRefusedError:
        print('[!] Server not available! Please, press enter to stop client.')
    except SystemExit:
        print('Socket closed')
        client_socket.close()  # close the connection


def kill_process(process_kill):
    # print('Kill process')
    process_kill.kill()
    process_kill.communicate()


def kill_thread(thread_id):
    try:
        # print('Kill thread')
        ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), ctypes.py_object(SystemExit))
        # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
        if ret == 0:
            raise ValueError("Thread ID " + str(thread_id) + " does not exist!")
        elif ret > 1:
            ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
            raise SystemError("PyThreadState_SetAsyncExc failed")
        print("[I] Successfully killed thread ", str(thread_id))
    except TypeError:
        pass


best_mac = ""
client_socket = socket.socket()
rssi_thread = threading.Thread(target=get_rssi)
server_thread = threading.Thread(target=server_conn)
connected = False


def main():
    # print('Main')

    try:
        # Global variables
        global best_mac
        global rssi_thread

        # In case of being connected to a network, disconnect
        disconnect(True)

        # Get the best FEC int terms of power and connect to it
        while best_mac == "":
            time.sleep(2)
            best_mac = get_mac_to_connect()
        connect(best_mac)

        # Thread controlling RX power from all AP and performing handovers
        rssi_thread = threading.Thread(target=get_rssi)
        rssi_thread.daemon = True
        rssi_thread.start()

        input('[*] Press enter to stop...')

        print('[!] Ending...')
        kill_thread(rssi_thread.ident)
        rssi_thread.join()
        disconnect(False)
    except KeyboardInterrupt:
        print('[!] Ending...')
        kill_thread(rssi_thread.ident)
        if rssi_thread.is_alive():
            rssi_thread.join()
        disconnect(False)
    except RuntimeError:
        pass


if __name__ == '__main__':
    main()
