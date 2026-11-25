import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5S
import org.kde.kirigami as Kirigami

// Protection chip: how this computer is connected right now.
//   red   "Anon · Tor"   all traffic through Tor (kill switch built in)
//   green "VPN · name"   a VPN is connected (🔒 when the VPN kill switch is on)
//   grey  "Not protected"
// The popup turns Anon mode, the VPN and the kill switch on or off (asks for the password when needed).
PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation
    readonly property string mode: root.st.anon ? "anon" : root.st.vpn ? "vpn" : "none"
    toolTipMainText: mode === "anon" ? "Anon mode: all traffic through Tor"
                   : mode === "vpn" ? "VPN on: " + root.st.vpn : "Not protected"
    toolTipSubText: (root.st.vpn_killswitch ? "Kill switch on: nothing leaves outside the VPN. " : "") + "Click for options."

    P5S.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            if (source === root.statusCmd) {
                try { root.st = JSON.parse(data["stdout"]) } catch (e) { }
            } else {
                root.busy = false
                root.refresh()
            }
            disconnectSource(source)
        }
        function run(cmd) { connectSource(cmd) }
    }
    readonly property string statusCmd: "xora status --json"
    property var st: ({})
    property bool busy: false
    function refresh() { exec.run(statusCmd) }
    function act(cmd) { if (!root.busy) { root.busy = true; exec.run(cmd) } }
    Timer { interval: 6000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }

    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 20
        spacing: Kirigami.Units.smallSpacing
        PC3.Label { text: root.toolTipMainText; font.bold: true }
        PC3.Label {
            Layout.fillWidth: true; wrapMode: Text.WordWrap; opacity: 0.8
            text: "VPN: hides your traffic from this network and your provider. Anon mode (Tor): nobody can link "
                + "what you do to who you are. Both can be on."
        }
        PC3.Button {
            Layout.fillWidth: true
            enabled: !root.busy
            icon.name: root.st.anon ? "security-low" : "security-high"
            text: root.busy ? "Working… (enter your password if asked)" : root.st.anon ? "Turn Anon mode off" : "Turn Anon mode on (Tor)"
            onClicked: root.act("xora anon " + (root.st.anon ? "off" : "on"))
        }
        PC3.Button {
            Layout.fillWidth: true
            enabled: !root.busy
            icon.name: "network-vpn"
            text: root.st.vpn ? "Disconnect VPN (" + root.st.vpn + ")" : "Connect VPN"
            onClicked: root.act("xora vpn " + (root.st.vpn ? "off" : "on"))
        }
        PC3.CheckBox {
            enabled: !root.busy
            checked: !!root.st.vpn_killswitch
            text: "VPN kill switch: block the internet if the VPN drops"
            onClicked: root.act("xora vpn killswitch " + (checked ? "on" : "off"))
        }
        PC3.Button {
            Layout.fillWidth: true
            flat: true
            icon.name: "configure"
            text: "Add or edit VPNs…"
            onClicked: { exec.run("systemsettings kcm_networkmanagement"); root.expanded = false }
        }
    }

    compactRepresentation: MouseArea {
        Layout.minimumWidth: r.implicitWidth + 16
        Layout.preferredWidth: Layout.minimumWidth
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: 4
            anchors.bottomMargin: 4
            radius: height / 2
            color: root.mode === "anon" ? "#3A1018" : root.mode === "vpn" ? "#0E2A1E" : "transparent"
            border.color: root.mode === "anon" ? "#F43F5E" : root.mode === "vpn" ? "#22C55E" : "transparent"
        }
        RowLayout {
            id: r
            anchors.centerIn: parent
            spacing: 6
            Kirigami.Icon {
                source: root.mode === "none" ? "security-low" : "security-high"
                implicitWidth: 14; implicitHeight: 14; isMask: true
                color: root.mode === "anon" ? "#FB7185" : root.mode === "vpn" ? "#4ADE80" : "#C3CAD6"
            }
            PC3.Label {
                text: root.busy ? "…" : root.mode === "anon" ? "Anon · Tor"
                    : root.mode === "vpn" ? "VPN · " + root.st.vpn + (root.st.vpn_killswitch ? " 🔒" : "")
                    : (root.st.vpn_killswitch ? "Blocked: no VPN" : "Not protected")
                color: root.mode === "anon" ? "#FECDD3" : root.mode === "vpn" ? "#BBF7D0" : "#C3CAD6"
                font.pixelSize: 12
            }
        }
    }
}
