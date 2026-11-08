# AtomEchoS3R
## 

AtomEchoS3R  M5Stack  ESP32-S3-PICO-1-N8R8 ,  ES8311 audio, MEMS microphone NS4150B . 

**display, **, usevoice. , use `idf.py monitor`  log status. 

## config, 

**config ESP32S3**

```bash
idf.py set-target esp32s3
```

** menuconfig config**

```bash
idf.py menuconfig
```

config: 

- `Xiaozhi Assistant` → `Board Type` →  `AtomEchoS3R`
- `Partition Table` → `Custom partition CSV file` → delete,  `partitions/v1/8m.csv`
- `Serial flasher config` → `Flash size` →  `8 MB`
- `Component config` → `ESP PSRAM` → `Support for external, SPI-connected RAM` → `SPI RAM config` →  `Octal Mode PSRAM`

 `S` ,  `Q` exit. 

****

```bash
idf.py build
```

****

 AtomEchoS3R connect,  RESET ,  RESET . 

```bash
idf.py flash
```

,  RESET buttonRestartdevice. 
