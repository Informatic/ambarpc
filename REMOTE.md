Bluetooth Remote
================

Bluetooth remote most probably communicates through Bluetooth Low Energy (based
on reports from people that it should work fine for a year without charging)

Discovery mode is enabled in camera by double-pressing wifi button. Discovery
happens in `.text:00011734` in `app_ble`. Its log is saved in
`/tmp/fuse/1970-1-1.log`. App expects BD address to begin with
`20:73:80`. If any BLE device with non-matching address is found,
`invalid remote ble control device` message with bdaddr and rssi is logged.
