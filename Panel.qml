import QtQuick
import Quickshell
import qs.Ui as Ui
import qs.Commons

Ui.Panel {
  id: root
  moduleName: "jon.modem"
  ipcTarget: "jon.modem"
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight
  property int cursor: 0
  readonly property var s: modem.state
  readonly property color ink: bar ? bar.foreground : Color.foreground
  readonly property string family: bar ? bar.fontFamily : Style.font.family
  function power() { modem.act(s.radio ? "power-off" : "power-on") }
  function connection() {
    if (s.connected) modem.act("disconnect")
    else if (s.radio && modem.profile.uuid) modem.act("connect")
  }
  function activate() {
    if (cursor === 0) power()
    else if (cursor === 1) connection()
    else if (cursor === 2 && modem.profile.uuid) modem.act(modem.profile.autoconnect ? "auto-off" : "auto-on")
    else if (cursor === 3 && s.connected) modem.act("test")
    else if (cursor === 4) modem.act("copy")
    else modem.refresh()
  }
  Service {
    id: modem
    panelOpen: root.opened
    intervalSec: Number(root.setting("refreshIntervalSec", 10))
  }
  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: "Mobile broadband · " + (root.s.status || "Checking…") + (root.s.carrier ? "\n" + root.s.carrier : "") + "\nClick: controls · Right-click: radio"
    iconComponent: Component {
      SignalIcon { quality: root.s.signal || 0; powered: !!root.s.radio; connected: !!root.s.connected; foreground: root.barForeground }
    }
    onPressed: function(b) { if (b === Qt.RightButton) root.power(); else root.toggle() }
  }
  Ui.KeyboardPanel {
    id: popup
    owner: root
    anchorItem: button
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: popup.fittedContentWidth(Style.space(390))
    contentHeight: popup.fittedContentHeight(content.implicitHeight)
    Ui.PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      blocked: profiles.popupOpen
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onMoveRequested: function(dx, dy) { root.cursor = (root.cursor + (dy || dx) + 6) % 6 }
      onActivateRequested: root.activate()
      onTextKey: function(t) {
        if (t === "p") root.power()
        else if (t === "c") root.connection()
        else if (t === "r") modem.refresh()
        else if (t === "t" && root.s.connected) modem.act("test")
      }
      Column {
        id: content
        width: parent.width
        spacing: Style.space(12)
        Ui.PanelHero {
          title: "Mobile broadband"
          meta: modem.busy ? "Working…" : root.s.status || "Checking…"
          foreground: root.ink
          fontFamily: root.family
          iconComponent: Component {
            SignalIcon {
              width: Style.space(32); height: Style.space(32)
              quality: root.s.signal || 0; powered: !!root.s.radio; connected: !!root.s.connected; foreground: root.ink
            }
          }
          trailingControl: Component {
            Ui.ToggleSwitch {
              checked: !!root.s.radio
              busy: modem.busy
              hasCursor: root.cursor === 0
              foreground: root.ink
              onToggled: root.power()
            }
          }
        }
        Text {
          width: parent.width
          text: root.s.present ? ((root.s.provider || "SIM") + (root.s.carrier ? "  ·  " + root.s.carrier : "") + (root.s.roaming ? "  ·  Roaming" : "")) : (root.s.hint || "ModemManager is unavailable or still detecting the modem.")
          textFormat: Text.PlainText
          wrapMode: Text.WordWrap
          color: root.ink; opacity: 0.7
          font.family: root.family; font.pixelSize: Style.font.body
        }
        Ui.PanelSeparator { foreground: root.ink }
        Row {
          width: parent.width; spacing: Style.space(16)
          Column {
            width: (parent.width - parent.spacing) / 2; spacing: Style.space(4)
            Text { text: "SIGNAL"; color: root.ink; opacity: 0.55; font.family: root.family; font.pixelSize: Style.font.caption; font.letterSpacing: 1 }
            Text {
              text: root.s.radio && root.s.present ? ((root.s.signalRecent ? root.s.signal + "%" : "—") + "  " + (root.s.technology || "")) : "—"
              color: root.ink; font.family: root.family; font.pixelSize: Style.font.title; font.bold: true
            }
          }
          Column {
            width: (parent.width - parent.spacing) / 2; spacing: Style.space(4)
            Text { text: "TRAFFIC NOW"; color: root.ink; opacity: 0.55; font.family: root.family; font.pixelSize: Style.font.caption; font.letterSpacing: 1 }
            Text { text: "↓ " + modem.bytes(modem.rxRate) + "/s"; color: root.ink; font.family: root.family; font.pixelSize: Style.font.body }
            Text { text: "↑ " + modem.bytes(modem.txRate) + "/s"; color: root.ink; opacity: 0.65; font.family: root.family; font.pixelSize: Style.font.body }
          }
        }
        Rectangle {
          width: parent.width; height: Style.space(4); radius: height / 2
          color: Qt.rgba(root.ink.r, root.ink.g, root.ink.b, 0.13)
          Rectangle {
            width: parent.width * Math.max(0, Math.min(100, root.s.radio ? root.s.signal || 0 : 0)) / 100
            height: parent.height; radius: parent.radius; color: Color.accent
          }
        }
        Ui.Dropdown {
          id: profiles
          width: parent.width
          visible: (root.s.profiles || []).length > 1
          label: "CONNECTION PROFILE"
          value: modem.profile.uuid || ""
          options: (root.s.profiles || []).map(function(p) { return {value: p.uuid, label: p.name} })
          foreground: root.ink
          enabled: !modem.busy && !root.s.connected
          onChanged: function(value) { modem.selectedProfile = value }
        }
        Ui.Button {
          width: parent.width
          text: root.s.connected ? "Disconnect data" : "Connect " + (modem.profile.name || "cellular")
          bordered: true; selected: !!root.s.connected
          enabled: !modem.busy && (!!root.s.connected || (!!root.s.radio && !!modem.profile.uuid))
          opacity: enabled ? 1 : 0.45
          hasCursor: root.cursor === 1
          foreground: root.ink; fontFamily: root.family
          onClicked: root.connection()
        }
        Ui.Toggle {
          width: parent.width
          label: "Connect automatically"
          description: "When this SIM and its radio are available"
          checked: !!modem.profile.autoconnect
          enabled: !modem.busy && !!modem.profile.uuid
          opacity: enabled ? 1 : 0.45
          hasCursor: root.cursor === 2
          foreground: root.ink; fontFamily: root.family
          onClicked: modem.act(modem.profile.autoconnect ? "auto-off" : "auto-on")
        }
        Ui.PanelSeparator { foreground: root.ink }
        Repeater {
          model: [
            {label: "Connection", value: root.s.route || "—"},
            {label: "IP address", value: root.s.ip || "—"},
            {label: "APN", value: root.s.apn || "—"},
            {label: "Interface totals", value: "↓ " + modem.bytes(root.s.rx) + "   ↑ " + modem.bytes(root.s.tx)},
            {label: "Modem", value: root.s.model || "—"}
          ]
          Row {
            required property var modelData
            width: content.width
            Text { width: parent.width * 0.35; text: modelData.label; textFormat: Text.PlainText; color: root.ink; opacity: 0.55; font.family: root.family; font.pixelSize: Style.font.bodySmall }
            Text { width: parent.width * 0.65; text: modelData.value; textFormat: Text.PlainText; color: root.ink; font.family: root.family; font.pixelSize: Style.font.bodySmall; horizontalAlignment: Text.AlignRight; elide: Text.ElideRight }
          }
        }
        Row {
          width: parent.width; spacing: Style.space(8)
          Ui.Button {
            width: (parent.width - parent.spacing) / 2
            text: "Test cellular"
            bordered: true; enabled: !modem.busy && !!root.s.connected
            opacity: enabled ? 1 : 0.45; hasCursor: root.cursor === 3
            foreground: root.ink; fontFamily: root.family
            onClicked: modem.act("test")
          }
          Ui.Button {
            width: (parent.width - parent.spacing) / 2
            text: "Copy diagnostics"
            bordered: true; enabled: !modem.busy
            hasCursor: root.cursor === 4
            foreground: root.ink; fontFamily: root.family
            onClicked: modem.act("copy")
          }
        }
        Text {
          width: parent.width
          visible: text !== ""
          text: modem.message || root.s.error || ""
          textFormat: Text.PlainText; wrapMode: Text.WrapAnywhere
          color: modem.actionFailed ? Color.urgent : root.ink
          font.family: root.family; font.pixelSize: Style.font.bodySmall
        }
        Ui.Button {
          width: parent.width; text: "Refresh status"
          enabled: !modem.busy; hasCursor: root.cursor === 5
          foreground: root.ink; fontFamily: root.family
          onClicked: modem.refresh()
        }
        Text {
          width: parent.width
          text: "P power · C connect · T test · R refresh · Esc close"
          textFormat: Text.PlainText; wrapMode: Text.WordWrap
          color: root.ink; opacity: 0.45; font.family: root.family; font.pixelSize: Style.font.caption
        }
      }
    }
  }
}
