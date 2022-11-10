import zipfile

filenames = ["C:\\DATA\\test\\t1.txt", "C:\\DATA\\test\\t2.txt"]

with zipfile.ZipFile("C:\\DATA\\test\\multiple_files.zip", mode="w") as archive:
    for filename in filenames:
        archive.write(filename)