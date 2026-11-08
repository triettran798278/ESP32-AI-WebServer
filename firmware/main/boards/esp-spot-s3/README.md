# ESP-Spot S3

## 

<div align="center">
    <a href="https://oshwhub.com/esp-college/esp-spot"><b>  </b></a>
    |
    <a href="https://www.bilibili.com/video/BV1ekRAYVEZ1/"><b> Bilibili Demo </b></a>
</div>

ESP-Spot  ESP Friends voice, microphone, speaker, IMU , use. ESP-Spot display,  RGB button. [](https://oshwhub.com/esp-college/esp-spot). 

ESP-Spot  ESP32-S3-WROOM-1-N16R8 . use Flash, modifyparam. 


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

- `Xiaozhi Assistant` → `Board Type` →  `ESP-Spot-S3`

 `S` ,  `Q` exit. 

****

```bash
idf.py build
```

****

```bash
idf.py flash
```

> [!TIP]
>
> ** ESP-Spot , **
> 1. ; 
> 2.  PCB ; 
> 3.  <kbd>BOOT</kbd>  PCB , ; 
> 
> ,  ESP-Spot . ,  PCB . 
