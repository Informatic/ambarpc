Amba JSON Protocol
==================

Messages are JSON objects sent back and forth, without any kind of delimiter in
between, through a TCP socket. In case of Xiaomi Yi `network_message_daemon` is
running on ports 8787 and 7878. Actual message parsing is happening in
`libamba_msg_framework.so.1` and `libmsgprocess.so.2`, and most of the requests
are forwarded into uITRON.

Every packet contains `msg_id` key depicting type of message sent, in most
cases being an rpc method identifier. Client packets also need `token` value,
which is handed by `MSG_AUTHENTICATE (257)` (or `AMBA_START_SESSION`, following
the naming in an android app) call. Messages sent from server to client contain
`msg_id` as mentioned before, and `rval`, which is a response code. Packets in
both directions can contain arbitrary keys when needed, for client-to-server
direction `param` and `type` are most common.

`msg_id` 7 (`MSG_STATUS`) messages can be sent from server to client
out-of-order and depict some kind of event.



Known `rval`s
-------------

 - -23  - Invalid `msg_id`
 - -21  - Value unchanged (`config_get`)
 - -4   - Session invalid, new token is needed
 - 0    - Success

Known `msg_id`s
---------------

### 257 - Session start / Authenticate
Returns new token in param field

    DEBUG:__main__:>> {'token': 0, 'msg_id': 257}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 257, u'param': 8}
    
### 258 - Session stop
Revokes current token

### 13 - Battery status
Returns whether device is running off battery or USB adapter, and current
battery charge status.

    DEBUG:__main__:>> {'token': 8, 'msg_id': 13}
    DEBUG:__main__:<< {u'type': u'adapter', u'rval': 0, u'msg_id': 13, u'param': u'86'}
    # Camera is running off USB adapter right now, 86% charge

### 1 - Config get
Returns current config value for key `type`

    DEBUG:__main__:>> {'token': 8, 'msg_id': 1, 'type': 'camera_clock'}
    DEBUG:__main__:<< {u'type': u'camera_clock', u'rval': 0, u'msg_id': 1, u'param': u'2016-03-28 02:00:18'}

### 2 - Config set
Sets config value for key `type` to `param`

    DEBUG:__main__:>> {'token': 8, 'msg_id': 2, 'type': 'osd_enable', 'param': 'on'}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 2}

### 3 - Config get all
Returns all configuration values

    DEBUG:__main__:>> {'token': 8, 'msg_id': 3}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 3, u'param': [{u'camera_clock': u'2016-03-28 02:02:09'}, {u'video_standard': u'NTSC'}, ...]}

### 4 - Storage format
Formats SD card

### 5 - Storage usage
Returns current storage usage and size in kilobytes, `type` request value can be either `total` (for total storage size), or `free` (for free storage size)

    DEBUG:__main__:>> {'token': 8, 'msg_id': 5, 'type': 'total'}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 5, u'param': 7774208}

### 259 - Preview start
Starts preview available on `rtmp://ADDRESS/live`

    DEBUG:__main__:>> {'token': 8, 'msg_id': 259, 'param': 'none_force'}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 259}

### 260 - Preview stop
Stops preview

    DEBUG:__main__:>> {'token': 8, 'msg_id': 260}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 260}

### 513 - Record start

    DEBUG:__main__:>> {'token': 8, 'msg_id': 513}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 513}
    DEBUG:__main__:<< {u'msg_id': 7, u'type': u'start_video_record'}

### 514 - Record stop

    DEBUG:__main__:>> {'token': 8, 'msg_id': 514}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 514}
    DEBUG:__main__:<< {u'msg_id': 7, u'type': u'video_record_complete', u'param': u'/tmp/fuse_d/DCIM/101MEDIA/YDXJ0420.mp4'}

### 769 - Capture photo
Captures photo. Works regardless of current mode, but camera can't be in recording state

    DEBUG:__main__:>> {'token': 8, 'msg_id': 769}
    DEBUG:__main__:<< {u'msg_id': 7, u'type': u'start_photo_capture', u'param': u'precise quality;off'}
    DEBUG:__main__:<< {u'msg_id': 7, u'type': u'precise_capture_data_ready'}
    DEBUG:__main__:<< {u'msg_id': 7, u'type': u'photo_taken', u'param': u'/tmp/fuse_d/DCIM/101MEDIA/YDXJ0421.jpg'}
    DEBUG:__main__:<< {u'rval': 0, u'msg_id': 514}
    
*More calls can be found in `ambarpc.py` for now*