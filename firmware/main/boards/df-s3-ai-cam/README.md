# DFRobot ESP32-S3 AI Camera Module

## 
ESP32-S3 AI CAMESP32-S3, videoimageprocessvoice, video, image, voiceAI. 
![](https://ws.dfrobot.com.cn/FsTrGbrX2NZAwzWS8OSQGOGikuYA)

[](https://wiki.dfrobot.com.cn/SKU_DFR1154_ESP32_S3_AI_CAM)

[](https://www.bilibili.com/video/BV1ktjSzNEUU/)

* usePDMmicrophone
*  OV3660 

## config
* BOOT: -/

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
Xiaozhi Assistant -> Board Type -> DFRobot ESP32-S3 AI Camera Module
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> Octal Mode PSRAM
```

**modify WiFi   10: **

```
Component config -> PHY -> (10)Max WiFi TX power (dBm)
```

**: **

```bash
idf.py build
```