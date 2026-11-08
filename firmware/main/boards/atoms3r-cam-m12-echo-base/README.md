# AtomS3R CAM/M12 + Echo Base

## 

<div align="center">
    <a href="https://docs.m5stack.com/zh_CN/core/AtomS3R%20Cam"><b> AtomS3R CAM  </b></a>
    |
    <a href="https://docs.m5stack.com/zh_CN/core/AtomS3R-M12"><b> AtomS3R M12  </b></a>
    |
    <a href="https://docs.m5stack.com/zh_CN/atom/Atomic%20Echo%20Base"><b> Echo Base  </b></a>
</div>

AtomS3R CAM, AtomS3R M12  M5Stack  ESP32-S3-PICO-1-N8R8 , . Atomic Echo Base  M5 Atom hostvoice,  ES8311 audio, MEMS microphone NS4150B . 

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

- `Xiaozhi Assistant` → `Board Type` →  `AtomS3R CAM/M12 + Echo Base`
- `Xiaozhi Assistant` → `IoT Protocol` →  `MCP` 
- `Partition Table` → `Custom partition CSV file` → delete,  `partitions/v1/8m.csv`
- `Serial flasher config` → `Flash size` →  `8 MB`

 `S` ,  `Q` exit. 

****

```bash
idf.py build
```

****

 AtomS3R CAM/M12 connect,  RESET ,  RESET . 

```bash
idf.py flash
```

,  RESET buttonRestart. 
