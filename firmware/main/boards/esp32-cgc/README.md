# address: 
- V1:[https://oshwhub.com/wdmomo/esp32-xiaozhi-kidpcb](https://oshwhub.com/wdmomo/esp32-xiaozhi-kidpcb)
- V2:[https://oshwhub.com/wdmomo/esp32-xiaozhi-kidpcb_copy](https://oshwhub.com/wdmomo/esp32-xiaozhi-kidpcb_copy)
- : [wdmomo.fun](https://www.wdmomo.fun:81/doc/index.html?file=001_%E8%AE%BE%E8%AE%A1%E9%A1%B9%E7%9B%AE/0001_%E5%B0%8F%E6%99%BAAI/002_ESP32-CGC%E5%BC%80%E5%8F%91%E6%9D%BF%E5%B0%8F%E6%99%BAAI)

# config

**config ESP32: **

```bash
idf.py set-target esp32
```

** menuconfig: **

```bash
idf.py menuconfig
```

**: **

```
Xiaozhi Assistant -> Board Type -> ESP32 CGC
```

**displaytype: **

```
Xiaozhi Assistant -> LCD Type -> "ST7735, Resolution 128*128"
```

**modify flash : **

```
Serial flasher config -> Flash size -> 4 MB
```

**modify: **

```
Partition Table -> Custom partition CSV file -> partitions/v1/4m.csv
```

**: **

```bash
idf.py build
```
