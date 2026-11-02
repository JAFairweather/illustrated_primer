// The Cyber Times: herdr's agents as a newspaper on the reMarkable 2, from herd-board-serve on the Mac. Each agent is
// a desk with a band of its own, most important first (waiting on the owner, working, done, idle): its section for the
// day (the morning edition's is yesterday's work, later ones today's so far), and under it, Developing News, its
// latest exchanges with the owner; a desk with nothing to report gets a line. The page scrolls. A long poll: the Mac
// answers as soon as anything changes, so the page redraws only then; every CLEAN editions it flashes black once to
// clear e-ink ghosting. Tap a desk to read all of it, the masthead for a fresh edition, the × at its top right to
// close (or drag from the top centre to the middle). Letters to the Editor: from a desk's page, write to it by hand;
// the Mac has Gemini read the writing, you see what it read, and only then is it sent into the agent's pane.
import QtQuick 2.5

Rectangle {
	id: root
	anchors.fill: parent
	color: "white"
	property string server: "@SERVER@"
	property var agents: []
	property var waiting: []
	property string edition: ""
	property string day: ""
	property string v: ""
	property string changed: ""
	property bool online: false
	property int number: 0
	property var reading: null
	property var req: null
	property var desk: null        // the desk a letter is being written to
	property string inked: ""      // what Gemini read in it
	property string note: ""
	readonly property int clean: 20
	readonly property int band: 904   // about 4 in at 226 dpi
	readonly property string serif: "EB Garamond"
	readonly property string sans: "Noto Sans"

	property int tz: 0       // the Mac's offset from UTC: the tablet keeps UTC

	signal close
	function unloading() { retry.stop(); watchdog.stop(); if (req) req.abort() }

	function hhmm(t) {
		var d = new Date((t + tz) * 1000)
		return ("0" + d.getUTCHours()).slice(-2) + ":" + ("0" + d.getUTCMinutes()).slice(-2)
	}
	function standing(s) {
		return s === "blocked" ? "WAITING ON YOU" : s === "working" ? "AT WORK" : s === "done" ? "FINISHED" : "QUIET"
	}
	function when() { return edition === "Morning" ? "yesterday" : "today" }
	function headline(a) {
		return a.section ? a.section.headline : (a.task || a.name + " at the desk")
	}
	function story(a) {
		return a.section ? a.section.body : "No dispatch from " + a.name + " " + when() + "."
	}
	function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;") }
	function exchanges(a) { return a.recent ? a.recent.slice(-3) : [] }
	function relevant(a) {
		return a.section !== null || (a.recent && a.recent.length > 0) || a.status === "blocked" || a.status === "working"
	}
	function developing(a) {
		if (a.status === "blocked") return a.name + " has stopped and is waiting for your answer. " + a.said
		return a.said || (a.status === "working" ? "At work; no word yet." : "Nothing developing.")
	}
	function dateline() {
		var d = new Date(Date.now() + tz * 1000)
		var days = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
		var months = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER",
			"OCTOBER", "NOVEMBER", "DECEMBER"]
		return days[d.getUTCDay()] + ", " + months[d.getUTCMonth()] + " " + d.getUTCDate() + ", " + d.getUTCFullYear()
	}
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
	function why(st, r) { return r && r.error ? r.error : st ? "status " + st : "the wire is down" }
	function write(a) { desk = a; inked = ""; note = ""; sheet.clear() }
	function readHand() {
		if (!sheet.inked) { note = "Write something first."; return }
		note = "Reading your hand…"
		post("/read", { png: sheet.toDataURL("image/png") }, function(st, r) {
			if (st === 200 && r) {
				inked = r.text
				note = inked ? "Is this what you wrote? Send it, or clear and write again." : "No words made out. Try again, a little larger."
			} else note = "Not read: " + why(st, r)
		})
	}
	function sendLetter() {
		note = "Sending to the " + desk.name + " desk…"
		post("/send", { pane: desk.pane, text: inked }, function(st, r) {
			if (st === 200) { desk = null; reading = null; v = ""; fetch("") }
			else note = "Not sent: " + why(st, r)
		})
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
				tz = j.tz || 0
				if (j.v !== v) {
					v = j.v
					agents = j.agents
					waiting = j.agents.filter(function(a) { return a.status === "blocked" })
					edition = j.edition
					day = j.day
					changed = hhmm(j.at)
					if (++number % clean === 0) flash.start()
				}
				fetch(v)
			} else {
				online = false
				retry.start()
			}
		}
		x.open("GET", server + "/herd.json" + (since ? "?since=" + since : ""))
		x.send()
		watchdog.restart()
	}

	Component.onCompleted: fetch("")
	Timer { id: retry; interval: 15000; onTriggered: fetch("") }
	Timer { id: watchdog; interval: 70000; onTriggered: { online = false; fetch("") } }   // a long poll the network lost

	Flickable {
		id: paper
		anchors.fill: parent
		contentWidth: width
		contentHeight: page.height + 80
		boundsBehavior: Flickable.StopAtBounds
		flickDeceleration: 6000
		clip: true

		Column {
			id: page
			x: 56; y: 40
			width: root.width - 112

			// the masthead
			Item {
				width: parent.width; height: masthead.height
				Column {
					id: masthead
					width: parent.width
					spacing: 6
					Item {
						width: parent.width; height: 40
						Text { text: "VOL. I · No. " + number; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2 }
						Text { anchors.horizontalCenter: parent.horizontalCenter; text: dateline(); font.family: sans; font.pixelSize: 22; font.letterSpacing: 2 }
						Text { anchors.right: shut.left; anchors.rightMargin: 28; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2
							text: online ? (edition ? edition.toUpperCase() + " EDITION · " + changed : "") : "WIRE DOWN" }
						Text { id: shut; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
							text: "×"; font.family: sans; font.pixelSize: 44
							MouseArea { anchors.fill: parent; anchors.margins: -30; onClicked: root.close() } }
					}
					Rectangle { width: parent.width; height: 2; color: "black" }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "The Cyber Times"
						font.family: serif; font.pixelSize: 136; font.weight: Font.Black }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Agent News for Modern Times"
						font.family: serif; font.italic: true; font.pixelSize: 36 }
					Item { width: 1; height: 8 }
					Rectangle { width: parent.width; height: 6; color: "black" }
					Item { width: 1; height: 4 }
					Rectangle { width: parent.width; height: 2; color: "black" }
				}
				MouseArea { anchors.fill: parent; z: -1; onClicked: { v = ""; fetch("") } }   // under the ×
			}

			// stop press: whoever is waiting on the owner
			Item { visible: waiting.length > 0; width: 1; height: 28 }
			Rectangle {
				visible: waiting.length > 0
				width: parent.width; height: stop.height + 40
				color: "black"
				Text {
					id: stop
					x: 32; y: 20; width: parent.width - 64
					color: "white"; font.family: serif; font.pixelSize: 48; font.weight: Font.Bold; wrapMode: Text.WordWrap
					textFormat: Text.PlainText
					text: "STOP PRESS: " + waiting.map(function(a) { return a.name }).join(", ") +
						(waiting.length === 1 ? " is" : " are") + " waiting on you"
				}
			}

			// a band for each desk with news; a line for each without
			Repeater {
				model: agents
				Item {
					property bool news: relevant(modelData)
					width: page.width; height: news ? band + 28 : quiet.height + 28
					clip: true
					Column {
						visible: news
						y: 28; width: parent.width; spacing: 12
						Rectangle { width: parent.width; height: 6; color: "black" }
						Item {
							width: parent.width; height: 36
							Text { text: "THE " + modelData.name.toUpperCase() + " DESK"; font.family: sans; font.pixelSize: 26
								font.bold: true; font.letterSpacing: 5; textFormat: Text.PlainText }
							Text { anchors.right: parent.right; text: standing(modelData.status); font.family: sans; font.pixelSize: 24
								font.letterSpacing: 3; font.bold: modelData.status === "blocked" }
						}
						Rectangle { width: parent.width; height: 2; color: "black" }
						// the day's section
						Text { text: headline(modelData); textFormat: Text.PlainText; font.family: serif; font.pixelSize: 52
							font.weight: Font.Bold; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 2
							elide: Text.ElideRight; lineHeight: 0.95 }
						Text { text: "By " + modelData.name.toUpperCase() + ", STAFF WRITER · " + when().toUpperCase()
							font.family: sans; font.pixelSize: 20; font.letterSpacing: 2; textFormat: Text.PlainText }
						Text { text: story(modelData); textFormat: Text.PlainText; font.family: serif; font.pixelSize: 29
							width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignJustify
							maximumLineCount: 8; elide: Text.ElideRight; lineHeight: 1.06 }
						// developing news: the latest exchanges
						Item { width: 1; height: 4 }
						Row {
							spacing: 18
							Text { text: "Developing News…"; font.family: serif; font.italic: true; font.pixelSize: 34; font.weight: Font.Bold }
							Text { visible: modelData.task !== ""; text: modelData.task
								textFormat: Text.PlainText; font.family: sans; font.pixelSize: 22; font.bold: true
								width: page.width - 360; elide: Text.ElideRight }
						}
						Rectangle { width: parent.width; height: 1; color: "black" }
						Text {
							visible: modelData.status === "blocked"
							text: modelData.name + " has stopped and is waiting for your answer."
							textFormat: Text.PlainText; font.family: serif; font.pixelSize: 30; font.weight: Font.Bold
						}
						Repeater {
							model: exchanges(modelData)
							Column {
								width: page.width; spacing: 4
								Text { text: "James: " + modelData.asked; textFormat: Text.PlainText; font.family: sans; font.pixelSize: 21
									font.italic: true; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 2; elide: Text.ElideRight }
								Text { visible: modelData.replied !== ""; text: modelData.replied; textFormat: Text.PlainText
									font.family: serif; font.pixelSize: 26; width: parent.width; wrapMode: Text.WordWrap
									maximumLineCount: 3; elide: Text.ElideRight; lineHeight: 1.03 }
							}
						}
						Repeater {
							model: modelData.letters || []
							Text { text: "James, by hand, " + hhmm(modelData.at) + ": " + modelData.text; textFormat: Text.PlainText
								font.family: sans; font.pixelSize: 21; font.italic: true; width: page.width; wrapMode: Text.WordWrap
								maximumLineCount: 2; elide: Text.ElideRight }
						}
						Text { visible: exchanges(modelData).length === 0 && modelData.status !== "blocked"
							text: modelData.said || "Nothing developing."; textFormat: Text.PlainText; font.family: serif
							font.pixelSize: 26; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 6; elide: Text.ElideRight }
					}
					Text {
						id: quiet
						visible: !news
						y: 28; width: parent.width; wrapMode: Text.WordWrap; font.family: serif; font.pixelSize: 30
						textFormat: Text.StyledText
						text: "<b>THE " + esc(modelData.name.toUpperCase()) + " DESK</b> — " +
							(modelData.status === "done" ? "finished" : "quiet") + (modelData.task ? "; " + esc(modelData.task) : "") + "."
					}
					MouseArea { anchors.fill: parent; onClicked: reading = modelData }
				}
			}
		}
	}

	// all of one desk's news
	Rectangle {
		visible: reading !== null
		anchors.fill: parent
		color: "white"
		Flickable {
			anchors.fill: parent
			contentHeight: full.height + 160
			boundsBehavior: Flickable.StopAtBounds
			flickDeceleration: 6000
			clip: true
			Column {
				id: full
				x: 96; y: 80; width: root.width - 192; spacing: 22
				Text { text: "THE CYBER TIMES · " + (reading ? "THE " + reading.name.toUpperCase() + " DESK" : ""); textFormat: Text.PlainText
					font.family: sans; font.pixelSize: 24; font.letterSpacing: 3 }
				Rectangle { width: parent.width; height: 2; color: "black" }
				Text { text: reading ? headline(reading) : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 72
					font.weight: Font.Bold; width: parent.width; wrapMode: Text.WordWrap; lineHeight: 0.95 }
				Text { text: reading ? "By " + reading.name.toUpperCase() + ", STAFF WRITER · " + when().toUpperCase() : ""
					textFormat: Text.PlainText; font.family: sans; font.pixelSize: 24; font.letterSpacing: 2 }
				Text { text: reading ? story(reading) : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 36
					lineHeight: 1.15; width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignJustify }
				Rectangle { width: parent.width; height: 2; color: "black" }
				Text { text: "Developing News…"; font.family: serif; font.italic: true; font.pixelSize: 44; font.weight: Font.Bold }
				Text { visible: reading !== null && reading.task !== ""; text: reading ? reading.task : ""; textFormat: Text.PlainText
					font.family: sans; font.pixelSize: 26; font.bold: true; width: parent.width; wrapMode: Text.WordWrap }
				Repeater {
					model: reading && reading.recent ? reading.recent : []
					Column {
						width: full.width; spacing: 6
						Text { text: "James: " + modelData.asked; textFormat: Text.PlainText; font.family: sans; font.pixelSize: 26
							font.italic: true; width: parent.width; wrapMode: Text.WordWrap }
						Text { text: modelData.replied; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 34
							lineHeight: 1.12; width: parent.width; wrapMode: Text.WordWrap }
					}
				}
				Text { visible: reading !== null && (!reading.recent || reading.recent.length === 0)
					text: reading ? developing(reading) : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 34
					lineHeight: 1.15; width: parent.width; wrapMode: Text.WordWrap }
				Rectangle { width: parent.width; height: 2; color: "black" }
				Text { text: "Letters to the Editor"; font.family: serif; font.italic: true; font.pixelSize: 44; font.weight: Font.Bold }
				Repeater {
					model: reading && reading.letters ? reading.letters : []
					Text { text: "James, by hand, " + hhmm(modelData.at) + ": " + modelData.text; textFormat: Text.PlainText
						font.family: sans; font.pixelSize: 26; font.italic: true; width: full.width; wrapMode: Text.WordWrap }
				}
				Rectangle {
					width: pen.width + 72; height: 88; color: "black"
					Text { id: pen; anchors.centerIn: parent; color: "white"; font.family: sans; font.pixelSize: 26; font.bold: true
						font.letterSpacing: 3; text: reading ? "WRITE TO THE " + reading.name.toUpperCase() + " DESK" : "" }
					MouseArea { anchors.fill: parent; onClicked: write(reading) }
				}
				Item { width: 1; height: 12 }
				Text { text: "Tap here to return to the front page."; font.family: serif; font.italic: true; font.pixelSize: 30
					MouseArea { anchors.fill: parent; anchors.margins: -30; onClicked: reading = null } }
			}
		}
		Rectangle {
			anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 32
			width: 96; height: 96; radius: 48; color: "white"; border.color: "black"; border.width: 3
			Text { anchors.centerIn: parent; text: "×"; font.family: sans; font.pixelSize: 56 }
			MouseArea { anchors.fill: parent; onClicked: reading = null }
		}
	}

	// a letter to a desk, by hand
	Rectangle {
		visible: desk !== null
		anchors.fill: parent
		color: "white"
		Column {
			id: letter
			x: 96; y: 72; width: root.width - 192; spacing: 18
			Text { text: "THE CYBER TIMES · LETTERS TO THE EDITOR"; font.family: sans; font.pixelSize: 24; font.letterSpacing: 3 }
			Rectangle { width: parent.width - 120; height: 2; color: "black" }
			Text { text: desk ? "To the " + desk.name + " desk" : ""; textFormat: Text.PlainText; font.family: serif
				font.pixelSize: 64; font.weight: Font.Bold }
			Text { text: desk ? developing(desk) : ""; textFormat: Text.PlainText; font.family: serif; font.italic: true
				font.pixelSize: 28; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 4; elide: Text.ElideRight }
			Item {
				width: parent.width; height: 1080
				Rectangle { anchors.fill: parent; anchors.margins: -3; color: "transparent"; border.color: "black"; border.width: 3 }
				Canvas {
					id: sheet
					anchors.fill: parent
					property var segs: []
					property bool wipe: true
					property bool inked: false
					function clear() { segs = []; wipe = true; inked = false; requestPaint() }
					onPaint: {
						var c = getContext("2d")
						if (wipe) {
							c.fillStyle = "white"; c.fillRect(0, 0, width, height)
							c.strokeStyle = "#c8c8c8"; c.lineWidth = 2
							for (var y = 110; y < height; y += 110) { c.beginPath(); c.moveTo(0, y); c.lineTo(width, y); c.stroke() }
							wipe = false
						}
						c.strokeStyle = "black"; c.lineWidth = 5; c.lineCap = "round"; c.lineJoin = "round"
						c.beginPath()
						for (var i = 0; i < segs.length; i++) { c.moveTo(segs[i][0], segs[i][1]); c.lineTo(segs[i][2], segs[i][3]) }
						c.stroke()
						segs = []
					}
				}
				MouseArea {
					anchors.fill: parent
					preventStealing: true
					property real lx: 0
					property real ly: 0
					onPressed: function(m) { lx = m.x; ly = m.y; sheet.segs.push([lx, ly, lx + 0.5, ly + 0.5]); sheet.inked = true
						inked = ""; sheet.requestPaint() }
					onPositionChanged: function(m) { sheet.segs.push([lx, ly, m.x, m.y]); lx = m.x; ly = m.y; sheet.requestPaint() }
				}
			}
			Text { visible: note !== ""; text: note; textFormat: Text.PlainText; font.family: sans; font.pixelSize: 24
				width: parent.width; wrapMode: Text.WordWrap }
			Text { visible: inked !== ""; text: "“" + inked + "”"; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 36
				width: parent.width; wrapMode: Text.WordWrap; lineHeight: 1.1 }
			Row {
				spacing: 28
				Rectangle {
					width: wipeLabel.width + 72; height: 88; color: "white"; border.color: "black"; border.width: 3
					Text { id: wipeLabel; anchors.centerIn: parent; text: "CLEAR"; font.family: sans; font.pixelSize: 26; font.bold: true
						font.letterSpacing: 3 }
					MouseArea { anchors.fill: parent; onClicked: { sheet.clear(); inked = ""; note = "" } }
				}
				Rectangle {
					width: goLabel.width + 72; height: 88; color: "black"
					Text { id: goLabel; anchors.centerIn: parent; color: "white"; font.family: sans; font.pixelSize: 26; font.bold: true
						font.letterSpacing: 3; text: inked === "" ? "READ MY HAND" : "SEND TO THE DESK" }
					MouseArea { anchors.fill: parent; onClicked: inked === "" ? readHand() : sendLetter() }
				}
			}
		}
		Rectangle {
			anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 32
			width: 96; height: 96; radius: 48; color: "white"; border.color: "black"; border.width: 3
			Text { anchors.centerIn: parent; text: "×"; font.family: sans; font.pixelSize: 56 }
			MouseArea { anchors.fill: parent; onClicked: desk = null }
		}
	}

	// the occasional black flash that clears e-ink ghosting
	Rectangle { id: black; anchors.fill: parent; color: "black"; visible: false }
	SequentialAnimation {
		id: flash
		PropertyAction { target: black; property: "visible"; value: true }
		PauseAnimation { duration: 400 }
		PropertyAction { target: black; property: "visible"; value: false }
	}
}
