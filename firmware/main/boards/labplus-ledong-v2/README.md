# labplus V2

## 
    : ESP32-S3 8MB psram 16MB flash	
    :
        button(A B) 	IO0 IO46
        	IIC
        6	IIC
        	IIC
        	IO6
         IIC P Y T H O N
        	IIC
    :
        	IO21
        RGB	IO16
         es8388	IIC	
        TFT LCD	jd9853 SPI
        	IIC


## config

### config ESP32S3, USB JTAG

```bash
idf.py set-target esp32s3
```

### menuconfigconfig

```bash
idf.py menuconfig
```

***: ***

```
Xiaozhi Assistant -> Board Type -> labplus Ledong_v2 board
```

***modify psram config: ***

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> quad Mode PSRAM
```

**: **

```bash
idf.py build
```

**: **

```bash
esptool.py -p /dev/ttyACM0 -b 1500000 --before default_reset --after hard_reset --chip esp32s3 write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB 0x0 bootloader/bootloader.bin 0x100000 xiaozhi.bin 0x8000 partition_table/partition-table.bin 0xd000 ota_data_initial.bin 0x10000 srmodels/srmodels.bin 
```

## use

### config
* A: -/
