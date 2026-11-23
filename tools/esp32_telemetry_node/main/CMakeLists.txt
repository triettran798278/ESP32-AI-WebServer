foreach(var WIFI_SSID WIFI_PASS TASMOTA_TOPIC BOARD_TAG BASE_TEMP BASE_HUM)
    if(NOT DEFINED ENV{${var}} OR "$ENV{${var}}" STREQUAL "")
        message(FATAL_ERROR "Required environment variable ${var} is not set")
    endif()
endforeach()

if(DEFINED ENV{I2C_SDA} AND NOT "$ENV{I2C_SDA}" STREQUAL "")
    set(NODE_I2C_SDA_VAL "$ENV{I2C_SDA}")
else()
    set(NODE_I2C_SDA_VAL "-1")
endif()
if(DEFINED ENV{I2C_SCL} AND NOT "$ENV{I2C_SCL}" STREQUAL "")
    set(NODE_I2C_SCL_VAL "$ENV{I2C_SCL}")
else()
    set(NODE_I2C_SCL_VAL "-1")
endif()
if(DEFINED ENV{LED_GPIO} AND NOT "$ENV{LED_GPIO}" STREQUAL "")
    set(NODE_LED_GPIO_VAL "$ENV{LED_GPIO}")
else()
    set(NODE_LED_GPIO_VAL "-1")
endif()
if(DEFINED ENV{RGB_GPIO} AND NOT "$ENV{RGB_GPIO}" STREQUAL "")
    set(NODE_RGB_GPIO_VAL "$ENV{RGB_GPIO}")
else()
    set(NODE_RGB_GPIO_VAL "-1")
endif()

file(WRITE "${CMAKE_BINARY_DIR}/node_config.h"
"#pragma once\n"
"#define NODE_WIFI_SSID \"$ENV{WIFI_SSID}\"\n"
"#define NODE_WIFI_PASS \"$ENV{WIFI_PASS}\"\n"
"#define NODE_TASMOTA_TOPIC \"$ENV{TASMOTA_TOPIC}\"\n"
"#define NODE_BOARD_TAG \"$ENV{BOARD_TAG}\"\n"
"#define NODE_BASE_TEMP $ENV{BASE_TEMP}\n"
"#define NODE_BASE_HUM $ENV{BASE_HUM}\n"
"#define NODE_I2C_SDA ${NODE_I2C_SDA_VAL}\n"
"#define NODE_I2C_SCL ${NODE_I2C_SCL_VAL}\n"
"#define NODE_LED_GPIO ${NODE_LED_GPIO_VAL}\n"
"#define NODE_RGB_GPIO ${NODE_RGB_GPIO_VAL}\n"
)

idf_component_register(
    SRCS "main.c"
    INCLUDE_DIRS "." "${CMAKE_BINARY_DIR}"
    REQUIRES esp_wifi nvs_flash mqtt esp_event esp_netif esp_timer esp_driver_i2c esp_driver_gpio esp_driver_rmt
)
