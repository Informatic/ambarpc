import blinker
import json
import logging
import pprint
import socket
import time


# Known msg_ids
MSG_CONFIG_GET = 1  # AMBA_GET_SETTING
MSG_CONFIG_SET = 2
MSG_CONFIG_GET_ALL = 3

MSG_FORMAT = 4
MSG_STORAGE_USAGE = 5

MSG_STATUS = 7
MSG_BATTERY = 13

MSG_AUTHENTICATE = 257
MSG_PREVIEW_START = 259
MSG_PREVIEW_STOP = 260  # 258 previously, which ends current session

MSG_RECORD_START = 513
MSG_RECORD_STOP = 514
MSG_CAPTURE = 769

MSG_RECORD_TIME = 515  # Returns param: recording length

# File management messages
MSG_RM = 1281  # Param: path, supports wildcards
MSG_LS = 1282  # (Optional) Param: directory (path to file kills the server)
MSG_CD = 1283  # Param: directory, Returns pwd: current directory
MSG_MEDIAINFO = 1026  # Param: filename, returns media_type, date, duration,
# framerate, size, resolution, ...

# Not supported yet
MSG_DOWNLOAD_CHUNK = 1285  # param, offset, fetch_size
MSG_DOWNLOAD_CANCEL = 1287  # param
MSG_UPLOAD_CHUNK = 1286  # md5sum, param (path), size, offset

# Other random msg ids found throughout app / binaries
MSG_GET_SINGLE_SETTING_OPTIONS = 9  # ~same as MSG_CONFIG_GET_ALL with param
MSG_SD_SPEED = 16777218  # Returns rval: -13
MSG_SD_TYPE = 16777217  # Returns param: sd_hc
MSG_GET_THUMB = 1025  # Type: thumb, param: path, returns -21 if already exists

# No response...?
MSG_QUERY_SESSION_HOLDER = 1793  # ??

MSG_UNKNOW = 83886081  # likely non-existent

MSG_BITRATE = 16  # Unknown syntax, param

# Unknown syntax, both take type, set takes param too
MSG_DIGITAL_ZOOM = 15
MSG_DIGITAL_ZOOM_SET = 14

# Sends wifi_will_shutdown event after that, takes a looong time (up to 2
# minutes)
MSG_RESTART_WIFI = 16777225

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
                self._buffer += self._socket.recv(1024)
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

    def config_get(self, param=None):
        """Returns dictionary of config values or single config"""
        if param:
            return self.call(MSG_CONFIG_GET, type=param)['param']

        data = self.call(MSG_CONFIG_GET_ALL)['param']

        # Downloaded config is list of single-item dicts
        return dict(reduce(lambda o, c: o + c.items(), data, []))

    def config_set(self, param, value):
        """Sets single config value"""
        # Wicked.
        return self.call(MSG_CONFIG_SET, param=value, type=param)

    def config_describe(self, param):
        """Returns config type (`settable` or `readonly`) and possible values
        when settable"""
        resp = self.call(MSG_CONFIG_GET_ALL, param=param)
        type, _, values = resp['param'][0][param].partition(':')
        return (type, values.split('#') if values else [])

    def capture(self):
        """Captures a photo. Blocks until photo is actually saved"""
        self.send_message(MSG_CAPTURE)
        return self.wait_for_message(MSG_STATUS, type='photo_taken')['param']

    def preview_start(self):
        """Starts RTSP preview stream available on rtsp://addr/live"""
        return self.call(MSG_PREVIEW_START, param='none_force')

    def preview_stop(self):
        """Stops live preview"""
        return self.call(MSG_PREVIEW_STOP)

    def record_start(self):
        """Starts video recording"""
        return self.call(MSG_RECORD_START)

    def record_stop(self):
        """Stops video recording"""
        return self.call(MSG_RECORD_STOP)

    def record_time(self):
        """Returns current recording length"""
        return self.call(MSG_RECORD_TIME)['param']

    def battery(self):
        """Returns battery status"""
        return self.call(MSG_BATTERY)

    def storage_usage(self, type='free'):
        """Returns `free` or `total` storage available"""
        return self.call(MSG_STORAGE_USAGE, type=type)

    def storage_format(self):
        """Formats SD card, use with CAUTION!"""
        return self.call(MSG_FORMAT)

    def ls(self, path):
        """Returns list of files, adding " -D -S" to path will return more
        info"""
        return self.call(MSG_LS, param=path)

    def cd(self, path):
        """Enters directory"""
        return self.call(MSG_CD, param=path)

    def rm(self, path):
        """Removes file, supports wildcards"""
        return self.call(MSG_RM, param=path)

    def mediainfo(self, path):
        """Returns information about media file, such as media_type, date,
        duration, framerate, size, resolution, ..."""
        return self.call(MSG_MEDIAINFO, param=path)

    # Deprecated
    start_preview = preview_start
    stop_preview = preview_stop
    start_record = record_start
    stop_record = record_stop
    get_config = config_get
    set_config = config_set
    describe_config = config_describe


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
