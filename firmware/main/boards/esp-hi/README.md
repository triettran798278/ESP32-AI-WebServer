# ESP-Hi

## 

<div align="center">
    <a href="https://oshwhub.com/esp-college/esp-hi"><b>  </b></a>
    |
    <a href="https://www.bilibili.com/video/BV1BHJtz6E2S"><b> Bilibili </b></a>
</div>

ESP-Hi  ESP Friends  ESP32C3 **** AI . ESP-Hi 0.96, , ****.  ESP32-C3 , , ,  Flash , ****. [](https://oshwhub.com/esp-college/esp-hi). 

## WebUI

ESP-Hi x  WebUI,  ESP-Hi connect Wi-Fi ,  `http://esp-hi.local/` use. 

,  `ESP_HI_WEB_CONTROL_ENABLED`,  `Component config` → `Servo Dog Configuration` → `Web Control` → `Enable ESP-HI Web Control`. 

## config, 

 ESP-Hi config sdkconfig , use. 

****

```bash
python ./scripts/release.py esp-hi
```

,  `esp-hi/config.json` modify menuconfig . 

****

```bash
idf.py flash
```


> [!TIP]
>
> ** ESP-Hi  USB Type-C api**, connect (/) . , : 
>
> ****
>
> 1. disconnect ESP-Hi , , connect. 
> 2.  ESP-Hi buttonconnect. 
> 
> , ESP-Hi (ESP32C3) , use. , . 
>
> ** log**
>
> set `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y`,  `Component config` → `ESP System Settings` → `Channel for console output`  `USB Serial/JTAG Controller`. . 
