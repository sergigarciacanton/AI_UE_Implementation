import subprocess
import time
best_mac = ''
try:
    while True:
        data = []
        try:
            iwlist_scan = subprocess.check_output(['sudo', 'iwlist', 'wlan0', 'scan'],
                                                  stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            print(e)
            break
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
                print('[D] ' + data[val])
                splitted_data = data[val].split(' ')
                i = 0
                while i < len(splitted_data):
                    if splitted_data[i] == '':
                        splitted_data.pop(i)
                    else:
                        i += 1
                if splitted_data[0] != 'Test301':
                    pass
                else:
                    if int(splitted_data[2]) > best_pow:
                        best_pow = int(splitted_data[2])
                        best_pow_mac = splitted_data[1]
                    if best_mac == splitted_data[1]:
                        current_pow = int(splitted_data[2])
                val += 1
            if current_pow < best_pow - 5:
                best_mac = best_pow_mac
        print(best_mac)
        time.sleep(1)
except KeyboardInterrupt:
    print('Stop')
