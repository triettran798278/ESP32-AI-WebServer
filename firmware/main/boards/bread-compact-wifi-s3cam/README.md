ESP32S3CAMboard, bread-compact-wifi-lcdmodify
useOV2640
IO, ESP32S3USB 19 20
config.hfile

 
# config

**config ESP32S3: **

```bash
idf.py set-target esp32s3
```

** menuconfig: **

```bash
idf.py menuconfig
```

**: **

```
Xiaozhi Assistant -> Board Type ->Breadboard (WiFi) + LCD + Camera
```

**: **

```bash
idf.py build flash
```