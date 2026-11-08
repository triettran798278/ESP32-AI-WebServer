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
Xiaozhi Assistant -> Board Type ->  ESP32 DevKit
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