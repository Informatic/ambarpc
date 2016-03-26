import blinker
import json
import logging
import pprint
import socket
import time


# Known msg_ids
MSG_CONFIG_SET = 2
MSG_CONFIG_GET = 3
MSG_STORAGE_USAGE = 5
MSG_STATUS = 7
MSG_BATTERY = 13
MSG_AUTHENTICATE = 257
MSG_PREVIEW_STOP = 258
MSG_PREVIEW_START = 259
MSG_RECORD_START = 513
MSG_RECORD_STOP = 514
MSG_CAPTURE = 769


# File management messages, not supported yet
MSG_RM = 1281
MSG_LS = 1282
MSG_CD = 1283
MSG_DOWNLOAD_CHUNK = 1285
MSG_UPLOAD_CHUNK = 1286

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    pass


class RPCError(Exception):
    pass


class AmbaRPCClient(object):
    address = None
    port = None

    _decoder = None
    _buffer = None
    _socket = None

    token = None

    def __init__(self, address='192.168.42.1', port=7878):
        self.address = address
        self.port = port

        self._decoder = json.JSONDecoder()
        self._buffer = ""

        ns = blinker.Namespace()
        self.raw_message = ns.signal('raw-message')
        self.event = ns.signal('event')

    def connect(self):
        """Connects to RPC service"""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        logger.info('Connecting...')
        self._socket.connect((self.address, self.port))
        self._socket.settimeout(1)
        logger.info('Connected')

    def authenticate(self):
        """Fetches auth token used for all the requests"""
        self.token = 0
        self.token = self.call(MSG_AUTHENTICATE)['param']
        logger.info('Authenticated')

    def send_message(self, msg_id, **kwargs):
        """Sends a single RPC message"""
        kwargs.setdefault('msg_id', msg_id)
        kwargs.setdefault('token', self.token)
        logger.debug('>> %r', kwargs)

        self._socket.send(json.dumps(kwargs))

    def parse_message(self):
        """Parses a single message from buffer and returns it, or None if no
        message could be parsed"""
        try:
            data, end_index = self._decoder.raw_decode(self._buffer)
        except ValueError:
            if self._buffer:
                logging.debug('Invalid message')
            else:
                logging.debug('Buffer empty')

            return None

        logger.debug('<< %r', data)

        self._buffer = self._buffer[end_index:]

        ev_data = data.copy()
        msg_id = ev_data.pop('msg_id', None)
        self.raw_message.send(msg_id, **ev_data)

        if 'type' in data and msg_id == MSG_STATUS:
            ev_type = ev_data.pop('type', None)
            self.event.send(ev_type, **ev_data)

        return data

    def wait_for_message(self, msg_id=None, timeout=-1, **kwargs):
        """Waits for a single message matched by msg_id and kwargs, with
        possible timeout (-1 means no timeout), and returns it"""
        st = time.time()
        while True:
            msg = True

            while msg and self._buffer:
                msg = self.parse_message()
                if not msg:
                    break

                if msg_id is None or msg['msg_id'] == msg_id and \
                        all(p in msg.items() for p in kwargs.items()):
                    return msg

            if timeout > 0 and time.time() - st > timeout:
                raise TimeoutException()

            try:
                self._buffer += self._socket.recv(512)
            except socket.timeout:
                pass

    def call(self, msg_id, raise_on_error=True, timeout=-1, **kwargs):
        """Sends single RPC request, raises RPCError when rval is not 0"""
        self.send_message(msg_id, **kwargs)
        resp = self.wait_for_message(msg_id, timeout=timeout)

        if resp.get('rval', 0) != 0 and raise_on_error:
            raise RPCError(resp)

        return resp

    def run(self):
        """Loops forever parsing all incoming messages"""
        while True:
            self.wait_for_message()

    def get_config(self):
        """Returns dictionary of config values"""
        data = self.call(MSG_CONFIG_GET)['param']

        # Downloaded config is list of single-item dicts
        return dict(reduce(lambda o, c: o + c.items(), data, []))

    def set_config(self, param, value):
        """Sets single config value"""
        # Wicked.
        return self.call(MSG_CONFIG_SET, param=value, type=param)

    def describe_config(self, param):
        """Returns config type (`settable` or `readonly`) and possible values
        when settable"""
        resp = self.call(MSG_CONFIG_GET, param=param)
        type, _, values = resp['param'][0][param].partition(':')
        return (type, values.split('#') if values else [])

    def capture(self):
        """Captures a photo. Blocks until photo is actually saved"""
        self.send_message(MSG_CAPTURE)
        return self.wait_for_message(MSG_STATUS, type='photo_taken')['param']

    def start_preview(self):
        """Starts RTSP preview stream available on rtsp://addr/live"""
        return self.call(MSG_PREVIEW_START, param='none_force')

    def stop_preview(self):
        """Stops live preview"""
        return self.call(MSG_PREVIEW_STOP)

    def start_record(self):
        """Starts video recording"""
        return self.call(MSG_RECORD_START)

    def stop_record(self):
        """Stops video recording"""
        return self.call(MSG_RECORD_STOP)

    def battery(self):
        """Returns battery status"""
        return self.call(MSG_BATTERY)

    def storage_usage(self, type='free'):
        """Returns `free` or `total` storage available."""
        return self.call(MSG_STORAGE_USAGE, type=type)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    c = AmbaRPCClient()
    c.connect()
    c.authenticate()

    @c.event.connect_via('vf_start')
    def vf_start(*args, **kwargs):
        print '*** STARTING ***'

    @c.event.connect_via('vf_stop')
    def vf_stop(*args, **kwargs):
        print '*** STOPPING ***'

    @c.event.connect_via('video_record_complete')
    def complete(type, param):
        print 'File saved in', param

    @c.event.connect
    def testing(*args, **kwargs):
        print 'event:', args, kwargs

    pprint.pprint(c.battery())
    c.run()
