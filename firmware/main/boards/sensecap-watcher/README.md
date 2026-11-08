
## 

```bash
python scripts/release.py sensecap-watcher
```

## config

```bash
idf.py set-target esp32s3
```

**config**

```bash
idf.py menuconfig
```



```
Xiaozhi Assistant -> Board Type -> SenseCAP Watcher
```

watcher config, menuconfig .

```
CONFIG_BOARD_TYPE_SENSECAP_WATCHER=y
CONFIG_ESPTOOLPY_FLASHSIZE_32MB=y
CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions/v1/32m.csv"
CONFIG_BOOTLOADER_CACHE_32BIT_ADDR_QUAD_FLASH=y
CONFIG_ESPTOOLPY_FLASH_MODE_AUTO_DETECT=n
CONFIG_IDF_EXPERIMENTAL_FEATURES=y
```

## 

```bash
idf.py -DBOARD_NAME=sensecap-watcher build flash
```

: deviceSenseCAP (version),processaddress, Error SenseCAP Watcher device (EUI ) , deviceSenseCAPconnect SenseCraft service! , device, ! 

use

```bash
# firstly backup the factory information partition which contains the credentials for connecting the SenseCraft server
esptool.py --chip esp32s3 --baud 2000000 --before default_reset --after hard_reset --no-stub read_flash 0x9000 204800 nvsfactory.bin

```