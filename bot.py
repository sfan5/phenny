#!/usr/bin/env python
"""
bot.py - Phenny IRC Bot
Copyright 2008, Sean B. Palmer, inamidst.com
Licensed under the Eiffel Forum License 2.

http://inamidst.com/phenny/
"""

import sys, os, re, threading, imp
import irc

home = os.getcwd()

def match_hostmask(matchstr, hostmask):
	ptrn = matchstr
	ptrn = ptrn.replace('\\', r'\\')
	ptrn = ptrn.replace(r'.', r'\.')
	ptrn = ptrn.replace(r'+', r'\+')
	ptrn = ptrn.replace(r'(', r'\(')
	ptrn = ptrn.replace(r')', r'\)')
	ptrn = ptrn.replace(r'^', r'\^')
	ptrn = ptrn.replace(r'$', r'\$')
	ptrn = ptrn.replace(r'|', r'\|')

	ptrn = ptrn.replace(r'*', r'.+')
	ptrn = ptrn.replace(r'?', r'.')
	ptrn = ptrn.replace(r'\a', r'[A-Za-z]+')
	ptrn = ptrn.replace(r'\n', r'[0-9]+')
	ptrn = ptrn.replace(r'\o', r'[0-9A-Za-z]+')
	ptrn = ptrn.replace(r'\h', r'[0-9A-Fa-f]+')

	rgx = re.compile('^' + ptrn + '$')
	m = rgx.match(hostmask)
	if m:
		return True
	else:
		return False

def decode(bytes):
   try: text = bytes.decode('utf-8')
   except UnicodeDecodeError:
      try: text = bytes.decode('iso-8859-1')
      except UnicodeDecodeError:
         text = bytes.decode('cp1252')
   return text

class Phenny(irc.Bot):
   def __init__(self, config):
      args = (config.nick, config.name, config.channels, config.password, config.ssl)
      irc.Bot.__init__(self, *args)
      self.config = config
      self.config.prefix = re.escape(self.config.prefix)
      self.doc = {}
      self.stats = {}
      self.setup()

   def setup(self):
      self.variables = {}

      filenames = []
      if not hasattr(self.config, 'enable'):
         for fn in os.listdir(os.path.join(home, 'modules')):
            if fn.endswith('.py') and not fn.startswith('_'):
               filenames.append(os.path.join(home, 'modules', fn))
      else:
         for fn in self.config.enable:
            filenames.append(os.path.join(home, 'modules', fn + '.py'))

      if hasattr(self.config, 'extra'):
         for fn in self.config.extra:
            if os.path.isfile(fn):
               filenames.append(fn)
            elif os.path.isdir(fn):
               for n in os.listdir(fn):
                  if n.endswith('.py') and not n.startswith('_'):
                     filenames.append(os.path.join(fn, n))

      modules = []
      excluded_modules = getattr(self.config, 'exclude', [])
      for filename in filenames:
         name = os.path.basename(filename)[:-3]
         if name in excluded_modules: continue
         # if name in sys.modules:
         #    del sys.modules[name]
         try: module = imp.load_source(name, filename)
         except Exception, e:
            print >> sys.stderr, "Error loading %s: %s (in bot.py)" % (name, e)
         else:
            if hasattr(module, 'setup'):
               module.setup(self)
            self.register(vars(module))
            modules.append(name)

      if modules:
         print >> sys.stderr, 'Registered modules:', ', '.join(modules)
      else: print >> sys.stderr, "Warning: Couldn't find any modules"

      self.bind_commands()

   def register(self, variables):
      # This is used by reload.py, hence it being methodised
      for name, obj in variables.iteritems():
         if hasattr(obj, 'commands') or hasattr(obj, 'rule'):
            self.variables[name] = obj
         elif name == "_export":
            for name_ in obj:
               __builtins__[name_] = obj[name_] # TODO?: Haxx!1!!

   def bind_commands(self):
      self.commands = {'high': {}, 'medium': {}, 'low': {}}
      self.hooks = []

      def bind(self, priority, regexp, func):
         print priority, regexp.pattern.encode('utf-8'), func
         # register documentation
         if not hasattr(func, 'name'):
            func.name = func.__name__
         if func.__doc__:
            if hasattr(func, 'example'):
               example = func.example
               example = example.replace('$nickname', self.nick)
            else: example = None
            self.doc[func.name] = (func.__doc__, example)
         self.commands[priority].setdefault(regexp, []).append(func)

      def sub(pattern, self=self):
         # These replacements have significant order
         pattern = pattern.replace('$nickname', re.escape(self.nick))
         return pattern.replace('$nick', r'%s[,:] +' % re.escape(self.nick))

      for name, func in self.variables.iteritems():

         if hasattr(func, 'hook') and func.hook:
            self.hooks.append(func)
            continue

         if not hasattr(func, 'priority'):
            func.priority = 'medium'

         if not hasattr(func, 'thread'):
            func.thread = True

         if not hasattr(func, 'nohook'):
            func.nohook = False

         if not hasattr(func, 'event'):
            func.event = 'PRIVMSG'
         else: func.event = func.event.upper()

         if hasattr(func, 'rule'):
            if isinstance(func.rule, str):
               pattern = sub(func.rule)
               regexp = re.compile(pattern)
               bind(self, func.priority, regexp, func)

            if isinstance(func.rule, tuple):
               # 1) e.g. ('$nick', '(.*)')
               if len(func.rule) == 2 and isinstance(func.rule[0], str):
                  prefix, pattern = func.rule
                  prefix = sub(prefix)
                  regexp = re.compile(prefix + pattern)
                  bind(self, func.priority, regexp, func)

               # 2) e.g. (['p', 'q'], '(.*)')
               elif len(func.rule) == 2 and isinstance(func.rule[0], list):
                  prefix = self.config.prefix
                  commands, pattern = func.rule
                  for command in commands:
                     command = r'(%s)\b(?: +(?:%s))?' % (command, pattern)
                     regexp = re.compile(prefix + command)
                     bind(self, func.priority, regexp, func)

               # 3) e.g. ('$nick', ['p', 'q'], '(.*)')
               elif len(func.rule) == 3:
                  prefix, commands, pattern = func.rule
                  prefix = sub(prefix)
                  for command in commands:
                     command = r'(%s) +' % command
                     regexp = re.compile(prefix + command + pattern)
                     bind(self, func.priority, regexp, func)

         if hasattr(func, 'commands'):
            for command in func.commands:
               template = r'^%s(%s)(?: +(.*))?$'
               pattern = template % (self.config.prefix, command)
               regexp = re.compile(pattern)
               bind(self, func.priority, regexp, func)

   def wrapped(self, origin, text, match):
      class PhennyWrapper(object):
         def __init__(self, phenny):
            self.bot = phenny

         def __getattr__(self, attr):
            sender = origin.sender or text
            if attr == 'reply':
               return (lambda msg:
                  self.bot.msg(sender, origin.nick + ': ' + msg))
            elif attr == 'say':
               return lambda msg: self.bot.msg(sender, msg)
            elif attr == 'match_hostmask':
               return lambda a, b: match_hostmask(a, b)
            return getattr(self.bot, attr)

      return PhennyWrapper(self)

   def input(self, origin, text, bytes, match, event, args):
      class CommandInput(unicode):
         def __new__(cls, text, origin, bytes, match, event, args):
            s = unicode.__new__(cls, text)
            s.sender = origin.sender
            s.nick = origin.nick
            s.event = event
            s.bytes = bytes
            s.match = match
            s.group = match.group
            s.groups = match.groups
            s.args = args
            s.hostmask = origin.hostmask
            s.admin = False
            for hmask in self.config.admins:
            	if match_hostmask(hmask, origin.hostmask):
            		s.admin = True
            s.owner = False
            owners = self.config.owner
            if type(owners) != type([]):
            	owners = [owners]
            for hmask in owners:
            	if match_hostmask(hmask, origin.hostmask):
            		s.owner = True
            if s.owner and not s.admin:
            	s.admin = True
            return s

      return CommandInput(text, origin, bytes, match, event, args)

   def call(self, func, origin, phenny, input):
      try: func(phenny, input)
      except Exception, e:
         self.error(origin)

   def limit(self, origin, func):
      if origin.sender and origin.sender.startswith('#'):
         if hasattr(self.config, 'limit'):
            limits = self.config.limit.get(origin.sender)
            if limits and (func.__module__ not in limits):
               return True
      return False

   def dispatch(self, origin, args):
      bytes, event, args = args[0], args[1], args[2:]
      text = decode(bytes)

      for priority in ('high', 'medium', 'low'):
         items = self.commands[priority].items()
         for regexp, funcs in items:
            for func in funcs:
               if event != func.event and func.event != '*': continue

               match = regexp.match(text)
               if match:
                  if self.limit(origin, func): continue

                  phenny = self.wrapped(origin, text, match)
                  input = self.input(origin, text, bytes, match, event, args)

                  if not func.nohook:
                     # Run all hooks and abort processing if one of them returns False
                     for hook in self.hooks:
                        if not hook(phenny, input, func):
                           continue

                  if func.thread:
                     targs = (func, origin, phenny, input)
                     t = threading.Thread(target=self.call, args=targs)
                     t.start()
                  else: self.call(func, origin, phenny, input)

                  for source in [origin.sender, origin.nick]:
                     try: self.stats[(func.name, source)] += 1
                     except KeyError:
                        self.stats[(func.name, source)] = 1

if __name__ == '__main__':
   print __doc__
