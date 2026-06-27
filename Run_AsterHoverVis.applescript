(*
@File        : Run_AsterHoverVis.applescript
@Time        : 2026/06/27 13:47:07
@Author      : Hai-Shuo Wang
@Version     : 1.0
@Contact     : wallen1732@gmail.com
*)

on run
	set appPath to POSIX path of (path to me)
	set appDir to do shell script "/usr/bin/dirname " & quoted form of appPath
	set launcherPath to appDir & "/Run_AsterHoverVis.command"
	set logPath to appDir & "/data/asterhovervis_launcher.log"
	set envText to ""
	set checkOnly to system attribute "ASTERHOVERVIS_CHECK_ONLY"
	if checkOnly is "1" then set envText to envText & "ASTERHOVERVIS_CHECK_ONLY=1 "
	set pythonPath to system attribute "ASTERHOVERVIS_PYTHON"
	if pythonPath is not "" then set envText to envText & "ASTERHOVERVIS_PYTHON=" & quoted form of pythonPath & " "
	set commandText to "cd " & quoted form of appDir & " && /bin/mkdir -p data && " & envText & "/bin/zsh " & quoted form of launcherPath & " > " & quoted form of logPath & " 2>&1"
	try
		do shell script commandText
	on error errorMessage number errorNumber
		display dialog "AsterHoverVis failed to start or exited with an error." & return & return & "Log:" & return & logPath & return & return & errorMessage buttons {"OK"} default button "OK" with title "AsterHoverVis" with icon stop
	end try
end run
