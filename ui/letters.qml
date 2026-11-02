// Correspondence: a conversation with one of the herd's agents, by hand, on the reMarkable 2, from herd-board-serve's
// /thread.json. Choose the agent from the list at the top; above, your exchanges with it (what you said, what it last
// wrote back), newest at the foot. You write in the tablet's own notebook "To NAME" (the native pen; folder
// Correspondence); READ MY PAGE has the server fetch its latest page and Gemini read it (/read); you see what it read, and only SEND puts it into the agent's pane (/send). The thread is a long poll: the agent's
// reply appears when it is written.
import QtQuick 2.5

Rectangle {
	id: root
	anchors.fill: parent
	color: "white"
	property string server: "@SERVER@"
	property var desks: []
	property var items: []
	property string pane: ""
	property string name: ""
	property string status: ""
	property string v: ""
	property bool online: false
	property bool choosing: false
	property string inked: ""      // what Gemini read on the notebook page
	property string note: ""
	property string sent: ""       // sent, not yet in the agent's transcript
	property var req: null
	property int tz: 0
	readonly property string serif: "EB Garamond"
	readonly property string sans: "Noto Sans"

	signal close
	function unloading() { retry.stop(); watchdog.stop(); if (req) req.abort() }

	function standing(s) {
		return s === "blocked" ? "WAITING ON YOU" : s === "working" ? "AT WORK" : s === "done" ? "FINISHED" : "QUIET"
	}
	function hhmm(t) {
		var d = new Date((t + tz) * 1000)
		return ("0" + d.getUTCHours()).slice(-2) + ":" + ("0" + d.getUTCMinutes()).slice(-2)
	}
	function why(st, r) { return r && r.error ? r.error : st ? "status " + st : "the wire is down" }
	function post(path, obj, done) {
		var x = new XMLHttpRequest()
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE) return
			var r = null
			try { r = JSON.parse(x.responseText) } catch (e) {}
			done(x.status, r)
		}
		x.open("POST", server + path)
		x.setRequestHeader("Content-Type", "application/json")
		x.send(JSON.stringify(obj))
	}
	function fetch(since) {
		if (req) req.abort()
		var x = new XMLHttpRequest()
		req = x
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE || x !== req) return
			watchdog.stop()
			req = null
			if (x.status === 200) {
				var j = JSON.parse(x.responseText)
				online = true
				desks = j.desks
				if (!pane && desks.length) { choose(desks[0]); return }
				if (j.v !== v) {
					v = j.v; name = j.name; status = j.status
					var last = j.items.length ? j.items[j.items.length - 1] : null
					if (sent && j.items.some(function(i) { return i.who === "you" && i.text === sent })) sent = ""
					items = j.items
					Qt.callLater(foot)
				}
				fetch(v)
			} else {
				online = false
				retry.start()
			}
		}
		x.open("GET", server + "/thread.json?pane=" + encodeURIComponent(pane) + (since ? "&since=" + since : ""))
		x.send()
		watchdog.restart()
	}
	function choose(d) {
		choosing = false
		if (d.pane === pane) return
		pane = d.pane; name = d.name; status = d.status; items = []; v = ""; sent = ""; note = ""
		fetch("")
	}
	function foot() { talk.contentY = Math.max(0, talk.contentHeight - talk.height) }
	function readHand() {
		note = "Reading your page in “To " + name + "”…"
		post("/read", { pane: pane }, function(st, r) {
			if (st === 200 && r) {
				inked = r.text
				note = inked ? "Is this what you wrote? Send it, or clear and write again." : "No words made out on its latest page."
			} else note = "Not read: " + why(st, r)
		})
	}
	function sendIt() {
		note = "Sending to " + name + "…"
		var t = inked
		post("/send", { pane: pane, text: t }, function(st, r) {
			if (st === 200) { sent = t; inked = ""; note = ""; Qt.callLater(foot) }
			else note = "Not sent: " + why(st, r)
		})
	}

	Component.onCompleted: fetch("")
	Timer { id: retry; interval: 15000; onTriggered: fetch(v) }
	Timer { id: watchdog; interval: 70000; onTriggered: { online = false; fetch("") } }   // a long poll the network lost

	// the masthead: who you are writing to
	Item {
		id: head
		x: 72; y: 48; width: root.width - 144; height: 176
		Text { text: "CORRESPONDENCE" + (online ? "" : " · OFF THE WIRE"); font.family: sans; font.pixelSize: 24; font.letterSpacing: 3 }
		Rectangle {
			id: picker
			y: 48; width: Math.min(parent.width - 140, pickName.width + 150); height: 104
			color: "white"; border.color: "black"; border.width: 3
			Text { id: pickName; x: 28; anchors.verticalCenter: parent.verticalCenter; textFormat: Text.PlainText
				text: name ? "With " + name : "Choose an agent"; font.family: serif; font.pixelSize: 52; font.weight: Font.Bold }
			Canvas {   // the drop-down's arrow: the tablet's fonts have no ▾
				anchors.right: parent.right; anchors.rightMargin: 32; anchors.verticalCenter: parent.verticalCenter
				width: 36; height: 22
				property bool up: choosing
				onUpChanged: requestPaint()
				onPaint: { var c = getContext("2d"); c.reset(); c.fillStyle = "black"; c.beginPath()
					if (up) { c.moveTo(0, 22); c.lineTo(36, 22); c.lineTo(18, 0) } else { c.moveTo(0, 0); c.lineTo(36, 0); c.lineTo(18, 22) }
					c.closePath(); c.fill() }
			}
			MouseArea { anchors.fill: parent; onClicked: choosing = !choosing }
		}
		Text { anchors.left: picker.right; anchors.leftMargin: 28; anchors.verticalCenter: picker.verticalCenter
			visible: status !== ""; text: standing(status); font.family: sans; font.pixelSize: 22; font.letterSpacing: 3
			font.bold: status === "blocked" }
		Rectangle {
			anchors.right: parent.right; y: -16
			width: 96; height: 96; radius: 48; color: "white"; border.color: "black"; border.width: 3
			Text { anchors.centerIn: parent; text: "×"; font.family: sans; font.pixelSize: 56 }
			MouseArea { anchors.fill: parent; anchors.margins: -20; onClicked: root.close() }
		}
		Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: "black" }
	}

	// the thread
	Flickable {
		id: talk
		x: 72; y: head.y + head.height + 16; width: root.width - 144
		height: desk.y - y - 24
		contentHeight: lines.height + 24
		clip: true
		boundsBehavior: Flickable.StopAtBounds
		Column {
			id: lines
			width: parent.width; spacing: 30
			Text { visible: items.length === 0 && !sent; width: parent.width; wrapMode: Text.WordWrap
				text: name ? "Nothing between you and " + name + " yet. Write below." : "Fetching the desks…"
				font.family: serif; font.italic: true; font.pixelSize: 32 }
			Repeater {
				model: items
				Column {
					width: lines.width; spacing: 6
					property bool mine: modelData.who === "you"
					Text { x: mine ? 120 : 0; text: (mine ? "YOU" : name.toUpperCase()) + " · " + hhmm(modelData.at)
						font.family: sans; font.pixelSize: 20; font.letterSpacing: 3; font.bold: !mine }
					Text { x: mine ? 120 : 0; width: lines.width - 120; text: modelData.text; textFormat: Text.PlainText
						wrapMode: Text.WordWrap; font.family: serif; font.pixelSize: mine ? 32 : 30; font.italic: mine; lineHeight: 1.08 }
				}
			}
			Column {
				visible: sent !== ""
				width: lines.width; spacing: 6
				Text { x: 120; text: "YOU · SENT, NOT YET READ"; font.family: sans; font.pixelSize: 20; font.letterSpacing: 3 }
				Text { x: 120; width: lines.width - 120; text: sent; textFormat: Text.PlainText; wrapMode: Text.WordWrap
					font.family: serif; font.pixelSize: 32; font.italic: true }
			}
			Text { visible: status === "working" && items.length > 0; text: name + " is at work…"; font.family: serif
				font.italic: true; font.pixelSize: 28; color: "#555555" }
		}
	}

	// where to write, and what was read there
	Column {
		id: desk
		x: 72; width: root.width - 144; spacing: 16
		anchors.bottom: parent.bottom; anchors.bottomMargin: 40
		Rectangle { width: parent.width; height: 2; color: "black" }
		Text { visible: pane !== "" && inked === ""; width: parent.width; wrapMode: Text.WordWrap; textFormat: Text.PlainText
			font.family: serif; font.pixelSize: 30; font.italic: true
			text: "Write to " + name + " in the notebook “To " + name + "” (in Correspondence), close it, and come back for READ MY PAGE." }
		Text { visible: note !== ""; text: note; textFormat: Text.PlainText; font.family: sans; font.pixelSize: 24
			width: parent.width; wrapMode: Text.WordWrap }
		Text { visible: inked !== ""; text: "“" + inked + "”"; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 32
			width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 4; elide: Text.ElideRight }
		Row {
			spacing: 28
			Rectangle {
				width: wipeLabel.width + 72; height: 88; color: "white"; border.color: "black"; border.width: 3
				Text { id: wipeLabel; anchors.centerIn: parent; text: "CLEAR"; font.family: sans; font.pixelSize: 26; font.bold: true
					font.letterSpacing: 3 }
				MouseArea { anchors.fill: parent; onClicked: { inked = ""; note = "" } }
			}
			Rectangle {
				width: goLabel.width + 72; height: 88; color: pane ? "black" : "#888888"
				Text { id: goLabel; anchors.centerIn: parent; color: "white"; font.family: sans; font.pixelSize: 26; font.bold: true
					font.letterSpacing: 3; text: inked === "" ? "READ MY PAGE" : "SEND TO " + name.toUpperCase() }
				MouseArea { anchors.fill: parent; enabled: pane !== ""; onClicked: inked === "" ? readHand() : sendIt() }
			}
		}
	}

	// the drop-down: every desk, most pressing first
	Rectangle {
		visible: choosing
		x: head.x; y: head.y + picker.y + picker.height - 3
		width: Math.max(picker.width, 640); height: list.height + 6
		color: "white"; border.color: "black"; border.width: 3
		Column {
			id: list
			x: 3; y: 3; width: parent.width - 6
			Repeater {
				model: desks
				Rectangle {
					width: list.width; height: 96
					color: modelData.pane === pane ? "#e6e6e6" : "white"
					Text { x: 28; anchors.verticalCenter: parent.verticalCenter; text: modelData.name; textFormat: Text.PlainText
						font.family: serif; font.pixelSize: 40 }
					Text { anchors.right: parent.right; anchors.rightMargin: 28; anchors.verticalCenter: parent.verticalCenter
						text: standing(modelData.status); font.family: sans; font.pixelSize: 20; font.letterSpacing: 3
						font.bold: modelData.status === "blocked" }
					Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: "#bbbbbb" }
					MouseArea { anchors.fill: parent; onClicked: choose(modelData) }
				}
			}
		}
	}
}
