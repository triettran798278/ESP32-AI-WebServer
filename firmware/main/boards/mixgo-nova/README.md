# Mixgo_Nova(YuanKong Youth) board

<img src="https://mixly.cn/public/icon/2024/6/09705006c1c643beb96338791ee1dea0_m.png" alt="Mixgo_Nova" width="200"/>

&zwnj;**[Mixgo_Nova](https://mixly.cn/fredqian/mixgo_nova)**&zwnj; , board, , support (Mixly) voice, . 

---

## 🛠️  config

**ES8374 CODE MIC: **

```
managed_components\espressif__esp_codec_dev\device\es8374

static int es8374_config_adc_input(audio_codec_es8374_t *codec, es_adc_input_t input)
{
    int ret = 0;
    int reg = 0;
    ret |= es8374_read_reg(codec, 0x21, &reg);
    if (ret == 0) {
        reg = (reg & 0xcf) | 0x24;
        ret |= es8374_write_reg(codec, 0x21, reg);
    }
    return ret;
}

PS: L386 reg = (reg & 0xcf) | 0x14;  reg = (reg & 0xcf) | 0x24;
```

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
Xiaozhi Assistant -> Board Type -> YuanKong Youth
```

**modify psram config: **

```
Component config -> ESP PSRAM -> SPI RAM config -> Mode (QUAD/OCT) -> QUAD Mode PSRAM
```

**modify Flash config: **

```
Serial flasher config -> Flash size -> 8 MB
Partition Table -> Custom partition CSV file -> partitions/v1/8m.csv
```

**: **

```bash
idf.py build
```

**BIN: **

```bash
idf.py merge-bin -o xiaozhi-nova.bin -f raw
```