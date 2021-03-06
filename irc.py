#!/usr/bin/env python
"""
irc.py - A Utility IRC Bot
Copyright 2008, Sean B. Palmer, inamidst.com
Licensed under the Eiffel Forum License 2.

http://inamidst.com/phenny/
"""

import sys, re, time, traceback
import socket, asyncore, asynchat, ssl, select

class Origin(object):
   source = re.compile(r'([^!]*)!?([^@]*)@?(.*)')

   def __init__(self, bot, source, args):
      match = Origin.source.match(source or '')
      self.nick, self.user, self.host = match.groups()
      self.hostmask = source or ''

      if len(args) > 1:
         target = args[1]
      else: target = None

      mappings = {bot.nick: self.nick, None: None}
      self.sender = mappings.get(target, target)

class Bot(asynchat.async_chat):
   def __init__(self, nick, name, channels, password=None, use_ssl=False):
      asynchat.async_chat.__init__(self)
      self.set_terminator(b'\n')
      self.buffer = ''

      self.nick = nick
      self.user = nick
      self.name = name
      self.password = password

      self.verbose = True
      self.channels = channels or []
      self.stack = []
      self.use_ssl = use_ssl

      import threading
      self.sending = threading.RLock()

   def initiate_send(self):
      self.sending.acquire()
      asynchat.async_chat.initiate_send(self)
      self.sending.release()

   def __write(self, args, text=None):
      #print('PUSH: %r %r %r' % (self, args, text))
      try:
         if text is not None:
            # 510 because CR and LF count too, as nyuszika7h points out
            self.push(bytes(' '.join(args) + ' :' + text, 'utf-8', 'ignore')[:510] + b'\r\n')
         else: self.push(bytes(' '.join(args), 'utf-8', 'ignore')[:510] + b'\r\n')
      except IndexError:
         pass

   def write(self, args, text=None):
      # This is a safe version of __write
      def safe(input):
         if not input: return ""
         input = input.replace('\n', '')
         return input.replace('\r', '')
      try:
         args = [safe(arg) for arg in args]
         if text is not None:
            text = safe(text)
         self.__write(args, text)
      except Exception as e: pass

   def run(self, host, port=6667):
      self.ssl_server_hostname = host
      self.initiate_connect(host, port)

   def initiate_connect(self, host, port):
      if self.verbose:
         print('Connecting to %s:%s...' % (host, port), file=sys.stderr)
      self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
      self.connect((host, port))
      try: asyncore.loop()
      except KeyboardInterrupt:
         sys.exit()

   def handle_connect(self):
      if self.use_ssl:
         self.del_channel()
         sslctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
         sslsock = sslctx.wrap_socket(self.socket,
            suppress_ragged_eofs=False, do_handshake_on_connect=False,
            server_hostname=self.ssl_server_hostname)
         # Keep attempting handshake until successful
         while True:
            try:
               sslsock.do_handshake()
               break
            except ssl.SSLError as error:
               if error.args[0] == ssl.SSL_ERROR_WANT_READ:
                  select.select([sslsock], [], [])
               elif error.args[0] == ssl.SSL_ERROR_WANT_WRITE:
                  select.select([], [sslsock], [])
               else:
                  raise
         sslsock.setblocking(1)
         self.set_socket(sslsock)
      if self.verbose:
         print("Connected!", file=sys.stderr)
      if self.password:
         self.write(('PASS', self.password))
      self.write(('NICK', self.nick))
      self.write(('USER', self.user, '+iw', self.nick), self.name)

   def handle_close(self):
      self.close()
      print("Connection was closed.", file=sys.stderr)

   def collect_incoming_data(self, data):
      self.buffer += str(data, 'utf-8', 'ignore')

   def found_terminator(self):
      line = self.buffer
      if line.endswith('\r'):
         line = line[:-1]
      self.buffer = ''

      #print('GOT:', repr(line))
      if line.startswith(':'):
         source, line = line[1:].split(' ', 1)
      else: source = None

      if ' :' in line:
         argstr, text = line.split(' :', 1)
      else: argstr, text = line, ''
      args = argstr.split()

      origin = Origin(self, source, args)
      self.dispatch(origin, tuple([text] + args))

      if args[0] == 'PING':
         self.write(('PONG', text))

   def dispatch(self, origin, args):
      pass

   def msg(self, recipient, text):
      self.sending.acquire()

      # No messages within the last 3 seconds? Go ahead!
      # Otherwise, wait so it's been at least 0.8 seconds + penalty
      if self.stack:
         elapsed = time.time() - self.stack[-1][0]
         if elapsed < 3:
            penalty = float(max(0, len(text) - 50)) / 70
            wait = 0.8 + penalty
            if elapsed < wait:
               time.sleep(wait - elapsed)

      # Loop detection
      messages = [m[1] for m in self.stack[-8:]]
      if messages.count(text) >= 5:
         text = '...'
         if messages.count('...') >= 3:
            self.sending.release()
            return

      def safe(input):
         if not input: return ""
         input = input.replace('\n', '')
         return input.replace('\r', '')
      self.__write(('PRIVMSG', safe(recipient)), safe(text))
      self.stack.append((time.time(), text))
      self.stack = self.stack[-10:]

      self.sending.release()

   def notice(self, dest, text):
      self.write(('NOTICE', dest), text)

   def error(self, origin):
      try:
         import traceback
         trace = traceback.format_exc()
         print(trace)
         lines = list(reversed(trace.splitlines()))

         report = [lines[0].strip()]
         for line in lines:
            line = line.strip()
            if line.startswith('File "/'):
               report.append(line[0].lower() + line[1:])
               break
         else: report.append('source unknown')

         self.msg(origin.sender, report[0] + ' (' + report[1] + ')')
      except: self.msg(origin.sender, "Got an error.")

class TestBot(Bot):
   def f_ping(self, origin, match, args):
      delay = m.group(1)
      if delay is not None:
         import time
         time.sleep(int(delay))
         self.msg(origin.sender, 'pong (%s)' % delay)
      else: self.msg(origin.sender, 'pong')
   f_ping.rule = r'^\.ping(?:[ \t]+(\d+))?$'

def main():
   # bot = TestBot('testbot', ['#d8uv.com'])
   # bot.run('irc.freenode.net')
   print(__doc__)

if __name__ == "__main__":
   main()
