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
Xiaozhi Assistant -> Board Type -> AtomS3R + Echo Base
```

**modify flash : **

```
Serial flasher config -> Flash size -> 8 MB
```

**modify: **

```
Partition Table -> Custom partition CSV file -> partitions/v1/8m.csv
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> Octal Mode PSRAM
```

**: **

```bash
idf.py build
```