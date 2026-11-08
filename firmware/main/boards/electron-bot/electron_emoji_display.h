#pragma once

#include <libs/gif/lv_gif.h>

#include "display/lcd_display.h"

// Electron BotGIF - useOtto6
LV_IMAGE_DECLARE(staticstate);  // status/
LV_IMAGE_DECLARE(sad);          // 
LV_IMAGE_DECLARE(happy);        // 
LV_IMAGE_DECLARE(scare);        // /
LV_IMAGE_DECLARE(buxue);        // /
LV_IMAGE_DECLARE(anger);        // 

/**
 * @brief Electron Bot GIF
 * LcdDisplay, GIFsupport
 */
class ElectronEmojiDisplay : public SpiLcdDisplay {
public:
    /**
     * @brief , paramSpiLcdDisplay
     */
    ElectronEmojiDisplay(esp_lcd_panel_io_handle_t panel_io, esp_lcd_panel_handle_t panel,
                         int width, int height, int offset_x, int offset_y, bool mirror_x,
                         bool mirror_y, bool swap_xy, DisplayFonts fonts);

    virtual ~ElectronEmojiDisplay() = default;

    // set
    virtual void SetEmotion(const char* emotion) override;

    // messageset
    virtual void SetChatMessage(const char* role, const char* content) override;

    // set
    virtual void SetIcon(const char* icon) override;

private:
    void SetupGifContainer();

    lv_obj_t* emotion_gif_;  ///< GIF

    struct EmotionMap {
        const char* name;
        const lv_image_dsc_t* gif;
    };

    static const EmotionMap emotion_maps_[];
};