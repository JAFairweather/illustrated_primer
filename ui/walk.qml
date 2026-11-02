// The Walk Edition: a walk with the R1, earbuds in, talking to the agents, as one front page on the reMarkable 2. From
// herd-board-serve's /walk.json: what the owner said to which agent, what was read back, and Gemini's headline, lede
// and the decisions made out loud. The latest walk first; tap an earlier one at the foot to read it, the masthead to
// check for a newer one. A walk still going (no 20 minutes of quiet yet) is marked LIVE and refreshed every minute.
import QtQuick 2.5

Rectangle {
	id: root
	anchors.fill: parent
	color: "white"
	property string server: "@SERVER@"
	property var walks: []
	property int shown: 0
	property bool online: false
	property var req: null
	readonly property string serif: "EB Garamond"
	readonly property string sans: "Noto Sans"
	readonly property var w: walks.length > shown ? walks[shown] : null

	property int tz: 0       // the Mac's offset from UTC: the tablet keeps UTC

	signal close
	function unloading() { tick.stop(); if (req) req.abort() }

	function hhmm(t) {
		var d = new Date((t + tz) * 1000)
		return ("0" + d.getUTCHours()).slice(-2) + ":" + ("0" + d.getUTCMinutes()).slice(-2)
	}
	function dateline(t) {
		var d = new Date((t + tz) * 1000)
		var days = ["SUNDAY", "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY"]
		var months = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE", "JULY", "AUGUST", "SEPTEMBER",
			"OCTOBER", "NOVEMBER", "DECEMBER"]
		return days[d.getUTCDay()] + " " + d.getUTCDate() + " " + months[d.getUTCMonth()]
	}
	function minutes(a) { return Math.max(1, Math.round((a.end - a.start) / 60)) }
	function headline(a) { return a.edition ? a.edition.headline : "A Walk With the Herd" }
	function lede(a) {
		return a.edition ? a.edition.lede : a.said + " replies were read back over " + minutes(a) +
			" minutes; the editor has not written this walk up yet."
	}
	function fetch() {
		if (req) req.abort()
		var x = new XMLHttpRequest()
		req = x
		x.onreadystatechange = function() {
			if (x.readyState !== XMLHttpRequest.DONE || x !== req) return
			req = null
			online = x.status === 200
			if (online) { var j = JSON.parse(x.responseText); tz = j.tz || 0; walks = j.walks }
		}
		x.open("GET", server + "/walk.json")
		x.send()
	}

	Component.onCompleted: fetch()
	Timer { id: tick; interval: 60000; repeat: true; running: true; onTriggered: if (shown === 0) fetch() }

	Flickable {
		anchors.fill: parent
		contentHeight: page.height + 120
		boundsBehavior: Flickable.StopAtBounds
		flickDeceleration: 6000
		clip: true

		Column {
			id: page
			x: 72; y: 40; width: root.width - 144; spacing: 18

			Item {
				width: parent.width; height: mast.height
				Column {
					id: mast
					width: parent.width; spacing: 6
					Item {
						width: parent.width; height: 40
						Text { text: "FILED FROM THE R1"; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2 }
						Text { anchors.horizontalCenter: parent.horizontalCenter; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2
							text: w ? dateline(w.start) : "" }
						Text { anchors.right: shut.left; anchors.rightMargin: 28; font.family: sans; font.pixelSize: 22; font.letterSpacing: 2
							font.bold: w !== null && w.live
							text: !online ? "WIRE DOWN" : w ? (w.live ? "LIVE · " : "") + hhmm(w.start) + "–" + hhmm(w.end) + " · " + minutes(w) + " MIN" : "" }
						Text { id: shut; anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
							text: "×"; font.family: sans; font.pixelSize: 44
							MouseArea { anchors.fill: parent; anchors.margins: -30; onClicked: root.close() } }
					}
					Rectangle { width: parent.width; height: 2; color: "black" }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "The Walk Edition"
						font.family: serif; font.pixelSize: 120; font.weight: Font.Black }
					Text { anchors.horizontalCenter: parent.horizontalCenter; text: "What Was Decided on Foot"
						font.family: serif; font.italic: true; font.pixelSize: 34 }
					Item { width: 1; height: 8 }
					Rectangle { width: parent.width; height: 6; color: "black" }
					Item { width: 1; height: 4 }
					Rectangle { width: parent.width; height: 2; color: "black" }
				}
				MouseArea { anchors.fill: parent; z: -1; onClicked: { shown = 0; fetch() } }   // under the ×
			}

			Text { visible: online && walks.length === 0; text: "No walks on file. Talk to the herd from the R1 and the paper will set itself."
				font.family: serif; font.italic: true; font.pixelSize: 34; width: parent.width; wrapMode: Text.WordWrap }

			// the front page
			Text { visible: w !== null; text: w ? headline(w) : ""; textFormat: Text.PlainText; font.family: serif
				font.pixelSize: 84; font.weight: Font.Bold; width: parent.width; wrapMode: Text.WordWrap; lineHeight: 0.92 }
			Text { visible: w !== null; text: w ? lede(w) : ""; textFormat: Text.PlainText; font.family: serif; font.pixelSize: 36
				lineHeight: 1.12; width: parent.width; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignJustify }

			// decided out loud
			Rectangle {
				visible: w !== null && w.edition !== null && w.edition.decisions.length > 0
				width: parent.width; height: decided.height + 48; color: "black"
				Column {
					id: decided
					x: 32; y: 24; width: parent.width - 64; spacing: 10
					Text { text: "DECIDED OUT LOUD"; color: "white"; font.family: sans; font.pixelSize: 24; font.bold: true; font.letterSpacing: 4 }
					Repeater {
						model: w && w.edition ? w.edition.decisions : []
						Text { text: "■  " + modelData; textFormat: Text.PlainText; color: "white"; font.family: serif; font.pixelSize: 32
							width: decided.width; wrapMode: Text.WordWrap }
					}
				}
			}

			// the wire: said and read back, side by side
			Row {
				visible: w !== null
				width: parent.width; spacing: 40
				Column {
					width: (page.width - 40) / 2; spacing: 12
					Text { text: "SAID ON THE WALK"; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
					Rectangle { width: parent.width; height: 2; color: "black" }
					Repeater {
						model: w ? w.asked : []
						Text { text: "<b>" + hhmm(modelData.at) + " to " + modelData.to + "</b> — " + modelData.text.replace(/&/g, "&amp;").replace(/</g, "&lt;")
							textFormat: Text.StyledText; font.family: serif; font.pixelSize: 26; width: parent.width; wrapMode: Text.WordWrap
							maximumLineCount: 5; elide: Text.ElideRight }
					}
					Text { visible: w !== null && w.asked.length === 0; text: "Not on file for this walk."; font.family: serif
						font.italic: true; font.pixelSize: 26 }
				}
				Column {
					width: (page.width - 40) / 2; spacing: 12
					Text { text: "READ BACK IN YOUR EARS"; font.family: sans; font.pixelSize: 22; font.bold: true; font.letterSpacing: 3 }
					Rectangle { width: parent.width; height: 2; color: "black" }
					Repeater {
						model: w ? w.told : []
						Text { text: "“" + modelData + "”"; textFormat: Text.PlainText; font.family: serif; font.italic: true
							font.pixelSize: 26; width: parent.width; wrapMode: Text.WordWrap; maximumLineCount: 5; elide: Text.ElideRight }
					}
				}
			}

			// earlier walks
			Rectangle { visible: walks.length > 1; width: parent.width; height: 6; color: "black" }
			Text { visible: walks.length > 1; text: "Earlier Walks"; font.family: serif; font.italic: true; font.pixelSize: 40; font.weight: Font.Bold }
			Repeater {
				model: walks
				Item {
					visible: index !== shown
					width: page.width; height: visible ? back.height + 20 : 0
					Text {
						id: back
						width: parent.width; wrapMode: Text.WordWrap; textFormat: Text.StyledText; font.family: serif; font.pixelSize: 30
						text: "<b>" + dateline(modelData.start) + ", " + hhmm(modelData.start) + "</b> · " + minutes(modelData) + " min — " +
							headline(modelData).replace(/&/g, "&amp;").replace(/</g, "&lt;")
					}
					MouseArea { anchors.fill: parent; onClicked: shown = index }
				}
			}
		}
	}
}
