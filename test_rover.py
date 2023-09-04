from dronekit import connect, VehicleMode
import dronekit
import time


def compare_location(prevLoc, currLoc):
    if prevLoc.lat == currLoc.lat and prevLoc.lon == currLoc.lon:
        return True
    else:
        return False


def main():
    vehicle = connect("tcp:127.0.0.1:5762", wait_ready=True, baud=115200)
    print("Vehicle connected")

    vehicle.mode = VehicleMode("GUIDED")
    while not vehicle.mode == VehicleMode("GUIDED"):
        time.sleep(1)
    print("Guided mode ready")

    vehicle.armed = True
    while not vehicle.armed:
        time.sleep(1)
    print("Armed vehicle")

    point = dronekit.LocationGlobal(41.275995, 1.987727, 0)
    vehicle.simple_goto(point, 1)
    arrived = False
    prevLoc = vehicle.location.global_frame
    time.sleep(1)
    print('Going to waypoint')
    while not arrived:
        arrived = compare_location(prevLoc, vehicle.location.global_frame)
        prevLoc = vehicle.location.global_frame
        time.sleep(1)

    vehicle.armed = False
    vehicle.close()


if __name__ == '__main__':
    main()
