Option Explicit
Dim shell, fso, root, python, script, mode
mode = "--gpu"
If WScript.Arguments.Count > 0 Then
    If LCase(WScript.Arguments(0)) = "cpu" Then mode = "--cpu"
End If
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
python = root & "\app\python\pythonw.exe"
script = root & "\app\server.py"
If Not fso.FileExists(python) Or Not fso.FileExists(script) Then
    MsgBox "The portable runtime is missing. Keep the app and models folders beside this launcher.", 16, "SHADER7 AI"
    WScript.Quit 1
End If
shell.CurrentDirectory = root
On Error Resume Next
shell.Run """" & python & """ -B """ & script & """ " & mode, 0, False
If Err.Number <> 0 Then
    MsgBox "Could not launch SHADER7 AI: " & Err.Description, 16, "SHADER7 AI"
    WScript.Quit 1
End If
