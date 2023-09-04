import configparser
import platform
import subprocess
import socket
import threading
import time
import json
import ctypes
import logging
import sys
from colorlog import ColoredFormatter
import os


class VNF:
    def __init__(self, json_data):
        self.source = json_data['source']
        self.target = json_data['target']
        self.gpu = json_data['gpu']
        self.ram = json_data['ram']
        self.bw = json_data['bw']
        self.previous_node = json_data['previous_node']
        self.current_node = json_data['current_node']
        self.fec_linked = json_data['fec_linked']
        self.user_id = json_data['user_id']


# Import settings from configuration file
system_os = platform.system()
config = configparser.ConfigParser()
config.read('ue.ini')
general = config['general']
# Logging configuration
logger = logging.getLogger('')
logger.setLevel(int(general['log_level']))
logger.addHandler(logging.FileHandler(general['log_file_name'], mode='w', encoding='utf-8'))
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(ColoredFormatter('%(log_color)s%(message)s'))
logger.addHandler(stream_handler)

# Global variables
best_mac = ""
client_socket = socket.socket()
connected = False
fec_id = -1
user_id = 1
my_vnf = None
previous_node = -1
next_node = -1
next_location = '0,0'
gps = None
bot = None
current_direction = 'u'
wireshark_if = 'Y'
video_if = 'n'


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
        from get_rx_rssi import get_BSSI
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
    elif system_os == 'Linux':
        data = []
        try:
            iwlist_scan = subprocess.check_output(['sudo', 'iwlist', 'wlan0', 'scan'],
                                                  stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            logger.error('[!] Unexpected error:' + str(e))
        else:
            iwlist_scan = iwlist_scan.decode('utf-8').split('Address: ')
            i = 1
            while i < len(iwlist_scan):
                bssid = iwlist_scan[i].split('\n')[0]
                ssid = iwlist_scan[i].split('ESSID:"')[1].split('"')[0]
                power = iwlist_scan[i].split('level=')[1].split(' dBm')[0]
                if ssid == 'Test301':
                    cell = ssid + ' ' + bssid + ' ' + power
                    data.append(cell)
                i += 1

        if len(data) > 0:
            best_pow = -100
            val = 0
            current_pow = -100
            best_pow_mac = ""
            while val < len(data):
                logger.debug('[D] ' + data[val])
                split_data = data[val].split(' ')
                i = 0
                while i < len(split_data):
                    if split_data[i] == '':
                        split_data.pop(i)
                    else:
                        i += 1
                if split_data[0] != general['wifi_ssid']:
                    pass
                else:
                    if int(split_data[2]) > best_pow:
                        best_pow = int(split_data[2])
                        best_pow_mac = split_data[1]
                    if best_mac == split_data[1]:
                        current_pow = int(split_data[2])
                val += 1
            if current_pow < best_pow - 5:
                return best_pow_mac
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
        elif system_os == 'Linux':
            num = subprocess.check_output(['nmcli', 'connection']).decode().split('\n')[1].split(' ')[1]
            process_disconnect = subprocess.Popen(
                'nmcli con down "' + general['wifi_ssid'] + ' ' + num + '"',
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            process_disconnect.communicate()
            connected = False
        else:
            logger.critical('[!] System OS not supported! Please, stop program...')
            return
    except ConnectionResetError:
        logger.warning('[!] Trying to reuse killed connection!')
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
            if general['wifi_ssid'] in str(subprocess.check_output("netsh wlan show interfaces")):
                logger.info('[I] Connected!')
                connected = True
            else:
                logger.warning('[!] Connection not established! Killing query and trying again...')
                process_connect.kill()
                process_connect.communicate()
                time.sleep(1)
    elif system_os == 'Linux':
        while not connected:
            process_connect = subprocess.Popen('nmcli d wifi connect ' + mac + ' password 1234567890',
                                               shell=True,
                                               stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE)
            process_connect.communicate()
            time.sleep(2)
            if general['wifi_ssid'] in str(subprocess.check_output("iwgetid")):
                logger.info('[I] Connected!')
                connected = True
            else:
                logger.warning('[!] Connection not established! Killing query and trying again...')
                process_connect.kill()
                process_connect.communicate()
                time.sleep(1)
    else:
        logger.critical('[!] System OS not supported! Please, stop program...')
        return

    # Thread controlling communications with server on FEC
    server_thread = threading.Thread(target=server_conn)
    server_thread.daemon = True
    server_thread.start()


def generate_vnf():
    # This function returns a new VNF object whose fields are given by console
    source = get_data_by_console(int, '[*] Introduce the source position: ')
    target = get_data_by_console(int, '[*] Introduce the target position: ')
    gpu = get_data_by_console(int, '[*] Introduce the needed GPU MB: ')
    ram = get_data_by_console(int, '[*] Introduce the needed RAM MB: ')
    bw = get_data_by_console(int, '[*] Introduce the needed bandwidth (Mbps): ')

    return VNF(dict(source=source, target=target, gpu=gpu, ram=ram, bw=bw, previous_node=-1,
                    current_node=source, fec_linked=fec_id, user_id=user_id))


def get_next_action(json_data):
    global next_node
    global next_location
    global my_vnf
    global current_direction
    logger.info('[I] Response from server: ' + str(json_data))
    if json_data['res'] == 200:
        next_node = json_data['next_node']
        if gps is not None:
            next_location = json_data['location']
        if json_data['action'] == 'e':
            logger.info('[I] Car reached target!')
            if bot is not None:
                bot.set_motor(1, 0)
                bot.set_motor(1, 0)
                bot.set_motor(2, 0)
                bot.set_motor(2, 0)
                if 'u' != current_direction:
                    # Return transbot to default direction
                    rotate('u')
                    current_direction = 'u'
            key_in = input('[?] Want to send a new VNF? Y/n: (Y) ')
            if key_in != 'n':
                my_vnf = None
                return False, False
            else:
                my_vnf = None
                return True, True
        else:
            return True, False
    elif json_data['res'] == 403:
        my_vnf = None
        logger.error('[!] Error! Required resources are not available on current FEC. '
                     'Ask for less resources.')
        return False, False
    elif json_data['res'] == 404:
        my_vnf = None
        logger.error('[!] Error! Required target does not exist. Ask for an existing target.')
        return False, False
    else:
        my_vnf = None
        logger.error('[!] Error ' + str(json_data['res']) + ' when sending VNF to FEC!')
        return False, False


def rotate(new_direction):
    if new_direction == 'r':
        fin_degrees = 90
    elif new_direction == 'd':
        fin_degrees = 180
    elif new_direction == 'l':
        fin_degrees = 270
    else:
        fin_degrees = 0

    if current_direction == 'r':
        current_degrees = 90
    elif current_direction == 'd':
        current_degrees = 180
    elif current_direction == 'l':
        current_degrees = 270
    else:
        current_degrees = 0

    degrees = fin_degrees - current_degrees
    if degrees > 180:
        degrees = degrees - 360
    elif degrees < -180:
        degrees = degrees + 360

    if degrees < 0:
        degrees = degrees * -1
        direction = -1
    else:
        direction = 1

    bot.set_motor(1, direction * int(general['motor_speed']))
    bot.set_motor(1, direction * int(general['motor_speed']))
    bot.set_motor(2, -direction * int(general['motor_speed']))
    bot.set_motor(2, -direction * int(general['motor_speed']))

    # rotate_time = 19.344 * pow(int(general['motor_speed'])-15, -0.853)
    rotate_time = 14.205 * pow(int(general['motor_speed'])-15, -0.802)
    time.sleep(rotate_time * degrees / 90)

    bot.set_motor(1, 0)
    bot.set_motor(1, 0)
    bot.set_motor(2, 0)
    bot.set_motor(2, 0)


def server_conn():
    # This function is running on a second thread as long as being connected to a FEC.
    # It sends data to the sockets server and waits for responses
    global client_socket
    global fec_id
    global my_vnf
    global user_id
    global next_node
    global next_location
    global bot
    global current_direction
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
        while True:
            stop = False
            if my_vnf is None:
                valid_vnf = False
                json_data = dict()
                while not valid_vnf:
                    my_vnf = generate_vnf()
                    message = json.dumps(dict(type="vnf", data=my_vnf.__dict__))  # take input
                    client_socket.send(message.encode())  # send message
                    data = client_socket.recv(1024).decode()  # receive response
                    json_data = json.loads(data)
                    valid_vnf, stop = get_next_action(json_data)
                if bot is not None:
                    if json_data['action'] != current_direction:
                        # Need to rotate transbot first
                        rotate(json_data['action'])
                        current_direction = json_data['action']
            while my_vnf is not None:
                # Move to next point
                if bot is not None:
                    bot.set_motor(1, int(general['motor_speed']))
                    bot.set_motor(1, int(general['motor_speed']))
                    bot.set_motor(2, int(general['motor_speed']))
                    bot.set_motor(2, int(general['motor_speed']))
                if gps is not None:
                    while gps.distance(float(next_location.split(',')[0]), float(next_location.split(',')[1]),
                                       gps.getLatitude(), gps.getLongitude()) > 2:
                        time.sleep(1)
                else:
                    input('[*] Press Enter when getting to the next point...')

                # Update state vector
                logger.info('[I] Reached next point! Sending changes to FEC...')
                my_vnf.previous_node = my_vnf.current_node
                my_vnf.current_node = next_node
                my_vnf.fec_linked = fec_id
                message = json.dumps(dict(type="state", data=dict(previous_node=my_vnf.previous_node,
                                                                  current_node=my_vnf.current_node,
                                                                  fec_linked=my_vnf.fec_linked,
                                                                  user_id=my_vnf.user_id)))
                client_socket.send(message.encode())  # send message
                data = client_socket.recv(1024).decode()  # receive response
                json_data = json.loads(data)
                valid_vnf, stop = get_next_action(json_data)
            if stop:
                break
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
        logger.debug("[D] Successfully killed thread " + str(thread_id))
    except Exception as e:
        logger.exception(e)


def main():
    # Main function
    # Global variables
    global best_mac
    global user_id
    global gps
    global bot
    global current_direction
    global wireshark_if
    global video_if
    try:
        # Get user_id
        user_id = get_data_by_console(int, '[*] Introduce your user ID: ')

        gps_if = input('[?] Want to use GPS locations? Y/n: (n) ')
        if gps_if == 'y' or gps_if == 'Y':
            from gps_handler import GPS
            gps = GPS()

        if system_os == 'Linux':
            video_if = input('[?] Want to consume a video stream? (requires gstreamer) Y/n: (n) ')
            transbot_if = input('[?] Is this device a Transbot? Y/n: (Y) ')
            if transbot_if != 'n' and transbot_if != 'N':
                from Transbot_Lib import Transbot
                bot = Transbot()
        elif system_os == 'Windows':
            video_if = input('[?] Want to consume a video stream? (requires VLC) Y/n: (n) ')

        if system_os == 'Linux':
            wireshark_if = input('[?] Capture packets with Wireshark? Y/n: (Y) ')
            if wireshark_if != 'n' and wireshark_if != 'N':
                script_path = os.path.dirname(os.path.realpath(__file__))
                os.system(
                    "sudo screen -S ue-wireshark -m -d sudo wireshark -i " + general['wlan_if_name'] + " -k -w " +
                    script_path + "/logs/ue-wireshark.pcap")
        # In case of being connected to a network, disconnect
        disconnect(True)

        # Get the best FEC in terms of power and connect to it
        while best_mac == "":
            time.sleep(2)
            best_mac = get_mac_to_connect()

        connect(best_mac)

        if system_os == 'Linux':
            if video_if == 'y' or video_if == 'Y':
                os.system("sudo screen -S ue-stream -m -d nvgstplayer-1.0 -i "
                          "http://rdmedia.bbc.co.uk/testcard/vod/manifests/avc-ctv-en-http.mpd")
        elif system_os == 'Windows':
            if video_if == 'y' or video_if == 'Y':
                os.system("vlc " + general['video_link'])
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
        if bot is not None:
            bot.set_motor(1, 0)
            bot.set_motor(1, 0)
            bot.set_motor(2, 0)
            bot.set_motor(2, 0)
            if 'u' != current_direction:
                # Return transbot to default direction
                rotate('u')
                current_direction = 'u'

        if system_os == 'Linux' and video_if == 'y' or video_if == 'Y':
            os.system("sudo screen -S ue-stream -X stuff '^C\n'")
        elif system_os == 'Windows' and video_if == 'y' or video_if == 'Y':
            os.system("taskkill /im vlc.exe")

        disconnect(False)

        if system_os == 'Linux' and wireshark_if != 'n' and wireshark_if != 'N':
            os.system("sudo screen -S ue-wireshark -X stuff '^C\n'")

    except Exception as e:
        logger.exception(e)
        logger.info('[!] Ending...')
        if bot is not None:
            bot.set_motor(1, 0)
            bot.set_motor(1, 0)
            bot.set_motor(2, 0)
            bot.set_motor(2, 0)
            if 'u' != current_direction:
                # Return transbot to default direction
                rotate('u')
                current_direction = 'u'

        if system_os == 'Linux' and video_if == 'y' or video_if == 'Y':
            os.system("sudo screen -S ue-stream -X stuff '^C\n'")
        elif system_os == 'Windows' and video_if == 'y' or video_if == 'Y':
            os.system("taskkill /im vlc.exe")

        disconnect(False)

        if wireshark_if != 'n' and wireshark_if != 'N':
            os.system("sudo screen -S ue-wireshark -X stuff '^C\n'")


if __name__ == '__main__':
    main()
