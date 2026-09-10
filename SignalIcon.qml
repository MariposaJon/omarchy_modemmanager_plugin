import QtQuick
import qs.Commons

Item {
  id: root
  property int quality: 0
  property bool powered: true
  property bool connected: false
  property color foreground: Color.foreground
  implicitWidth: Style.space(24)
  implicitHeight: Style.space(24)
  Row {
    anchors.fill: parent
    spacing: parent.width * 0.08
    Repeater {
      model: 4
      Rectangle {
        required property int index
        width: root.width * 0.19
        height: root.height * (0.25 + index * 0.22)
        anchors.bottom: parent.bottom
        radius: Math.max(1, width * 0.15)
        color: root.connected ? Color.accent : root.foreground
        opacity: root.powered && index < Math.max(1, Math.ceil(root.quality / 25)) ? 1 : 0.2
      }
    }
  }
  Rectangle {
    visible: !root.powered
    width: parent.width * 1.25
    height: Math.max(1, parent.height * 0.08)
    anchors.centerIn: parent
    rotation: -45
    color: root.foreground
  }
}
