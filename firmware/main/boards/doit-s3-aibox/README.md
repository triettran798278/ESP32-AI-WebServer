# SiBoAI

* usePDMmicrophone
* useLED

## config
* BUTTON3: -/
* BUTTON1: volume+
* BUTTON2: volume-

## config

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
Xiaozhi Assistant -> Board Type -> SiBoAI
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> Octal Mode PSRAM
```

**: **

```bash
idf.py build
```