import configparser
import platform
import subprocess
import socket
import time
import json
import ctypes
import logging
import sys
from colorlog import ColoredFormatter
import os
from dronekit import connect, VehicleMode
import dronekit
import math
from vnf_generator import VNF


class CAV:
    def __init__(self, system_os, general, logger):
        self.system_os = system_os
        self.client_socket = None
        self.connected = False
        self.fec_id = None
        self.user_id = None
        self.my_vnf = None
        self.previous_node = None
        self.next_node = None
        self.next_location = None
        self.logger = logger
        if general['rover_if'] != 'n' and general['rover_if'] != 'N':
            self.vehicle = connect(general['rover_conn'], wait_ready=True, baud=115200)
            self.logger.info("[I] Connected to vehicle")

            self.vehicle.mode = VehicleMode("GUIDED")
            while not self.vehicle.mode == VehicleMode("GUIDED"):
                time.sleep(1)
            self.logger.info("[I] Guided mode ready")

            self.vehicle.armed = True
            while not self.vehicle.armed:
                time.sleep(1)
            self.logger.info("[I] Armed vehicle")
        else:
            self.vehicle = None
        self.vehicle_active = False
        self.general = general

        self.start_cav()

    def get_data_by_console(self, data_type, message):
        # Function that reads a console entry asking for data to store into a variable
        valid = False
        output = None
        if data_type == int:
            while not valid:
                try:
                    output = int(input(message))
                    valid = True
                except ValueError:
                    self.logger.warning('[!] Error in introduced data! Must use int values. Try again...')
                    valid = False
                except Exception as e:
                    self.logger.warning('[!] Unexpected error ' + str(e) + '! Try again...')
                    valid = False
        elif data_type == float:
            while not valid:
                try:
                    output = float(input(message))
                    valid = True
                except ValueError:
                    self.logger.warning('[!] Error in introduced data! Must use float values. Try again...')
                    valid = False
                except Exception as e:
                    self.logger.warning('[!] Unexpected error ' + str(e) + '! Try again...')
                    valid = False
        else:
            self.logger.error('[!] Data type getter not implemented!')
        return output

    def get_mac_to_connect(self):
        # Function that returns the wireless_conn_manager the mac of the best FEC to connect.
        # Takes into account a hysteresis margin of 5 dB for changing FEC
        # return 'ab:cd:ef:ac:cd:ef'
        best_mac = ''
        if self.system_os == 'Windows':
            from get_rx_rssi import get_BSSI
            json_data = json.loads(str(get_BSSI()).replace("'", "\""))
            if len(json_data) > 0:
                best_pow = -100
                best_val = -1
                val = 0
                current_pow = -100
                while val < len(json_data):
                    # self.logger.debug('[D] ' + str(json_data[str(val)]))
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
        elif self.system_os == 'Linux':
            data = []
            try:
                iwlist_scan = subprocess.check_output(['sudo', 'iwlist', 'wlan0', 'scan'],
                                                      stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                self.logger.error('[!] Unexpected error:' + str(e))
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
                    # self.logger.debug('[D] ' + data[val])
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
            self.logger.critical('[!] System OS not supported! Please, stop program...')
            return

    def handover(self, address):
        # Function that handles handovers. First disconnects from current FEC and after connects to the new one
        self.logger.info('[I] Performing handover to ' + address)
        self.disconnect(False)
        self.fec_connect(address)

    def disconnect(self, starting):
        # Disconnects from current FEC
        try:
            if not starting and self.connected:
                message = json.dumps(dict(type="bye"))  # take input
                self.client_socket.send(message.encode())  # send message
                self.client_socket.recv(1024).decode()  # receive response
            if general['training_if'] != 'y' and general['training_if'] != 'Y':
                if self.system_os == 'Windows':
                    process_disconnect = subprocess.Popen(
                        'netsh wlan disconnect',
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                    process_disconnect.communicate()
                    self.connected = False
                elif self.system_os == 'Linux':
                    num = subprocess.check_output(['nmcli', 'connection']).decode().split('\n')[1].split(' ')[1]
                    process_disconnect = subprocess.Popen(
                        'nmcli con down "' + general['wifi_ssid'] + ' ' + num + '"',
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                    process_disconnect.communicate()
                    self.connected = False
                else:
                    self.logger.critical('[!] System OS not supported! Please, stop program...')
                    return
        except ConnectionResetError:
            self.logger.warning('[!] Trying to reuse killed connection!')
        except Exception as e:
            self.logger.exception(e)

    def fec_connect(self, address):
        # This function manages connecting to a new FEC given its MAC address
        if general['training_if'] != 'y' and general['training_if'] != 'Y':
            if self.system_os == 'Windows':
                while not self.connected:
                    process_connect = subprocess.Popen(
                        general['wifi_handler_file'] + ' /ConnectAP "' + general['wifi_ssid'] + '" "' + address + '"',
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE)
                    process_connect.communicate()
                    time.sleep(2)
                    if general['wifi_ssid'] in str(subprocess.check_output("netsh wlan show interfaces")):
                        self.logger.info('[I] Connected!')
                        self.connected = True
                    else:
                        self.logger.warning('[!] Connection not established! Killing query and trying again...')
                        process_connect.kill()
                        process_connect.communicate()
                        time.sleep(1)
            elif self.system_os == 'Linux':
                while not self.connected:
                    process_connect = subprocess.Popen('nmcli d wifi connect ' + address + ' password 1234567890',
                                                       shell=True,
                                                       stdout=subprocess.PIPE,
                                                       stderr=subprocess.PIPE)
                    process_connect.communicate()
                    time.sleep(2)
                    if general['wifi_ssid'] in str(subprocess.check_output("iwgetid")):
                        self.logger.info('[I] Connected!')
                        self.connected = True
                    else:
                        self.logger.warning('[!] Connection not established! Killing query and trying again...')
                        process_connect.kill()
                        process_connect.communicate()
                        time.sleep(1)
            else:
                self.logger.critical('[!] System OS not supported! Please, stop program...')
                return

            host = general['fec_ip']
        else:
            host = address
        port = int(general['fec_port'])  # socket server port number
        self.client_socket = socket.socket()
        ready = False
        while not ready:
            try:
                self.client_socket.connect((host, port))  # connect to the server
                ready = True
            except OSError:
                time.sleep(1)
        auth_valid = False
        while not auth_valid:
            message = json.dumps(dict(type="auth", user_id=self.user_id))  # take input

            self.client_socket.send(message.encode())  # send message
            data = self.client_socket.recv(1024).decode()  # receive response
            json_data = json.loads(data)
            if json_data['res'] == 200:
                self.logger.info('[I] Successfully authenticated to FEC ' + str(json_data['id']) + '!')
                self.fec_id = json_data['id']
                auth_valid = True
                if self.my_vnf is not None:
                    self.my_vnf['cav_fec'] = self.fec_id
            else:
                self.logger.error('[!] Error ' + str(json_data['res']) + ' when authenticating to FEC!')
                if general['training_if'] != 'y' and general['training_if'] != 'Y':
                    self.user_id = self.get_data_by_console(int, '[*] Introduce a valid user ID: ')
                else:
                    self.user_id = 1

    def generate_vnf(self):
        # This function returns a new VNF object whose fields are given by console
        source = self.get_data_by_console(int, '[*] Introduce the source position: ')
        target = self.get_data_by_console(int, '[*] Introduce the target position: ')
        gpu = self.get_data_by_console(int, '[*] Introduce the needed GPU MB: ')
        ram = self.get_data_by_console(int, '[*] Introduce the needed RAM MB: ')
        bw = self.get_data_by_console(int, '[*] Introduce the needed bandwidth (Mbps): ')

        return dict(source=source, target=target, gpu=gpu, ram=ram, bw=bw, previous_node=source,
                    current_node=source, cav_fec=self.fec_id, time_steps=-1, user_id=self.user_id)

    def distance(self, lat1, lng1, lat2, lng2):
        # Finds the distance between two sets of coordinates
        deg_to_rad = math.pi / 180
        dLat = (lat1 - lat2) * deg_to_rad
        dLng = (lng1 - lng2) * deg_to_rad
        a = pow(math.sin(dLat / 2), 2) + math.cos(lat1 * deg_to_rad) * \
            math.cos(lat2 * deg_to_rad) * pow(math.sin(dLng / 2), 2)
        b = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6371000 * b

    def kill_thread(self, thread_id):
        # This functions kills a thread. It is used for stopping the program or disconnecting from a FEC
        try:
            ret = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), ctypes.py_object(SystemExit))
            # ref: http://docs.python.org/c-api/init.html#PyThreadState_SetAsyncExc
            if ret == 0:
                raise ValueError("Thread ID " + str(thread_id) + " does not exist!")
            elif ret > 1:
                ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                raise SystemError("PyThreadState_SetAsyncExc failed")
            self.logger.debug("[D] Successfully killed thread " + str(thread_id))
        except Exception as e:
            self.logger.exception(e)

    def stop_program(self):
        self.logger.info('[!] Ending...')

        if self.system_os == 'Linux' and general['video_if'] == 'y' or general['video_if'] == 'Y':
            os.system("sudo screen -S ue-stream -X stuff '^C\n'")
        elif self.system_os == 'Windows' and general['video_if'] == 'y' or general['video_if'] == 'Y':
            os.system("taskkill /im vlc.exe")

        self.disconnect(False)

        if self.system_os == 'Linux' and general['wireshark_if'] != 'n' and general['wireshark_if'] != 'N':
            os.system("sudo screen -S ue-wireshark -X stuff '^C\n'")
        if self.system_os == 'Linux' and general['rover_if'] != 'n' and general['rover_if'] != 'N':
            self.logger.debug('[D] Disarming vehicle...')
            self.vehicle.armed = False
            self.vehicle.close()

    def start_cav(self):
        # Main function
        try:
            # Get user_id
            if general['training_if'] != 'y' and general['training_if'] != 'Y':
                self.user_id = self.get_data_by_console(int, '[*] Introduce your user ID: ')
            else:
                self.user_id = 1

            if self.system_os == 'Linux':
                wireshark_if = general['wireshark_if']
                if wireshark_if != 'n' and wireshark_if != 'N':
                    script_path = os.path.dirname(os.path.realpath(__file__))
                    os.system(
                        "sudo screen -S ue-wireshark -m -d sudo wireshark -i " + general['wlan_if_name'] + " -k -w " +
                        script_path + "/logs/ue-wireshark.pcap")
                video_if = general['video_if']
            elif self.system_os == 'Windows':
                video_if = general['video_if']
            else:
                self.logger.critical('[!] System OS not supported!')
                exit(-1)

            # In case of being connected to a network, disconnect
            self.disconnect(True)

            # Get the best FEC in terms of power and connect to it
            if general['training_if'] != 'y' and general['training_if'] != 'Y':
                best_mac = ''
                while best_mac == '':
                    time.sleep(2)
                    best_mac = self.get_mac_to_connect()

                self.fec_connect(best_mac)
            else:
                self.fec_connect('192.168.0.2')
            if self.system_os == 'Linux':
                if video_if == 'y' or video_if == 'Y':
                    os.system("sudo screen -S ue-stream -m -d nvgstplayer-1.0 -i "
                              "http://rdmedia.bbc.co.uk/testcard/vod/manifests/avc-ctv-en-http.mpd")
            elif self.system_os == 'Windows':
                if video_if == 'y' or video_if == 'Y':
                    os.system("vlc " + general['video_link'])

            try:
                # iterator = 0
                while True:
                    stop = False
                    if self.my_vnf is None:
                        valid_vnf = False
                        while not valid_vnf:
                            if general['training_if'] != 'y' and general['training_if'] != 'Y':
                                self.my_vnf = self.generate_vnf()
                            else:
                                random_vnf = VNF().get_request()
                                self.my_vnf = dict(source=random_vnf['source'],
                                                   target=random_vnf['target'], gpu=random_vnf['gpu'],
                                                   ram=random_vnf['ram'], bw=random_vnf['bw'],
                                                   previous_node=random_vnf['source'],
                                                   current_node=random_vnf['source'], cav_fec=self.fec_id,
                                                   time_steps=-1, user_id=self.user_id)
                            message = json.dumps(dict(type="vnf", data=self.my_vnf))  # take input
                            self.client_socket.send(message.encode())  # send message
                            data = self.client_socket.recv(1024).decode()  # receive response
                            json_data = json.loads(data)
                            self.logger.info('[I] Response from server: ' + str(json_data))
                            # if iterator == 0:
                            #     iterator += 1
                            #     json_data = dict(res=200, next_node=8, location='41.27607627820264,1.988212939805942')
                            # elif iterator == 1:
                            #     iterator += 1
                            #     json_data = dict(res=200, next_node=4, location='41.27618043781608,1.988175200657076')
                            # elif iterator == 2:
                            #     iterator += 1
                            #     json_data = dict(res=200, next_node=3, location='41.27614011136027,1.988006030851253')
                            # elif iterator == 3:
                            #     iterator += 1
                            #     json_data = dict(res=200, next_node=7, location='41.27603977014193,1.988058630277008')
                            # else:
                            #    json_data = dict(res=200, next_node=-1, location='41.27603977014193,1.988058630277008')
                            if json_data['res'] == 200:
                                self.next_node = json_data['next_node']
                                if self.vehicle is not None and self.next_node != -1:
                                    self.next_location = json_data['location']
                                if json_data['next_node'] == -1:
                                    self.logger.info('[I] Car reached target!')
                                    if general['training_if'] != 'y' and general['training_if'] != 'Y':
                                        key_in = input('[?] Want to send a new VNF? Y/n: (Y) ')
                                    else:
                                        key_in = 'n'
                                    if key_in != 'n':
                                        self.my_vnf = None
                                        valid_vnf = False
                                        stop = False
                                    else:
                                        self.my_vnf = None
                                        valid_vnf = True
                                        stop = True
                                else:
                                    valid_vnf = True
                                    stop = False
                            elif json_data['res'] == 403:
                                self.my_vnf = None
                                self.logger.error('[!] Error! Required resources are not available on current FEC. '
                                             'Ask for less resources.')
                                valid_vnf = False
                                stop = False
                            elif json_data['res'] == 404:
                                self.my_vnf = None
                                self.logger.error('[!] Error! Required target does not exist. Ask for an existing target.')
                                valid_vnf = False
                                stop = False
                            else:
                                self.my_vnf = None
                                self.logger.error('[!] Error ' + str(json_data['res']) + ' when sending VNF to FEC!')
                                valid_vnf = False
                                stop = False
                    while self.my_vnf is not None:
                        # Move to next point
                        if general['training_if'] != 'y' and general['training_if'] != 'Y':
                            if json_data['cav_fec'] is not self.my_vnf['cav_fec']:
                                self.handover(json_data['fec_mac'])
                        else:
                            if json_data['cav_fec'] is not self.my_vnf['cav_fec']:
                                self.handover(json_data['fec_ip'])
                        if self.vehicle is not None and self.vehicle_active is False:
                            point = dronekit.LocationGlobal(float(self.next_location.split(',')[0]),
                                                            float(self.next_location.split(',')[1]), 0)
                            self.logger.info('[I] Moving towards first target...')
                            self.vehicle.simple_goto(point, 1)
                            self.vehicle_active = True
                        if self.vehicle is not None and self.vehicle_active is True:
                            while self.distance(float(self.next_location.split(',')[0]),
                                                float(self.next_location.split(',')[1]),
                                                self.vehicle.location.global_frame.lat,
                                                self.vehicle.location.global_frame.lon) > 3:
                                time.sleep(1)
                        else:
                            if general['training_if'] != 'y' and general['training_if'] != 'Y':
                                input('[*] Press Enter when getting to the next point...')

                        # Update state vector
                        self.logger.info('[I] Reaching next point! Sending changes to FEC...')
                        self.my_vnf['previous_node'] = self.my_vnf['current_node']
                        self.my_vnf['current_node'] = self.next_node
                        self.my_vnf['cav_fec'] = self.fec_id
                        message = json.dumps(dict(type="state", data=dict(previous_node=self.my_vnf['previous_node'],
                                                                          current_node=self.my_vnf['current_node'],
                                                                          cav_fec=self.my_vnf['cav_fec'],
                                                                          time_steps=self.my_vnf['time_steps'],
                                                                          user_id=self.my_vnf['user_id'])))
                        self.client_socket.send(message.encode())  # send message
                        data = self.client_socket.recv(1024).decode()  # receive response
                        json_data = json.loads(data)
                        self.logger.info('[I] Response from server: ' + str(json_data))
                        # if iterator == 0:
                        #     iterator += 1
                        #     json_data = dict(res=200, next_node=8, location='41.27607627820264,1.988212939805942')
                        # elif iterator == 1:
                        #     iterator += 1
                        #     json_data = dict(res=200, next_node=4, location='41.27618043781608,1.988175200657076')
                        # elif iterator == 2:
                        #     iterator += 1
                        #     json_data = dict(res=200, next_node=3, location='41.27614011136027,1.988006030851253')
                        # elif iterator == 3:
                        #     iterator += 1
                        #     json_data = dict(res=200, next_node=7, location='41.27603977014193,1.988058630277008')
                        # else:
                        #     json_data = dict(res=200, next_node=-1, location='41.27603977014193,1.988058630277008')
                        if json_data['res'] == 200:
                            self.next_node = json_data['next_node']
                            if self.vehicle is not None and json_data['next_node'] != -1:
                                arriving_location = self.next_location
                                self.next_location = json_data['location']
                            if json_data['next_node'] == -1:
                                self.logger.info('[I] Car reached target!')
                                if general['training_if'] != 'y' and general['training_if'] != 'Y':
                                    key_in = input('[?] Want to send a new VNF? Y/n: (Y) ')
                                else:
                                    key_in = 'n'
                                if key_in != 'n':
                                    self.my_vnf = None
                                    stop = False
                                else:
                                    self.my_vnf = None
                                    stop = True
                            else:
                                stop = False
                                if self.vehicle is not None and self.vehicle_active is True:
                                    while self.distance(float(arriving_location.split(',')[0]),
                                                        float(arriving_location.split(',')[1]),
                                                        self.vehicle.location.global_frame.lat,
                                                        self.vehicle.location.global_frame.lon) > 1:
                                        time.sleep(1)
                                    self.logger.info('[I] Reached next point! Loading next target...')
                                    point = dronekit.LocationGlobal(float(self.next_location.split(',')[0]),
                                                                    float(self.next_location.split(',')[1]), 0)
                                    self.vehicle.simple_goto(point, 1)
                        elif json_data['res'] == 403:
                            self.my_vnf = None
                            self.logger.error('[!] Error! Required resources are not available on current FEC. '
                                         'Ask for less resources.')
                            stop = False
                        elif json_data['res'] == 404:
                            self.my_vnf = None
                            self.logger.error('[!] Error! Required target does not exist. Ask for an existing target.')
                            stop = False
                        else:
                            self.my_vnf = None
                            self.logger.error('[!] Error ' + str(json_data['res']) + ' when sending VNF to FEC!')
                            stop = False
                    if stop:
                        break
                message = json.dumps(dict(type="bye"))  # take input
                self.client_socket.send(message.encode())  # send message
                self.client_socket.close()  # close the connection

            except ConnectionRefusedError:
                self.logger.error('[!] FEC server not available! Please, press enter to stop client.')
            except SystemExit:
                message = json.dumps(dict(type="bye"))  # take input
                self.client_socket.send(message.encode())  # send message
                self.client_socket.close()  # close the connection
            except Exception as e:
                self.logger.exception(e)
        except KeyboardInterrupt:
            self.stop_program()
        except Exception as e:
            self.logger.exception(e)
            self.stop_program()


if __name__ == '__main__':
    # Import settings from configuration file
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

    my_cav = CAV(platform.system(), general, logger)
