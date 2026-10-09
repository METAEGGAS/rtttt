[app]
title = Quotex Trading
package.name = quotexapp
package.domain = org.quotex

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json

version = 0.1
requirements = python3,kivy==2.3.0,requests,websocket-client,urllib3,certifi,chardet,idna,pyjnius

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.accept_sdk_license = True
android.archs = arm64-v8a
android.allow_backup = True
android.logcat_filters = *:S python:D
android.wakelock = True

# ⭐ منع تنزيل ANT (مش محتاجينه)
android.skip_update = False
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
