' ──────────────────────────────────────────────────────
' FinalGrid — Start server in background (no window)
' Called by Task Scheduler on Windows login.
' To see the server console, run start.bat manually.
' ──────────────────────────────────────────────────────
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c start.bat hidden", 0, False
