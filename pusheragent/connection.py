import websocket
try:
    import simplejson as json
except:
    import json

from threading import Thread, Timer
import time

import logging

class Connection(Thread):
    def __init__(self, eventHandler, url):
        self.socket = None
        self.socket_id = ""
        self.eventCallbacks = {}
        self.eventHandler = eventHandler
        self.url = url
        self.needsReconnect = False
        self.reconnectInterval = 10
        self.pingReceived = False
        self.pingTimeout = 30

        self.bind("pusher:connection_established", self._connect_handler)
        self.bind("pusher:connection_failed", self._failed_handler)
        self.bind("pusher:ping", self._ping_handler)

        self.state = "initialized"

        self.logger = logging.getLogger(__name__)
        if self.logger.getEffectiveLevel() == logging.DEBUG:
            websocket.enableTrace(True)

        # From Martyn's comment at: https://pusher.tenderapp.com/discussions/problems/36-no-messages-received-after-1-idle-minute-heartbeat
        #   "We send a ping every 5 minutes in an attempt to keep connections 
        #   alive..."
        # This is why we set the connection timeout to 5 minutes, since we can
        # expect a pusher heartbeat message every 5 minutes.  Adding 5 sec to
        # account for small timing delays which may cause messages to not be
        # received in exact 5 minute intervals.
        self.connectionTimeout = 315
        self.connectionTimer = Timer(self.connectionTimeout, self._connectionTimedOut)

        self.pingInterval = 120
        self.pingTimer = Timer(self.pingInterval, self._send_ping)
        self.pingTimer.start()

        Thread.__init__(self)

    def bind(self, stateEvent, callback):
        if stateEvent not in self.eventCallbacks.keys():
            self.eventCallbacks[stateEvent] = []

        self.eventCallbacks[stateEvent].append(callback)

    def disconnect(self):
        self.needsReconnect = False
        self.socket.close()

    def run(self):
        try:
            self._connect()
        except:
            raise
        finally:
            self.running = False
        

    def _connect(self):
        self.state = "connecting"

        self.socket = websocket.WebSocketApp(self.url, 
                                             self._on_open, 
                                             self._on_message,
                                             self._on_error,
                                             self._on_close)

        self.socket.run_forever()

        while (self.needsReconnect):
            self.logger.debug("Attempting to connect again in %s seconds." % self.reconnectInterval)
            self.state = "unavailable"
            time.sleep(self.reconnectInterval)
            self.socket.run_forever()

    def _on_open(self, ws):
        self.logger.debug("Connection: Connection opened")
        self.connectionTimer.start()

    def _on_error(self, ws, error):
        self.logger.error("Pusher Client Connection: Error - %s" % error)
        self.state = "failed"
        self.needsReconnect = True

    def _on_message(self, ws, message):
        # Stop our timeout timer, since we got some data
        self.connectionTimer.cancel()
        self.pingTimer.cancel()

        params = self._parse(message)

        self.logger.info('Message received: %s' % str(message))

        if 'event' in params.keys():
            if 'channel' not in params.keys():
                # We've got a connection event.  Lets handle it.
                if params['event'] in self.eventCallbacks.keys():
                    self.logger.debug("Connection: Handling params and firing callbacks")
                    for callback in self.eventCallbacks[params['event']]:
                        self.logger.info(callback)
                        callback(params['data'])
                else:
                    self.logger.debug("Connection: Unhandled event")
            else:
                # We've got a channel event.  Lets pass it up to the pusher
                # so it can be handled by the appropriate channel.
                self.logger.debug("Connection: Channel event")
                self.eventHandler(params['event'], 
                                  params['data'], 
                                  params['channel'])

        # We've handled our data, so restart our connection timeout handler
        self.connectionTimer = Timer(self.connectionTimeout, self._connectionTimedOut)
        self.connectionTimer.start()

        self.pingTimer = Timer(self.pingInterval, self._send_ping)
        self.pingTimer.start()

    def _on_close(self, ws):
        self.logger.info("Connection: Connection closed")
        self.state = "disconnected"

    def _parse(self, message):
        return json.loads(message)

    def _send_event(self, eventName, data):
        self.logger.info('Connection: sending event %s' % eventName)
        self.socket.send(json.dumps({'event':eventName, 'data':data}))

    def _send_ping(self):
        self.logger.debug("Connection: ping to pusher")

        self.socket.send(json.dumps({'event':'pusher:ping', 'data':''}))
        self.pingTimer = Timer(self.pingTimeout, self._check_ping)
        self.pingTimer.start()

    def _check_ping(self):
        self.pingTimer.cancel()
        if (self.pingReceived == True):
            self.pingReceived = False
        else:
            self.logger.info("Did not receive ping in time.  Will attempt to reconnect.")
            self.state = "failed"
            self.needsReconnect = True
            self.socket.close()

    def _connect_handler(self, data):
        # parsed = json.loads(data)
        # self.socket_id = parsed['socket_id'] # original
        self.socket_id = data['socket_id']
        
        self.state = "connected"

    def _failed_handler(self, data):
        parsed = json.loads(data)
        self.state = "failed"

    def _ping_handler(self, data):
        self.logger.info("Connection: ping from pusher")
        self.pingReceived = True

        self.logger.info("Connection: returning a pong to pusher")
        self.socket.send(json.dumps({'event':'pusher:pong', 'data':''}))

    def _connectionTimedOut(self):
        self.logger.info("Did not receive any data in time.  Reconnecting.")
        self.state = "failed"
        self.needsReconnect = True
        self.socket.close()
