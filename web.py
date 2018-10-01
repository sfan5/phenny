#!/usr/bin/env python
"""
web.py - Web Facilities
Copyright sfan5, 2014
"""

import re
import urllib
import urllib.request
import urllib.parse
import json as jsonlib
from html.entities import html5 as name2codepoint

user_agent = "Mozilla/5.0 (compatible; Phenny; +https://github.com/sfan5/phenny)"
request_timeout = 10.0

def get(uri, amount=-1):
	global user_agent
	req = urllib.request.Request(uri, headers={"User-Agent": user_agent})
	try:
		f = urllib.request.urlopen(req, timeout=request_timeout, cadefault=True)
	except urllib.error.HTTPError as e:
		return b"", e.code
	if amount > 0:
		content = f.read(amount)
	else:
		content = f.read()
	f.close()
	return content, f.status

def head(uri):
	global user_agent
	req = urllib.request.Request(uri, headers={"User-Agent": user_agent}, method="HEAD")
	try:
		f = urllib.request.urlopen(req, timeout=request_timeout, cadefault=True)
	except urllib.error.HTTPError as e:
		return {}, e.code
	headers = dict(f.info().items())
	f.close()
	return headers, f.status


def post(uri, query):
	global user_agent
	data = bytes(urllib.parse.urlencode(query), 'ascii')
	req = urllib.request.Request(uri, data=data, headers={"User-Agent": user_agent})
	try:
		f = urllib.request.urlopen(req, timeout=request_timeout, cadefault=True)
	except urllib.error.HTTPError as e:
		return b"", e.code
	content = f.read()
	f.close()
	return content, f.status

def entity(match):
	value = match.group(1)
	if value.lower().startswith('#x'):
		return chr(int(value[2:], 16))
	elif value.startswith('#'):
		return chr(int(value[1:]))
	elif (value + ';') in name2codepoint:
		return name2codepoint[value + ';']
	return '[' + value + ']'

r_entity = re.compile(r'&([^;\s]+);')

def decode(html):
	return r_entity.sub(entity, html)

def json(text):
	return jsonlib.loads(text)

def urlencode(text):
	return urllib.parse.urlencode({'a': text})[2:]

