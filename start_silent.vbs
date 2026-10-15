' Silent launcher for Wchart Tasi subscribers app.
' Starts the Flask server in the background with no console window,
' then opens the site in the default browser.
Option Explicit

Dim sh, fso, base, py, app, url, ret
Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

base = fso.GetParentFolderName(WScript.ScriptFullName)
py   = base & "\.venv\Scripts\python.exe"
app  = base & "\app.py"
url  = "http://127.0.0.1:5002"

' If the server is already listening on 5002, just open the browser.
ret = sh.Run("powershell -NoProfile -Command ""if (Get-NetTCPConnection -LocalPort 5002 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }""", 0, True)

If ret <> 0 Then
    sh.CurrentDirectory = base
    If fso.FileExists(py) Then
        sh.Run """" & py & """ """ & app & """", 0, False
    Else
        sh.Run "python """ & app & """", 0, False
    End If
    WScript.Sleep 3000
End If

sh.Run "rundll32 url.dll,FileProtocolHandler " & url, 0, False
