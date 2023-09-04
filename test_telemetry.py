from dronekit import connect
import time
from datetime import datetime


def main():
    connection_string = 'tcp:127.0.0.1:5762'
    vehicle = connect(connection_string, wait_ready=True, baud=115200)

    print('Vehicle connected')

    while vehicle.armed is False:
        time.sleep(1)

    while True:
        now = datetime.now()
        tiempo = now.strftime('%H:%M:%S:%M')
        print(tiempo)
        print(vehicle.mode.name)
        print(vehicle.location.global_frame)
        print(vehicle.airspeed)
        print(vehicle.attitude)
        time.sleep(1)


if __name__ == '__main__':
    main()
