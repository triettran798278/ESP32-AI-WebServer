# EchoEar 

## 

<div align="center">
    <a href="https://oshwhub.com/esp-college/echoear"><b>  </b></a>
</div>

EchoEar  AI ,  ESP32-S3-WROOM-1 , 1.85  QSPI , , supportvoice. [](https://oshwhub.com/esp-college/echoear). 

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

### config
- `Xiaozhi Assistant` → `Board Type` →  `EchoEar`

### config
- `Partition Table` → `Partition Table` →  `Custom partition table CSV`
- `Partition Table` → `Custom partition CSV file` →  `partitions/v1/16m_echoear.csv`

### UI

EchoEar supportUI, modify: 

####  ()
```c
#define USE_LVGL_DEFAULT    0
```
- ****: use `EmoteDisplay` 
- ****: support, , status
- ****: , 
- ****: `anim::EmoteDisplay` + `anim::EmoteEngine`

#### LVGLdefault
```c
#define USE_LVGL_DEFAULT    1
```
- ****: useLVGL
- ****: 
- ****: GUI
- ****: `SpiLcdDisplay`

#### modify
1.  `main/boards/echoear/EchoEar.cc` file
2. 29: `#define USE_LVGL_DEFAULT    0`
3. modify (01) 
4. 

> ****: EchoEar use16MB Flash, useconfig, OTAupdate, file. 

 `S` ,  `Q` exit. 

****

```bash
idf.py build
```

****

 EchoEar connect, ****, : 

```bash
idf.py flash
```