# The GPS module used is a Grove GPS module
# http://www.seeedstudio.com/depot/Grove-GPS-p-959.html
import math
import simplekml
import serial
import time

ser = serial.Serial('COM5', 9600, timeout=0)
ser.flush()


def clean_string(in_str):
    """Removes non-numerical characters, only keeps 0123456789.-"""
    out_str = "".join([c for c in in_str if c in "0123456789.-"])
    if len(out_str) == 0:
        out_str = "-1"
    return out_str


def safe_float(in_str):
    """Converts to float. If there is an error, a default
    value is returned
    """
    try:
        out_str = float(in_str)
    except ValueError:
        out_str = -1.0
    return out_str


# Convert to decimal degrees
def decimal_degrees(raw_degrees):
    """Converts coordinates to decimal values"""
    try:
        degrees = float(raw_degrees) // 100
        d = float(raw_degrees) % 100 / 60
        return degrees + d
    except Exception as e:
        print(e)
        return raw_degrees


class GPS:
    """"Connect to GPS and read its values"""

    inp = []
    inp2 = []
    GGA = []
    RMC = []
    values = []

    def __init__(self):
        """Instantiates an object of the class
        and runs the refresh() method
        """
        self.refresh()

    def refresh(self):
        """Reads data from the GPS and stores them in
        a global array of the class
        """
        while True:
            line = ser.readline()
            GPS.inp = line.decode('ISO-8859-1')
            # print(GPS.inp + "\n") # uncomment for debugging
            # GGA data for latitude, longitude, satellites,
            # altitude, and UTC position
            if GPS.inp[0:6] == '$GPGGA':
                GPS.GGA = GPS.inp.split(",")
                if len(GPS.GGA) >= 10:
                    break
            time.sleep(0.1)  # needed by the cmd in order not to crash
        while True:
            GPS.inp2 = ser.readline().decode('ISO-8859-1')
            if GPS.inp2[0:6] == '$GPRMC':  # RMC data to get velocity
                GPS.RMC = GPS.inp2.split(",")
                if len(GPS.RMC) >= 8:
                    break
            time.sleep(0.1)

        # initialize values obtained from the GPS device

        if GPS.GGA[1] == '':
            ti = ""
        else:
            ti = GPS.GGA[1].split(".")[0]

            # convert to standard time format
            ti = ti[0:2] + ":" + ti[2:4] + ":" + ti[4:]

        if GPS.GGA[2] == '':  # latitude. Technically a float
            lat = -1.0
        else:
            lat = decimal_degrees(safe_float(clean_string(GPS.GGA[2])))

        if GPS.GGA[3] == '':  # this should be either N or S
            lat_ns = ""
        else:
            lat_ns = str(GPS.GGA[3])
        if lat_ns == "S":
            lat = -lat

        if GPS.GGA[4] == '':  # longitude. Technically a float
            long = -1.0
        else:
            long = decimal_degrees(safe_float(clean_string(GPS.GGA[4])))

        if GPS.GGA[5] == '':  # this should be either W or E
            long_ew = ""
        else:
            long_ew = str(GPS.GGA[5])
        if long_ew == "W":
            long = -long

        if GPS.GGA[7] == '':  # number of satellites
            sats = 0
        else:
            sats = int(clean_string(GPS.GGA[7]))

        if GPS.GGA[9] == '':  # altitude
            alt = -1.0
        else:
            alt = GPS.GGA[9]

        if GPS.RMC[7] == '':  # speed
            spd = 0.0
        else:
            # conversion from knots to km/h
            spd = 1.852 * safe_float(GPS.RMC[7])

        GPS.values = [lat, lat_ns, long, long_ew, sats, alt, spd, ti]

    # Accessor methods for all the desired GPS values
    def getLatitude(self):
        """Returns the latitude"""
        return GPS.values[0]

    def getNS(self):
        """Returns whether the latitude coordinates
        are North or South
        """
        return GPS.values[1]

    def getLongitude(self):
        """Returns the longitude"""
        return GPS.values[2]

    def getEW(self):
        """Returns whether the longitude coordinates
        are East or West
        """
        return GPS.values[3]

    def getSatellites(self):
        """Returns the number of satellites the GPS is connected to"""
        return GPS.values[4]

    def getAltitude(self):
        """Returns the altitude"""
        return GPS.values[5]

    def getSpeed(self):
        """Returns the speed in km/h"""
        return GPS.values[6]

    def getUTCPosition(self):
        """Returns the UTC time"""
        return GPS.values[7]

    def distance(self, lat1, lng1, lat2, lng2):
        """Find the distance between two sets of coordinates"""
        degtorad = math.pi / 180
        dLat = (lat1 - lat2) * degtorad
        dLng = (lng1 - lng2) * degtorad
        a = pow(math.sin(dLat / 2), 2) + math.cos(lat1 * degtorad) * \
            math.cos(lat2 * degtorad) * pow(math.sin(dLng / 2), 2)
        b = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return 6371 * b


if __name__ == "__main__":
    gps = GPS()

    kml = simplekml.Kml()
    i = 0
    prevLat = 41.275
    prevLon = 1.988

    # if all the following outputs have values, it shows the GPS module
    # was able to connect to the satellites properly
    while True:
        try:
            print("Latitude: " + str(gps.getLatitude()))
            print("Longitude: " + str(gps.getLongitude()))
            print("Number of satellites: " + str(gps.getSatellites()))
            print("UTC position: " + gps.getUTCPosition())
            print("Altitude: " + str(gps.getAltitude()))
            print('Speed: ' + str(gps.getSpeed()))
            # print("Distance:", gps.distance(41.275631, 1.987350, gps.getLatitude(), gps.getLongitude())*1000)
            if str(gps.getLongitude()) != "-1.0" \
                    and str(gps.getLatitude()) != "-1.0" \
                    and gps.distance(prevLon, prevLat, gps.getLongitude(), gps.getLatitude()) < 100:
                kml.newpoint(name=str(i), coords=[(gps.getLongitude(), gps.getLatitude())])

            time.sleep(1)
            gps.refresh()
            i += 1
        except KeyboardInterrupt:
            kml.save("kml_files/paseo_farolas_3.kml")
            break

    # print("Distance:", gps.distance(41.27610333333334, 1.9880499999999999,
    #                                 41.27618166666666, 1.9880616666666668))
    # print("Distance:", gps.distance(41.27610333333334, 1.9880499999999999,
    #                                 41.276308333333326, 1.98773))
    # print("Distance:", gps.distance(41.27610333333334, 1.9880499999999999,
    #                                 41.27637500000001, 1.988023333333333))
    # print("Distance:", gps.distance(41.27618166666666, 1.9880616666666668,
    #                                 41.276308333333326, 1.98773))
    # print("Distance:", gps.distance(41.27618166666666, 1.9880616666666668,
    #                                 41.27637500000001, 1.988023333333333))
    # print("Distance:", gps.distance(41.276308333333326, 1.98773,
    #                                 41.27637500000001, 1.988023333333333))
