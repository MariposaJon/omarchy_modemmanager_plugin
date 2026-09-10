import QtQuick
import Quickshell.Io

Item {
  id: root
  property bool panelOpen: false
  property int intervalSec: 10
  property var modemState: ({present: false, radio: false, connected: false, status: "Checking modem…", profiles: []})
  property string selectedProfile: ""
  property string message: ""
  property bool actionFailed: false
  property string pendingAction: ""
  readonly property bool busy: actionProcess.running || pendingAction !== ""
  property real rxRate: 0
  property real txRate: 0
  property var previous: null
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("modem.py").toString().replace(/^file:\/\//, ""))
  readonly property var profile: {
    var profiles = root.modemState.profiles || []
    for (var i = 0; i < profiles.length; i++)
      if (profiles[i].uuid === selectedProfile) return profiles[i]
    return profiles.length ? profiles[0] : ({uuid: "", name: "No saved profile", autoconnect: false})
  }
  function bytes(n) {
    n = Math.max(0, Number(n) || 0)
    var units = ["B", "KiB", "MiB", "GiB"]
    var index = 0
    while (n >= 1024 && index < 3) { n /= 1024; index++ }
    return n.toFixed(index ? 1 : 0) + " " + units[index]
  }
  function refresh() {
    if (!statusProcess.running && !busy) statusProcess.running = true
  }
  function act(name) {
    if (busy) return
    if (statusProcess.running) { pendingAction = name; return }
    message = name === "test" ? "Testing HTTPS through cellular…" : name === "power-on" ? "Turning on · waiting for network…" : "Applying…"
    actionFailed = false
    actionProcess.command = ["python3", helper, name, "--profile", profile.uuid || ""]
    actionProcess.running = true
  }
  function ingest(raw) {
    try {
      var next = JSON.parse(raw)
      if (!next.ok) {
        modemState = {present: false, radio: false, connected: false, status: next.status || "Status unavailable", profiles: [], error: next.error}
        previous = null; rxRate = 0; txRate = 0
        return
      }
      var elapsed = previous ? next.timestamp - previous.timestamp : 0
      if (previous && next.connected && previous.connected && next.interface === previous.interface && elapsed > 0) {
        rxRate = Math.max(0, next.rx - previous.rx) / elapsed
        txRate = Math.max(0, next.tx - previous.tx) / elapsed
      } else { rxRate = 0; txRate = 0 }
      previous = next
      modemState = next
      var exists = (next.profiles || []).some(function(p) { return p.uuid === selectedProfile })
      if (!exists) selectedProfile = next.profile || ""
    } catch (e) {
      modemState = {present: false, radio: false, connected: false, status: "Status unavailable", profiles: [], error: "Could not read modem status"}
    }
  }
  onPanelOpenChanged: refresh()
  Timer {
    interval: root.panelOpen ? 3000 : Math.max(5, root.intervalSec) * 1000
    running: true; repeat: true; triggeredOnStart: true
    onTriggered: root.refresh()
  }
  Process {
    id: statusProcess
    command: ["python3", root.helper, "status"]
    stdout: StdioCollector { id: statusOut; waitForEnd: true }
    stderr: StdioCollector { id: statusErr; waitForEnd: true }
    // Quickshell metadata omits QProcess::ExitStatus; this handler uses neither parameter.
    // qmllint disable signal-handler-parameters
    onExited: function() {
      if (statusOut.text.trim()) root.ingest(statusOut.text)
      else root.ingest(JSON.stringify({ok: false, error: statusErr.text || "Backend did not respond"}))
      if (root.pendingAction !== "") {
        var nextAction = root.pendingAction
        root.pendingAction = ""
        Qt.callLater(function() { root.act(nextAction) })
      }
    }
    // qmllint enable signal-handler-parameters
  }
  Process {
    id: actionProcess
    stdout: StdioCollector { id: actionOut; waitForEnd: true }
    stderr: StdioCollector { id: actionErr; waitForEnd: true }
    // Quickshell metadata omits QProcess::ExitStatus; this handler uses neither parameter.
    // qmllint disable signal-handler-parameters
    onExited: function() {
      try {
        var result = JSON.parse(actionOut.text)
        root.actionFailed = !result.ok
        root.message = result.message || result.error || "Action failed"
      } catch (e) { root.actionFailed = true; root.message = actionErr.text || "Action failed" }
      delayedRefresh.restart()
    }
    // qmllint enable signal-handler-parameters
  }
  Timer { id: delayedRefresh; interval: 500; onTriggered: root.refresh() }
  Timer {
    interval: 180000; running: actionProcess.running
    onTriggered: { actionProcess.signal(15); root.message = "Action timed out"; root.actionFailed = true }
  }
  Timer {
    interval: 20000; running: statusProcess.running
    onTriggered: statusProcess.signal(15)
  }
}
