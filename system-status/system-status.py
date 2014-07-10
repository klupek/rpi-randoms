#!/usr/bin/env python3
import pifacecad
import re
from functools import partial
from time import sleep, strftime
import threading
import subprocess
from shutil import copyfile

cad = pifacecad.PiFaceCAD()
cad.lcd.blink_off()
cad.lcd.cursor_off()
cad.lcd.clear()
cad.lcd.backlight_on()
cad.lcd.set_cursor(0,0)

def get_scanner_status():
	return False, "Scanner: idle"

FRIENDLY_NAMES = {
	'hp_LaserJet_3020': 'HP'
}

def get_printer_status(name):
#	global FRIENDLY_NAMES
	result = subprocess.check_output(['lpstat', '-l', name]).decode('utf-8')
	alerts = re.search(r'Alerts: (.+?)\n', result)
	fname = FRIENDLY_NAMES[name]
	jobs = len(re.findall(r'^[^\t]', result, flags=re.M))
	if re.search(r'Paused', subprocess.check_output(['lpstat', '-p', name]).decode('utf-8')):
		return True, fname + ': paused(%d)' % ( jobs )
	elif re.search(r'disabled', subprocess.check_output(['lpstat', '-p', name]).decode('utf-8')):
		return False, fname + ': error(%d)' % ( jobs )
	elif re.search(r'job-printing', subprocess.check_output(['lpstat', '-l', name]).decode('utf-8')):
		return False, fname + ': print(%d)' % ( jobs )
	elif alerts:
		return True, fname + ":!" + alerts.group(1)
	elif re.search(r'is idle', subprocess.check_output(['lpstat', '-p', name]).decode('utf-8')):
		return False, fname + ': idle'
	elif jobs > 0:
		return True, fname + ": %d jobs" % ( jobs )
	else:
		return True, fname + ': offline'
		

GET_IP_CMD = "hostname --all-ip-addresses"

def run_cmd(cmd):
	return subprocess.check_output(cmd, shell=True).decode('utf-8')

def get_ip():
	return False, 'IP: ' + run_cmd(GET_IP_CMD)[:-1]


BTN_RIGHT = 7
BTN_LEFT = 6
BTN_ENTER = 5

BTN_5 = 4
BTN_4 = 3
BTN_3 = 2
BTN_2 = 1
BTN_1 = 0



lines = [ get_ip, get_scanner_status ]
lines.append( partial( get_printer_status, 'hp_LaserJet_3020' ) )
#lines.append( partial( get_printer_status, 'bar' ) )

index = -1
direction = 1
def print_status():
	global index
	global direction
	global lines
	global cad
	global backlight_timer
	global backlight_timeout
	cad.lcd.set_cursor(0,0)
	printable = lines[index:index+2]
	for line in printable:
		needs_attention, output = line()
		if needs_attention: 
			backlight_timer = backlight_timeout
			cad.lcd.backlight_on()

		cad.lcd.write(output[0:15].ljust(15) + "\n")
	
printer_lock = threading.Lock()
printer_sleep = 0
backlight_timer = 10
backlight_timeout = 30
listener = pifacecad.SwitchEventListener(chip=cad)
ignore_buttons = False

def scroll_status(x, event):
	global printer_lock
	global index
	global lines
	global printer_sleep
	global backlight_timer
	global backlight_timeout
	global cad
	global ignore_buttons
	if ignore_buttons: return

	with printer_lock:
		printer_sleep = 15
		backlight_timer = backlight_timeout
		cad.lcd.backlight_on()
		index += x
		if index > len(lines)-2: index = len(lines)-2
		if index < 0: index = 0
		print ( 'event: index = %d, direction = %d, printing lines %d-%d' % (index, direction, index, index+1) )
		print_status()


def scan_single_a4(event):
	global printer_lock
	global cad
	global listener
	global ignore_buttons

	if ignore_buttons: return
	with printer_lock:
		ignore_buttons = True
		cad.lcd.backlight_on()
		cad.lcd.clear()
		cad.lcd.write('Scanning\n')
		fn = strftime('%y%m%d%H%M%S')
		cad.lcd.write(fn + '.png')
		rc = subprocess.call('scanimage --buffer-size=40960 --mode Color --resolution 150 --compression None -l 0 -t 0 -x 210 -y 297 > /tmp/' + fn + '.pnm', shell=True)
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('SCAN ERROR'.ljust(15))
			sleep(3)
		else:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('Convert'.ljust(15))
			rc = subprocess.call('convert /tmp/%s.pnm /tmp/%s.png' % (fn, fn), shell=True)
			if rc != 0:
				cad.lcd.set_cursor(0,0)
				cad.lcd.write('CONVERT ERROR'.ljust(15))
				sleep(3)
			else:
				copyfile('/tmp/%s.png' % (fn), '/mnt/storage/tmp/Scanner/%s.png' % (fn))
				cad.lcd.set_cursor(0,0)
				cad.lcd.write('Complete'.ljust(15))
				sleep(2)
		ignore_buttons = False


listener.register(BTN_RIGHT, pifacecad.IODIR_FALLING_EDGE, partial(scroll_status, 1))
listener.register(BTN_LEFT, pifacecad.IODIR_FALLING_EDGE, partial(scroll_status, -1))
listener.register(BTN_1, pifacecad.IODIR_FALLING_EDGE, scan_single_a4)
listener.activate()

while True:
	with printer_lock:
		if printer_sleep > 0: 
			printer_sleep -= 5
		else:
			index += direction
			if index > len(lines)-2 or index < 0:
				index -= direction
				direction = -direction
				index += direction
			
			print ( 'index = %d, direction = %d, printing lines %d-%d' % (index, direction, index, index+1) )
			print_status()

		if backlight_timer > 0:
			backlight_timer -= 5
			if backlight_timer == 0:
				cad.lcd.backlight_off()
	sleep(5)

