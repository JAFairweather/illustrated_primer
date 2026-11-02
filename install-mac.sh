#!/bin/sh
# install-mac.sh: run herd-board-serve and herd-board-tunnel under launchd for this user, started at login and again
# whenever they stop (the tunnel every 30 s while the tablet is away). Logs: ~/Library/Logs/herd-board-*.log.
set -e
D=$(cd "$(dirname "$0")" && pwd) A=~/Library/LaunchAgents
for n in serve tunnel; do
	l=pub.nave.herd-board.$n
	cat >"$A/$l.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
	<key>Label</key><string>$l</string>
	<key>ProgramArguments</key><array><string>$D/herd-board-$n</string></array>
	<key>EnvironmentVariables</key><dict><key>PATH</key><string>$HOME/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string></dict>
	<key>RunAtLoad</key><true/>
	<key>KeepAlive</key><true/>
	<key>ThrottleInterval</key><integer>30</integer>
	<key>StandardOutPath</key><string>$HOME/Library/Logs/herd-board-$n.log</string>
	<key>StandardErrorPath</key><string>$HOME/Library/Logs/herd-board-$n.log</string>
</dict></plist>
PLIST
	launchctl bootout "gui/$(id -u)/$l" 2>/dev/null || true
	launchctl bootstrap "gui/$(id -u)" "$A/$l.plist"
	echo "started $l"
done
