"""Installs the CC0 MakeHuman asset packs into this study's own Blender profile.

./blender.sh -b -P mpfb/install.py -- out/downloads/*/*_cc0.zip
"""

import sys

import bpy

packs = sys.argv[sys.argv.index("--") + 1 :]
for pack in packs:
    print("Installing", pack)
    result = bpy.ops.mpfb.load_pack(filepath=pack)
    print(result)
bpy.ops.wm.save_userpref()
