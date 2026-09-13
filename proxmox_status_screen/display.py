# SPDX-License-Identifier: GPL-3.0-or-later
#
# Display wrapper around the vendored LCD drivers.
#
# Adapted from turing-smart-screen-python's library/display.py, but decoupled from
# the upstream config module: everything is read from AppConfig instead.

from typing import Any, Dict

from proxmox_status_screen.config import AppConfig
from proxmox_status_screen.log import logger

# Base classes / orientation enum live in the vendored driver
from display_driver.lcd.lcd_comm import Orientation


def _get_theme_orientation(theme_data: Dict[str, Any], reverse: bool) -> Orientation:
    orientation = str(theme_data.get("display", {}).get("orientation", "portrait")).lower()
    if orientation == "landscape":
        return Orientation.REVERSE_LANDSCAPE if reverse else Orientation.LANDSCAPE
    return Orientation.REVERSE_PORTRAIT if reverse else Orientation.PORTRAIT


def _get_theme_size(theme_data: Dict[str, Any]) -> tuple:
    size = str(theme_data.get("display", {}).get("size", '3.5"'))
    sizes = {
        '0.96"': (80, 160),
        '2.1"': (480, 480),
        '2.8"': (480, 480),
        '3.5"': (320, 480),
        '4.6"': (320, 960),
        '5"': (480, 800),
        '5.2"': (720, 1280),
        '8"': (800, 1280),
        '8.8"': (480, 1920),
        '9.2"': (480, 1920),
        '12.3"': (720, 1920),
    }
    if size not in sizes:
        logger.warning("Unknown display size '%s' in theme, defaulting to 3.5\"", size)
        return 320, 480
    return sizes[size]


class Display:
    def __init__(self, config: AppConfig, update_queue=None):
        self.config = config
        self.lcd = self._create_lcd(update_queue)

    def _create_lcd(self, update_queue):
        revision = self.config.display.revision
        com_port = self.config.display.com_port
        width, height = _get_theme_size(self.config.theme_data)

        # Imports are local so that unused hardware revisions (and their optional
        # dependencies, e.g. pyusb/pycryptodome for TUR_USB) are not required.
        if revision == "A":
            from display_driver.lcd.lcd_comm_rev_a import LcdCommRevA

            logger.info("Selected display revision A")
            return LcdCommRevA(com_port=com_port, update_queue=update_queue)
        if revision == "B":
            from display_driver.lcd.lcd_comm_rev_b import LcdCommRevB

            logger.info("Selected display revision B")
            return LcdCommRevB(com_port=com_port, update_queue=update_queue)
        if revision == "C":
            from display_driver.lcd.lcd_comm_rev_c import LcdCommRevC

            logger.info("Selected display revision C")
            return LcdCommRevC(
                com_port=com_port,
                update_queue=update_queue,
                display_width=width,
                display_height=height,
            )
        if revision == "D":
            from display_driver.lcd.lcd_comm_rev_d import LcdCommRevD

            logger.info("Selected display revision D")
            return LcdCommRevD(com_port=com_port, update_queue=update_queue)
        if revision == "TUR_USB":
            from display_driver.lcd.lcd_comm_turing_usb import LcdCommTuringUSB

            logger.info("Selected display revision TUR_USB")
            return LcdCommTuringUSB()
        if revision == "WEACT_A":
            from display_driver.lcd.lcd_comm_weact_a import LcdCommWeActA

            logger.info("Selected display revision WeAct A")
            return LcdCommWeActA(com_port=com_port, update_queue=update_queue)
        if revision == "WEACT_B":
            from display_driver.lcd.lcd_comm_weact_b import LcdCommWeActB

            logger.info("Selected display revision WeAct B")
            return LcdCommWeActB(com_port=com_port, update_queue=update_queue)
        if revision == "SIMU":
            from display_driver.lcd.lcd_simulated import LcdSimulated

            logger.info("Selected simulated display (screencap.png)")
            return LcdSimulated(
                display_width=width,
                display_height=height,
                webserver_port=self.config.display.simu_webserver_port,
                enable_webserver=self.config.display.simu_webserver,
            )

        raise ValueError(
            f"Unknown display revision '{revision}' (expected A/B/C/D/TUR_USB/WEACT_A/WEACT_B/SIMU)"
        )

    def initialize_display(self) -> None:
        if self.config.display.reset_on_startup:
            self.lcd.Reset()
        self.lcd.InitializeComm()
        self.turn_on()
        self.lcd.SetOrientation(
            _get_theme_orientation(self.config.theme_data, self.config.display.reverse)
        )

    def turn_on(self) -> None:
        self.lcd.ScreenOn()
        self.lcd.SetBrightness(self.config.display.brightness)
        rgb_led = self.config.theme_data.get("display", {}).get("rgb_led", (255, 255, 255))
        self.lcd.SetBackplateLedColor(rgb_led)

    def turn_off(self) -> None:
        try:
            self.lcd.ScreenOff()
            self.lcd.SetBackplateLedColor(led_color=(0, 0, 0))
        except Exception:  # noqa: BLE001 - best effort on shutdown
            logger.debug("Failed to turn display off", exc_info=True)

    def display_static_images(self) -> None:
        for name, image in (self.config.theme_data.get("static_images") or {}).items():
            logger.debug("Drawing static image: %s", name)
            self.lcd.DisplayBitmap(
                bitmap_path=self.config.theme_asset(image.get("path")),
                x=image.get("x", 0),
                y=image.get("y", 0),
                width=image.get("width", 0),
                height=image.get("height", 0),
            )

    def display_static_text(self) -> None:
        for name, text in (self.config.theme_data.get("static_text") or {}).items():
            logger.debug("Drawing static text: %s", name)
            self.lcd.DisplayText(
                text=str(text.get("text", "")),
                x=text.get("x", 0),
                y=text.get("y", 0),
                width=text.get("width", 0),
                height=text.get("height", 0),
                font=self.config.font_path(
                    text.get("font", "roboto-mono/RobotoMono-Regular.ttf")
                ),
                font_size=text.get("font_size", 10),
                font_color=text.get("font_color", (0, 0, 0)),
                background_color=text.get("background_color", (255, 255, 255)),
                background_image=self.config.theme_asset(text.get("background_image")),
                align=text.get("align", "left"),
                anchor=text.get("anchor", "lt"),
            )
