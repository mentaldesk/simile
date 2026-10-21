"""Installs the three CC0 MakeHuman asset packs the study uses into its own Blender profile.

./blender.sh -b -P mpfb/install.py -- out/downloads/makehuman_system_assets_cc0.zip \
    out/downloads/shirts01_cc0.zip out/downloads/pants01_cc0.zip

Hats 01 and Hair 01 aren't needed: the only things the study would take from them, a cap and a
bun, say AGPL3 in their own files.
"""

import sys

import bpy

packs = sys.argv[sys.argv.index("--") + 1 :]
for pack in packs:
    print("Installing", pack)
    result = bpy.ops.mpfb.load_pack(filepath=pack)
    print(result)
bpy.ops.wm.save_userpref()
