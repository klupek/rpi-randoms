#!/usr/bin/env python3
import pifacecad
import re
from functools import partial
from time import sleep, strftime
import time
import threading
import queue
import subprocess
from shutil import copyfile

def init():
	cad = pifacecad.PiFaceCAD()
	cad.lcd.blink_off()
	cad.lcd.cursor_off()
	cad.lcd.clear()
	cad.lcd.backlight_on()
	cad.lcd.set_cursor(0,0)
	return cad

FRIENDLY_NAMES = {
	'hp_LaserJet_3020': 'HP'
}

def get_scanner_status():
	return False, "Scanner: idle"

def get_printer_status(name):
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
		

def run_cmd(cmd):
	return subprocess.check_output(cmd, shell=True).decode('utf-8')

def get_ip():
	return False, 'IP: ' + run_cmd('hostname --all-ip-addresses')[:-1]


backlight_timer = time.time()+15
backlight_timeout = 30

def print_status(index, direction, lines, cad):
	global backlight_timer
	global backlight_timeout
	cad.lcd.set_cursor(0,0)
	printable = lines[index:index+2]
	for line in printable:
		needs_attention, output = line()
		if needs_attention: 
			backlight_timer = backlight_timeout
			cad.lcd.backlight_on()

		cad.lcd.write(output[0:15].ljust(16) + "\n")

BTN_RIGHT = 7
BTN_LEFT = 6
BTN_ENTER = 5

BTN_5 = 4
BTN_4 = 3
BTN_3 = 2
BTN_2 = 1
BTN_1 = 0

event_queue = queue.Queue()

def push_button_event(event_queue, i, event):
	event_queue.put(i, block=False)
	
cad = init()
listener = pifacecad.SwitchEventListener(chip=cad)
for i in range(0, 8):
	listener.register(i, pifacecad.IODIR_FALLING_EDGE, partial(push_button_event, event_queue, i))

listener.activate()

scroll_interval = 5
scroll_next_refresh = time.time()

lines = [ get_ip, get_scanner_status, partial( get_printer_status, 'hp_LaserJet_3020' ) ]
index = -1
direction = 1

def scroll_status(x, lines, cad):
	global index
	global backlight_timer
	global backlight_timeout
	global scroll_next_refresh 

	scroll_next_refresh  = time.time()+15
	backlight_timer = time.time()+backlight_timeout
	cad.lcd.backlight_on()
	index += x
	if index > len(lines)-2: index = len(lines)-2
	if index < 0: index = 0

def scan_single_a4(cad):
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
	cad.lcd.backlight_off()

def scan_autocrop(cad):
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
		cad.lcd.write('Convert + trim'.ljust(15))
		rc = subprocess.call('convert /tmp/%s.pnm -fuzz 30%% -trim /tmp/%s.png' % (fn, fn), shell=True)
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('CONVERT ERROR'.ljust(15))
			sleep(3)
		else:
			copyfile('/tmp/%s.png' % (fn), '/mnt/storage/tmp/Scanner/%s.png' % (fn))
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('Complete'.ljust(15))
			sleep(2)
	cad.lcd.backlight_off()


while True:
	event = None
	try:
		event = event_queue.get(block=False)
	except queue.Empty:
		pass

	if event != None:
		if event == BTN_RIGHT:
			scroll_status(1, lines, cad)
			print_status(index, direction,lines,cad)
		elif event == BTN_LEFT:
			scroll_status(-1, lines, cad)
			print_status(index, direction,lines,cad)
		elif event == BTN_1:
			scan_single_a4(cad)
		elif event == BTN_2:
			scan_autocrop(cad)
		else:
			pass

	elif scroll_next_refresh <= time.time():
		scroll_next_refresh = time.time() + scroll_interval
		index += direction
		if index > len(lines)-2 or index < 0:
			index -= direction
			direction = -direction
			index += direction
		print_status(index,direction,lines,cad)
	
	if backlight_timer != 0 and backlight_timer <= time.time():
		cad.lcd.backlight_off()
		backlight_timer = 0

		

	sleep(0.2)



	



