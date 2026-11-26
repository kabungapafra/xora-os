import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5S
import org.kde.kirigami as Kirigami

// Power & Session, in the top-right drop-down (system tray): lock, sleep, restart, shut down, log out.
// Restart, shut down and log out go through KDE's confirmation screen, so nothing happens by accident.
PlasmoidItem {
    id: root
    Plasmoid.icon: "system-shutdown"
    toolTipMainText: "Power & Session"
    toolTipSubText: "Lock, sleep, restart, shut down or log out"
    switchWidth: Kirigami.Units.gridUnit * 10
    switchHeight: Kirigami.Units.gridUnit * 10

    P5S.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => disconnectSource(source)
        function run(cmd) { connectSource(cmd) }
    }
    readonly property string prompt: "dbus-send --session --type=method_call --dest=org.kde.LogoutPrompt /LogoutPrompt org.kde.LogoutPrompt."
    function act(cmd) { root.expanded = false; exec.run(cmd) }

    fullRepresentation: ColumnLayout {
        Layout.preferredWidth: Kirigami.Units.gridUnit * 14
        spacing: Kirigami.Units.smallSpacing
        Repeater {
            model: [
                { label: "Lock screen", icon: "system-lock-screen", cmd: "loginctl lock-session" },
                { label: "Sleep", icon: "system-suspend", cmd: "systemctl suspend" },
                { label: "Restart…", icon: "system-reboot", cmd: root.prompt + "promptReboot" },
                { label: "Shut down…", icon: "system-shutdown", cmd: root.prompt + "promptShutDown" },
                { label: "Log out…", icon: "system-log-out", cmd: root.prompt + "promptLogout" },
                { label: "Switch user", icon: "system-switch-user",
                  cmd: "dbus-send --system --type=method_call --print-reply --dest=org.freedesktop.DisplayManager /org/freedesktop/DisplayManager/Seat0 org.freedesktop.DisplayManager.Seat.SwitchToGreeter" }
            ]
            delegate: PC3.ToolButton {
                required property var modelData
                Layout.fillWidth: true
                icon.name: modelData.icon
                text: modelData.label
                onClicked: root.act(modelData.cmd)
            }
        }
    }
}
