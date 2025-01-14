from autobahn.asyncio.websocket import WebSocketServerProtocol, WebSocketServerFactory
import ssl

import asyncio
import sys, traceback
from binascii import hexlify
import json

from .wssclient import DebugPrinter

class Client:
	def __init__(self, handle):
		self.handle = handle
		self.closeHandler = None

	def close(self):
		try:
			self.handle.sendClose(code=WebSocketClientProtocol.CLOSE_STATUS_CODE_NORMAL)
		except:
			pass

		if self.closeHandler:
			self.closeHandler()

	def sendMessage(self, msg, isBinary):
		self.handle.sendMessage(msg, isBinary)

	def sendTextMsg(self, msg, encoding='utf-8'):
		self.sendMessage(msg.encode(encoding), False)

	def sendBinaryMsg(self, msg):
		self.sendMessage(msg, True)

	def setCloseHandler(self, callback):
		self.closeHandler = callback

class Server(DebugPrinter):

	def __init__(self, port = 9000, useSsl = True, sslCert = "server.crt", sslKey= "server.key", debug = True):
		DebugPrinter.__init__(self, debug)
		self.clients = []
		self.knownClients = {}
		self.broadcastRate = 10
		self.broadcastMsg = None
		self.throttle = False
		self.encodeMsg = False
		self.debug = debug
		self.port = port
		self.sslcert = sslCert
		self.sslkey = sslKey
		self.ssl = useSsl

	def registerClient(self, client):
		self.clients.append(Client(client))

	def hasClients(self):
		return len(self.clients)

	def client(self, client_handle):
		for c in self.clients:
			if c.handle == client_handle:
				return c

	def broadcast(self, msg, isBinary = False):
		try:
			if self.throttle:
				self.broadcastMsg = msg
			else:
				if self.encodeMsg:
					msg = base64.b64encode(self.msg)
				for c in self.clients:
					if isBinary:
						c.sendBinaryMsg(msg)
					else:
						c.sendTextMsg(msg)
		except:
			self.print_debug("exception while broadcast()")
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
                          limit=6, file=sys.stdout)


	def unregisterClient(self, client):
		if isinstance(client, Client):
			client = client.handle

		for c in self.clients:
			if c.handle == client:
				c.close()
				self.clients.remove(c)
				return True

	def setBinaryHandler(self, binaryHandlerCallback):
		self.onBinaryMessage = binaryHandlerCallback

	def setTextHandler(self, textHandlerCallback):
		self.onMessage = textHandlerCallback

	def onBinaryMessage(self, msg, fromClient):
		pass

	def onMessage(self, msg, fromClient):
		"override this in subclass"
		pass

	def start(self):
		self.print_debug("start() called... debug = {}".format(self.debug))
		ws = "ws"

		sslcontext = None
		if self.ssl:
			try:
				sslcontext = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
				sslcontext.load_cert_chain(self.sslcert, self.sslkey)
				self.print_debug("using ssl")
			except Exception as ex:
				sslcontext = None
				self.print_debug("failed to use ssl")
				raise Exception("failed to use ssl: {}".format(ex))

			ws = "wss"	

		ResourceProtocol.server = self

		factory = WebSocketServerFactory(u"{0}://127.0.0.1:{1}".format(ws, self.port))
		factory.protocol = ResourceProtocol

		loop = asyncio.get_event_loop()

		coro = loop.create_server(factory, '', self.port, ssl=sslcontext)
		self.server = loop.run_until_complete(coro)

		self.print_debug("server should be started now")

	def startTwisted(self):
		from twisted.python import log
		log.startLogging(open("wssserver.log", "w"))

		self.print_debug("startTwisted() started")
		ws = "ws"

		ResourceProtocol.server = self

		sslcontext = None
		if self.ssl:
			self.print_debug("using wss... and ssl")
			sslcontext = ssl.DefaultOpenSSLContextFactory(self.sslkey, self.sslcert)
			ws = "wss"

		factory = WebSocketServerFactory(u"{}://127.0.0.1:{}".format(ws, self.port))
		factory.protocol = ResourceProtocol

		listenWS(factory, sslcontext)

		reactor.run()

class ResourceProtocol(WebSocketServerProtocol):
	server = None

	def onConnect(self, request):
		ResourceProtocol.server.print_debug("Client connecting: {0}".format(request.peer))

	def onOpen(self):
		ResourceProtocol.server.print_debug("WebSocket connection open.")
		ResourceProtocol.server.registerClient(self)

	def onMessage(self, payload, isBinary):
		try:
			if isBinary:
				ResourceProtocol.server.onBinaryMessage(payload, ResourceProtocol.server.client(self))
			else:
				ResourceProtocol.server.onMessage(payload, ResourceProtocol.server.client(self))
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
                          limit=6, file=sys.stdout)

	def onClose(self, wasClean, code, reason):
		try:
			ResourceProtocol.server.print_debug("WebSocket connection closed: {0}".format(reason))
			ResourceProtocol.server.unregisterClient(self)
		except:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
			traceback.print_exception(exc_type, exc_value, exc_traceback,
                          limit=2, file=sys.stdout)


def server_main(ServerClass = Server, **kwargs):

	import argparse

	parser = argparse.ArgumentParser()
	parser.add_argument('--ssl', dest="usessl", help="use ssl.", action='store_true')
	parser.add_argument('--debug', dest="debug", help="turn on debugging.", action='store_true')
	parser.add_argument('--sslcert', dest="sslcert", default="server.crt", nargs=1, help="ssl certificate")
	parser.add_argument('--sslkey', dest="sslkey", default="server.key", nargs=1, help="ssl key")
	parser.add_argument('--port', help="port of server", default=9000)

	args, unknown = parser.parse_known_args()

	loop = asyncio.get_event_loop()

	if args.port:
		kwargs["port"] = args.port

	s = ServerClass(useSsl=args.usessl, **kwargs)
	s.debug = args.debug
	
	return s


if __name__ == "__main__":
	
	loop = asyncio.get_event_loop()

	s = server_main()

	async def sendData():
		while True:
			try:
				print("trying to broadcast to {} clients...".format(len(s.clients)))
				s.broadcast("{'hello' : 'world' }", False)
			except:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				traceback.print_tb(exc_traceback, limit=1, file=sys.stdout)
				traceback.print_exception(exc_type, exc_value, exc_traceback,
	                          limit=2, file=sys.stdout)

			await asyncio.sleep(30)

	loop.create_task(sendData())

	def onMessage(msg, client):
		print("received message: {}".format(msg))

	s.onMessage = onMessage

	s.start()

	loop.run_forever()
