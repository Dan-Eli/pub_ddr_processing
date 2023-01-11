import zipfile
import tempfile
from dataclasses import dataclass
from typing import List
import pathlib
import os
import urllib
import requests
import json
import unicodedata
from urllib.request import urlopen, Request
import re

text = b'\u00e8a'
x = text.decode('unicode_escape')
print (x)
0/0

try:
    text = unicode(text, 'utf-8')
except (TypeError, NameError): # unicode is a default on python 3
    pass
text = unicodedata.normalize('NFD', text)
text = text.encode('ascii', 'ignore')
text = text.decode("utf-8")
0/0






import http.client
print(http.client.responses[504])
0/0


msg = """Le layer 'nodatanodata2', dans le projet fran\u00e7ais, a un nom court 'test1_fr__nodota' qui n'a pas d'\u00e9quivalance dans le projet anglais.\n
Le layer 'coco', dans le projet fran\u00e7ais, a un nom court 'test1_fr__coco' qui n'a pas d'\u00e9quivalance dans le projet anglais. """

print (msg.encode('utf-8').decode('utf-8'))

0/0


msg1 = bytes(msg,'utf-8').decode('utf-8')

print(msg1)
0/0

repl = lambda m: m.group().encode('ascii', 'strict').decode('unicode-escape')

print (msg.decode('unicode-escape').encode('utf-8'))


0/0

@dataclass
class coco:
    a: str
    b: str

@dataclass
class bozo:
    c: coco
    b: str = None

d = bozo("s", "d")
print (d)
0/0




a = [
  {
    "theme_uuid": "a78c820c-9e31-4296-bf75-a94384c1b1c5",
    "title": {
      "en": "Agriculture, construction and land use",
      "fr": "Agriculture, constructions et occupation du territoire"
    }
  },
  {
    "theme_uuid": "f0611e86-5863-4761-902e-e58baba0c110",
    "title": {
      "en": "Environment",
      "fr": "Environnement"
    }
  },
  {
    "theme_uuid": "0f1c62fc-5325-483e-b2d9-fb98cfe397f5",
    "title": {
      "en": "Fauna, flora and biodiversity",
      "fr": "Faune, flore et biodiversité"
    }
  },
  {
    "theme_uuid": "13244ca2-83b5-4ccc-bc18-689829cd5b94",
    "title": {
      "en": "Hydrography and hydrology",
      "fr": "Hydrographie et hydrologie"
    }
  },
  {
    "theme_uuid": "9b1125c2-e280-4278-89c8-a497cf300f9e",
    "title": {
      "en": "Mining, energy and forestry",
      "fr": "Mines, énergie et exploitation forestière"
    }
  },
  {
    "theme_uuid": "e7087e59-a57f-432b-81db-065f4d40e797",
    "title": {
      "en": "Science, technology and Earth observation",
      "fr": "Sciences, technologies et observation de la Terre"
    }
  },
  {
    "theme_uuid": "9c9de3c4-e0dd-4c0d-b393-fce2147bf22f",
    "title": {
      "en": "Society",
      "fr": "Société"
    }
  },
  {
    "theme_uuid": "2aaee1ae-e253-41bf-9f47-eeaa3a27e6a7",
    "title": {
      "en": "Topography, geology and natural disasters",
      "fr": "Topographie, géologie et catastrophes naturelles"
    }
  },
  {
    "theme_uuid": "40b7310c-1409-4fa8-a007-eda4fbb99fa1",
    "title": {
      "en": "Toponymy and administrative boundaries",
      "fr": "Toponymie et limites administratives"
    }
  },
  {
    "theme_uuid": "70187cc5-d8e7-4318-94e3-74e3586f8cf3",
    "title": {
      "en": "Transport and communication networks",
      "fr": "Réseaux de transport et de communication"
    }
  }
]
for item in a:
    title = item['title']
    en = title['en']
    fr = title['fr']
    print (en)
    print(fr)


0/0


url = 'https://qgis.ddr-stage.services.geo.ca/api/login'
headers = {"accept": "application/json",
           "Content-type": "application/json"}

json_doc = { "password": "Dani3Eli!",
             "username": "daniel-pilon"}
json_str = json.dumps(json_doc)  # Serialize the json document
print (json_str)
response = requests.post(url, verify=False, headers=headers, json=json_doc)
status = response.status_code
print (status)
print (response.json())
0/0

a = '1234567890'
b = a.replace(a[0:0],"."*0)
print (a)
0/0
url="https://opendata.gov.nl.ca/public/opendata/page/?page-id=datasets-spatial"
httprequest = Request(url, headers={"Accept": "text/html",'User-Agent': 'Mozilla/5.0'})

with urlopen(httprequest) as response:
    print(response.status)
    print(response.read().decode())

0/0




from pathlib import Path, PureWindowsPath
import traceback



from datetime import datetime

try:
    0/0
    raise ValueError()
except ValueError as err:
    print ("Erreur", err)

exit(0)


now = datetime.now() # current date and time

date_time = now.strftime("%Y-%m-%d %H:%M")
print("date and time:",date_time)



try:
    raise ValueError('Testing exceptions: The input is in incorrect order', 'one', 'two', 'four')
except ValueError as err:
    e = traceback.format_exc()
    print('Error: ', e)



exit(0)
# I've explicitly declared my path as being in Windows format, so I can use forward slashes in it.
filename = PureWindowsPath("source_data\\text_files\\raw_data.txt")

# Convert path to the right format for the current operating system
correct_path = os.path.join("c:\\DATA", "test", "t1.txt")
print (correct_path)
#control_file = {
#    "generic_parameters": {
#        "department":
#    },
#    "autres" : [
#        {
#         "a":"b"
#        }
#    ]
#}
0/0

p = pathlib.PurePath("C:\\DATA\\test\\t1.txt").name
#p = pathlib.PurePath("t1.txt").name
print (pathlib.PurePath.joinpath("C:\\DATA\\test", "toto.txt"))
print(p)
0/0

@dataclass
class ControlFile:
    department: str = None
    download_info_id: str = None
    email: str = None
    qgis_server_id: str = None
    download_package_name: str = ''
    core_subject_term: str = ''
    csz_collection_linked: str = ''
    in_project_filename: List[str] = None
    json_document: str = None

xf = ControlFile()
xf.emaill = 'coco'
xf.in_project_filename = ['toto']
print (xf)

folder = tempfile.TemporaryDirectory(prefix="tmp_")

print (folder)
folder = tempfile.TemporaryDirectory(prefix="tmp_")
print (folder)

print ("ttt", tempfile.mkdtemp(prefix='coco_'))


with folder as f:
    print(f" Temp dir created", f)

0/0

filenames = ["C:\\DATA\\test\\t1.txt", "C:\\DATA\\test\\t2.txt"]

with zipfile.ZipFile("C:\\DATA\\test\\multiple_files.zip", mode="w") as archive:
    for filename in filenames:
        archive.write(filename)