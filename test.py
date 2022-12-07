import zipfile
import tempfile
from dataclasses import dataclass
from typing import List
import pathlib
import os
import urllib
import requests
from urllib.request import urlopen, Request


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