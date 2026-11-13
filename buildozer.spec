[app]

# App identity: confirm package domain/name before creating a public release.
title = BKOMIK Ludo Master
package.name = bkomikludomaster
package.domain = com.bkomik

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,txt,md
version = 1.0.0

requirements = python3,kivy
p4a.branch = develop
orientation = portrait
fullscreen = 0

# TCP sockets for local Wi-Fi multiplayer.
android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 35
android.minapi = 24
android.accept_sdk_license = True
android.archs = arm64-v8a, armeabi-v7a

# This is a starter profile. Review current Buildozer/python-for-android and
# Google Play requirements before building or submitting.

[buildozer]
log_level = 2
warn_on_root = 1
