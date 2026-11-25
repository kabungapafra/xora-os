import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PC3
import org.kde.plasma.plasma5support as P5S
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root
    preferredRepresentation: compactRepresentation
    readonly property color accent: "#1EC8F0"
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
        Layout.minimumWidth: row.implicitWidth + Kirigami.Units.smallSpacing * 2
        Layout.preferredWidth: Layout.minimumWidth
        hoverEnabled: true
        onClicked: root.expanded = !root.expanded
        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Kirigami.Units.largeSpacing
            Image {
                source: "file:///usr/share/xora/xora-logo-dark.svg"
                sourceSize.height: Math.round(compact.height * 0.55)
                fillMode: Image.PreserveAspectFit
                Layout.alignment: Qt.AlignVCenter
            }
            Rectangle {
                implicitWidth: pill.implicitWidth + 24
                implicitHeight: Math.min(30, compact.height - 6)
                radius: 8
                color: compact.containsMouse || root.expanded ? "#24233F" : "#1B1A33"
                border.color: "#2C2B48"
                RowLayout {
                    id: pill
                    anchors.centerIn: parent
                    spacing: 8
                    Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: root.st.space ? root.accent : "#5A5D78" }
                    PC3.Label {
                        text: root.st.space ? "Space: <b>" + root.st.space + "</b>" : "No Space open"
                        textFormat: Text.StyledText
                        color: "#E6EAF2"
                        font.pixelSize: 13
                    }
                    Kirigami.Icon { source: "arrow-down"; implicitWidth: 12; implicitHeight: 12; color: "#9AA4B5" }
                }
            }
        }
    }

    fullRepresentation: ColumnLayout {
        Layout.minimumWidth: Kirigami.Units.gridUnit * 18
        Layout.minimumHeight: Kirigami.Units.gridUnit * 12
        spacing: Kirigami.Units.smallSpacing
        Kirigami.Heading { text: "Spaces"; level: 4 }
        PC3.Label {
            visible: !(root.st.spaces && root.st.spaces.length)
            text: "No Spaces yet. Press New Space and pick a project folder."
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
            opacity: 0.7
        }
        Repeater {
            model: root.st.spaces || []
            delegate: PC3.ItemDelegate {
                Layout.fillWidth: true
                highlighted: modelData.name === root.st.space
                contentItem: RowLayout {
                    Rectangle { implicitWidth: 8; implicitHeight: 8; radius: 4; color: modelData.running > 0 ? root.accent : "#5A5D78" }
                    PC3.Label { text: modelData.name; font.bold: modelData.name === root.st.space; Layout.fillWidth: true }
                    PC3.Label { text: modelData.running + "/" + modelData.services + " services"; opacity: 0.6 }
                }
                onClicked: { root.konsole("--hold -- xora space open " + modelData.name); root.expanded = false }
            }
        }
        Item { Layout.fillHeight: true }
        RowLayout {
            PC3.Button {
                text: "New Space"
                icon.name: "list-add"
                onClicked: { exec.run("xora center"); root.expanded = false }
            }
            PC3.Button {
                text: "Timeline"
                icon.name: "document-open-recent"
                onClicked: { exec.run("xora center timeline" + (root.st.space ? " --space " + root.st.space : "")); root.expanded = false }
            }
            PC3.Button {
                visible: !!root.st.space
                text: "Close Space"
                onClicked: { exec.run("xora space close " + root.st.space); root.expanded = false; root.refresh() }
            }
        }
    }
}
