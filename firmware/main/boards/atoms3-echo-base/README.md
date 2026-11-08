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
Xiaozhi Assistant -> Board Type -> AtomS3 + Echo Base
```

**closevoice: **

```
Xiaozhi Assistant -> [ ] voiceaudioprocess -> Unselect
```

**modify flash : **

```
Serial flasher config -> Flash size -> 8 MB
```

**modify: **

```
Partition Table -> Custom partition CSV file -> partitions/v1/8m.csv
```

**close PSRAM: **

```
Component config -> ESP PSRAM -> [ ] Support for external, SPI-connected RAM -> Unselect
```

**: **

```bash
idf.py build
```