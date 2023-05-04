from pyembedded.gps_module.gps import GPS
import time

gps = GPS(port='COM1', baud_rate=9600)

while True:
    print(gps.get_lat_long())
    time.sleep(2)
