#pragma once

#include <libs/gif/lv_gif.h>

#include "display/lcd_display.h"
#include "otto_emoji_gif.h"

/**
 * @brief OttoGIF
 * LcdDisplay, GIFsupport
 */
class OttoEmojiDisplay : public SpiLcdDisplay {
public:
    /**
     * @brief , paramSpiLcdDisplay
     */
    OttoEmojiDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel, int width,
                     int height, int offset_x, int offset_y, bool mirror_x, bool mirror_y,
                     bool swap_xy, DisplayFonts fonts);

    virtual ~OttoEmojiDisplay() = default;

    // set
    virtual void SetEmotion(const char* emotion) override;

    // messageset
    virtual void SetChatMessage(const char* role, const char* content) override;

    // SetIcon
    virtual void SetIcon(const char* icon) override;

private:
    void SetupGifContainer();

    lv_obj_t* emotion_gif_;  ///< GIF

    struct EmotionMap {
        const char* name;
        const lv_img_dsc_t* gif;
    };

    static const EmotionMap emotion_maps_[];
};