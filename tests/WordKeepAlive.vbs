Option Explicit
Dim objShell, objFSO, strTempFile, wordApp, appName
Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strTempFile = objShell.ExpandEnvironmentStrings("%TEMP%") & "\WordKeepAlive_Mutex.txt"
If objFSO.FileExists(strTempFile) Then
    objShell.Popup "WordKeepAlive 已在运行", 2, "提示", 64
    WScript.Quit
End If
Dim objMutexFile
Set objMutexFile = objFSO.CreateTextFile(strTempFile, True)
objMutexFile.Write WScript.ProcessId
objMutexFile.Close

ApplyRegistryOptimizations

Set wordApp = GetWordInstance()
If wordApp Is Nothing Then
    objShell.Popup "未检测到 Microsoft Word 或 WPS，请确认已安装", 3, "错误", 16
    WScript.Quit
End If

objShell.Popup appName & " 后台驻留已启动，打开文档将更快", 2, "WordKeepAlive", 64

Do While True
    If wordApp Is Nothing Then
        Set wordApp = GetWordInstance()
        If wordApp Is Nothing Then
            WScript.Sleep 60000
        End If
    Else
        On Error Resume Next
        Dim testName
        testName = wordApp.Name
        If Err.Number <> 0 Then
            Err.Clear
            Set wordApp = GetWordInstance()
        End If
        On Error Goto 0
    End If
    WScript.Sleep 30000
Loop

Function GetWordInstance()
    On Error Resume Next
    Set GetWordInstance = GetObject(, "Word.Application")
    If Not (GetWordInstance Is Nothing) Then
        appName = "Microsoft Word"
        On Error Goto 0
        Exit Function
    End If
    On Error Goto 0

    On Error Resume Next
    Set GetWordInstance = GetObject(, "KWPS.Application")
    If Not (GetWordInstance Is Nothing) Then
        appName = "WPS"
        On Error Goto 0
        Exit Function
    End If
    On Error Goto 0

    On Error Resume Next
    Set GetWordInstance = CreateObject("Word.Application")
    If Not (GetWordInstance Is Nothing) Then
        GetWordInstance.Visible = False
        GetWordInstance.DisplayAlerts = False
        appName = "Microsoft Word"
        On Error Goto 0
        Exit Function
    End If
    On Error Goto 0

    On Error Resume Next
    Set GetWordInstance = CreateObject("KWPS.Application")
    If Not (GetWordInstance Is Nothing) Then
        GetWordInstance.Visible = False
        GetWordInstance.DisplayAlerts = False
        appName = "WPS"
        On Error Goto 0
        Exit Function
    End If
    On Error Goto 0
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
    On Error Goto 0
End Sub
