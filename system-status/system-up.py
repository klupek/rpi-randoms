#!/usr/bin/env python3
import pifacecad
import re
from time import sleep

cad = pifacecad.PiFaceCAD()
cad.lcd.blink_off()
cad.lcd.cursor_off()
cad.lcd.clear()
cad.lcd.backlight_on()
cad.lcd.set_cursor(0,0)
cad.lcd.write('System is UP\nStatus loading.')
sleep(3)
cad.lcd.backlight_off()

