
[ ESP32-C6-Touch-AMOLED-1.43](https://www.waveshare.net/shop/ESP32-C6-Touch-AMOLED-1.43.htm)
[ ESP32-C6-Touch-AMOLED-1.43-B](https://www.waveshare.net/shop/ESP32-C6-Touch-AMOLED-1.43-B.htm)

# config

****

```bash
git clone https://github.com/78/xiaozhi-esp32.git
```

****

```bash
cd xiaozhi-esp32
```

**config ESP32C6**

```bash
idf.py set-target esp32c6
```

** menuconfig**

```bash
idf.py menuconfig
```

****

```bash
Xiaozhi Assistant -> Board Type -> Waveshare ESP32-C6-Touch-AMOLED-1.43
```

****

```ba
idf.py build
```

****

```bash
idf.py build flash monitor
```

