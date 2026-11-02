"""James's contacts and the Mac's Messages app, for a handwritten note he has confirmed on his page.

Names, numbers and paths reach AppleScript only as arguments, never as script text. The first use asks macOS for
permission to control Contacts and Messages; until James allows it these calls time out and nothing is sent.
"""
import os
import re
import shutil
import subprocess

# Messages reads attachments it can reach; a copy in Pictures is also James's record of what went out.
SENT = os.path.expanduser('~/Pictures/Notebook notes')

LOOKUP = '''on run argv
	set q to item 1 of argv
	set out to ""
	tell application "Contacts"
		if q is "me" then
			set found to {my card}
		else
			set found to every person whose first name is q or nickname is q or name is q
			if found is {} then set found to every person whose name contains q
		end if
		repeat with p in found
			repeat with ph in phones of p
				set out to out & (name of p) & tab & (label of ph) & tab & (value of ph) & linefeed
			end repeat
		end repeat
	end tell
	return out
end run'''

SEND = '''on run argv
	set {svc, handle, f} to argv
	tell application "Messages"
		if svc is "sms" then
			set acct to first account whose service type is SMS and enabled is true
		else
			set acct to first account whose service type is iMessage and enabled is true
		end if
		send (POSIX file f) to participant handle of acct
	end tell
end run'''


def _osascript(script, *args, timeout=30):
    r = subprocess.run(['osascript', '-', *args], input=script, capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise OSError(r.stderr.strip()[-200:] or 'osascript failed')
    return r.stdout


def lookup(name):
    """[(full name, number)] for a name as written (or "me"), one number per person: a mobile or iPhone one first."""
    people = {}
    for line in _osascript(LOOKUP, name).splitlines():
        full, label, number = (line.split('\t') + ['', ''])[:3]
        if not re.search(r'\d{7}', re.sub(r'\D', '', number)):
            continue
        mobile = bool(re.search(r'mobile|iphone', label, re.I))
        if full not in people or mobile and not people[full][1]:
            people[full] = (number.strip(), mobile)
    return [(full, number) for full, (number, _) in people.items()]


def ending(number):
    return re.sub(r'\D', '', number)[-4:]


def send_picture(via, number, png_path, request):
    """Hand the picture to Messages for one recipient, by iMessage or SMS. Returns the copy's path."""
    if via not in ('imessage', 'sms'):
        raise ValueError('iMessage or SMS only')
    os.makedirs(SENT, exist_ok=True)
    copy = os.path.join(SENT, f'{request}.png')
    shutil.copyfile(png_path, copy)
    _osascript(SEND, via, number, copy, timeout=60)
    return copy
