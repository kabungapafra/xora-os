"""Build step: make KDE's lock screen use XORA's Ubuntu-style clock and always-blurred wallpaper.
Fails (and so stops the image build) if KDE changed the parts it patches."""
import re
import sys

p = sys.argv[1]
s = open(p).read()
assert s.count("        WallpaperFader {") == 1, "WallpaperFader block changed"
s = s.replace("        WallpaperFader {", "        XoraWallpaperFader {")
m = re.search(r"\n        Clock \{\n            id: clock\n.*?\n        \}\n", s, re.S)
assert m and "y: (mainBlock.userList.y + mainStack.y)/2 - height/2" in m.group(0), "Clock block changed"
s = s[:m.start()] + """
        XoraClock {
            id: clock
            shadow: clockShadow
            promptVisible: lockScreenRoot.uiVisible
            visible: config.alwaysShowClock
            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(parent.height * 0.42 - height / 2)
        }
""" + s[m.end():]
open(p, "w").write(s)
