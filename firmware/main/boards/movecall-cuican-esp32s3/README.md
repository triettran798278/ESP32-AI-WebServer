# ESP32-S3 config

## 

### set

```bash
idf.py set-target esp32s3
```

### config: 

```bash
idf.py menuconfig
```
### Flash config:

```
Serial flasher config -> Flash size -> 8 MB
```

### config: 

```
Partition Table -> Custom partition CSV file -> partitions/v1/8m.csv
```

### board: 

```
Xiaozhi Assistant -> Board Type -> Movecall CuiCan CuiCan AI Pendant
```

### : 

```
Component config → Compiler options → Optimization Level → Optimize for size (-Os)
```

### : 

```bash
idf.py build
```