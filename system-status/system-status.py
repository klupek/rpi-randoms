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
import os

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
		return True, fname + ': print(%d)' % ( jobs )
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
			backlight_timer = time.time()+backlight_timeout
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

lines = [ get_ip, partial( get_printer_status, 'hp_LaserJet_3020' ) ]
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

def scan_single_document(cad, msg, submsg, filename):
	cad.lcd.clear()
	cad.lcd.write(msg.ljust(16) + '\n')
	cad.lcd.write(submsg.ljust(16))
	rc = subprocess.call('scanimage --buffer-size=40960 --mode Color --resolution 150 --compression None -l 0 -t 0 -x 210 -y 297 > ' + filename, shell=True)
	if rc != 0:
		cad.lcd.set_cursor(0,0)
		cad.lcd.write('SCAN ERROR'.ljust(15))
		sleep(3)
		return False
	else:
		return True

def scan_single_a4(cad):
	cad.lcd.backlight_on()	
	fn = strftime('%y%m%d%H%M%S')

	if scan_single_document(cad, "Scanning", fn + '.png', '/tmp/%s.pnm' % ( fn )):
		cad.lcd.set_cursor(0,0)
		cad.lcd.write('Convert'.ljust(15))
		rc = subprocess.call('convert /tmp/%s.pnm /tmp/%s.png' % (fn, fn), shell=True)
		os.unlink('/tmp/%s.pnm' % (fn))
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('CONVERT ERROR'.ljust(15))
			sleep(3)
		else:
			copyfile('/tmp/%s.png' % (fn), '/mnt/storage/tmp/Scanner/%s.png' % (fn))
			os.unlink('/tmp/%s.png' % (fn))
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('Complete'.ljust(15))
			sleep(2)
	cad.lcd.backlight_off()

def clear_queue(eq):
	try:
		while not eq.empty():
			eq.get(block=False)
	except:
		pass


def scan_documents_impl(cad, eq):
	fn = strftime('%y%m%d%H%M%S')
	index = 1
	keepgoing = True

	while keepgoing:
		pagefn = "%s-%d"  % (fn, index)
		if scan_single_document(cad, "Scan page %d" % (index), pagefn, '/tmp/' + pagefn + '.pnm'):
			cad.lcd.clear()
			cad.lcd.write('%d pages scanned\n' % (index))
			cad.lcd.write('Continue, stop?')
			for event in iter(eq.get, b''):
				if event == BTN_5:
					keepgoing = False
					break
				elif event == BTN_3 or event == BTN_4:
					index += 1
					break
				else: 
					pass
			clear_queue(eq)
		else:
			index -= 1
	return index, fn

def scan_documents(cad, eq):
	cad.lcd.backlight_on()
	index, fn = scan_documents_impl(cad, eq)
	
	for i in range(1, index+1):
		cad.lcd.clear()
		cad.lcd.write('Convert %d/%d\n' % (i, index))
		pagefn = '%s-%d' % (fn, i)
		cad.lcd.write(pagefn)
		
		rc = subprocess.call('convert -density 150 /tmp/%s.pnm /tmp/%s.png' % (pagefn, pagefn), shell=True)
		os.unlink('/tmp/%s.pnm' % (pagefn))
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('CONVERT ERROR'.ljust(15))
			sleep(3)
			return
		else:
			copyfile('/tmp/%s.png' % (pagefn), '/mnt/storage/tmp/Scanner/%s.png' % (pagefn))
			os.unlink('/tmp/%s.png' % (pagefn))
	
	cad.lcd.clear()
	cad.lcd.write('Complete\n')
	cad.lcd.write('%d documents' % (index))
	sleep(2)
	cad.lcd.backlight_off()
	return index

def scan_pdf(cad, eq):
	cad.lcd.backlight_on()
	index, fn = scan_documents_impl(cad, eq)
	
	for i in range(1, index+1):
		cad.lcd.clear()
		cad.lcd.write('Convert %d/%d\n' % (i, index))
		pagefn = '%s-%d' % (fn, i)
		cad.lcd.write(pagefn)
		
		rc = subprocess.call('convert -quality 85 -density 150 /tmp/%s.pnm /tmp/%s.jpg' % (pagefn, pagefn), shell=True)
		os.unlink('/tmp/%s.pnm' % (pagefn))
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('CONVERT ERROR'.ljust(15))
			sleep(3)
			return
	
	cad.lcd.clear()
	cad.lcd.write('%d pages ->\n' % (index))
	cad.lcd.write(fn + '.pdf')
	cmd = "convert " + " ".join(map((lambda x: "/tmp/%s-%d.jpg" % (fn, x)),range(1,index+1))) + ' /mnt/storage/tmp/Scanner/' + fn + '.pdf'
	rc = subprocess.call(cmd, shell=True)
	for i in range(1, index+1):
		pagefn = '/tmp/%s-%d.jpg' % (fn, i)
		os.unlink(pagefn)
	
	cad.lcd.clear()
	cad.lcd.write('Complete\n')
	cad.lcd.write('%d documents' % (index))
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
		os.unlink('/tmp/%s.pnm' % (fn))
		if rc != 0:
			cad.lcd.set_cursor(0,0)
			cad.lcd.write('CONVERT ERROR'.ljust(15))
			sleep(3)
		else:
			copyfile('/tmp/%s.png' % (fn), '/mnt/storage/tmp/Scanner/%s.png' % (fn))
			os.unlink('/tmp/%s.png' % (fn))
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

	if event is not None:
		if event == BTN_RIGHT:
			scroll_status(1, lines, cad)
			print_status(index, direction,lines,cad)
		elif event == BTN_LEFT:
			scroll_status(-1, lines, cad)
			print_status(index, direction,lines,cad)
		elif event == BTN_1:
			scan_single_a4(cad)
			clear_queue(event_queue)
		elif event == BTN_2:
			scan_autocrop(cad)
			clear_queue(event_queue)
		elif event == BTN_3:
			scan_documents(cad, event_queue)
			clear_queue(event_queue)
		elif event == BTN_4:
			scan_pdf(cad, event_queue)
			clear_queue(event_queue)
		else:
			pass

	elif scroll_next_refresh <= time.time():
		if backlight_timer > time.time():
			scroll_next_refresh = time.time() + 1
		else:
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



	



