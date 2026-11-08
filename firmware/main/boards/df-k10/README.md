# DFRobot Unihiker K10

## config
* A: -/, 1s-volume
* B: -/, 1s-volume

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
Xiaozhi Assistant -> Board Type -> DFRobot Unihiker K10
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> Octal Mode PSRAM
```

**: **

```bash
idf.py build
```