[app]
title = HRNet人事关系管理
package.name = hrnet
package.domain = org.hrnet
source.dir = .
source.include_exts = py,png,jpg,kv,ttf,db
source.include_patterns = ziti.ttf
version = 1.0
requirements = hostpython3==3.12,python3==3.12,kivy==2.3.1,openpyxl
orientation = portrait
fullscreen = 0
android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.arch = armeabi-v7a,arm64-v8a
android.add_src = ziti.ttf

[buildozer]
log_level = 2
warn_on_root = 1
