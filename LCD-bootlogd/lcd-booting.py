#!/usr/bin/env python3
import pifacecad
import re


cad = pifacecad.PiFaceCAD()
cad.lcd.blink_off()
cad.lcd.cursor_off()
cad.lcd.clear()
cad.lcd.backlight_on()
cad.lcd.set_cursor(0,0)
cad.lcd.write('Booting...')

FIFO = '/piface/lcd-booting.input'
while True:
	with open(FIFO) as fifo:
		line = fifo.readline()
		line = re.sub(r'^.+?:.+?:.+?:( \[\.+\] )?','', line) # remove timestamp and [...] trash
		line = re.sub(r'\^\[\[\?\d+[lcmh]|\^\[\[\d+[Gm;]\[?(\d+m)?|\^\[\d+', '', line) # remove control chars
		cad.lcd.set_cursor(0,1)
		cad.lcd.write(line[0:16])
