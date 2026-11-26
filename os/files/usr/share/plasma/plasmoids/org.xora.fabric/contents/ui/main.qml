import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5S
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation
// runs `xora …` and other commands; JSON from `xora status --json` lands in root.st
    P5S.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        onNewData: (source, data) => {
            if (source === root.statusCmd) {
                try { root.st = JSON.parse(data["stdout"]) } catch (e) { }
            }
            disconnectSource(source)
        }
        function run(cmd) { connectSource(cmd) }
    }
    readonly property string statusCmd: "xora status --json"
    property var st: ({})
    function refresh() { exec.run(statusCmd) }
    function konsole(args) { exec.run("xora-term " + args) }
    Timer { interval: 8000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }

    compactRepresentation: MouseArea {
        id: compact
        Layout.minimumWidth: chip.implicitWidth + 4
        Layout.preferredWidth: Layout.minimumWidth
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded
        Rectangle {
            id: chip
            anchors.centerIn: parent
            implicitWidth: r.implicitWidth + 20
            implicitHeight: Math.min(26, compact.height - 8)
            radius: height / 2
            color: compact.containsMouse ? "#143049" : "#0F2335"
            RowLayout {
                id: r
                anchors.centerIn: parent
                spacing: 6
                Kirigami.Icon { source: "network-workgroup"; implicitWidth: 14; implicitHeight: 14; color: "#67DAF7"; isMask: true }
                PC3.Label {
                    // devices counts this computer too: with nothing linked, invite linking instead of "1 device"
                    text: (root.st.devices || 1) <= 1 ? "Fabric · link a device"
                          : "Fabric · " + root.st.devices + " devices"
                         + (root.st.queued_jobs ? " · " + root.st.queued_jobs + " queued" : "")
                    color: "#67DAF7"
                    font.pixelSize: 12
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 16
        spacing: Kirigami.Units.smallSpacing
        Kirigami.Heading { text: "Fabric"; level: 4 }
        PC3.Label { text: "This computer"; font.bold: true }
        Repeater {
            model: root.st.paired || []
            delegate: PC3.Label { text: modelData }
        }
        PC3.Label {
            visible: !(root.st.paired && root.st.paired.length)
            text: "No other devices linked yet."
            opacity: 0.7
        }
        RowLayout {
            PC3.Button { text: "Show devices"; icon.name: "view-list-details"; onClicked: { exec.run("xora center pair"); root.expanded = false } }
            PC3.Button { text: "Add a device"; icon.name: "list-add"; onClicked: { exec.run("xora center pair"); root.expanded = false } }
        }
    }
}
