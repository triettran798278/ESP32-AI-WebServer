# use 

* [M5Stack Tab5 docs](https://docs.m5stack.com/zh_CN/core/Tab5)

## 

 [](https://pan.baidu.com/s/1dgbUQtMyVLSCSBJLHARpwQ?pwd=1234) : 1234 

```shell
esptool.py --chip esp32p4 -p /dev/ttyACM0 -b 460800 --before=default_reset --after=hard_reset write_flash --flash_mode dio --flash_freq 80m --flash_size 16MB 0x00 tab5_xiaozhi_v1_addr0.bin 
```

## use

* idf version: v5.5-dev

1. set esp32p4

```shell
idf.py set-target esp32p4 
```

2. modifyconfig 

```shell
cp main/boards/m5stack-tab5/sdkconfig.tab5 sdkconfig
```

3. 

```shell
idf.py build flash monitor
```

> [!NOTE]
> :  ( 2 ) ,  LED start, . 


## log

@2025/05/17 

1. listening... getvoice???
2. 
3. volume
 
## TODO
