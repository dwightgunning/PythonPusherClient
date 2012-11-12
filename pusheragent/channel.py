import logging
logging.basicConfig()

class Channel():

    def __init__(self, channelName):
        self.logger = logging.getLogger(__name__)
        
        self.name = channelName
        self.event_callbacks = {}

        self.logger.debug('Channel instantiated')

    def bind(self, eventName, callback):
        self.logger.debug('Channel: Binding - %s' % eventName)

        if eventName not in self.event_callbacks.keys():
            self.event_callbacks[eventName] = []

        self.event_callbacks[eventName].append(callback)

    def trigger(self, eventName, data):
        pass

    def _handle_event(self, eventName, data):
        self.logger.debug('Channel handling event: %s' % eventName)

        if eventName in self.event_callbacks.keys():
            for callback in self.event_callbacks[eventName]:
                self.logger.debug('delegating event to %s' % callback)
                callback(data)
