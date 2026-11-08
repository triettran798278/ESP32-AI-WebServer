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
Xiaozhi Assistant -> Board Type -> LILYGO T-CameraPlus-S3_V1_0_V1_1LILYGO T-CameraPlus-S3_V1_2
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> Quad Mode PSRAM
```

**: **

```bash
idf.py build
```

<a href="https://github.com/Xinyuan-LilyGO/T-CameraPlus-S3" target="_blank" title="LILYGO T-CameraPlus-S3">LILYGO T-CameraPlus-S3</a>