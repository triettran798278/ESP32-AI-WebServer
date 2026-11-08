# microphone, 20257 (JC3636W518) microphone, display, 2528userI2S Type PDM,

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
Xiaozhi Assistant -> Board Type -> TaiJi XiaoPaiesp32s3

Xiaozhi Assistant -> taiji-pi-S3 I2S Type -> I2S Type PDM
```

**modifyPSRAMconfig: **

```
component config -> ESP PSRAM -> SPI RAM config -> Try to allocate memories of WiFi and LWIP in SPIRAM firstly. If failed, allocate internal memory

```

**: **

```bash
idf.py build
```
