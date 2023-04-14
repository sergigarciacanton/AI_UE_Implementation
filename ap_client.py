import subprocess


process1 = subprocess.Popen(
        'netsh wlan connect {0}'.format('Test301'),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
stdout1, stderr1 = process1.communicate()

input('Press Enter to disconnect...')

process2 = subprocess.Popen(
        'netsh wlan disconnect',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
stdout2, stderr2 = process2.communicate()
