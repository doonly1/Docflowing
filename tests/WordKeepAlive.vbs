Option Explicit
Dim objShell, objFSO, strTempFile, objFile
Dim wmi, watcher, eventObj
Dim isStarting

isStarting = 0

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strTempFile = objShell.ExpandEnvironmentStrings("%TEMP%") & "\WordKeepAlive_Mutex.txt"

' Check if another instance is running
If objFSO.FileExists(strTempFile) Then
    On Error Resume Next
    objFSO.DeleteFile strTempFile, True
    If Err.Number <> 0 Then
        Err.Clear
        On Error GoTo 0
        objShell.Popup "WordKeepAlive is already running.", 1, "Hint", 64
        WScript.Quit
    End If
    On Error GoTo 0
End If

On Error Resume Next
Set objFile = objFSO.OpenTextFile(strTempFile, 2, True)
If Err.Number <> 0 Then
    Err.Clear
    On Error GoTo 0
    objShell.Popup "Another instance is running.", 2, "Hint", 64
    WScript.Quit
End If
On Error GoTo 0

ApplyRegistryOptimizations

' Start initial hidden Word instance
Call StartHiddenWord

' Setup WMI event watcher
On Error Resume Next
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
If Err.Number <> 0 Then
    Err.Clear
    On Error GoTo 0
    objShell.Popup "WMI not available.", 3, "Error", 16
    objFile.Close
    objFSO.DeleteFile strTempFile, True
    WScript.Quit
End If

Set watcher = wmi.ExecNotificationQuery( _
    "SELECT * FROM __InstanceDeletionEvent" & _
    " WITHIN 0.1" & _
    " WHERE TargetInstance ISA 'Win32_Process'" & _
    " AND TargetInstance.Name = 'WINWORD.EXE'" _
)
If Err.Number <> 0 Or watcher Is Nothing Then
    Err.Clear
    On Error GoTo 0
    objShell.Popup "Failed to setup WMI watcher.", 3, "Error", 16
    objFile.Close
    objFSO.DeleteFile strTempFile, True
    WScript.Quit
End If
On Error GoTo 0

objShell.Popup "WordKeepAlive started. Word will restart instantly after exit.", 1, "WordKeepAlive", 64

' Event-driven loop
Do While True
    On Error Resume Next
    Set eventObj = watcher.NextEvent(100)
    If Err.Number = 0 Then
        Call StartHiddenWord
    End If
    Err.Clear
    On Error GoTo 0
Loop

Sub StartHiddenWord()
    ' Prevent concurrent creation
    If isStarting <> 0 Then Exit Sub
    isStarting = 1

    ' If Word is already running (user reopened it), do nothing
    If IsWinwordRunning() Then
        isStarting = 0
        Exit Sub
    End If

    ' Create hidden Word instance via CreateObject (no window flash)
    On Error Resume Next
    Dim wdApp
    Set wdApp = CreateObject("Word.Application")
    If Err.Number = 0 And Not wdApp Is Nothing Then
        wdApp.Visible = False
        wdApp.DisplayAlerts = False
        On Error Resume Next
        wdApp.Documents.Add
        If Err.Number <> 0 Then Err.Clear
        On Error GoTo 0
    End If
    Err.Clear
    On Error GoTo 0

    If wdApp Is Nothing Then
        On Error Resume Next
        Set wdApp = CreateObject("KWPS.Application")
        If Err.Number = 0 And Not wdApp Is Nothing Then
            wdApp.Visible = False
            wdApp.DisplayAlerts = False
            On Error Resume Next
            wdApp.Documents.Add
            If Err.Number <> 0 Then Err.Clear
            On Error GoTo 0
        End If
        Err.Clear
        On Error GoTo 0
    End If

    isStarting = 0
End Sub

Function IsWinwordRunning()
    IsWinwordRunning = False
    On Error Resume Next
    Dim wmiChk, colChk, procChk
    Set wmiChk = GetObject("winmgmts:\\.\root\cimv2")
    If Err.Number <> 0 Then Exit Function
    Set colChk = wmiChk.ExecQuery("SELECT Name FROM Win32_Process WHERE Name = 'WINWORD.EXE'")
    If Err.Number = 0 Then
        For Each procChk In colChk
            IsWinwordRunning = True
            Exit For
        Next
    End If
    On Error GoTo 0
End Function

Sub ApplyRegistryOptimizations()
    On Error Resume Next
    Dim regBase, i
    For i = 12 To 16
        regBase = "HKEY_CURRENT_USER\Software\Microsoft\Office\" & i & ".0\Word\Options\"
        objShell.RegWrite regBase & "NoReReg", 1, "REG_DWORD"
        objShell.RegWrite regBase & "NoRereg", 1, "REG_DWORD"
        objShell.RegWrite regBase & "DisableBootCheck", 1, "REG_DWORD"
        objShell.RegWrite regBase & "StartupVerifySSL", 0, "REG_DWORD"
    Next
    On Error GoTo 0
End Sub
