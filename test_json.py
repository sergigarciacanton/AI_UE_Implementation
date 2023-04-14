import json

x = "{'0': ['90:E8:68:83:FA:DD', 'Test301', '-39'], '1': ['90:E8:68:84:3B:97', 'Test301', '-61']}".replace("'", "\"")
print(x)

y = json.loads(x)

# the result is a Python dictionary:
print(y['0'][0])
print(len(y))
