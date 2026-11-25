#!/bin/bash
# XORA boot health: the parts that must work after an update. A failure here (3 boots in a row)
# rolls the whole OS back to the previous version.
set -euo pipefail
/usr/bin/xora --version >/dev/null                              # the xora command and its Python
systemctl is-enabled --quiet display-manager.service            # a login screen will start
systemctl is-active --quiet NetworkManager.service              # networking is up (not "online": offline is fine)
test -x /usr/lib/xora/hooks/anon && test -f /usr/lib/firewalld/zones/xora.xml   # privacy pieces present
echo "XORA core checks passed"
