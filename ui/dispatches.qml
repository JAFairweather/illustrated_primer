// Field Dispatches: the R1 recorder's notes (herd-record: title, summary, transcript) as postcards on the reMarkable
// 2, from herd-board-serve's /dispatches.json. Tap a card to read it whole; from there, hand it to a desk: pick an
// agent, confirm, and its title, summary and where the full note is go into that agent's pane. Tap the masthead to
// check for new ones. Or strike it out: draw a big X across the open dispatch and SUBMIT, and the Mac moves its note
// and recording into ~/Recordings/.deleted; nothing goes to a desk.
import QtQuick 2.5

Rectangle {
	id: root
	anchors.fill: parent
	color: "white"
	property string server: "@SERVER@"
	property var cards: []
	property var desks: []
	property var open: null       // the card being read
	property var to: null         // the desk it is about to go to
	property string note: ""
	property bool crossed: false   // a big X drawn across the open dispatch
	property bool online: false
	readonly property string serif: "EB Garamond"
	readonly property string sans: "Noto Sans"

	signal close
	function unloading() {}

	function fetch() {
		var x = new XMLHttpRequest()
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE) return
			online = x.status === 200
			if (online) { var j = JSON.parse(x.responseText); cards = j.dispatches; desks = j.desks }
		}
		x.open("GET", server + "/dispatches.json")
		x.send()
	}
	function hand() {
		note = "Handing it to the " + to.name + " desk…"
		var x = new XMLHttpRequest()
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE) return
			var r = null
			try { r = JSON.parse(x.responseText) } catch (e) {}
			note = x.status === 200 ? "Handed to the " + r.to + " desk." : "Not handed over: " + (r && r.error ? r.error : "the wire is down")
			to = null
		}
		x.open("POST", server + "/hand")
		x.setRequestHeader("Content-Type", "application/json")
		x.send(JSON.stringify({ pane: to.pane, file: open.file }))
	}

	function strike() {
		note = "Striking it out…"
		var x = new XMLHttpRequest()
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE) return
			var r = null
			try { r = JSON.parse(x.responseText) } catch (e) {}
			if (x.status === 200) { open = null; to = null; note = ""; ink.clear(); fetch() }
			else note = "Not struck out: " + (r && r.error ? r.error : "the wire is down")
		}
		x.open("POST", server + "/strike")
		x.setRequestHeader("Content-Type", "application/json")
		x.send(JSON.stringify({ file: open.file }))
	}
	// an X: a long stroke down to the right and another down to the left
	function isCross(strokes) {
		var down = false, up = false
		for (var i = 0; i < strokes.length; i++) {
			var k = strokes[i]
			if (k.maxx - k.minx < 300 || k.maxy - k.miny < 160) continue
			if ((k.x1 - k.x0) * (k.y1 - k.y0) > 0) down = true; else up = true
		}
		return down && up
	}

	Component.onCompleted: fetch()

	Flickable {
		anchors.fill: parent
		contentHeight: page.height + 120
		boundsBehavior: Flickable.StopAtBounds
		flickDeceleration: 6000
		clip: true

		Column {
			id: page
			x: 72; y: 40; width: root.width - 144; spacing: 24

			Item {
				width: parent.width; height: mast.height
				Column {
					id: mast
					width: parent.width; spacing: 6
					Item {
						width: parent.width; height: 40
						Text { text: "RECORDED ON THE R1"; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2 }
						Text { anchors.right: shut.left; anchors.rightMargin: 28; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2
							text: online ? cards.length + " ON FILE" : "WIRE DOWN" }
						Text { id: shut; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
							text: "×"; font.family: sans; font.pixelSize: 44
							MouseArea { anchors.fill: parent; anchors.margins: -30; onClicked: root.close() } }
					}
					Rectangle { width: parent.width; height: 2; color: "black" }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Field Dispatches"
						font.family: serif; font.pixelSize: 120; font.weight: Font.Black }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Postcards From the Pocket Recorder"
						font.family: serif; font.italic: true; font.pixelSize: 34 }
					Item { width: 1; height: 8 }
					Rectangle { width: parent.width; height: 6; color: "black" }
				}
				MouseArea { anchors.fill: parent; z: -1; onClicked: fetch() }   // under the ×
			}

			Text { visible: online && cards.length === 0; text: "No dispatches yet. Record one with the R1's recorder."
				font.family: serif; font.italic: true; font.pixelSize: 34 }

			Grid {
				columns: 2; columnSpacing: 36; rowSpacing: 36
				Repeater {
					model: cards
					Rectangle {
						width: (page.width - 36) / 2; height: 520
						color: "white"; border.color: "black"; border.width: 3
						Rectangle { x: parent.width - 120; y: 20; width: 96; height: 112; color: "white"; border.color: "black"; border.width: 2
							Text { anchors.centerIn: parent; text: "R1"; font.family: serif; font.pixelSize: 44; font.weight: Font.Black } }
						Column {
							x: 28; y: 24; width: parent.width - 176; spacing: 10
							Text { text: modelData.meta.toUpperCase(); textFormat: Text.PlainText; font.family: sans; font.pixelSize: 20
								font.letterSpacing: 2; width: parent.width; elide: Text.ElideRight }
							Text { text: modelData.title; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 40; font.weight: Font.Bold
								width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 3; elide: Text.ElideRight; lineHeight: 0.95 }
						}
						Rectangle { x: 28; y: 190; width: parent.width - 56; height: 2; color: "black" }
						Text { x: 28; y: 208; width: parent.width - 56; height: 290; text: modelData.summary; textFormat: Text.PlainText
							font.family: serif; font.italic: true; font.pixelSize: 26; wrapMode: Text.WordWrap; elide: Text.ElideRight; lineHeight: 1.05 }
						MouseArea { anchors.fill: parent; onClicked: { open = modelData; to = null; note = ""; ink.clear() } }
					}
				}
			}
		}
	}

	// one dispatch, whole, and handing it to a desk
	Rectangle {
		visible: open !== null
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
				Text { text: "FIELD DISPATCH · " + (open ? open.meta.toUpperCase() : ""); textFormat: Text.PlainText
					font.family: sans; font.pixelSize: 24; font.letterSpacing: 3; width: parent.width - 120; elide: Text.ElideRight }
				Rectangle { width: parent.width; height: 2; color: "black" }
				Item {   // the dispatch, and the stylus over it
					width: parent.width; height: words.height
					Column {
						id: words
						width: parent.width; spacing: 22
						Text { text: open ? open.title : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 68
							font.weight: Font.Bold; width: parent.width; wrapMode: Text.WordWrap; lineHeight: 0.95 }
						Text { text: open ? open.summary : ""; textFormat: Text.PlainText; font.family: serif; font.italic: true; font.pixelSize: 34
							lineHeight: 1.12; width: parent.width; wrapMode: Text.WordWrap }
						Rectangle { width: parent.width; height: 2; color: "black" }
						Text { text: open ? open.transcript : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 30
							lineHeight: 1.12; width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignJustify }
					}
					Canvas {
						id: ink
						anchors.fill: parent
						property var segs: []
						property var strokes: []
						property bool wipe: false
						function clear() { segs = []; strokes = []; crossed = false; wipe = true; requestPaint() }
						onPaint: {
							var c = getContext("2d")
							if (wipe) { c.clearRect(0, 0, width, height); wipe = false }
							c.strokeStyle = "black"; c.lineWidth = 7; c.lineCap = "round"; c.lineJoin = "round"
							c.beginPath()
							for (var i = 0; i < segs.length; i++) { c.moveTo(segs[i][0], segs[i][1]); c.lineTo(segs[i][2], segs[i][3]) }
							c.stroke()
							segs = []
						}
					}
					// A pen's lift doesn't always arrive: a jump that long starts a new stroke, not a line to it.
					Item {
						id: hand
						anchors.fill: parent
						property var k: null
						function down(x, y) { k = { x0: x, y0: y, x1: x, y1: y, minx: x, maxx: x, miny: y, maxy: y }
							ink.segs.push([x, y, x + 0.5, y + 0.5]); ink.requestPaint() }
						function to(x, y) { if (!k) return
							if (Math.abs(x - k.x1) + Math.abs(y - k.y1) > 80) { up(); down(x, y); return }
							ink.segs.push([k.x1, k.y1, x, y]); k.x1 = x; k.y1 = y
							k.minx = Math.min(k.minx, x); k.maxx = Math.max(k.maxx, x); k.miny = Math.min(k.miny, y)
							k.maxy = Math.max(k.maxy, y); ink.requestPaint() }
						function up() { if (!k) return; var a = ink.strokes; a.push(k); k = null; ink.strokes = a; crossed = isCross(a)
							note = crossed ? "" : "A big X across it strikes it out." }
						MouseArea {
							anchors.fill: parent
							preventStealing: true
							onPressed: function(m) { if (!hand.k) hand.down(m.x, m.y) }
							onPositionChanged: function(m) { hand.to(m.x, m.y) }
							onReleased: hand.up()
						}
					}
				}
				Row {
					visible: ink.strokes.length > 0
					spacing: 28
					Rectangle {
						width: inkLabel.width + 72; height: 88; color: "white"; border.color: "black"; border.width: 3
						Text { id: inkLabel; anchors.centerIn: parent; text: "WIPE THE INK"; font.family: sans; font.pixelSize: 26; font.bold: true
							font.letterSpacing: 3 }
						MouseArea { anchors.fill: parent; onClicked: { ink.clear(); note = "" } }
					}
					Rectangle {
						width: strikeLabel.width + 72; height: 88; color: crossed ? "black" : "#aaaaaa"
						Text { id: strikeLabel; anchors.centerIn: parent; color: "white"; text: "SUBMIT · DELETE IT"; font.family: sans
							font.pixelSize: 26; font.bold: true; font.letterSpacing: 3 }
						MouseArea { anchors.fill: parent; enabled: crossed; onClicked: strike() }
					}
				}
				Rectangle { width: parent.width; height: 6; color: "black" }
				Text { text: to ? "Hand this to the " + to.name + " desk?" : "Hand it to a desk"; textFormat: Text.PlainText
					font.family: serif; font.italic: true; font.pixelSize: 44; font.weight: Font.Bold }
				Flow {
					visible: to === null
					width: parent.width; spacing: 20
					Repeater {
						model: desks
						Rectangle {
							width: deskName.width + 56; height: 80; color: "white"; border.color: "black"; border.width: 3
							Text { id: deskName; anchors.centerIn: parent; text: modelData.name.toUpperCase(); textFormat: Text.PlainText
								font.family: sans; font.pixelSize: 26; font.bold: true; font.letterSpacing: 3 }
							MouseArea { anchors.fill: parent; onClicked: { to = modelData; note = "" } }
						}
					}
				}
				Row {
					visible: to !== null
					spacing: 28
					Rectangle {
						width: noLabel.width + 72; height: 88; color: "white"; border.color: "black"; border.width: 3
						Text { id: noLabel; anchors.centerIn: parent; text: "NOT YET"; font.family: sans; font.pixelSize: 26; font.bold: true; font.letterSpacing: 3 }
						MouseArea { anchors.fill: parent; onClicked: to = null }
					}
					Rectangle {
						width: yesLabel.width + 72; height: 88; color: "black"
						Text { id: yesLabel; anchors.centerIn: parent; color: "white"; text: "HAND IT OVER"; font.family: sans; font.pixelSize: 26
							font.bold: true; font.letterSpacing: 3 }
						MouseArea { anchors.fill: parent; onClicked: hand() }
					}
				}
				Text { visible: note !== ""; text: note; textFormat: Text.PlainText; font.family: sans; font.pixelSize: 26; font.bold: true
					width: parent.width; wrapMode: Text.WordWrap }
			}
		}
		Rectangle {
			anchors.right: parent.right; anchors.top: parent.top; anchors.margins: 32
			width: 96; height: 96; radius: 48; color: "white"; border.color: "black"; border.width: 3
			Text { anchors.centerIn: parent; text: "×"; font.family: sans; font.pixelSize: 56 }
			MouseArea { anchors.fill: parent; onClicked: { open = null; to = null; note = ""; ink.clear() } }
		}
	}
}
